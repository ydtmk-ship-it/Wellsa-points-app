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
# ユーティリティ
# ===============================
def clean_name(s: str):
    return (
        str(s)
        .encode("utf-8", "ignore")
        .decode("utf-8")
        .replace("　", "")
        .replace(" ", "")
        .replace("\n", "")
        .replace("\r", "")
        .strip()
        .lower()
    )

def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=["日付", "利用者名", "項目", "ポイント", "所属部署", "コメント"])

def save_data(df):
    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")

def read_user_list():
    if os.path.exists(USER_FILE):
        df_user = pd.read_csv(USER_FILE)
        if "氏名" in df_user.columns:
            return df_user
    return pd.DataFrame(columns=["氏名", "施設"])

def read_item_list():
    if os.path.exists(ITEM_FILE):
        return pd.read_csv(ITEM_FILE)
    return pd.DataFrame(columns=["項目", "ポイント"])

def read_facility_list():
    if os.path.exists(FACILITY_FILE):
        return pd.read_csv(FACILITY_FILE)
    return pd.DataFrame(columns=["施設名"])

# ===============================
# AIコメント生成（本人＋項目限定）
# ===============================
def generate_comment(user_name, item, points):
    try:
        if os.path.exists(DATA_FILE):
            df_hist = pd.read_csv(DATA_FILE)
            df_hist = df_hist[(df_hist["利用者名"] == user_name) & (df_hist["項目"] == item)]
            if not df_hist.empty:
                recent_comments = " / ".join(df_hist["コメント"].dropna().tail(5).tolist())
                history_summary = f"{user_name}さんの過去の『{item}』コメント例: {recent_comments}"
            else:
                history_summary = f"{user_name}さんの『{item}』にはまだコメント履歴がありません。"
        else:
            history_summary = f"{user_name}さんのコメント履歴はまだありません。"

        prompt = f"""
あなたは障がい福祉施設の職員です。
{user_name}さんが『{item}』の活動に{points}ポイントを獲得しました。
やさしいトーンで短い励ましコメントを作ってください。
活動に対して必ず「ありがとう」を含め、30文字以内、日本語、絵文字1つ。
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
        return f"{user_name}さん、今日もありがとう😊"

# ===============================
# モード選択
# ===============================
mode = st.sidebar.radio("モードを選択", ["利用者モード", "職員モード"])

# =========================================================
# 職員モード（略：前回のv24部分そのまま）
# =========================================================
# =========================================================
# 職員モード
# =========================================================
if mode == "職員モード":
    st.title("📝 職員モード")

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
            df_item = read_item_list()
            df_user = read_user_list()

            if df_user.empty:
                st.warning("利用者が未登録です。")
                user_name = None
            else:
                user_list = df_user["氏名"].dropna().tolist()
                user_name = st.selectbox("利用者を選択", user_list)

            if not df_item.empty:
                selected_item = st.selectbox("活動項目を選択", df_item["項目"].tolist())
                points_value = int(df_item.loc[df_item["項目"] == selected_item, "ポイント"].values[0])
                st.number_input("付与ポイント数", value=points_value, disabled=True)
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
                    st.info(f"AIコメント: {comment}")

        # --- 履歴閲覧 ---
        elif staff_tab == "履歴閲覧":
            st.subheader("🗂 ポイント履歴")
            if df.empty:
                st.info("まだデータがありません。")
            else:
                df["削除"] = False
                edited_df = st.data_editor(df, use_container_width=True)
                delete_rows = edited_df[edited_df["削除"]]
                if st.button("チェックした行を削除"):
                    if not delete_rows.empty:
                        df = df.drop(delete_rows.index)
                        save_data(df)
                        st.success(f"{len(delete_rows)} 件を削除しました。")
                        st.rerun()

        # --- 利用者登録（✓削除対応） ---
        elif staff_tab == "利用者登録" and is_admin:
            st.subheader("🧍‍♀️ 利用者登録")
            df_fac = read_facility_list()
            facility_list = df_fac["施設名"].dropna().tolist() if not df_fac.empty else []
            if not facility_list:
                st.info("⚠️ 施設が未登録です。『施設設定』で登録してください。")

            with st.form("user_register_form"):
                col1, col2 = st.columns(2)
                with col1:
                    last_name = st.text_input("姓")
                with col2:
                    first_name = st.text_input("名")
                facility = st.selectbox("所属施設", facility_list, index=0 if facility_list else None)
                submitted = st.form_submit_button("登録")

            if submitted and last_name and first_name and facility:
                full_name = f"{last_name.strip()} {first_name.strip()}"
                df_user = read_user_list()
                df_user = pd.concat([df_user, pd.DataFrame([{"氏名": full_name, "施設": facility}])], ignore_index=True)
                df_user.to_csv(USER_FILE, index=False, encoding="utf-8-sig")
                st.success(f"{full_name}（{facility}）を登録しました。")
                st.rerun()

            df_user = read_user_list()
            if not df_user.empty:
                df_user["削除"] = False
                edited_users = st.data_editor(df_user, use_container_width=True)
                delete_targets = edited_users[edited_users["削除"]]
                if st.button("チェックした利用者を削除"):
                    df_user = df_user.drop(delete_targets.index)
                    df_user.to_csv(USER_FILE, index=False, encoding="utf-8-sig")
                    st.success(f"{len(delete_targets)} 名を削除しました。")
                    st.rerun()

        # --- 活動項目設定（✓削除対応） ---
        elif staff_tab == "活動項目設定" and is_admin:
            st.subheader("⚙ 活動項目設定")
            with st.form("item_form"):
                item = st.text_input("活動項目名")
                points = st.number_input("ポイント数", min_value=1, step=1)
                submitted = st.form_submit_button("登録")
            if submitted and item:
                df_item = read_item_list()
                df_item = pd.concat([df_item, pd.DataFrame([{"項目": item, "ポイント": points}])], ignore_index=True)
                df_item.to_csv(ITEM_FILE, index=False, encoding="utf-8-sig")
                st.success(f"{item}（{points}pt）を登録しました。")
                st.rerun()

            df_item = read_item_list()
            if not df_item.empty:
                df_item["削除"] = False
                edited_items = st.data_editor(df_item, use_container_width=True)
                delete_targets = edited_items[edited_items["削除"]]
                if st.button("チェックした項目を削除"):
                    df_item = df_item.drop(delete_targets.index)
                    df_item.to_csv(ITEM_FILE, index=False, encoding="utf-8-sig")
                    st.success(f"{len(delete_targets)} 件の活動項目を削除しました。")
                    st.rerun()

        # --- 施設設定（✓削除対応） ---
        elif staff_tab == "施設設定" and is_admin:
            st.subheader("🏠 施設設定")
            with st.form("facility_form"):
                facility_name = st.text_input("施設名")
                submitted = st.form_submit_button("登録")
            if submitted and facility_name:
                df_fac = read_facility_list()
                df_fac = pd.concat([df_fac, pd.DataFrame([{"施設名": facility_name}])], ignore_index=True)
                df_fac.to_csv(FACILITY_FILE, index=False, encoding="utf-8-sig")
                st.success(f"施設『{facility_name}』を登録しました。")
                st.rerun()

            df_fac = read_facility_list()
            if not df_fac.empty:
                df_fac["削除"] = False
                edited_fac = st.data_editor(df_fac, use_container_width=True)
                delete_targets = edited_fac[edited_fac["削除"]]
                if st.button("チェックした施設を削除"):
                    df_fac = df_fac.drop(delete_targets.index)
                    df_fac.to_csv(FACILITY_FILE, index=False, encoding="utf-8-sig")
                    st.success(f"{len(delete_targets)} 件の施設を削除しました。")
                    st.rerun()

        # --- グループホーム別ランキング（月選択） ---
        elif staff_tab == "グループホーム別ランキング":
            st.subheader("🏠 グループホーム別ポイントランキング（月ごと）")
            if os.path.exists(DATA_FILE) and os.path.exists(USER_FILE):
                df = pd.read_csv(DATA_FILE)
                df_user = read_user_list()
                if not df.empty:
                    df["年月"] = pd.to_datetime(df["日付"], errors="coerce").dt.to_period("M").astype(str)
                    month_list = sorted(df["年月"].dropna().unique(), reverse=True)
                    selected_month = st.selectbox("表示する月を選択", month_list, index=0)
                    df_month = df[df["年月"] == selected_month]
                    merged = pd.merge(df_month, df_user[["氏名", "施設"]], left_on="利用者名", right_on="氏名", how="left")
                    df_home = merged.groupby("施設", dropna=False)["ポイント"].sum().reset_index().fillna({"施設": "（未登録）"})
                    df_home = df_home.sort_values("ポイント", ascending=False)
                    df_home["順位"] = range(1, len(df_home) + 1)
                    df_home["順位表示"] = df_home["順位"].apply(lambda x: "🥇" if x == 1 else "🥈" if x == 2 else "🥉" if x == 3 else str(x))
                    st.dataframe(df_home[["順位表示", "施設", "ポイント"]], use_container_width=True)
                else:
                    st.info("ポイントデータがありません。")
            else:
                st.info("データがありません。")

        st.sidebar.button("🚪 ログアウト", on_click=lambda: (st.session_state.clear(), st.rerun()))


# =========================================================
# 🧍‍♀️ 利用者モード
# =========================================================
if mode == "利用者モード":
    st.title("👫 利用者モード")

    if "user_logged_in" not in st.session_state:
        st.session_state["user_logged_in"] = False
        st.session_state["user_name"] = None

    df_user = read_user_list()

    # --- ログイン ---
    if not st.session_state["user_logged_in"]:
        if df_user.empty:
            st.info("利用者が登録されていません。職員に登録を依頼してください。")
        else:
            user_list = df_user["氏名"].dropna().tolist()
            selected_name = st.selectbox("あなたのお名前を選んでください", user_list)
            if st.button("ログイン"):
                st.session_state["user_logged_in"] = True
                st.session_state["user_name"] = selected_name
                st.success(f"{selected_name} さん、ようこそ！")
                st.rerun()

    # --- ログイン後 ---
    else:
        user_name = st.session_state["user_name"]
        st.sidebar.success(f"✅ ログイン中：{user_name}")
        df = load_data()
        df_user = read_user_list()

        user_facility = df_user.loc[df_user["氏名"] == user_name, "施設"].iloc[0] if user_name in df_user["氏名"].values else "未登録"

        st.markdown(f"### 🏠 所属施設：{user_facility}")

        # --- 自分のポイント履歴 ---
        df_user_points = df[df["利用者名"] == user_name]

        if not df_user_points.empty:
            st.subheader("💎 最近のポイント履歴")
            st.dataframe(df_user_points[["日付", "項目", "ポイント", "コメント"]].sort_values("日付", ascending=False), use_container_width=True)

            # --- 月ごとのがんばり ---
            st.subheader("📅 あなたの月ごとのがんばり")

            df_user_points["年月"] = pd.to_datetime(df_user_points["日付"], errors="coerce").dt.to_period("M").astype(str)
            monthly_points = df_user_points.groupby("年月")["ポイント"].sum().reset_index().sort_values("年月")
            monthly_points["前月比"] = monthly_points["ポイント"].diff()
            monthly_points["変化"] = monthly_points["前月比"].apply(lambda x: "↑" if x > 0 else ("↓" if x < 0 else "→"))
            monthly_points["バッジ"] = monthly_points["前月比"].apply(
                lambda x: "🏅 成長" if x > 0 else ("💪 がんばろう" if x < 0 else "🟢 維持")
            )

            monthly_points_display = monthly_points.rename(columns={
                "年月": "月", "ポイント": "合計ポイント", "変化": "前月比", "バッジ": "評価"
            })
            st.dataframe(monthly_points_display, use_container_width=True)

            if len(monthly_points) >= 2:
                last_row = monthly_points.iloc[-1]
                if last_row["前月比"] > 0:
                    st.success("🏅 成長バッジを獲得しました！前月よりポイントアップ！")
                elif last_row["前月比"] < 0:
                    st.warning("💪 がんばろうバッジ：前月より少なめでした。来月もファイト！")
                else:
                    st.info("🟢 ポイントは前月と同じです。継続がんばっていますね！")

            # --- 累計ポイント ---
            total_points = int(df_user_points["ポイント"].sum())
            st.metric("✨ あなたの累計ポイント", f"{total_points} pt")

        else:
            st.info("まだポイント履歴がありません。")

        # --- グループホーム別ランキング ---
        st.subheader("🏠 グループホーム別ポイントランキング")
        df_user_all = read_user_list()
        if not df.empty and not df_user_all.empty:
            df = pd.merge(df, df_user_all, left_on="利用者名", right_on="氏名", how="left")
            df["年月"] = pd.to_datetime(df["日付"], errors="coerce").dt.to_period("M").astype(str)

            month_list = sorted(df["年月"].dropna().unique(), reverse=True)
            selected_month = st.selectbox("表示する月を選択", month_list, index=0)
            df_month = df[df["年月"] == selected_month]
            df_home = df_month.groupby("施設", dropna=False)["ポイント"].sum().reset_index().fillna({"施設": "（未登録）"})
            df_home = df_home.sort_values("ポイント", ascending=False)
            df_home["順位"] = range(1, len(df_home) + 1)
            df_home["順位表示"] = df_home["順位"].apply(
                lambda x: "🥇" if x == 1 else "🥈" if x == 2 else "🥉" if x == 3 else str(x)
            )

            def highlight_row(row):
                if row["施設"] == user_facility:
                    return ['background-color: #b3d9ff'] * len(row)
                else:
                    return [''] * len(row)

            st.dataframe(
                df_home[["順位表示", "施設", "ポイント"]].style.apply(highlight_row, axis=1),
                use_container_width=True
            )

        st.sidebar.button("🚪 ログアウト", on_click=lambda: (st.session_state.clear(), st.rerun()))
