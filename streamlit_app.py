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

def load_points():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=["日付", "利用者名", "項目", "ポイント", "所属部署", "コメント"])

def save_points(df):
    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")

def read_users():
    if os.path.exists(USER_FILE):
        return pd.read_csv(USER_FILE)
    return pd.DataFrame(columns=["氏名", "施設", "メモ"])

def read_items():
    if os.path.exists(ITEM_FILE):
        return pd.read_csv(ITEM_FILE)
    return pd.DataFrame(columns=["項目", "ポイント"])

def read_facilities():
    if os.path.exists(FACILITY_FILE):
        return pd.read_csv(FACILITY_FILE)
    return pd.DataFrame(columns=["施設名"])

def generate_comment(item, points):
    try:
        df_hist = load_points()
        df_hist = df_hist[df_hist["項目"] == item]
        if not df_hist.empty:
            recent_comments = " / ".join(df_hist["コメント"].dropna().tail(5).tolist())
            history_summary = f"過去の『{item}』コメント例: {recent_comments}"
        else:
            history_summary = f"『{item}』にはまだコメント履歴がありません。"

        prompt = f"""
あなたは障がい者福祉施設の職員です。
以下の履歴を踏まえて、今回『{item}』の活動に{points}ポイント付与します。
やさしいトーンで短い励ましコメントを生成。
必ず「ありがとう」を含め、30文字以内、日本語、絵文字1つ。
{history_summary}
"""
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "あなたは温かく励ます福祉職員です。"},
                {"role": "user", "content": prompt}
            ]
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return "今日もありがとう😊"

def month_col(df_points):
    df = df_points.copy()
    df["年月"] = pd.to_datetime(df["日付"], errors="coerce").dt.to_period("M").astype(str)
    return df

