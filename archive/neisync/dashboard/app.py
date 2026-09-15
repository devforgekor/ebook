import streamlit as st
import requests
import altair as alt

API_BASE = "http://localhost:8000"

st.title("NEISync 대시보드")

st.header("수집/분석/품질 현황")

col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("급식")
    stats = requests.get(f"{API_BASE}/analyze/meal").json()
    st.write(stats)
    quality = requests.get(f"{API_BASE}/quality/meal").json()
    st.write("품질:", quality)
with col2:
    st.subheader("일정")
    stats = requests.get(f"{API_BASE}/analyze/schedule").json()
    st.write(stats)
    quality = requests.get(f"{API_BASE}/quality/schedule").json()
    st.write("품질:", quality)
with col3:
    st.subheader("시간표")
    stats = requests.get(f"{API_BASE}/analyze/timetable").json()
    st.write(stats)
    quality = requests.get(f"{API_BASE}/quality/timetable").json()
    st.write("품질:", quality)

st.header("리포트 다운로드")
st.write("급식/일정/시간표 데이터를 엑셀로 다운로드할 수 있습니다.")
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(f"[급식 엑셀 다운로드]({API_BASE}/export/meal)")
with col2:
    st.markdown(f"[일정 엑셀 다운로드]({API_BASE}/export/schedule)")
with col3:
    st.markdown(f"[시간표 엑셀 다운로드]({API_BASE}/export/timetable)")

st.header("급식 데이터 추이 (최근 30일)")
try:
    import pandas as pd
    import datetime
    # 최근 30일 데이터 집계
    API_BASE = "http://localhost:8000"
    today = datetime.date.today()
    dates = [(today - datetime.timedelta(days=i)).strftime('%Y%m%d') for i in range(29, -1, -1)]
    records = []
    for d in dates:
        resp = requests.get(f"{API_BASE}/status/meal?shard=odd").json()
        records.append({"date": d, "success": resp.get("success", 0), "failed": resp.get("failed", 0)})
    df = pd.DataFrame(records)
    chart = alt.Chart(df).mark_line().encode(
        x='date:T',
        y='success:Q',
        tooltip=['date', 'success', 'failed']
    ).properties(title="급식 수집 성공 건수 (최근 30일)")
    st.altair_chart(chart, use_container_width=True)
except Exception as e:
    st.warning(f"그래프 표시 오류: {e}")
