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
        return pd.DataFrame(), None

    df_points["年月"] = pd.to_datetime(df_points["日付"], errors="coerce").dt.to_period("M").astype(str)
    month_list = sorted(df_points["年月"].unique(), reverse=True)
    selected_month = st.selectbox("表示する月を選択", month_list, index=0)
    df_month = df_points[df_points["年月"] == selected_month]

    merged = pd.merge(df_month, df_users[["氏名", "施設"]],
                      left_on="利用者名", right_on="氏名", how="left")
    df_home = merged.groupby("施設")["ポイント"].sum().reset_index().sort_values("ポイント", ascending=False)
    df_home["順位"] = range(1, len(df_home) + 1)
    return df_home, selected_month

# =========================================================
# メインロジック
# =========================================================
mode = st.sidebar.radio("モードを選択", ["利用者モード", "職員モード"])

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

    else:
        dept = st.session_state["staff_dept"]
        is_admin = st.session_state["is_admin"]
        st.sidebar.success(f"✅ ログイン中：{dept}")

        tabs = ["ポイント付与", "履歴閲覧", "事業所別ランキング"]
        if is_admin:
            tabs += ["利用者登録", "活動項目設定", "施設設定"]
        choice = st.sidebar.radio("機能を選択", tabs)

        df = load_data()

        # --- 管理者専用画面群 ---
        if choice == "利用者登録" and is_admin:
            st.subheader("🧍‍♀️ 利用者登録")
            if os.path.exists(FACILITY_FILE):
                df_fac = pd.read_csv(FACILITY_FILE)
                facility_list = df_fac["施設名"].tolist()
            else:
                facility_list = []
            with st.form("user_reg"):
                last = st.text_input("姓")
                first = st.text_input("名")
                facility = st.selectbox("グループホーム", facility_list, index=None, placeholder="選択してください")
                submit = st.form_submit_button("登録")
            if submit and last and first and facility:
                full = f"{last} {first}"
                df_user = pd.read_csv(USER_FILE) if os.path.exists(USER_FILE) else pd.DataFrame(columns=["氏名", "施設"])
                df_user = pd.concat([df_user, pd.DataFrame([{"氏名": full, "施設": facility}])], ignore_index=True)
                df_user.to_csv(USER_FILE, index=False, encoding="utf-8-sig")
                st.success(f"{full}（{facility}）を登録しました。")
                st.rerun()
            if os.path.exists(USER_FILE):
                df_user = pd.read_csv(USER_FILE)
                df_user["削除"] = False
                edited = st.data_editor(df_user, use_container_width=True)
                delete = edited[edited["削除"]]
                if st.button("チェックした利用者を削除"):
                    df_user = df_user.drop(delete.index)
                    df_user.to_csv(USER_FILE, index=False, encoding="utf-8-sig")
                    st.success("削除しました。")
                    st.rerun()

        elif choice == "活動項目設定" and is_admin:
            st.subheader("🧩 活動項目設定")
            with st.form("item_form"):
                item = st.text_input("活動項目名")
                point = st.number_input("ポイント", min_value=1, step=1)
                sub = st.form_submit_button("登録")
            if sub and item:
                df_item = pd.read_csv(ITEM_FILE) if os.path.exists(ITEM_FILE) else pd.DataFrame(columns=["項目", "ポイント"])
                df_item = pd.concat([df_item, pd.DataFrame([{"項目": item, "ポイント": point}])], ignore_index=True)
                df_item.to_csv(ITEM_FILE, index=False, encoding="utf-8-sig")
                st.success(f"『{item}』（{point}pt）を登録しました。")
                st.rerun()
            if os.path.exists(ITEM_FILE):
                df_item = pd.read_csv(ITEM_FILE)
                df_item["削除"] = False
                edited = st.data_editor(df_item, use_container_width=True)
                delete = edited[edited["削除"]]
                if st.button("チェックした項目を削除"):
                    df_item = df_item.drop(delete.index)
                    df_item.to_csv(ITEM_FILE, index=False, encoding="utf-8-sig")
                    st.success("削除しました。")
                    st.rerun()

        elif choice == "施設設定" and is_admin:
            st.subheader("🏠 グループホーム設定")
            with st.form("fac_form"):
                name = st.text_input("グループホーム名（例：グループホーム美園）")
                submit = st.form_submit_button("登録")
            if submit and name:
                df_fac = pd.read_csv(FACILITY_FILE) if os.path.exists(FACILITY_FILE) else pd.DataFrame(columns=["施設名"])
                df_fac = pd.concat([df_fac, pd.DataFrame([{"施設名": name}])], ignore_index=True)
                df_fac.to_csv(FACILITY_FILE, index=False, encoding="utf-8-sig")
                st.success(f"『{name}』を登録しました。")
                st.rerun()
            if os.path.exists(FACILITY_FILE):
                df_fac = pd.read_csv(FACILITY_FILE)
                df_fac["削除"] = False
                edited = st.data_editor(df_fac, use_container_width=True)
                delete = edited[edited["削除"]]
                if st.button("チェックした施設を削除"):
                    df_fac = df_fac.drop(delete.index)
                    df_fac.to_csv(FACILITY_FILE, index=False, encoding="utf-8-sig")
                    st.success("削除しました。")
                    st.rerun()

        # 他（ポイント付与・履歴・ランキング）は前回のコードのまま動作
        # ...
