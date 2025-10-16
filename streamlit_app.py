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
# ユーティリティ関数
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

def show_df(df_or_styler):
    st.dataframe(df_or_styler, use_container_width=True, hide_index=True)

def edit_df(df):
    return st.data_editor(df, use_container_width=True, hide_index=True)


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
活動に対して「通所してくれてありがとう」「来てくれてありがとう」など、必ず文章に「してくれてありがとう」を含め、30文字以内、日本語、絵文字1つ。
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
# 職員モード
# =========================================================
if mode == "職員モード":
    st.title("📝 職員モード")

    # =========================================================
    # 共通表示関数（Styler対応・インデックス非表示）
    # =========================================================
    def show_table(df):
        import pandas as pd
        if isinstance(df, pd.io.formats.style.Styler):
            st.dataframe(df.data.reset_index(drop=True), use_container_width=True, hide_index=True)
        else:
            st.dataframe(df.reset_index(drop=True), use_container_width=True, hide_index=True)

    # =========================================================
    # ログイン状態管理
    # =========================================================
    if "staff_logged_in" not in st.session_state:
        st.session_state["staff_logged_in"] = False
    if "is_admin" not in st.session_state:
        st.session_state["is_admin"] = False

    # =========================================================
    # ログイン画面
    # =========================================================
    if not st.session_state["staff_logged_in"]:
        dept = st.selectbox("部署を選択", list(STAFF_ACCOUNTS.keys()) + ["管理者"])
        input_id = st.text_input("ログインID")
        input_pass = st.text_input("パスワード", type="password")

        if st.button("ログイン"):
            if dept == "管理者":
                if input_id == ADMIN_ID and input_pass == ADMIN_PASS:
                    st.session_state.update({
                        "staff_logged_in": True,
                        "staff_dept": "管理者",
                        "is_admin": True
                    })
                    st.success("管理者としてログインしました！")
                    st.rerun()
                else:
                    st.error("管理者IDまたはパスワードが違います。")
            else:
                stored_id, stored_pass = STAFF_ACCOUNTS[dept].split("|")
                if input_id == stored_id and input_pass == stored_pass:
                    st.session_state.update({
                        "staff_logged_in": True,
                        "staff_dept": dept,
                        "is_admin": False
                    })
                    st.success(f"{dept} としてログインしました！")
                    st.rerun()
                else:
                    st.error("IDまたはパスワードが違います。")

    # =========================================================
    # ログイン後
    # =========================================================
    else:
        dept = st.session_state["staff_dept"]
        is_admin = st.session_state["is_admin"]
        st.sidebar.success(f"✅ ログイン中：{dept}")

        # 管理者は全機能表示
        staff_tab_list = (
            ["ポイント付与", "履歴閲覧", "月次ランキング", "累計利用者ランキング",
             "利用者登録", "活動項目設定", "施設設定"]
            if is_admin
            else ["ポイント付与", "履歴閲覧", "月次ランキング", "累計利用者ランキング"]
        )

        staff_tab = st.sidebar.radio("機能を選択", staff_tab_list)
        df = load_data()

        # =========================================================
        # ポイント付与
        # =========================================================
        if staff_tab == "ポイント付与":
            st.subheader("💎 ポイント付与")
            df_item = read_item_list()
            df_user = read_user_list()

            if df_user.empty:
                st.warning("利用者が未登録です。")
            else:
                user_list = df_user["氏名"].dropna().tolist()
                user_name = st.selectbox("利用者を選択", user_list)

                if not df_item.empty:
                    selected_item = st.selectbox("活動項目を選択", df_item["項目"].tolist())
                    points_value = int(df_item.loc[df_item["項目"] == selected_item, "ポイント"].values[0])
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
                        st.info(f"AIコメント: {comment}")

        # =========================================================
        # 履歴閲覧
        # =========================================================
        elif staff_tab == "履歴閲覧":
            st.subheader("📜 ポイント履歴の閲覧")
            if df.empty:
                st.info("まだ履歴データがありません。")
            else:
                df_user = read_user_list()
                user_options = ["すべて"] + df_user["氏名"].dropna().unique().tolist()
                selected_user = st.selectbox("利用者を選択（またはすべて）", user_options)
                df_view = df.copy() if selected_user == "すべて" else df[df["利用者名"] == selected_user]
                if not df_view.empty:
                    df_view = df_view.sort_values("日付", ascending=False).reset_index(drop=True)
                    df_view.rename(columns={"コメント": "AIコメント"}, inplace=True)
                    show_table(df_view[["日付", "利用者名", "項目", "ポイント", "所属部署", "AIコメント"]])
                else:
                    st.info("該当する履歴がありません。")

        # =========================================================
        # 月次ランキング（月・施設別）
        # =========================================================
        elif staff_tab == "月次ランキング":
            st.subheader("🏆 月次ランキング（月・施設別）")
            if df.empty:
                st.info("まだポイントデータがありません。")
            else:
                df_all_users = read_user_list()
                df_rank = df.copy()
                df_rank["年月"] = pd.to_datetime(df_rank["日付"], errors="coerce").dt.to_period("M").astype(str)
                month_list = sorted(df_rank["年月"].dropna().unique(), reverse=True)
                if month_list:
                    selected_month = st.selectbox("表示する月を選択", month_list, index=0)
                    df_month = df_rank[df_rank["年月"] == selected_month]
                    merged = pd.merge(df_month, df_all_users[["氏名", "施設"]],
                                      left_on="利用者名", right_on="氏名", how="left")

                    facility_list = ["すべて"] + sorted(merged["施設"].dropna().unique().tolist())
                    selected_facility = st.selectbox("施設を選択（またはすべて）", facility_list)
                    if selected_facility != "すべて":
                        merged = merged[merged["施設"] == selected_facility]

                    # =========================================================
                    # 施設別ランキング：合計ポイント＆1人あたりポイント
                    # =========================================================

                    # --- 合計ポイント ---
                    df_home_total = merged.groupby("施設", dropna=False)["ポイント"].sum().reset_index().fillna({"施設": "（未登録）"})
                    df_home_total = df_home_total.sort_values("ポイント", ascending=False).reset_index(drop=True)
                    df_home_total["順位"] = range(1, len(df_home_total) + 1)
                    df_home_total["順位表示"] = df_home_total["順位"].apply(
                        lambda x: "🥇" if x == 1 else "🥈" if x == 2 else "🥉" if x == 3 else str(x)
                    )

                    st.markdown("### 🏠 施設別ランキング（合計ポイント）")
                    show_table(df_home_total[["順位表示", "施設", "ポイント"]])

                    # --- 1人あたり平均ポイント ---
                    df_fac_users = df_all_users.groupby("施設")["氏名"].nunique().reset_index()
                    df_fac_users.rename(columns={"氏名": "利用者数"}, inplace=True)

                    df_home_avg = pd.merge(df_home_total, df_fac_users, on="施設", how="left")
                    df_home_avg["利用者数"] = df_home_avg["利用者数"].fillna(0).astype(int)
                    df_home_avg["1人あたりポイント"] = df_home_avg.apply(
                        lambda x: 0 if x["利用者数"] == 0 else round(x["ポイント"] / x["利用者数"], 1),
                        axis=1
                    )

                    df_home_avg = df_home_avg.sort_values("1人あたりポイント", ascending=False).reset_index(drop=True)
                    df_home_avg["順位"] = range(1, len(df_home_avg) + 1)
                    df_home_avg["順位表示"] = df_home_avg["順位"].apply(
                        lambda x: "🥇" if x == 1 else "🥈" if x == 2 else "🥉" if x == 3 else str(x)
                    )

                    st.markdown("### 🧮 施設別ランキング（1人あたり平均ポイント）")
                    show_table(df_home_avg[["順位表示", "施設", "1人あたりポイント"]])


                    # 利用者別集計
                    df_user_rank = merged.groupby(["利用者名", "施設"], dropna=False)["ポイント"].sum().reset_index()
                    df_user_rank = df_user_rank.sort_values("ポイント", ascending=False).head(10).reset_index(drop=True)
                    df_user_rank["順位"] = range(1, len(df_user_rank) + 1)
                    df_user_rank["順位表示"] = df_user_rank["順位"].apply(
                        lambda x: "🥇" if x == 1 else "🥈" if x == 2 else "🥉" if x == 3 else str(x))
                    st.markdown("### 👥 利用者別ランキング（上位10名）")
                    show_table(df_user_rank[["順位表示", "利用者名", "施設", "ポイント"]])

        # =========================================================
        # 累計利用者ランキング
        # =========================================================
        elif staff_tab == "累計利用者ランキング":
            st.subheader("👑 累計利用者ランキング")
            if df.empty:
                st.info("データがありません。")
            else:
                df_all_users = read_user_list()
                total_rank = pd.merge(df, df_all_users[["氏名", "施設"]],
                                      left_on="利用者名", right_on="氏名", how="left")
                total_rank = total_rank.groupby(["利用者名", "施設"])["ポイント"].sum().reset_index()
                total_rank = total_rank.sort_values("ポイント", ascending=False).head(10).reset_index(drop=True)
                total_rank["順位"] = range(1, len(total_rank) + 1)
                total_rank["順位表示"] = total_rank["順位"].apply(
                    lambda x: "🥇" if x == 1 else "🥈" if x == 2 else "🥉" if x == 3 else str(x))
                show_table(total_rank[["順位表示", "利用者名", "施設", "ポイント"]])

        # =========================================================
        # 管理者限定：利用者登録
        # =========================================================
        elif staff_tab == "利用者登録" and is_admin:
            st.subheader("👫 利用者登録")
            df_fac = read_facility_list()
            facilities = df_fac["施設名"].tolist() if not df_fac.empty else []
            with st.form("user_form"):
                last_name = st.text_input("姓")
                first_name = st.text_input("名")
                facility = st.selectbox("グループホームを選択", facilities)
                submitted = st.form_submit_button("登録")
            if submitted and last_name and first_name and facility:
                full_name = f"{last_name} {first_name}"
                df_user = read_user_list()
                new_user = {"氏名": full_name, "施設": facility}
                df_user = pd.concat([df_user, pd.DataFrame([new_user])], ignore_index=True)
                df_user.to_csv(USER_FILE, index=False, encoding="utf-8-sig")
                st.success(f"{full_name}（{facility}）を登録しました。")
                st.rerun()

            if os.path.exists(USER_FILE):
                df_user = read_user_list()
                if not df_user.empty:
                    df_user["削除"] = False
                    edited = st.data_editor(df_user, use_container_width=True, hide_index=True)
                    delete_targets = edited[edited["削除"]]
                    if st.button("チェックした利用者を削除"):
                        df_user = df_user.drop(delete_targets.index)
                        df_user.to_csv(USER_FILE, index=False, encoding="utf-8-sig")
                        st.success("削除しました。")
                        st.rerun()

        # =========================================================
        # 管理者限定：活動項目設定
        # =========================================================
        elif staff_tab == "活動項目設定" and is_admin:
            st.subheader("🧩 活動項目設定")
            with st.form("item_form"):
                item_name = st.text_input("活動項目名")
                point_value = st.number_input("ポイント数", min_value=1, step=1)
                submitted = st.form_submit_button("登録")
            if submitted and item_name:
                df_item = read_item_list()
                df_item = pd.concat([df_item, pd.DataFrame([{"項目": item_name, "ポイント": point_value}])],
                                    ignore_index=True)
                df_item.to_csv(ITEM_FILE, index=False, encoding="utf-8-sig")
                st.success(f"{item_name} を登録しました。")
                st.rerun()

            if os.path.exists(ITEM_FILE):
                df_item = read_item_list()
                if not df_item.empty:
                    df_item["削除"] = False
                    edited = st.data_editor(df_item, use_container_width=True, hide_index=True)
                    delete_targets = edited[edited["削除"]]
                    if st.button("チェックした項目を削除"):
                        df_item = df_item.drop(delete_targets.index)
                        df_item.to_csv(ITEM_FILE, index=False, encoding="utf-8-sig")
                        st.success("削除しました。")
                        st.rerun()

        # =========================================================
        # 管理者限定：施設設定
        # =========================================================
        elif staff_tab == "施設設定" and is_admin:
            st.subheader("🏠 グループホーム設定")
            with st.form("fac_form"):
                name = st.text_input("グループホーム名")
                submitted = st.form_submit_button("登録")
            if submitted and name:
                df_fac = read_facility_list()
                df_fac = pd.concat([df_fac, pd.DataFrame([{"施設名": name}])],
                                   ignore_index=True)
                df_fac.to_csv(FACILITY_FILE, index=False, encoding="utf-8-sig")
                st.success(f"{name} を登録しました。")
                st.rerun()

            if os.path.exists(FACILITY_FILE):
                df_fac = read_facility_list()
                if not df_fac.empty:
                    df_fac["削除"] = False
                    edited = st.data_editor(df_fac, use_container_width=True, hide_index=True)
                    delete_targets = edited[edited["削除"]]
                    if st.button("チェックした施設を削除"):
                        df_fac = df_fac.drop(delete_targets.index)
                        df_fac.to_csv(FACILITY_FILE, index=False, encoding="utf-8-sig")
                        st.success("削除しました。")
                        st.rerun()

