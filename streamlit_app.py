import streamlit as st
import pandas as pd
import os
from datetime import date, datetime
from openai import OpenAI
import matplotlib.pyplot as plt

# ===============================
# 基本設定
# ===============================
st.set_page_config(page_title="ウェルサポイント", page_icon="💎", layout="wide")

DATA_FILE = "points_data.csv"
USER_FILE = "users.csv"
ITEM_FILE = "items.csv"
FACILITY_FILE = "facilities.csv"
BADGE_FILE = "badges.csv"

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
STAFF_ACCOUNTS = st.secrets["staff_accounts"]
ADMIN_ID = st.secrets["admin"]["id"]
ADMIN_PASS = st.secrets["admin"]["password"]

# ===============================
# 共通関数
# ===============================
def normalize_name(name: str):
    return str(name).strip().replace("　", " ").lower()

def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=["日付", "利用者名", "項目", "ポイント", "所属部署", "コメント"])

def save_data(df):
    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")

def load_badges():
    if os.path.exists(BADGE_FILE):
        return pd.read_csv(BADGE_FILE)
    return pd.DataFrame(columns=["氏名", "年月", "バッジ", "日付"])

def save_badges(df):
    df.to_csv(BADGE_FILE, index=False, encoding="utf-8-sig")

# --- AIコメント生成（履歴学習付き） ---
def generate_comment(user_name, item, points):
    try:
        if os.path.exists(DATA_FILE):
            df_hist = pd.read_csv(DATA_FILE)
            df_hist = df_hist[(df_hist["利用者名"] == user_name) & (df_hist["項目"] == item)]
            if not df_hist.empty:
                recent_comments = " / ".join(df_hist["コメント"].dropna().tail(5).tolist())
                history_summary = f"過去の『{item}』での{user_name}さんへのコメント例: {recent_comments}"
            else:
                history_summary = f"{user_name}さんへの『{item}』コメント履歴はまだありません。"
        else:
            history_summary = f"{user_name}さんへの『{item}』コメント履歴はまだありません。"

        prompt = f"""
あなたは障がい者福祉施設の職員です。
{user_name}さんが『{item}』の活動に{points}ポイントを獲得しました。
これまでの傾向を参考に、やさしく短い励ましコメントを作成してください。
必ず「ありがとう」を含み、30文字以内、日本語、絵文字1つ。
{history_summary}
"""
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "あなたは温かく励ます福祉職員です。"},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "今日もありがとう😊"

# --- バッジ判定（前月比＋成長/がんばろう） ---
def check_badge(user_name):
    df = load_data()
    if df.empty:
        return None
    df["年月"] = pd.to_datetime(df["日付"], errors="coerce").dt.to_period("M").astype(str)

    # 月ごと合計ポイント
    monthly_points = df[df["利用者名"] == user_name].groupby("年月")["ポイント"].sum().reset_index().sort_values("年月")

    if len(monthly_points) < 2:
        return None  # 前月データなし

    this_month = monthly_points.iloc[-1]
    last_month = monthly_points.iloc[-2]

    badge = None
    if this_month["ポイント"] > last_month["ポイント"]:
        badge = "🌟 成長バッジ"
    elif this_month["ポイント"] < last_month["ポイント"]:
        badge = "💪 がんばろうバッジ"

    if badge:
        df_badge = load_badges()
        exists = not df_badge[
            (df_badge["氏名"] == user_name) & (df_badge["年月"] == this_month["年月"]) & (df_badge["バッジ"] == badge)
        ].empty
        if not exists:
            new_badge = pd.DataFrame([{
                "氏名": user_name,
                "年月": this_month["年月"],
                "バッジ": badge,
                "日付": datetime.now().strftime("%Y-%m-%d")
            }])
            df_badge = pd.concat([df_badge, new_badge], ignore_index=True)
            save_badges(df_badge)
            return badge
    return None

# =========================================================
# 利用者モード
# =========================================================
st.title("🧍‍♀️ 利用者モード")
df = load_data()

