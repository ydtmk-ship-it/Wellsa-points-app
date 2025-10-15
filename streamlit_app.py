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
# 関数
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

# --- 施設別ランキング作成 ---
def facility_ranking(df_points, df_users):
    if df_points.empty or df_users.empty:
        return pd.DataFrame()

    df_points["年月"] = pd.to_datetime(df_points["日付"], errors="coerce").dt.to_period("M").astype(str)
    month_list = sorted(df_points["年月"].unique(), reverse=True)
    selected_month = st.selectbox("表示する月を選択", month_list, index=0)
    df_month = df_points[df_points["年月"] == selected_month]

    merged = pd.merge(df_month, df_users[["氏名", "施設"]],
                      left_on="利用者名", right_on="氏名", how="left")
    df_home = merged.groupby("施設")["ポイント"].sum().reset_index().sort_values("ポイント", ascending=False)
    df_home["順位"] = range(1, len(df_home) + 1)
    return df_home, selected_month

# ===============================
# モード選択
# ===============================
mode = st.sidebar.radio("モードを選択", ["利用者モード", "職員モード"])

# =========================================================
# 職員モード
# =========================================================
if mode == "職員モード":
    st.title("👩‍💼 職員モード")

    if "staff_logged_in" not in st.session_state:
        st.session_state["staff_logged_in"] = False
    if "is_admin" not in st.session_state:
        st.session_state["is_admin"] = False

    # --- ログイン ---
    if not st.session_state["staff_logged_in"]:
        dept = st.selectbox("部署を選択", list(STAFF_ACCOUNTS.keys()) + ["管理者"])
        input_id = st.text_input("ログインID")
        input_pass = st.text_input("パスワード", type="password")

        if st.button("ログイン"):
            if dept == "管理者":
                if input_id == ADMIN_ID and input_pass == ADMIN_PASS:
                    st.session_state.update({"staff_logged_in": True, "staff_dept": "管理者", "is_admin": True})
                    st.success("管理者としてログインしました！")
                    st.rerun()
                else:
                    st.error("管理者IDまたはパスワードが違います。")
            else:
                stored_id, stored_pass = STAFF_ACCOUNTS[dept].split("|")
                if input_id == stored_id and input_pass == stored_pass:
                    st.session_state.update({"staff_logged_in": True, "staff_dept": dept, "is_admin": False})
                    st.success(f"{dept} としてログインしました！")
                    st.rerun()
                else:
                    st.error("IDまたはパスワードが違います。")

    # --- ログイン後 ---
    else:
        dept = st.session_state["staff_dept"]
        is_admin = st.session_state["is_admin"]
        st.sidebar.success(f"✅ ログイン中：{dept}")

        staff_tab_list = ["ポイント付与", "履歴閲覧", "事業所別ランキング"]
        if is_admin:
            staff_tab_list += ["利用者登録", "活動項目設定", "施設設定"]

        staff_tab = st.sidebar.radio("機能を選択", staff_tab_list)
        df = load_data()

        # --- ポイント付与 ---
        if staff_tab == "ポイント付与":
            st.subheader("💎 ポイント付与")
            df_item = pd.read_csv(ITEM_FILE) if os.path.exists(ITEM_FILE) else pd.DataFrame(columns=["項目", "ポイント"])

            if os.path.exists(USER_FILE):
                df_user = pd.read_csv(USER_FILE)
                user_list = df_user["氏名"].dropna().tolist() if "氏名" in df_user.columns else []
                user_name = st.selectbox("利用者を選択", user_list)
            else:
                st.warning("利用者が未登録です。")
                user_name = None

            if not df_item.empty:
                selected_item = st.selectbox("活動項目を選択", df_item["項目"].tolist())
                if selected_item in df_item["項目"].values:
                    points_value = int(df_item.loc[df_item["項目"] == selected_item, "ポイント"].values[0])
                else:
                    points_value = 0
                st.number_input("付与ポイント数", value=points_value, key="display_points", disabled=True)
            else:
                st.warning("活動項目が未登録です。")
                selected_item, points_value = None, 0

            if st.button("ポイントを付与"):
                if user_name and selected_item:
                    comment = generate_comment(user_name, selected_item, points_value)
                    new_record = {
                        "日付": date.today().strftime("%Y-%m-%d"),
                        "利用者名": user_name,
                        "項目": selected_item,
                        "ポイント": points_value,
                        "所属部署": dept,
                        "コメント": comment
                    }
                    df = pd.concat([df, pd.DataFrame([new_record])], ignore_index=True)
                    save_data(df)
                    st.success(f"{user_name} に {points_value} pt を付与しました！")
                    st.info(f"💬 AIコメント: {comment}")

                    # バッジ判定
                    badge = check_badge(user_name)
                    if badge:
                        st.toast(f"🏅 {user_name} さんが {badge} を獲得しました！")

        # --- 履歴閲覧 ---
        elif staff_tab == "履歴閲覧":
            st.subheader("🗂 ポイント履歴")
            if df.empty:
                st.info("まだデータがありません。")
            else:
                st.dataframe(df)

        # --- 事業所別ランキング ---
        elif staff_tab == "事業所別ランキング":
            st.subheader("🏠 グループホーム別ポイントランキング（月ごと）")
            if not os.path.exists(USER_FILE):
                st.warning("利用者データがありません。")
            elif df.empty:
                st.info("まだポイントデータがありません。")
            else:
                df_users = pd.read_csv(USER_FILE)
                df_home, selected_month = facility_ranking(df, df_users)
                if not df_home.empty:
                    st.write(f"### 📅 {selected_month} のランキング")
                    st.dataframe(df_home[["順位", "施設", "ポイント"]], use_container_width=True)
                else:
                    st.info("該当月のデータがありません。")

        if st.button("🚪 ログアウト"):
            st.session_state.clear()
            st.rerun()

# =========================================================
# 利用者モード
# =========================================================
else:
    st.title("🧍‍♀️ 利用者モード")
    df = load_data()

    if not st.session_state.get("user_logged_in"):
        last_name = st.text_input("姓を入力してください")
        first_name = st.text_input("名を入力してください")
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
                        st.error("登録されていない利用者です。職員に確認してください。")
    else:
        user_name = st.session_state["user_name"]
        st.sidebar.success(f"✅ ログイン中：{user_name}")

        st.subheader("💎 あなたのポイント履歴")
        df_user_points = df[df["利用者名"].apply(normalize_name) == normalize_name(user_name)]
        if df_user_points.empty:
            st.info("まだポイント履歴がありません。")
        else:
            st.dataframe(df_user_points[["日付", "項目", "ポイント", "コメント"]].sort_values("日付", ascending=False))

        # --- 事業所別ランキング（利用者画面にも表示） ---
        st.subheader("🏠 グループホーム別ポイントランキング（月ごと）")
        if os.path.exists(USER_FILE) and not df.empty:
            df_all_users = pd.read_csv(USER_FILE)
            df_home, selected_month = facility_ranking(df, df_all_users)
            if not df_home.empty:
                st.write(f"### 📅 {selected_month} のランキング")
                st.dataframe(df_home[["順位", "施設", "ポイント"]], use_container_width=True)
            else:
                st.info("該当月のデータがありません。")

        if st.button("🚪 ログアウト"):
            st.session_state.clear()
            st.rerun()
