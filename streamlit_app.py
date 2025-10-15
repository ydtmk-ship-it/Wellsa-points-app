import streamlit as st
import pandas as pd
from datetime import datetime, date
from openai import OpenAI
import os
import re
import calendar

# ====== OpenAI（Secretsから安全に読み込み）======
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ====== ファイル定義 ======
DATA_FILE = "points_data.csv"
USERS_FILE = "users.csv"

# ====== 初期化 ======
if not os.path.exists(DATA_FILE):
    pd.DataFrame(columns=["日付", "利用者名", "活動内容", "ポイント", "コメント"]).to_csv(
        DATA_FILE, index=False, encoding="utf-8-sig"
    )
if not os.path.exists(USERS_FILE):
    pd.DataFrame(columns=["利用者名", "生年月日"]).to_csv(
        USERS_FILE, index=False, encoding="utf-8-sig"
    )

# ====== 名前正規化 ======
def normalize_name(name: str) -> str:
    """名前の全角・半角・空白を統一"""
    if not isinstance(name, str):
        return ""
    name = name.strip()
    name = re.sub(r"\s+", "", name)
    name = name.replace("　", "")
    return name

# ====== バッジ付与判定（今月の通所日が半分以上）======
def check_attendance_badge(df, user_name):
    """今月の通所日数が月の半分以上ならバッジ付与"""
    today = date.today()
    year, month = today.year, today.month
    days_in_month = calendar.monthrange(year, month)[1]
    half_days = days_in_month // 2

    df["normalized_name"] = df["利用者名"].apply(normalize_name)
    this_month = df[df["日付"].str.startswith(f"{year}-{month:02d}")]
    user_data = this_month[this_month["normalized_name"] == user_name]

    visit_days = user_data["日付"].apply(lambda x: x.split(" ")[0]).nunique()
    if visit_days >= half_days:
        return f"🏅 バッジ獲得！今月 {visit_days} 日通所しました（{half_days} 日以上で達成）"
    else:
        return f"📅 今月 {visit_days} 日通所。あと {half_days - visit_days} 日でバッジ獲得！"

# ====== Streamlit設定 ======
st.set_page_config(page_title="ウェルサポイント", page_icon="🌟", layout="centered")
st.title("🌟 ウェルサポイント")

# ====== モード選択 ======
mode = st.sidebar.radio("モードを選択", ["職員モード", "利用者モード"])
st.sidebar.write("---")

# ====== セッション初期化 ======
if "user_auth" not in st.session_state:
    st.session_state.user_auth = False
if "user_name" not in st.session_state:
    st.session_state.user_name = None

