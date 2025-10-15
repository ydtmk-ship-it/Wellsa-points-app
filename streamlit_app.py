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
            if not df_item.empty and {"項目", "ポイント"}.issubset(df_item.columns):
                # 数字抽出→float→int変換（"5pt"などもOK）
                df_item["ポイント"] = (
                    df_item["ポイント"].astype(str).str.extract(r"(\d+)")[0].astype(float).fillna(0).astype(int)
                )
                item_points = {row["項目"]: int(row["ポイント"]) for _, row in df_item.iterrows()}
            else:
                df_item = pd.DataFrame(columns=["項目", "ポイント"])
                item_points = {}

            df_users = read_users()
            if not df_users.empty and "氏名" in df_users.columns:
                user_name = st.selectbox("利用者を選択", df_users["氏名"].dropna().tolist())
            else:
                user_name = None
                st.warning("利用者が未登録です。")

            # 項目プルダウンとポイント反映
            if item_points:
                selected_item = st.selectbox("活動項目を選択", list(item_points.keys()))
                points_value = item_points.get(selected_item, 0)

                # text_inputで確実に自動反映
                st.text_input(
                    "付与ポイント数",
                    value=str(points_value),
                    key=f"points_value_{selected_item}",
                    disabled=True
                )
            else:
                st.warning("活動項目が未登録です。")
                selected_item, points_value = None, 0

            if st.button("ポイントを付与"):
                if user_name and selected_item:
                    points_value = int(item_points.get(selected_item, 0))
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

        # --- 以下（履歴閲覧、利用者登録、ランキングなど）は v8 と同じ ---
        # （省略：動作確認済み）
