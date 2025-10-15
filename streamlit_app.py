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

# OpenAI クライアント（コメント生成用）
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Secretsから職員アカウントを取得
STAFF_ACCOUNTS = st.secrets["staff_accounts"]


# ===============================
# 関数
# ===============================

def normalize_name(name: str):
    """名前の全角・半角や空白を統一"""
    return str(name).strip().replace("　", " ").lower()


def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    else:
        return pd.DataFrame(columns=["日付", "利用者名", "項目", "ポイント", "所属部署"])


def save_data(df):
    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")


# ===============================
# サイドバー：モード選択
# ===============================

mode = st.sidebar.radio("モードを選択", ["利用者モード", "職員モード"])

# =========================================================
# 職員モード
# =========================================================
if mode == "職員モード":
    st.title("👩‍💼 職員モード")

    # --- ログイン処理 ---
    if "staff_logged_in" not in st.session_state:
        st.session_state["staff_logged_in"] = False

    if not st.session_state["staff_logged_in"]:
        dept = st.selectbox("部署を選択", list(STAFF_ACCOUNTS.keys()))
        input_id = st.text_input("ログインID", key="staff_id")
        input_pass = st.text_input("パスワード", type="password", key="staff_pass")

        if st.button("ログイン"):
            stored_id, stored_pass = STAFF_ACCOUNTS[dept].split("|")
            if input_id == stored_id and input_pass == stored_pass:
                st.session_state["staff_logged_in"] = True
                st.session_state["staff_dept"] = dept
                st.success(f"{dept} としてログインしました！")
                st.rerun()
            else:
                st.error("IDまたはパスワードが違います。")

    else:
        dept = st.session_state["staff_dept"]
        st.sidebar.success(f"✅ {dept} ログイン中")

        staff_tab = st.sidebar.radio(
            "機能を選択",
            [
                "ポイント付与",
                "履歴閲覧",
                "利用者登録",
                "活動項目設定",
                "ランキング（項目別）",
                "月別ポイントランキング（利用者別）",
                "ポイント推移グラフ"
            ]
        )

        df = load_data()

        # --- ポイント付与 ---
        if staff_tab == "ポイント付与":
            st.subheader("💎 ポイント付与")

            user_name = st.text_input("利用者名を入力")
            selected_item = st.text_input("項目（例：皿洗い・通所日など）")
            points_value = st.number_input("付与ポイント数", min_value=0, step=10)

            if st.button("ポイントを付与"):
                if user_name and selected_item:
                    points = int(points_value)
                    date_today = date.today().strftime("%Y-%m-%d")

                    new_record = {
                        "日付": date_today,
                        "利用者名": user_name,
                        "項目": selected_item,
                        "ポイント": points,
                        "所属部署": dept
                    }

                    df = pd.concat([df, pd.DataFrame([new_record])], ignore_index=True)
                    save_data(df)

                    st.success(f"{user_name} に {points} pt を付与しました！（{dept}）")
                else:
                    st.warning("利用者名と項目を入力してください。")

        # --- 履歴閲覧 ---
        elif staff_tab == "履歴閲覧":
            st.subheader("🗂 ポイント履歴一覧")
            if df.empty:
                st.info("まだデータがありません。")
            else:
                st.dataframe(
                    df.sort_values("日付", ascending=False),
                    use_container_width=True
                )

        # --- ランキング（月別ポイント） ---
        elif staff_tab == "月別ポイントランキング（利用者別）":
            st.subheader("🏆 月別ポイント獲得ランキング（上位10名）")

            if df.empty:
                st.info("まだポイント記録がありません。")
            else:
                df["日付DATE"] = pd.to_datetime(df["日付"], errors="coerce")
                df["年月"] = df["日付DATE"].dt.to_period("M").astype(str)
                months = sorted(df["年月"].dropna().unique(), reverse=True)

                selected_month = st.selectbox("📅 表示する月を選択", months, index=0)
                year, month = map(int, selected_month.split("-"))

                df_month = df[
                    (df["日付DATE"].dt.year == year)
                    & (df["日付DATE"].dt.month == month)
                ]

                if df_month.empty:
                    st.info(f"{selected_month} の記録はありません。")
                else:
                    rank_df = (
                        df_month.groupby("利用者名")["ポイント"].sum().reset_index()
                    ).sort_values("ポイント", ascending=False)
                    rank_df["順位"] = range(1, len(rank_df) + 1)
                    top10 = rank_df.head(10)

                    st.dataframe(top10[["順位", "利用者名", "ポイント"]])
                    st.bar_chart(top10.set_index("利用者名")["ポイント"])

        # --- ポイント推移グラフ ---
        elif staff_tab == "ポイント推移グラフ":
            st.subheader("📈 利用者別ポイント推移グラフ")

            if df.empty:
                st.info("まだポイントデータがありません。")
            else:
                df["日付DATE"] = pd.to_datetime(df["日付"], errors="coerce")
                df["年月"] = df["日付DATE"].dt.to_period("M").astype(str)
                monthly_points = (
                    df.groupby(["利用者名", "年月"])["ポイント"].sum().reset_index()
                )
                users = sorted(monthly_points["利用者名"].unique())
                selected_users = st.multiselect(
                    "表示する利用者を選択", users, default=users[:3]
                )

                if len(selected_users) > 0:
                    chart_df = monthly_points[monthly_points["利用者名"].isin(selected_users)]
                    chart_df = chart_df.pivot(index="年月", columns="利用者名", values="ポイント").fillna(0)
                    st.line_chart(chart_df, use_container_width=True)
                    st.dataframe(chart_df)
                else:
                    st.info("利用者を選択してください。")

        # --- ログアウト ---
        if st.button("🚪 ログアウト"):
            st.session_state["staff_logged_in"] = False
            st.experimental_rerun()


