# streamlit_app.py
import streamlit as st
import pandas as pd
from datetime import datetime
from openai import OpenAI
import os

# ▼ ここにOpenAI APIキーを入れる（安全にするなら環境変数で）
os.environ["OPENAI_API_KEY"] = "sk-xxxxx"  # ←あなたのAPIキーに置き換え
client = OpenAI()

# データ保存用ファイル
DATA_FILE = "points_data.csv"

# 初回起動時にCSVを用意
if not os.path.exists(DATA_FILE):
    df = pd.DataFrame(columns=["日付", "利用者名", "活動内容", "ポイント", "コメント"])
    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")

# Streamlit設定
st.set_page_config(page_title="ポイント管理アプリ", page_icon="⭐", layout="centered")
st.title("🌸 福祉支援ポイント管理アプリ（β）")

st.sidebar.header("職員用メニュー")
staff_name = st.sidebar.text_input("職員名を入力")
st.sidebar.write("---")
view_mode = st.sidebar.radio("表示モードを選択", ["ポイント付与", "履歴閲覧"])

# ---------------------------------------------------------------------
# ポイント付与モード
# ---------------------------------------------------------------------
if view_mode == "ポイント付与":
    st.subheader("🎯 ポイントを付与する")

    user = st.text_input("利用者名")
    activity = st.text_input("活動内容（例：皿洗い・通所・リハパン卒業など）")
    point = st.number_input("ポイント数", min_value=1, step=1, value=10)

    if st.button("✨ コメントを自動生成して登録"):
        if not user or not activity:
            st.warning("利用者名と活動内容を入力してください。")
        else:
            # OpenAIでコメント生成
            prompt = f"福祉施設の職員として、利用者さんが『{activity}』をしてくれました。\
            優しく前向きに褒める短いコメントを日本語で30文字以内で書いてください。"
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "あなたは思いやりのある福祉職員です。"},
                    {"role": "user", "content": prompt}
                ]
            )
            comment = response.choices[0].message.content.strip()

            # CSVに追記
            df = pd.read_csv(DATA_FILE)
            new_row = {
                "日付": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "利用者名": user,
                "活動内容": activity,
                "ポイント": point,
                "コメント": comment
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")

            st.success(f"✅ {user}さんに{point}ptを付与しました！")
            st.info(f"💬 コメント：{comment}")

# ---------------------------------------------------------------------
# 履歴閲覧モード
# ---------------------------------------------------------------------
else:
    st.subheader("📊 ポイント履歴")
    df = pd.read_csv(DATA_FILE)

    if len(df) == 0:
        st.info("まだ記録がありません。")
    else:
        user_filter = st.text_input("利用者名で絞り込み")
        if user_filter:
            df = df[df["利用者名"].str.contains(user_filter, case=False, na=False)]

        total_points = df.groupby("利用者名")["ポイント"].sum().reset_index()
        st.write("### 🧾 利用者別合計ポイント")
        st.dataframe(total_points, use_container_width=True)

        st.write("### 📋 詳細履歴")
        st.dataframe(df.sort_values("日付", ascending=False), use_container_width=True)
