import streamlit as st
import pandas as pd
import os
from datetime import date, datetime
from openai import OpenAI

# ===============================
# 基本設定
# ===============================
st.set_page_config(page_title="ウェルサポイント", page_icon="💎", layout="wide")

DATA_FILE = "points_data.csv"     # 付与履歴
USER_FILE = "users.csv"           # 利用者マスタ（姓, 名, 氏名, 施設）
ITEM_FILE = "items.csv"           # 活動項目マスタ（項目, ポイント）
BADGE_FILE = "badges.csv"         # バッジ履歴（年月, 氏名, バッジ, 差分）

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
STAFF_ACCOUNTS = st.secrets["staff_accounts"]        # 例: {"グループホーム": "wellgh|well1001", ...}
ADMIN_ID = st.secrets["admin"]["id"]
ADMIN_PASS = st.secrets["admin"]["password"]

# ===============================
# ユーティリティ
# ===============================
def normalize_name(s: str) -> str:
    return str(s).strip().replace("　", " ").lower()

def ensure_dir_files():
    # CSVの空ファイルを用意（存在しない場合）
    if not os.path.exists(DATA_FILE):
        pd.DataFrame(columns=["日付", "利用者名", "項目", "ポイント", "所属部署", "コメント"]).to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
    if not os.path.exists(USER_FILE):
        pd.DataFrame(columns=["姓", "名", "氏名", "施設"]).to_csv(USER_FILE, index=False, encoding="utf-8-sig")
    if not os.path.exists(ITEM_FILE):
        pd.DataFrame(columns=["項目", "ポイント"]).to_csv(ITEM_FILE, index=False, encoding="utf-8-sig")
    if not os.path.exists(BADGE_FILE):
        pd.DataFrame(columns=["年月", "氏名", "バッジ", "差分"]).to_csv(BADGE_FILE, index=False, encoding="utf-8-sig")

def load_points():
    ensure_dir_files()
    return pd.read_csv(DATA_FILE)

def save_points(df: pd.DataFrame):
    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")

def read_users():
    ensure_dir_files()
    df = pd.read_csv(USER_FILE)
    # 後方互換：氏名しかない古い形式でも動くよう調整
    if "氏名" not in df.columns:
        df["氏名"] = ""
    if "姓" not in df.columns:
        df["姓"] = df["氏名"].apply(lambda x: str(x).split(" ")[0] if isinstance(x, str) and " " in x else "")
    if "名" not in df.columns:
        df["名"] = df["氏名"].apply(lambda x: str(x).split(" ")[1] if isinstance(x, str) and " " in x else "")
    if df["氏名"].isna().any():
        df["氏名"] = (df["姓"].fillna("").astype(str).str.strip() + " " + df["名"].fillna("").astype(str).str.strip()).str.strip()
    if "施設" not in df.columns:
        df["施設"] = ""
    return df

def read_items():
    ensure_dir_files()
    df = pd.read_csv(ITEM_FILE)
    # 数字抽出→int（"5pt", "５ポイント"などもOK）
    if not df.empty and "ポイント" in df.columns:
        df["ポイント"] = df["ポイント"].astype(str).str.extract(r"(\d+)")[0].astype(float).fillna(0).astype(int)
    return df

def load_badges():
    ensure_dir_files()
    return pd.read_csv(BADGE_FILE)

def save_badges(df: pd.DataFrame):
    df.to_csv(BADGE_FILE, index=False, encoding="utf-8-sig")

def month_col(df_points: pd.DataFrame) -> pd.DataFrame:
    df = df_points.copy()
    df["年月"] = pd.to_datetime(df["日付"], errors="coerce").dt.to_period("M").astype(str)
    return df

def current_month_str() -> str:
    today = date.today()
    return f"{today.year}-{today.month:02d}"

def prev_month_str() -> str:
    today = date.today()
    if today.month == 1:
        return f"{today.year-1}-12"
    return f"{today.year}-{today.month-1:02d}"

# ===============================
# AIコメント（履歴学習・ありがとう必須）
# ===============================
def generate_comment(item: str, points: int) -> str:
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