def style_highlight_my_fac(df, my_facility):
    def _row_style(row):
        color = "#fff3bf" if row.get("施設") == my_facility else ""
        return [f"background-color: {color}"] * len(row)
    return df.style.apply(_row_style, axis=1)

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

        tabs = ["ポイント付与", "履歴閲覧", "グループホーム別ランキング"]
        if is_admin:
            tabs += ["利用者登録", "活動項目設定", "施設設定"]
        choice = st.sidebar.radio("機能を選択", tabs)

        df_points = load_points()

        # --- ポイント付与 ---
        if choice == "ポイント付与":
            st.subheader("💎 ポイント付与")

            df_item = read_items()
            item_points = {}
            if not df_item.empty and {"項目", "ポイント"}.issubset(df_item.columns):
                df_item["ポイント"] = pd.to_numeric(df_item["ポイント"], errors="coerce").fillna(0).astype(int)
                item_points = {r["項目"]: int(r["ポイント"]) for _, r in df_item.iterrows()}

            df_users = read_users()
            if "氏名" in df_users.columns and not df_users.empty:
                user_name = st.selectbox("利用者を選択", df_users["氏名"].dropna().tolist())
            else:
                user_name = None
                st.warning("利用者が未登録です。『利用者登録』から登録してください。")

            if item_points:
                selected_item = st.selectbox("活動項目を選択", list(item_points.keys()))
                points_value = item_points.get(selected_item, 0)
                st.text_input("付与ポイント数", value=str(points_value), key=f"points_{selected_item}", disabled=True)
            else:
                selected_item, points_value = None, 0
                st.warning("活動項目が未登録です。『活動項目設定』から登録してください。")

            if st.button("ポイントを付与"):
                if user_name and selected_item:
                    points_value = item_points.get(selected_item, 0)
                    comment = generate_comment(selected_item, points_value)
                    new_row = {
                        "日付": date.today().strftime("%Y-%m-%d"),
                        "利用者名": user_name,
                        "項目": selected_item,
                        "ポイント": points_value,
                        "所属部署": dept,
                        "コメント": comment
                    }
                    df_points = pd.concat([df_points, pd.DataFrame([new_row])], ignore_index=True)
                    save_points(df_points)
                    st.success(f"{user_name} に {points_value} pt を付与しました！")
                    st.info(f"AIコメント: {comment}")
                else:
                    st.warning("利用者と項目を選択してください。")

        # --- 履歴閲覧 ---
        elif choice == "履歴閲覧":
            st.subheader("🗂 ポイント履歴")
            if df_points.empty:
                st.info("まだデータがありません。")
            else:
                df_points["削除"] = False
                edited = st.data_editor(df_points, use_container_width=True, key="hist_editor")
                targets = edited[edited["削除"]]
                if st.button("チェックした行を削除"):
                    if not targets.empty:
                        df_points = df_points.drop(targets.index)
                        save_points(df_points)
                        st.success(f"{len(targets)} 件を削除しました。")
                        st.rerun()
                    else:
                        st.warning("削除対象が選ばれていません。")

        # --- 活動項目設定 ---
        elif choice == "活動項目設定" and is_admin:
            st.subheader("🧩 活動項目設定")
            with st.form("item_form"):
                item_name = st.text_input("活動項目名")
                point_value = st.number_input("ポイント数", min_value=1, step=1)
                submitted = st.form_submit_button("登録")
            if submitted and item_name:
                df_item = read_items()
                df_item = pd.concat([df_item, pd.DataFrame([{"項目": item_name, "ポイント": point_value}])], ignore_index=True)
                df_item.to_csv(ITEM_FILE, index=False, encoding="utf-8-sig")
                st.success(f"活動項目『{item_name}』（{point_value}pt）を登録しました。")
                st.rerun()

            df_item = read_items()
            if not df_item.empty:
                df_item["削除"] = False
                edited = st.data_editor(df_item, use_container_width=True, key="items_editor")
                targets = edited[edited["削除"]]
                if st.button("チェックした項目を削除"):
                    df_item = df_item.drop(targets.index)
                    df_item.to_csv(ITEM_FILE, index=False, encoding="utf-8-sig")
                    st.success(f"{len(targets)} 件の活動項目を削除しました。")
                    st.rerun()

        # --- 利用者登録 ---
        elif choice == "利用者登録":
            st.subheader("🧍‍♀️ 利用者登録")
            df_fac = read_facilities()
            facility_list = df_fac["施設名"].tolist() if not df_fac.empty else []
            with st.form("user_form"):
                last = st.text_input("姓")
                first = st.text_input("名")
                facility = st.selectbox("グループホームを選択", facility_list, index=None, placeholder="選択してください")
                memo = st.text_area("メモ（任意）")
                submitted = st.form_submit_button("登録")
            if submitted and last and first and facility:
                full = f"{last} {first}"
                df_users = read_users()
                df_users = pd.concat([df_users, pd.DataFrame([{"氏名": full, "施設": facility, "メモ": memo}])], ignore_index=True)
                df_users.to_csv(USER_FILE, index=False, encoding="utf-8-sig")
                st.success(f"{full}（{facility}）を登録しました。")
                st.rerun()

            df_users = read_users()
            if not df_users.empty:
                df_users["削除"] = False
                edited = st.data_editor(df_users, use_container_width=True, key="users_editor")
                targets = edited[edited["削除"]]
                if st.button("チェックした利用者を削除"):
                    df_users = df_users.drop(targets.index)
                    df_users.to_csv(USER_FILE, index=False, encoding="utf-8-sig")
                    st.success(f"{len(targets)} 名を削除しました。")
                    st.rerun()

        # --- 施設設定 ---
        elif choice == "施設設定" and is_admin:
            st.subheader("🏠 グループホーム設定")
            with st.form("fac_form"):
                fac_name = st.text_input("グループホーム名（例：グループホーム美園）")
                submitted = st.form_submit_button("登録")
            if submitted and fac_name:
                df_fac = read_facilities()
                df_fac = pd.concat([df_fac, pd.DataFrame([{"施設名": fac_name}])], ignore_index=True)
                df_fac.to_csv(FACILITY_FILE, index=False, encoding="utf-8-sig")
                st.success(f"グループホーム『{fac_name}』を登録しました。")
                st.rerun()

            df_fac = read_facilities()
            if not df_fac.empty:
                df_fac["削除"] = False
                edited = st.data_editor(df_fac, use_container_width=True, key="fac_editor")
                targets = edited[edited["削除"]]
                if st.button("チェックしたグループホームを削除"):
                    df_fac = df_fac.drop(targets.index)
                    df_fac.to_csv(FACILITY_FILE, index=False, encoding="utf-8-sig")
                    st.success(f"{len(targets)} 件のグループホームを削除しました。")
                    st.rerun()

        # --- グループホーム別ランキング ---
        elif choice == "グループホーム別ランキング":
            st.subheader("🏠 グループホーム別ポイントランキング（月ごと）")
            df_users = read_users()
            if df_points.empty:
                st.info("まだポイントデータがありません。")
            elif df_users.empty or "施設" not in df_users.columns:
                st.info("利用者データ（施設含む）がありません。")
            else:
                dfm = month_col(df_points)
                months = sorted(dfm["年月"].unique(), reverse=True)
                m = st.selectbox("表示する月を選択", months, index=0)
                mdf = dfm[dfm["年月"] == m]
                merged = pd.merge(mdf, df_users[["氏名", "施設"]], left_on="利用者名", right_on="氏名", how="left")
                home = merged.groupby("施設")["ポイント"].sum().reset_index().sort_values("ポイント", ascending=False)
                home["順位"] = range(1, len(home) + 1)
                st.dataframe(home[["順位", "施設", "ポイント"]], use_container_width=True)

        if st.button("🚪 ログアウト"):
            st.session_state["staff_logged_in"] = False
            st.session_state["is_admin"] = False
            st.rerun()