if not st.session_state.get("user_logged_in"):
    st.subheader("🔑 ログイン")
    last_name = st.text_input("姓を入力")
    first_name = st.text_input("名を入力")
    if st.button("ログイン"):
        full_name = f"{last_name} {first_name}"
        normalized = normalize_name(full_name)
        if os.path.exists(USER_FILE):
            df_user = pd.read_csv(USER_FILE)
            if "氏名" in df_user.columns:
                registered = [normalize_name(n) for n in df_user["氏名"]]
                if normalized in registered:
                    st.session_state["user_logged_in"] = True
                    st.session_state["user_name"] = full_name
                    st.success(f"{full_name} さん、ようこそ！")
                    st.rerun()
                else:
                    st.error("登録されていない利用者です。")
else:
    user_name = st.session_state["user_name"]
    st.sidebar.success(f"✅ ログイン中：{user_name}")

    # --- ポイント履歴 ---
    st.subheader("💎 あなたのポイント履歴")
    df_user_points = df[df["利用者名"].apply(normalize_name) == normalize_name(user_name)]
    if df_user_points.empty:
        st.info("まだポイント履歴がありません。")
    else:
        st.dataframe(df_user_points[["日付", "項目", "ポイント", "コメント"]].sort_values("日付", ascending=False))

    # --- 月ごとのポイント棒グラフ ---
    st.subheader("📊 あなたの獲得ポイント（月ごと）")
    if not df_user_points.empty:
        df_user_points["年月"] = pd.to_datetime(df_user_points["日付"], errors="coerce").dt.to_period("M").astype(str)
        monthly_points = df_user_points.groupby("年月")["ポイント"].sum().reset_index()
        plt.figure(figsize=(6,3))
        plt.bar(monthly_points["年月"], monthly_points["ポイント"])
        plt.xlabel("年月")
        plt.ylabel("合計ポイント")
        plt.title("月ごとのポイント推移")
        st.pyplot(plt)

    # --- 前月比バッジ判定 ---
    badge = check_badge(user_name)
    if badge:
        st.success(f"🎖 新しいバッジを獲得しました：{badge}")

    # --- グループホーム別ランキング ---
    st.subheader("🏠 グループホーム別ランキング（月ごと）")
    if os.path.exists(USER_FILE) and not df.empty:
        df_all_users = pd.read_csv(USER_FILE)
        df["年月"] = pd.to_datetime(df["日付"], errors="coerce").dt.to_period("M").astype(str)
        month_list = sorted(df["年月"].unique(), reverse=True)
        selected_month = st.selectbox("📅 表示する月を選択", month_list, index=0)

        df_month = df[df["年月"] == selected_month]
        merged = pd.merge(df_month, df_all_users[["氏名", "施設"]],
                          left_on="利用者名", right_on="氏名", how="left")
        df_home = merged.groupby("施設")["ポイント"].sum().reset_index().sort_values("ポイント", ascending=False)
        df_home["順位"] = range(1, len(df_home) + 1)

        # 自施設特定
        my_facility = None
        if "氏名" in df_all_users.columns and "施設" in df_all_users.columns:
            match = df_all_users.loc[
                df_all_users["氏名"].apply(normalize_name) == normalize_name(user_name), "施設"
            ]
            if not match.empty:
                my_facility = match.iloc[0]

        if not df_home.empty:
            def medal_icon(rank):
                if rank == 1:
                    return "🥇 1"
                elif rank == 2:
                    return "🥈 2"
                elif rank == 3:
                    return "🥉 3"
                else:
                    return str(rank)
            df_home["順位"] = df_home["順位"].apply(medal_icon)

            def highlight_my_facility(row):
                if my_facility and row["施設"] == my_facility:
                    return ['background-color: #FFFACD'] * len(row)
                else:
                    return [''] * len(row)

            styled_df = df_home[["順位", "施設", "ポイント"]].style.apply(highlight_my_facility, axis=1)
            st.dataframe(styled_df, use_container_width=True)
            st.markdown("""
            🥇1位　🥈2位　🥉3位　🏠自施設＝<span style="background-color:#FFFACD">黄色</span>
            """, unsafe_allow_html=True)

            if my_facility:
                st.markdown(f"🏠 あなたの所属施設：**{my_facility}**（黄色で表示）")
        else:
            st.info("該当月のデータがありません。")

    if st.button("🚪 ログアウト"):
        st.session_state.clear()
        st.rerun()
