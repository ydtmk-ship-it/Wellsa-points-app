import streamlit as st
import pandas as pd
import os
from datetime import date
from openai import OpenAI

# ===============================
# 基本設定
# ===============================
st.set_page_config(page_title="ウェルサポイント", page_icon="💎", layout="wide")

DATA_FILE = "points_data.csv"
USER_FILE = "users.csv"
ITEM_FILE = "items.csv"
FACILITY_FILE = "facilities.csv"

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

def generate_comment(item, points):
    try:
        if os.path.exists(DATA_FILE):
            df_hist = pd.read_csv(DATA_FILE)
            df_hist = df_hist[df_hist["項目"] == item]
            if not df_hist.empty:
                recent_comments = " / ".join(df_hist["コメント"].dropna().tail(5).tolist())
                history_summary = f"過去の『{item}』コメント例: {recent_comments}"
            else:
                history_summary = f"『{item}』にはまだコメント履歴がありません。"
        else:
            history_summary = "コメント履歴はまだありません。"

        prompt = f"""
あなたは障がい者福祉施設の職員です。
以下の履歴を踏まえて、今回『{item}』の活動に{points}ポイント付与します。
やさしいトーンで短い励ましコメントを生成。
必ず「ありがとう」を含め、30文字以内、日本語、絵文字1つ。
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

        staff_tab_list = ["ポイント付与", "履歴閲覧", "グループホーム別ランキング"]
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
                    comment = generate_comment(selected_item, points_value)
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
                    st.info(f"AIコメント: {comment}")

        # --- 履歴閲覧 ---
        elif staff_tab == "履歴閲覧":
            st.subheader("🗂 ポイント履歴")
            if df.empty:
                st.info("まだデータがありません。")
            else:
                df["削除"] = False
                edited_df = st.data_editor(df, use_container_width=True, key="delete_hist")
                delete_rows = edited_df[edited_df["削除"]]
                if st.button("チェックした行を削除"):
                    if not delete_rows.empty:
                        df = df.drop(delete_rows.index)
                        save_data(df)
                        st.success(f"{len(delete_rows)} 件を削除しました。")
                        st.rerun()

        # --- グループホーム別ランキング ---
        elif staff_tab == "グループホーム別ランキング":
            st.subheader("🏠 グループホーム別ポイントランキング（月ごと）")
            if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
                st.info("まだポイントデータがありません。")
            elif not os.path.exists(USER_FILE):
                st.info("利用者データがありません。")
            else:
                df = pd.read_csv(DATA_FILE)
                df_user = pd.read_csv(USER_FILE)
                if "施設" in df_user.columns:
                    df["年月"] = pd.to_datetime(df["日付"], errors="coerce").dt.to_period("M").astype(str)
                    month_list = sorted(df["年月"].unique(), reverse=True)
                    selected_month = st.selectbox("表示する月を選択", month_list, index=0)
                    df_month = df[df["年月"] == selected_month]
                    merged = pd.merge(df_month, df_user[["氏名", "施設"]],
                                      left_on="利用者名", right_on="氏名", how="left")
                    df_home = merged.groupby("施設")["ポイント"].sum().reset_index().sort_values("ポイント", ascending=False)
                    df_home["順位"] = range(1, len(df_home) + 1)
                    df_home["順位表示"] = df_home["順位"].apply(
                        lambda x: "🥇" if x == 1 else "🥈" if x == 2 else "🥉" if x == 3 else f"{x}"
                    )
                    st.dataframe(df_home[["順位表示", "施設", "ポイント"]], use_container_width=True)

        # --- 利用者登録 ---
        elif staff_tab == "利用者登録" and is_admin:
            st.subheader("🧍‍♀️ 利用者登録")
            with st.form("user_form"):
                last_name = st.text_input("姓")
                first_name = st.text_input("名")
                full_name = f"{last_name} {first_name}".strip()
                facility = st.selectbox("所属グループホームを選択",
                                        pd.read_csv(FACILITY_FILE)["施設名"].tolist() if os.path.exists(FACILITY_FILE) else [])
                submitted_user = st.form_submit_button("登録")
            if submitted_user and full_name:
                df_user = pd.read_csv(USER_FILE) if os.path.exists(USER_FILE) else pd.DataFrame(columns=["氏名", "施設"])
                df_user = pd.concat([df_user, pd.DataFrame([{"氏名": full_name, "施設": facility}])], ignore_index=True)
                df_user.to_csv(USER_FILE, index=False, encoding="utf-8-sig")
                st.success(f"利用者『{full_name}（{facility}）』を登録しました。")
                st.rerun()

            if os.path.exists(USER_FILE):
                df_user = pd.read_csv(USER_FILE)
                df_user["削除"] = False
                edited_user = st.data_editor(df_user, use_container_width=True, key="user_edit")
                delete_rows = edited_user[edited_user["削除"]]
                if st.button("✓ チェックした利用者を削除"):
                    if not delete_rows.empty:
                        df_user = df_user.drop(delete_rows.index)
                        df_user.to_csv(USER_FILE, index=False, encoding="utf-8-sig")
                        st.success(f"{len(delete_rows)} 名の利用者を削除しました。")
                        st.rerun()

        # --- 活動項目設定 ---
        elif staff_tab == "活動項目設定" and is_admin:
            st.subheader("⚙ 活動項目設定")
            with st.form("item_form"):
                item_name = st.text_input("活動項目名")
                point_value = st.number_input("ポイント数", min_value=1, step=1)
                submitted_item = st.form_submit_button("登録")
            if submitted_item and item_name:
                df_item = pd.read_csv(ITEM_FILE) if os.path.exists(ITEM_FILE) else pd.DataFrame(columns=["項目", "ポイント"])
                df_item = pd.concat([df_item, pd.DataFrame([{"項目": item_name, "ポイント": point_value}])], ignore_index=True)
                df_item.to_csv(ITEM_FILE, index=False, encoding="utf-8-sig")
                st.success(f"活動項目『{item_name}（{point_value} pt）』を登録しました。")
                st.rerun()

            if os.path.exists(ITEM_FILE):
                df_item = pd.read_csv(ITEM_FILE)
                df_item["削除"] = False
                edited_item = st.data_editor(df_item, use_container_width=True, key="item_edit")
                delete_rows = edited_item[edited_item["削除"]]
                if st.button("✓ チェックした項目を削除"):
                    if not delete_rows.empty:
                        df_item = df_item.drop(delete_rows.index)
                        df_item.to_csv(ITEM_FILE, index=False, encoding="utf-8-sig")
                        st.success(f"{len(delete_rows)} 件を削除しました。")
                        st.rerun()

        # --- 施設設定 ---
        elif staff_tab == "施設設定" and is_admin:
            st.subheader("🏠 グループホーム設定")
            with st.form("facility_form"):
                facility_name = st.text_input("グループホーム名（例：グループホーム美園）")
                submitted_facility = st.form_submit_button("登録")
            if submitted_facility and facility_name:
                df_fac = pd.read_csv(FACILITY_FILE) if os.path.exists(FACILITY_FILE) else pd.DataFrame(columns=["施設名"])
                df_fac = pd.concat([df_fac, pd.DataFrame([{"施設名": facility_name}])], ignore_index=True)
                df_fac.to_csv(FACILITY_FILE, index=False, encoding="utf-8-sig")
                st.success(f"グループホーム『{facility_name}』を登録しました。")
                st.rerun()

            if os.path.exists(FACILITY_FILE):
                df_fac = pd.read_csv(FACILITY_FILE)
                df_fac["削除"] = False
                edited_fac = st.data_editor(df_fac, use_container_width=True, key="fac_edit")
                delete_rows = edited_fac[edited_fac["削除"]]
                if st.button("✓ チェックした施設を削除"):
                    if not delete_rows.empty:
                        df_fac = df_fac.drop(delete_rows.index)
                        df_fac.to_csv(FACILITY_FILE, index=False, encoding="utf-8-sig")
                        st.success(f"{len(delete_rows)} 件の施設を削除しました。")
                        st.rerun()

        # --- ログアウト ---
        if st.button("🚪 ログアウト"):
            st.session_state["staff_logged_in"] = False
            st.session_state["is_admin"] = False
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

        df["normalized_name"] = df["利用者名"].apply(normalize_name)
        df_user_points = df[df["normalized_name"] == normalize_name(user_name)]

        # 💬 最新のありがとうコメントカード
        if not df_user_points.empty and "コメント" in df_user_points.columns:
            last_comment = df_user_points["コメント"].dropna().iloc[-1]
            st.markdown(f"""
            <div style='background-color:#e6f2ff;padding:10px;border-radius:10px;margin-bottom:10px;'>
                <h4 style='color:#007BFF;'>💬 最近のありがとうメッセージ</h4>
                <p style='font-size:18px;margin:0;'>{last_comment}</p>
            </div>
            """, unsafe_allow_html=True)

        # 💎 あなたのありがとう履歴
        st.subheader("💎 あなたのありがとう履歴")
        if df_user_points.empty:
            st.info("まだポイント履歴がありません。")
        else:
            df_view = df_user_points[["日付", "項目", "ポイント", "コメント"]].sort_values("日付", ascending=False)
            df_view.rename(columns={"コメント": "AIからのメッセージ"}, inplace=True)
            st.dataframe(df_view, use_container_width=True)

        if st.button("🚪 ログアウト"):
            st.session_state["user_logged_in"] = False
            st.rerun()