# =========================================================
# 利用者モード
# =========================================================
else:
    st.title("🧍‍♀️ 利用者モード")
    df_points = load_points()
    df_users = read_users()

    # --- ログイン ---
    if not st.session_state.get("user_logged_in"):
        last = st.text_input("姓を入力してください")
        first = st.text_input("名を入力してください")
        if st.button("ログイン"):
            if last and first:
                full = f"{last} {first}"
                normalized = normalize_name(full)
                if "氏名" in df_users.columns and not df_users.empty:
                    registered = {normalize_name(n): n for n in df_users["氏名"].dropna().tolist()}
                    if normalized in registered:
                        # 施設を取得
                        row = df_users[df_users["氏名"] == registered[normalized]].head(1)
                        my_fac = row["施設"].iloc[0] if "施設" in row.columns and not row.empty else ""
                        st.session_state["user_logged_in"] = True
                        st.session_state["user_name"] = registered[normalized]
                        st.session_state["user_facility"] = my_fac
                        st.success(f"{registered[normalized]} さん、ようこそ！")
                        st.rerun()
                    else:
                        st.error("登録されていない利用者です。職員に確認してください。")
                else:
                    st.error("利用者データがありません。職員に確認してください。")

    # --- マイページ ---
    if st.session_state.get("user_logged_in"):
        my_name = st.session_state["user_name"]
        my_fac = st.session_state.get("user_facility", "")
        st.sidebar.success(f"✅ ログイン中：{my_name}（{my_fac}）")

        if df_points.empty:
            st.info("まだポイント履歴がありません。")
        else:
            # 自分の履歴
            df_points["normalized_name"] = df_points["利用者名"].apply(normalize_name)
            me = df_points[df_points["normalized_name"] == normalize_name(my_name)]

            # 累計 & 履歴
            st.subheader("💎 あなたのポイント履歴")
            total = int(me["ポイント"].sum()) if not me.empty else 0
            st.metric("累計ポイント", f"{total} pt")

            if not me.empty:
                st.dataframe(
                    me[["日付", "項目", "ポイント", "コメント"]].sort_values("日付", ascending=False),
                    use_container_width=True
                )

                # 月別推移
                me_m = month_col(me).groupby("年月")["ポイント"].sum().reset_index().sort_values("年月")
                st.line_chart(me_m.set_index("年月")["ポイント"])

                # 最近のコメント
                st.write("### 📝 最近のコメント（直近5件）")
                recent = me.sort_values("日付", ascending=False).head(5)[["日付", "項目", "コメント"]]
                st.dataframe(recent, use_container_width=True)

            # グループホーム別ランキング（ハイライト付き）
            st.subheader("🏠 グループホーム別ポイントランキング（月ごと）")
            if not df_users.empty and "施設" in df_users.columns:
                dfm = month_col(df_points)
                months = sorted(dfm["年月"].unique(), reverse=True)
                m = st.selectbox("表示する月を選択", months, index=0, key="user_month")
                mdf = dfm[dfm["年月"] == m]
                merged = pd.merge(mdf, df_users[["氏名", "施設"]], left_on="利用者名", right_on="氏名", how="left")
                home = merged.groupby("施設")["ポイント"].sum().reset_index().sort_values("ポイント", ascending=False)
                home["順位"] = range(1, len(home) + 1)
                home = home[["順位", "施設", "ポイント"]]
                # 自施設をハイライト
                styled = style_highlight_my_fac(home, my_fac)
                st.dataframe(styled, use_container_width=True)

        if st.button("🚪 ログアウト"):
            st.session_state["user_logged_in"] = False
            st.rerun()
