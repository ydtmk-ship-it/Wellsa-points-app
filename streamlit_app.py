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

# OpenAI クライアント
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Secretsから職員・管理者アカウントを取得
STAFF_ACCOUNTS = st.secrets["staff_accounts"]
ADMIN_ID = st.secrets["admin"]["id"]
ADMIN_PASS = st.secrets["admin"]["password"]

# ===============================
# 関数群
# ===============================
def normalize_name(name: str):
    """名前の空白などを統一"""
    return str(name).strip().replace("　", " ").lower()

def load_data():
    """ポイント履歴を読み込み"""
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    else:
        return pd.DataFrame(columns=["日付", "利用者名", "項目", "ポイント", "所属部署", "コメント"])

def save_data(df):
    """ポイント履歴を保存"""
    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")

def generate_comment(item, points):
    """AIが過去コメント傾向を学習し、必ず「ありがとう」を含む短いコメントを生成"""
    try:
        # 過去コメント履歴を取得
        if os.path.exists(DATA_FILE):
            df_hist = pd.read_csv(DATA_FILE)
            df_hist = df_hist[df_hist["項目"] == item]
            if not df_hist.empty:
                recent_comments = " / ".join(df_hist["コメント"].dropna().tail(5).tolist())
                history_summary = f"過去の『{item}』のコメント例: {recent_comments}"
            else:
                history_summary = f"『{item}』にはまだコメント履歴がありません。"
        else:
            history_summary = "コメント履歴はまだありません。"

        prompt = f"""
あなたは障がい者福祉施設の職員です。
以下は過去のコメント傾向です：
{history_summary}

今回は『{item}』という活動に対して{points}ポイントを付与します。
これまでの傾向を踏まえ、やさしいトーンで短い励ましコメントを作ってください。
必ず「ありがとう」という言葉を1回以上含めてください。
30文字以内、日本語、絵文字を1つ入れてください。
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "あなたは温かく励ます福祉職員です。"},
                {"role": "user", "content": prompt}
            ]
        )
        comment = response.choices[0].message.content.strip()
        return comment

    except Exception:
        return "今日もありがとう😊"

# ===============================
# サイドバー
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

    # --- ログイン画面 ---
    if not st.session_state["staff_logged_in"]:
        dept = st.selectbox("部署を選択", list(STAFF_ACCOUNTS.keys()) + ["管理者"])
        input_id = st.text_input("ログインID")
        input_pass = st.text_input("パスワード", type="password")

        if st.button("ログイン"):
            if dept == "管理者":
                if input_id == ADMIN_ID and input_pass == ADMIN_PASS:
                    st.session_state["staff_logged_in"] = True
                    st.session_state["staff_dept"] = "管理者"
                    st.session_state["is_admin"] = True
                    st.success("管理者としてログインしました！")
                    st.rerun()
                else:
                    st.error("管理者IDまたはパスワードが違います。")
            else:
                stored_id, stored_pass = STAFF_ACCOUNTS[dept].split("|")
                if input_id == stored_id and input_pass == stored_pass:
                    st.session_state["staff_logged_in"] = True
                    st.session_state["staff_dept"] = dept
                    st.session_state["is_admin"] = False
                    st.success(f"{dept} としてログインしました！")
                    st.rerun()
                else:
                    st.error("IDまたはパスワードが違います。")

    # --- ログイン後 ---
    else:
        dept = st.session_state["staff_dept"]
        is_admin = st.session_state["is_admin"]
        st.sidebar.success(f"✅ ログイン中：{dept}")

        # 管理者のみ設定画面を表示
        staff_tab_list = [
            "ポイント付与",
            "履歴閲覧",
            "月別ポイントランキング（利用者別）",
            "ポイント推移グラフ"
        ]
        if is_admin:
            staff_tab_list.insert(2, "利用者登録")
            staff_tab_list.insert(3, "活動項目設定")

        staff_tab = st.sidebar.radio("機能を選択", staff_tab_list)
        df = load_data()

        # --- ポイント付与 ---
        if staff_tab == "ポイント付与":
            st.subheader("💎 ポイント付与")

            # 利用者プルダウン
            if os.path.exists(USER_FILE):
                df_user = pd.read_csv(USER_FILE)
                user_list = df_user["氏名"].dropna().tolist() if "氏名" in df_user.columns else []
                user_name = st.selectbox("利用者を選択", user_list)
            else:
                st.warning("利用者が未登録です。『利用者登録』で登録してください。")
                user_name = None

            # 項目プルダウン＋ポイント自動反映
            if os.path.exists(ITEM_FILE):
                df_item = pd.read_csv(ITEM_FILE)
                item_list = df_item["項目"].tolist()
                selected_item = st.selectbox("活動項目を選択", item_list)
                points_value = int(df_item.loc[df_item["項目"] == selected_item, "ポイント"].values[0])
                st.number_input("付与ポイント数", value=points_value, key="auto_point", disabled=True)
            else:
                st.warning("活動項目が未登録です。『活動項目設定』で追加してください。")
                selected_item = None
                points_value = 0

            if st.button("ポイントを付与"):
                if user_name and selected_item:
                    date_today = date.today().strftime("%Y-%m-%d")
                    comment = generate_comment(selected_item, points_value)
                    st.info(f"✨ AIコメント: {comment}")

                    new_record = {
                        "日付": date_today,
                        "利用者名": user_name,
                        "項目": selected_item,
                        "ポイント": points_value,
                        "所属部署": dept,
                        "コメント": comment
                    }
                    df = pd.concat([df, pd.DataFrame([new_record])], ignore_index=True)
                    save_data(df)
                    st.success(f"{user_name} に {points_value} pt を付与しました！（{dept}）")
                else:
                    st.warning("利用者と項目を選択してください。")

        # --- 履歴閲覧（削除機能付き） ---
        elif staff_tab == "履歴閲覧":
            st.subheader("🗂 ポイント履歴一覧")
            if df.empty:
                st.info("まだデータがありません。")
            else:
                st.dataframe(df.sort_values("日付", ascending=False), use_container_width=True)
                delete_index = st.number_input("削除したい行番号（上から0,1,2...）", min_value=0, step=1)
                if st.button("選択行を削除"):
                    if delete_index < len(df):
                        df = df.drop(df.index[int(delete_index)])
                        save_data(df)
                        st.success("選択した履歴を削除しました。")
                        st.rerun()

        # --- 利用者登録（削除機能付き） ---
        elif staff_tab == "利用者登録" and is_admin:
            st.subheader("🧍‍♀️ 利用者登録")

            with st.form("user_register_form"):
                last_name = st.text_input("姓")
                first_name = st.text_input("名")
                memo = st.text_area("メモ（任意）")
                submitted = st.form_submit_button("登録")

            if submitted and last_name and first_name:
                full_name = f"{last_name} {first_name}"
                df_user = pd.read_csv(USER_FILE) if os.path.exists(USER_FILE) else pd.DataFrame(columns=["氏名", "メモ"])
                new_user = {"氏名": full_name, "メモ": memo}
                df_user = pd.concat([df_user, pd.DataFrame([new_user])], ignore_index=True)
                df_user.to_csv(USER_FILE, index=False, encoding="utf-8-sig")
                st.success(f"{full_name} さんを登録しました。")
                st.rerun()

            if os.path.exists(USER_FILE):
                df_user = pd.read_csv(USER_FILE)
                st.dataframe(df_user)
                delete_name = st.selectbox("削除したい利用者を選択", df_user["氏名"])
                if st.button("選択利用者を削除"):
                    df_user = df_user[df_user["氏名"] != delete_name]
                    df_user.to_csv(USER_FILE, index=False, encoding="utf-8-sig")
                    st.success(f"{delete_name} を削除しました。")
                    st.rerun()

        # --- 活動項目設定（編集・削除機能付き） ---
        elif staff_tab == "活動項目設定" and is_admin:
            st.subheader("🛠 活動項目設定")

            with st.form("item_register_form"):
                item_name = st.text_input("活動項目名（例：皿洗い手伝い）")
                point_value = st.number_input("ポイント数", min_value=0, step=10)
                submitted_item = st.form_submit_button("登録")

            if submitted_item and item_name:
                df_item = pd.read_csv(ITEM_FILE) if os.path.exists(ITEM_FILE) else pd.DataFrame(columns=["項目", "ポイント"])
                new_item = {"項目": item_name, "ポイント": point_value}
                df_item = pd.concat([df_item, pd.DataFrame([new_item])], ignore_index=True)
                df_item.to_csv(ITEM_FILE, index=False, encoding="utf-8-sig")
                st.success(f"活動項目『{item_name}』を登録しました。")
                st.rerun()

            if os.path.exists(ITEM_FILE):
                df_item = pd.read_csv(ITEM_FILE)
                st.dataframe(df_item)

                edit_item = st.selectbox("編集する項目を選択", df_item["項目"])
                new_point = st.number_input("新しいポイント数", min_value=0, step=10)
                if st.button("ポイントを更新"):
                    df_item.loc[df_item["項目"] == edit_item, "ポイント"] = new_point
                    df_item.to_csv(ITEM_FILE, index=False, encoding="utf-8-sig")
                    st.success(f"{edit_item} のポイントを {new_point} に更新しました。")
                    st.rerun()

                delete_item = st.selectbox("削除する項目を選択", df_item["項目"], key="del_item")
                if st.button("選択項目を削除"):
                    df_item = df_item[df_item["項目"] != delete_item]
                    df_item.to_csv(ITEM_FILE, index=False, encoding="utf-8-sig")
                    st.success(f"{delete_item} を削除しました。")
                    st.rerun()

        # --- ログアウト ---
        if st.button("🚪 ログアウト"):
            st.session_state["staff_logged_in"] = False
            st.session_state["is_admin"] = False
            st.rerun()

# =========================================================
# 利用者モード（登録者のみログイン可）
# =========================================================
else:
    st.title("🧍‍♀️ 利用者モード")

    df = load_data()

    if not st.session_state.get("user_logged_in"):
        last_name = st.text_input("姓を入力してください")
        first_name = st.text_input("名を入力してください")

        if st.button("ログイン"):
            if last_name and first_name:
                full_name = f"{last_name} {first_name}"
                normalized_input = normalize_name(full_name)

                if os.path.exists(USER_FILE):
                    df_user = pd.read_csv(USER_FILE)
                    registered_names = [normalize_name(n) for n in df_user["氏名"].dropna().tolist()]
                    if normalized_input in registered_names:
                        st.session_state["user_logged_in"] = True
                        st.session_state["user_name"] = normalized_input
                        st.success(f"{full_name} さん、こんにちは！")
                        st.rerun()
                    else:
                        st.error("登録されていない利用者です。職員に確認してください。")
                else:
                    st.error("利用者データがまだ登録されていません。")

    if st.session_state.get("user_logged_in"):
        name = st.session_state["user_name"]
        st.sidebar.success(f"✅ ログイン中：{name}")

        if df.empty:
            st.info("まだポイントデータがありません。")
        else:
            df["normalized_name"] = df["利用者名"].apply(normalize_name)
            df_user = df[df["normalized_name"] == name]

            if df_user.empty:
                st.warning("あなたの記録はまだありません。")
            else:
                st.write("### 💎 あなたのポイント履歴")
                st.dataframe(
                    df_user[["日付", "項目", "ポイント", "所属部署", "コメント"]]
                    .sort_values("日付", ascending=False)
                    .reset_index(drop=True),
                    use_container_width=True
                )

                st.write("### 📈 月別ポイント推移")
                df_user["日付DATE"] = pd.to_datetime(df_user["日付"], errors="coerce")
                df_user["年月"] = df_user["日付DATE"].dt.to_period("M").astype(str)
                my_monthly = df_user.groupby("年月")["ポイント"].sum().reset_index().sort_values("年月")
                st.line_chart(my_monthly.set_index("年月")["ポイント"])

        if st.button("🚪 ログアウト"):
            st.session_state["user_logged_in"] = False
            st.rerun()