# ---------------------------------------------------
# 職員モード
# ---------------------------------------------------
if mode == "職員モード":
    st.sidebar.header("職員メニュー")
    staff_tab = st.sidebar.radio("機能を選択", ["ポイント付与", "履歴閲覧", "利用者登録"])

    # --- 利用者登録 ---
    if staff_tab == "利用者登録":
        st.subheader("🗂️ 利用者登録（ログイン用の氏名・生年月日）")
        name = st.text_input("利用者名（例：山田太郎 または 山田 太郎）")
        bday = st.date_input("生年月日", value=date(2000, 1, 1), format="YYYY-MM-DD")

        if st.button("➕ 登録/更新"):
            users = pd.read_csv(USERS_FILE)
            bday_str = bday.strftime("%Y-%m-%d")
            norm_name = normalize_name(name)
            users["normalized_name"] = users["利用者名"].apply(normalize_name)
            mask = users["normalized_name"] == norm_name

            if name.strip() == "":
                st.warning("利用者名を入力してください。")
            else:
                if mask.any():
                    users.loc[mask, "生年月日"] = bday_str
                    st.success(f"✅ {name} さんの生年月日を更新しました（{bday_str}）")
                else:
                    users = pd.concat(
                        [users, pd.DataFrame([{"利用者名": name, "生年月日": bday_str}])],
                        ignore_index=True,
                    )
                    st.success(f"✅ {name} さんを登録しました（{bday_str}）")
                users.to_csv(USERS_FILE, index=False, encoding="utf-8-sig")

        st.write("### 現在の登録利用者")
        users = pd.read_csv(USERS_FILE)
        st.dataframe(users, use_container_width=True)

    # --- ポイント付与 ---
    elif staff_tab == "ポイント付与":
        st.subheader("🎯 ポイントを付与する")
        user = st.text_input("利用者名（登録時と同じ表記でもOK）")
        activity = st.text_input("活動内容（例：皿洗い・通所など）")
        point = st.number_input("ポイント数", min_value=1, step=1, value=10)

        if st.button("✨ コメントを自動生成して登録"):
            if not user or not activity:
                st.warning("利用者名と活動内容を入力してください。")
            else:
                prompt = (
                    f"福祉施設の職員として、利用者さんが『{activity}』をしてくれました。"
                    "優しく前向きに褒める短いコメントを日本語で30文字以内で書いてください。"
                )
                try:
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "あなたは思いやりのある福祉職員です。"},
                            {"role": "user", "content": prompt},
                        ],
                    )
                    comment = response.choices[0].message.content.strip()
                except Exception:
                    comment = "ありがとう！とても助かりました。"
                    st.warning("OpenAIコメント生成に失敗したため、定型文を使用しました。")

                df = pd.read_csv(DATA_FILE)
                new_row = {
                    "日付": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "利用者名": normalize_name(user),
                    "活動内容": activity,
                    "ポイント": point,
                    "コメント": comment,
                }
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")

                st.success(f"✅ {user}さんに{point}ptを付与しました！")
                st.info(f"💬 コメント：{comment}")

    # --- 履歴閲覧 ---
    elif staff_tab == "履歴閲覧":
        st.subheader("📊 ポイント履歴（全体）")
        df = pd.read_csv(DATA_FILE)
        if len(df) == 0:
            st.info("まだ記録がありません。")
        else:
            df["normalized_name"] = df["利用者名"].apply(normalize_name)
            user_filter = st.text_input("利用者名で絞り込み")
            if user_filter:
                df = df[
                    df["normalized_name"].str.contains(normalize_name(user_filter), case=False, na=False)
                ]

            total_points = df.groupby("利用者名")["ポイント"].sum().reset_index()
            st.write("### 🧾 利用者別合計ポイント")
            st.dataframe(total_points.sort_values("ポイント", ascending=False), use_container_width=True)

            st.write("### 📋 詳細履歴")
            st.dataframe(df.sort_values("日付", ascending=False), use_container_width=True)

# ---------------------------------------------------
# 利用者モード
# ---------------------------------------------------
else:
    st.subheader("🧍‍♀️ 利用者モード")

    # --- 未ログイン時 ---
    if not st.session_state.user_auth:
        st.info("あなたのページを見るには、氏名と生年月日を入力してください。")
        in_name = st.text_input("お名前（例：山田太郎 または 山田 太郎）")
        in_bday = st.date_input("生年月日", value=date(2000, 1, 1), format="YYYY-MM-DD")

        if st.button("🔐 ログイン"):
            users = pd.read_csv(USERS_FILE)
            bday_str = in_bday.strftime("%Y-%m-%d")
            in_name_norm = normalize_name(in_name)
            users["normalized_name"] = users["利用者名"].apply(normalize_name)
            hit = users[
                (users["normalized_name"] == in_name_norm)
                & (users["生年月日"] == bday_str)
            ]

            if not hit.empty:
                st.session_state.user_auth = True
                st.session_state.user_name = in_name_norm
                st.success(f"✅ ログインしました：{in_name} さん")
                st.rerun()
            else:
                st.error("名前または生年月日が見つかりません。職員に確認してください。")

    # --- ログイン済み時 ---
    else:
        name = st.session_state.user_name
        st.success(f"👋 ようこそ、{name} さん")

        if st.button("🚪 ログアウト"):
            st.session_state.user_auth = False
            st.session_state.user_name = None
            st.rerun()

        df = pd.read_csv(DATA_FILE)
        df["normalized_name"] = df["利用者名"].apply(normalize_name)
        my = df[df["normalized_name"] == name]

        if my.empty:
            st.info("まだポイントの記録がありません。")
        else:
            total = my["ポイント"].sum()
            st.write(f"### 🌟 現在の合計ポイント：{total} pt")

            # バッジ表示
            badge_text = check_attendance_badge(df, name)
            if "🏅" in badge_text:
                st.success(badge_text)
            else:
                st.info(badge_text)

            st.write("### 📖 自分の記録（新しい順）")
            st.dataframe(
                my[["日付", "活動内容", "ポイント", "コメント"]].sort_values("日付", ascending=False),
                use_container_width=True,
            )