# =========================================================
# 利用者モード
# =========================================================
elif mode == "利用者モード":
    # =========================================================
    # タイトル（ログイン状態によって動的に表示）
    # =========================================================
    if st.session_state.get("user_logged_in"):
        user_name = st.session_state["user_name"]
        st.markdown(
            f"<h2 style='margin-top: 5px;'>🔔 {user_name} さん</h2>",
            unsafe_allow_html=True
        )
    else:
        st.title("🧍‍♀️ 利用者モード")

    df = load_data()

    # =========================================================
    # 共通テーブル表示（HTML統一：非編集・幅統一・インデックス非表示・ハイライト維持）
    # =========================================================
    def show_table(tbl):
        import pandas as pd

        # 共通CSS（全テーブルに統一感を出す）
        css = """
        <style>
        .ws-wrap { overflow-x: auto; }
        .ws-wrap table { width: 100%; border-collapse: collapse; table-layout: auto; }
        .ws-wrap thead th { background: #f8f9fb; position: sticky; top: 0; z-index: 1; }
        .ws-wrap th, .ws-wrap td { padding: 8px 10px; border-bottom: 1px solid #eee; text-align: left; }
        </style>
        """

        # Styler（ハイライトあり）は index を確実に隠して HTML 化
        if isinstance(tbl, pd.io.formats.style.Styler):
            try:
                tbl = tbl.hide(axis="index")
            except Exception:
                try:
                    tbl = tbl.hide_index()
                except Exception:
                    pass
            html = tbl.to_html()
        else:
            # DataFrame は index を落として HTML 化
            html = tbl.reset_index(drop=True).to_html(index=False, border=0)

        st.markdown(css + f"<div class='ws-wrap'>{html}</div>", unsafe_allow_html=True)

    # =========================================================
    # ログイン処理
    # =========================================================
    if not st.session_state.get("user_logged_in"):
        last_name = st.text_input("姓（例：田中）")
        first_name = st.text_input("名（例：太郎）")

        if st.button("ログイン"):
            chosen = None
            if last_name or first_name:
                typed_full = f"{last_name.strip()} {first_name.strip()}".strip()
                df_user = read_user_list()
                if not df_user.empty:
                    df_user["clean_name"] = df_user["氏名"].apply(clean_name)
                    mask = df_user["clean_name"] == clean_name(typed_full)
                    if mask.any():
                        chosen = df_user.loc[mask, "氏名"].iloc[0]

            if chosen:
                st.session_state.clear()
                st.session_state["user_logged_in"] = True
                st.session_state["user_name"] = chosen
                st.success(f"{chosen} さん、ようこそ！")
                st.rerun()
            else:
                st.error("登録されていない利用者です。職員に確認してください。")

    # =========================================================
    # ログイン後
    # =========================================================
    else:
        user_name = st.session_state["user_name"]
        st.sidebar.success(f"✅ ログイン中：{user_name}")
        df_all_users = read_user_list()
        df_local = df.copy()
        df_local["__clean"] = df_local["利用者名"].apply(clean_name)
        df_user_points = df_local[df_local["__clean"] == clean_name(user_name)].drop(columns="__clean", errors="ignore")

        # 💬 最近のありがとう
        if not df_user_points.empty:
            comment_col = "コメント" if "コメント" in df_user_points.columns else (
                "AIからのメッセージ" if "AIからのメッセージ" in df_user_points.columns else None
            )
            if comment_col:
                recent_comment = df_user_points[comment_col].dropna()
                if not recent_comment.empty:
                    last_comment = recent_comment.iloc[-1]
                    st.markdown(
                        f"<div style='background:#e6f2ff;padding:10px;border-radius:8px;'>"
                        f"<h4>💬 最近のありがとう</h4><p>{last_comment}</p></div>",
                        unsafe_allow_html=True
                    )
                    # タイトルとの行間
                    st.markdown("<div style='margin-bottom: 30px;'></div>", unsafe_allow_html=True)

        # 💎 あなたのありがとう履歴（ランキングと同じ形式に統一）
        st.subheader("💎 ウェルサポイント履歴")
        if df_user_points.empty:
            st.info("まだポイント履歴がありません。")
        else:
            df_view = df_user_points[["日付", "項目", "ポイント", "コメント"]].copy()
            df_view.rename(columns={"コメント": "メッセージ"}, inplace=True)
            show_table(df_view.sort_values("日付", ascending=False))

        # 🌱 月ごとのがんばり（ランキングと同じ形式に統一）
        st.subheader("🌱 ウェルサポイント推移")
        if not df_user_points.empty:
            monthly_points = (
                df_user_points.assign(年月=pd.to_datetime(df_user_points["日付"], errors="coerce").dt.to_period("M").astype(str))
                .groupby("年月")["ポイント"].sum()
                .reset_index()
                .sort_values("年月")
            )
            monthly_points["前月比"] = monthly_points["ポイント"].diff()
            monthly_points["バッジ"] = monthly_points["前月比"].apply(
                lambda x: "🏅 成長" if x > 0 else ("💪 がんばろう" if x < 0 else "🟢 維持")
            )
            monthly_points.rename(columns={"年月": "月", "ポイント": "合計ポイント"}, inplace=True)
            show_table(monthly_points)

        # 🏠 施設別ランキング（月ごと）
        st.subheader("🏠 グルホランキング（月ごと）")
        if os.path.exists(USER_FILE) and not df.empty:
            df_all_users = read_user_list()
            df_rank = df.copy()
            df_rank["年月"] = pd.to_datetime(df_rank["日付"], errors="coerce").dt.to_period("M").astype(str)
            month_list = sorted(df_rank["年月"].dropna().unique(), reverse=True)
            if month_list:
                selected_month = st.selectbox("表示する月を選択", month_list, index=0)
                df_month = df_rank[df_rank["年月"] == selected_month]
                merged = pd.merge(
                    df_month, df_all_users[["氏名", "施設"]],
                    left_on="利用者名", right_on="氏名", how="left"
                )

                # 自施設名（ハイライト用）を取得
                user_fac_series = df_all_users.loc[df_all_users["氏名"] == user_name, "施設"]
                user_fac = user_fac_series.iloc[0] if not user_fac_series.empty else None

                # --- 合計ポイント ---
                df_home_total = (
                    merged.groupby("施設", dropna=False)["ポイント"].sum().reset_index()
                    .fillna({"施設": "（未登録）"})
                    .sort_values("ポイント", ascending=False)
                    .reset_index(drop=True)
                )
                df_home_total["順位"] = range(1, len(df_home_total) + 1)
                df_home_total["順位表示"] = df_home_total["順位"].apply(
                    lambda x: "🥇" if x == 1 else "🥈" if x == 2 else "🥉" if x == 3 else str(x)
                )

                def hl_fac_total(row):
                    if user_fac is not None and row["施設"] == user_fac:
                        return ['background-color: #d2e3fc'] * len(row)
                    return [''] * len(row)

                st.markdown("### 🏆 合計ウェルサポイント")
                show_table(
                    df_home_total[["順位表示", "施設", "ポイント"]].style.apply(hl_fac_total, axis=1)
                )

                # --- 1人あたり平均ポイント ---
                df_fac_users = df_all_users.groupby("施設")["氏名"].nunique().reset_index()
                df_fac_users.rename(columns={"氏名": "利用者数"}, inplace=True)

                df_home_avg = pd.merge(df_home_total, df_fac_users, on="施設", how="left")
                df_home_avg["利用者数"] = df_home_avg["利用者数"].fillna(0).astype(int)
                df_home_avg["1人あたりポイント"] = df_home_avg.apply(
                    lambda x: 0 if x["利用者数"] == 0 else round(x["ポイント"] / x["利用者数"], 1),
                    axis=1
                )
                df_home_avg = (
                    df_home_avg.sort_values("1人あたりポイント", ascending=False)
                    .reset_index(drop=True)
                )
                df_home_avg["順位"] = range(1, len(df_home_avg) + 1)
                df_home_avg["順位表示"] = df_home_avg["順位"].apply(
                    lambda x: "🥇" if x == 1 else "🥈" if x == 2 else "🥉" if x == 3 else str(x)
                )

                def hl_fac_avg(row):
                    if user_fac is not None and row["施設"] == user_fac:
                        return ['background-color: #d2e3fc'] * len(row)
                    return [''] * len(row)

                st.markdown("### 🧮 1人あたりウェルサポイント")
                show_table(
                    df_home_avg[["順位表示", "施設", "1人あたりポイント"]].style.apply(hl_fac_avg, axis=1)
                )

            else:
                st.info("月別データがありません。")

        # 👥 月別利用者ランキング（上位10名）
        st.subheader("🏅 月別利用者ランキング")
        if not df.empty:
            df_rank_user = df.copy()
            df_rank_user["年月"] = pd.to_datetime(df_rank_user["日付"], errors="coerce").dt.to_period("M").astype(str)
            month_list_user = sorted(df_rank_user["年月"].dropna().unique(), reverse=True)
            if month_list_user:
                selected_month_user = st.selectbox("ランキング月を選択", month_list_user, index=0)
                df_month_user = df_rank_user[df_rank_user["年月"] == selected_month_user]
                merged_user = pd.merge(
                    df_month_user, df_all_users[["氏名", "施設"]],
                    left_on="利用者名", right_on="氏名", how="left"
                )
                df_user_rank = merged_user.groupby(["利用者名", "施設"], dropna=False)["ポイント"].sum().reset_index()
                df_user_rank = df_user_rank.sort_values("ポイント", ascending=False).head(10).reset_index(drop=True)
                df_user_rank["順位"] = range(1, len(df_user_rank) + 1)
                df_user_rank["順位表示"] = df_user_rank["順位"].apply(
                    lambda x: "🥇" if x == 1 else "🥈" if x == 2 else "🥉" if x == 3 else str(x)
                )

                def hl_user(row):
                    if row["利用者名"] == user_name:
                        return ['background-color: #d2e3fc'] * len(row)
                    return [''] * len(row)

                show_table(
                    df_user_rank[["順位表示", "利用者名", "施設", "ポイント"]].style.apply(hl_user, axis=1)
                )

        # 👑 累計利用者ランキング（上位10名）
        st.subheader("👑 累計利用者ランキング")
        if not df.empty:
            merged_total = pd.merge(
                df, df_all_users[["氏名", "施設"]],
                left_on="利用者名", right_on="氏名", how="left"
            )
            df_total = merged_total.groupby(["利用者名", "施設"])["ポイント"].sum().reset_index()
            df_total = df_total.sort_values("ポイント", ascending=False).head(10).reset_index(drop=True)
            df_total["順位"] = range(1, len(df_total) + 1)
            df_total["順位表示"] = df_total["順位"].apply(
                lambda x: "🥇" if x == 1 else "🥈" if x == 2 else "🥉" if x == 3 else str(x)
            )

            def hl_total(row):
                if row["利用者名"] == user_name:
                    return ['background-color: #d2e3fc'] * len(row)
                return [''] * len(row)

            show_table(
                df_total[["順位表示", "利用者名", "施設", "ポイント"]].style.apply(hl_total, axis=1)
            )

        # 🚪 ログアウト
        st.sidebar.button("🚪 ログアウト", on_click=lambda: (st.session_state.clear(), st.rerun()))