# ===============================
# 成長/がんばろうバッジ 自動付与
# ===============================
def check_and_award_growth_badges(df_points: pd.DataFrame) -> list:
    """
    今月と前月のポイント合計を利用者ごとに比較し、
    今月>前月→🌸成長バッジ、今月<前月→🌧がんばろうバッジ を自動付与。
    すでに同年月・同氏名のレコードが BADGE_FILE にあれば重複付与しない。
    戻り値：今回新規付与されたバッジのリスト（通知用）
    """
    ensure_dir_files()
    if df_points.empty:
        return []

    df_users = read_users()
    dfm = month_col(df_points)
    cm = current_month_str()
    pm = prev_month_str()

    # 月×氏名で集計
    cur = dfm[dfm["年月"] == cm].groupby("利用者名")["ポイント"].sum().reset_index()
    prv = dfm[dfm["年月"] == pm].groupby("利用者名")["ポイント"].sum().reset_index()

    # すべての氏名の集合
    all_names = set(cur["利用者名"].tolist()) | set(prv["利用者名"].tolist())

    # 既存バッジ
    badges = load_badges()
    new_awards = []
    rows = []

    for name in all_names:
        cur_sum = int(cur[cur["利用者名"] == name]["ポイント"].sum()) if name in set(cur["利用者名"]) else 0
        prv_sum = int(prv[prv["利用者名"] == name]["ポイント"].sum()) if name in set(prv["利用者名"]) else 0
        diff = cur_sum - prv_sum
        badge = None
        if diff > 0:
            badge = "🌸成長バッジ"
        elif diff < 0:
            badge = "🌧がんばろうバッジ"

        if badge:
            # 既に同年月・氏名・バッジがあればスキップ
            exists = (
                (not badges.empty) and
                (badges[(badges["年月"] == cm) & (badges["氏名"] == name) & (badges["バッジ"] == badge)].shape[0] > 0)
            )
            if not exists:
                rows.append({"年月": cm, "氏名": name, "バッジ": badge, "差分": diff})
                new_awards.append({"氏名": name, "バッジ": badge, "差分": diff})

    if rows:
        badges = pd.concat([badges, pd.DataFrame(rows)], ignore_index=True)
        save_badges(badges)

    return new_awards

def get_user_badges(name: str) -> pd.DataFrame:
    badges = load_badges()
    if badges.empty:
        return badges
    return badges[badges["氏名"] == name].sort_values(["年月"], ascending=False)

# ===============================
# セッション初期化
# ===============================
if "user_logged_in" not in st.session_state:
    st.session_state["user_logged_in"] = False
if "staff_logged_in" not in st.session_state:
    st.session_state["staff_logged_in"] = False
if "is_admin" not in st.session_state:
    st.session_state["is_admin"] = False

# ===============================
# モード選択
# ===============================
mode = st.sidebar.radio("モードを選択", ["利用者モード", "職員モード"])

# =========================================================
# 職員モード
# =========================================================
if mode == "職員モード":
    st.title("👩‍💼 職員モード")

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

        # 👉 入室時に当月のバッジ判定＆付与（重複はBADGE_FILE側で防止）
        df_points_all = load_points()
        new_awards = check_and_award_growth_badges(df_points_all)

        # 🔔 通知（サイドバー）
        with st.sidebar.expander("🔔 今月のバッジ通知", expanded=True):
            if new_awards:
                for a in new_awards:
                    st.write(f"{a['氏名']} に **{a['バッジ']}** を付与（差分 {a['差分']} pt）")
            else:
                st.caption("今月の新規付与はありません。")

        tabs = ["ポイント付与", "履歴閲覧", "グループホーム別ランキング"]
        if is_admin:
            tabs += ["利用者登録", "活動項目設定"]
        choice = st.sidebar.radio("機能を選択", tabs)

        # --- ポイント付与 ---
        if choice == "ポイント付与":
            st.subheader("💎 ポイント付与")
            df_item = read_items()
            df_users = read_users()
            df_points = load_points()

            # 利用者プルダウン
            if not df_users.empty and "氏名" in df_users.columns:
                user_name = st.selectbox("利用者を選択", df_users["氏名"].dropna().tolist())
            else:
                user_name = None
                st.warning("利用者が未登録です。")

            # 項目＆ポイント
            if not df_item.empty and {"項目", "ポイント"}.issubset(df_item.columns):
                item_points = dict(zip(df_item["項目"], df_item["ポイント"]))
                selected_item = st.selectbox("活動項目を選択", list(item_points.keys()))
                points_value = int(item_points.get(selected_item, 0))
                st.text_input("付与ポイント数", value=str(points_value), disabled=True, key=f"points_{selected_item}")
            else:
                item_points, selected_item, points_value = {}, None, 0
                st.warning("活動項目が未登録です。")

            if st.button("ポイントを付与"):
                if user_name and selected_item:
                    # AIコメント（履歴学習）
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

        # --- 履歴閲覧（✓で削除） ---
        elif choice == "履歴閲覧":
            st.subheader("🗂 ポイント履歴")
            df_points = load_points()
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

        # --- 活動項目設定（管理者） ---
        elif choice == "活動項目設定" and is_admin:
            st.subheader("🧩 活動項目設定")
            with st.form("item_form"):
                item_name = st.text_input("活動項目名")
                point_value = st.number_input("ポイント数", min_value=1, step=1)
                submitted = st.form_submit_button("登録")
            if submitted and item_name:
                df_item = read_items()
                df_item = pd.concat([df_item, pd.DataFrame([{"項目": item_name, "ポイント": int(point_value)}])], ignore_index=True)
                df_item.to_csv(ITEM_FILE, index=False, encoding="utf-8-sig")
                st.success(f"活動項目『{item_name}』（{int(point_value)}pt）を登録しました。")
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

        # --- 利用者登録（姓・名・施設、✓削除） ---
        elif choice == "利用者登録":
            st.subheader("🧍‍♀️ 利用者登録")
            with st.form("user_form"):
                last = st.text_input("姓")
                first = st.text_input("名")
                facility = st.text_input("グループホーム（施設名）")
                submitted = st.form_submit_button("登録")
            if submitted and last and first and facility:
                df_users = read_users()
                full = f"{last.strip()} {first.strip()}"
                df_users = pd.concat(
                    [df_users, pd.DataFrame([{"姓": last.strip(), "名": first.strip(), "氏名": full, "施設": facility.strip()}])],
                    ignore_index=True,
                )
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

        # --- グループホーム別ランキング ---
        elif choice == "グループホーム別ランキング":
            st.subheader("🏠 グループホーム別ポイントランキング（月ごと）")
            df_points = load_points()
            df_users = read_users()
            if df_points.empty:
                st.info("まだポイントデータがありません。")
            elif df_users.empty or "施設" not in df_users.columns:
                st.info("利用者データ（施設含む）がありません。")
            else:
                dfm = month_col(df_points)
                months = sorted(dfm["年月"].unique(), reverse=True)
                m = st.selectbox("表示する月を選択", months, index=0)
                merged = pd.merge(dfm, df_users[["氏名", "施設"]], left_on="利用者名", right_on="氏名", how="left")
                df_month = merged[merged["年月"] == m]
                result = df_month.groupby("施設")["ポイント"].sum().reset_index().sort_values("ポイント", ascending=False)
                result["順位"] = range(1, len(result) + 1)
                st.dataframe(result[["順位", "施設", "ポイント"]], use_container_width=True)