# =========================================================
# 利用者モード
# =========================================================
else:
    st.title("🧍‍♀️ 利用者モード")

    df = load_data()

    name = st.text_input("氏名（フルネーム）を入力してください")
    birth = st.date_input("生年月日を入力してください")

    if st.button("ログイン"):
        if name:
            st.session_state["user_logged_in"] = True
            st.session_state["user_name"] = normalize_name(name)
            st.success(f"{name} さん、こんにちは！")
            st.experimental_rerun()

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
                    df_user[["日付", "項目", "ポイント", "所属部署"]]
                    .sort_values("日付", ascending=False)
                    .reset_index(drop=True),
                    use_container_width=True
                )

                # --- 月別ポイント推移 ---
                st.write("### 📈 月別ポイント推移")
                df_user["日付DATE"] = pd.to_datetime(df_user["日付"], errors="coerce")
                df_user["年月"] = df_user["日付DATE"].dt.to_period("M").astype(str)
                my_monthly = (
                    df_user.groupby("年月")["ポイント"].sum().reset_index().sort_values("年月")
                )
                st.line_chart(my_monthly.set_index("年月")["ポイント"])

                # --- 前月比較バッジ ---
                if len(my_monthly) >= 2:
                    current_month = my_monthly.iloc[-1]
                    prev_month = my_monthly.iloc[-2]
                    diff = current_month["ポイント"] - prev_month["ポイント"]

                    if diff > 0:
                        msg = f"🌟 成長バッジ獲得！ 前月より {diff} pt 増加しました👏"
                        st.success(msg)
                        st.toast(msg, icon="🌟")
                        st.balloons()
                    elif diff < 0:
                        msg = f"💪 がんばろうバッジ！ 前月より {abs(diff)} pt 減少しました。"
                        st.warning(msg)
                        st.toast(msg, icon="💪")
                    else:
                        msg = "📊 前月と同じポイントでした。"
                        st.info(msg)
                        st.toast(msg, icon="📊")
                else:
                    st.caption("※ まだ比較できる前月データがありません。")

        if st.button("🚪 ログアウト"):
            st.session_state["user_logged_in"] = False
            st.experimental_rerun()
