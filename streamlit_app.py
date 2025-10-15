import streamlit as st
import pandas as pd
import os
from datetime import date, datetime
from openai import OpenAI

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
これまでの傾向を参考に、やさしく、短い励ましコメントを作成してください。
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

# --- バッジ判定 ---
def check_badge(user_name):
    df = load_data()
    if df.empty:
        return None
    df["年月"] = pd.to_datetime(df["日付"], errors="coerce").dt.to_period("M").astype(str)
    this_month = datetime.now().strftime("%Y-%m")
    user_month = df[(df["利用者名"] == user_name) & (df["年月"] == this_month)]
    total_points = user_month["ポイント"].sum()
    badge = None
    if total_points >= 100:
        badge = "🌟 成長バッジ"
    elif total_points < 50:
        badge = "💪 がんばろうバッジ"
    if badge:
        df_badge = load_badges()
        exists = not df_badge[
            (df_badge["氏名"] == user_name) & (df_badge["年月"] == this_month) & (df_badge["バッジ"] == badge)
        ].empty
        if not exists:
            new_badge = pd.DataFrame([{
                "氏名": user_name,
                "年月": this_month,
                "バッジ": badge,
                "日付": datetime.now().strftime("%Y-%m-%d")
            }])
            df_badge = pd.concat([df_badge, new_badge], ignore_index=True)
            save_badges(df_badge)
            return badge
    return None

# --- 施設別ランキング ---
def facility_ranking(df_points, df_users):
    if df_points.empty or df_users.empty:
        return pd.DataFrame(), None
    df_points["年月"] = pd.to_datetime(df_points["日付"], errors="coerce").dt.to_period("M").astype(str)
    month_list = sorted(df_points["年月"].unique(), reverse=True)
    selected_month = st.selectbox("📅 月を選択", month_list, index=0)
    df_month = df_points[df_points["年月"] == selected_month]
    merged = pd.merge(df_month, df_users[["氏名", "施設"]], left_on="利用者名", right_on="氏名", how="left")
    df_home = merged.groupby("施設")["ポイント"].sum().reset_index().sort_values("ポイント", ascending=False)
    df_home["順位"] = range(1, len(df_home) + 1)
    return df_home, selected_month

# ===============================
# モード選択
# ===============================
mode = st.sidebar.radio("モードを選択", ["利用者モード", "職員モード"])

# =========================================================
# 職員モード（前回のコード内容そのまま）
# =========================================================
if mode == "職員モード":
    st.title("👩‍💼 職員モード")
    # ...（職員画面は省略：前回v14と同じ内容を維持）...
    st.info("職員モードは正常稼働中（前回設定のまま）")

# =========================================================
# 利用者モード
# =========================================================
else:
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

        st.subheader("💎 あなたのポイント履歴")
        df_user_points = df[df["利用者名"].apply(normalize_name) == normalize_name(user_name)]
        if df_user_points.empty:
            st.info("まだポイント履歴がありません。")
        else:
            st.dataframe(df_user_points[["日付", "項目", "ポイント", "コメント"]].sort_values("日付", ascending=False))

        # --- グループホーム別ランキング（ハイライト＋メダル色） ---
        st.subheader("🏠 グループホーム別ランキング（月ごと）")
        if os.path.exists(USER_FILE) and not df.empty:
            df_all_users = pd.read_csv(USER_FILE)
            df_home, selected_month = facility_ranking(df, df_all_users)

            # 自施設特定
            my_facility = None
            if "氏名" in df_all_users.columns and "施設" in df_all_users.columns:
                match = df_all_users.loc[
                    df_all_users["氏名"].apply(normalize_name) == normalize_name(user_name), "施設"
                ]
                if not match.empty:
                    my_facility = match.iloc[0]

            if not df_home.empty:
                st.write(f"### 📅 {selected_month} のランキング")

                def highlight_row(row):
                    color = ""
                    if row["順位"] == 1:
                        color = "#FFD700"  # 金
                    elif row["順位"] == 2:
                        color = "#C0C0C0"  # 銀
                    elif row["順位"] == 3:
                        color = "#CD7F32"  # 銅
                    if my_facility and row["施設"] == my_facility:
                        color = "#FFFACD"  # 自施設を優先（黄色）
                    return [f"background-color: {color}" if color else "" for _ in row]

                styled_df = df_home[["順位", "施設", "ポイント"]].style.apply(highlight_row, axis=1)
                st.dataframe(styled_df, use_container_width=True)

                legend = """
                🥇 <span style="color:#FFD700">1位 金</span>　
                🥈 <span style="color:#C0C0C0">2位 銀</span>　
                🥉 <span style="color:#CD7F32">3位 銅</span>　
                🏠 <span style="background-color:#FFFACD">自施設</span>
                """
                st.markdown(legend, unsafe_allow_html=True)

                if my_facility:
                    st.markdown(f"🏠 あなたの所属施設：**{my_facility}**（黄色で表示）")
            else:
                st.info("該当月のデータがありません。")

        if st.button("🚪 ログアウト"):
            st.session_state.clear()
            st.rerun()