# =========================================================
# 利用者モード
# =========================================================
if mode == "利用者モード":
    st.title("🧍‍♀️ 利用者モード")

    df_users = read_users()
    if not st.session_state["user_logged_in"]:
        col1, col2 = st.columns(2)
        with col1:
            last = st.text_input("姓")
        with col2:
            first = st.text_input("名")

        if st.button("ログイン"):
            full = f"{last.strip()} {first.strip()}"
            if not df_users.empty and "氏名" in df_users.columns and full in df_users["氏名"].values:
                my_fac = df_users.loc[df_users["氏名"] == full, "施設"].iloc[0] if "施設" in df_users.columns else ""
                st.session_state["user_logged_in"] = True
                st.session_state["user_name"] = full
                st.session_state["user_facility"] = my_fac
                st.success("ログインしました！")
                st.rerun()
            else:
                st.error("登録されていません。職員に確認してください。")

    else:
        user_name = st.session_state["user_name"]
        user_fac = st.session_state.get("user_facility", "")
        st.sidebar.success(f"✅ ログイン中：{user_name}（{user_fac}）")

        df_points = load_points()
        st.subheader(f"💎 {user_name} さんのポイント履歴")
        df_user = df_points[df_points["利用者名"] == user_name]
        total = int(df_user["ポイント"].sum()) if not df_user.empty else 0
        st.metric("累計ポイント", f"{total} pt")

        if df_user.empty:
            st.info("まだポイント履歴がありません。")
        else:
            st.dataframe(df_user[["日付", "項目", "ポイント", "コメント"]].sort_values("日付", ascending=False), use_container_width=True)

            # バッジ表示
            st.write("### 🏅 あなたのバッジ")
            my_badges = get_user_badges(user_name)
            if my_badges.empty:
                st.caption("まだ付与されたバッジはありません。")
            else:
                st.dataframe(my_badges[["年月", "バッジ", "差分"]], use_container_width=True)

        # グループホーム別ランキング（自施設⭐）
        st.subheader("🏠 グループホーム別ランキング（月ごと）")
        if not df_points.empty and not df_users.empty:
            dfm = month_col(df_points)
            months = sorted(dfm["年月"].unique(), reverse=True)
            m = st.selectbox("表示する月を選択", months, index=0, key="user_month")
            merged = pd.merge(dfm, df_users[["氏名", "施設"]], left_on="利用者名", right_on="氏名", how="left")
            df_month = merged[merged["年月"] == m]
            result = df_month.groupby("施設")["ポイント"].sum().reset_index().sort_values("ポイント", ascending=False)
            result["順位"] = range(1, len(result) + 1)
            # 自施設に⭐列
            result["⭐"] = result["施設"].apply(lambda x: "⭐" if x == user_fac else "")
            st.dataframe(result[["順位", "施設", "ポイント", "⭐"]], use_container_width=True)

# ===============================
# 共通：サイドバー最下部にログアウト常時表示
# ===============================
st.sidebar.divider()
if st.sidebar.button("🚪 ログアウト"):
    # すべてのログイン状態を解除
    for key in ["staff_logged_in", "is_admin", "user_logged_in"]:
        st.session_state[key] = False
    for key in ["staff_dept", "user_name", "user_facility"]:
        if key in st.session_state:
            st.session_state.pop(key)
    st.success("ログアウトしました。")
    st.rerun()
