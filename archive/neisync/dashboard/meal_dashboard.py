import streamlit as st
import sqlite3
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="NEIS 급식 대시보드", layout="wide")
st.title("🥗 NEIS 급식 데이터 대시보드")

# DB 파일 선택
st.sidebar.header("DB 파일 선택")
data_dir = Path("data")
db_files = list(data_dir.glob("**/*.db"))
db_path = st.sidebar.selectbox("DB 파일", db_files, format_func=str)

# 날짜/학교 필터
conn = sqlite3.connect(db_path)
df = pd.read_sql_query("SELECT * FROM meal", conn)
conn.close()

if df.empty:
    st.warning("급식 데이터가 없습니다.")
    st.stop()

school_ids = df["school_id"].unique()
dates = df["meal_date"].unique()

school_id = st.sidebar.selectbox("학교 ID", school_ids)
date = st.sidebar.selectbox("날짜", sorted(dates, reverse=True))

filtered = df[(df["school_id"] == school_id) & (df["meal_date"] == date)]

st.subheader(f"학교 {school_id} | 날짜 {date} 급식 정보")
st.dataframe(filtered)

# 통계/시각화
st.subheader("전체 급식 데이터 통계")
st.write(f"총 {len(df)}건, 학교 수: {df['school_id'].nunique()}개, 날짜 수: {df['meal_date'].nunique()}일")
st.bar_chart(df.groupby("meal_date").size())
