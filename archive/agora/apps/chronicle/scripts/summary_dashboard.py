"""
summary_dashboard.py
- data/summary/ 폴더의 도메인별 요약 json을 읽어 표와 그래프로 시각화
- Streamlit 기반 대시보드
- 실행: streamlit run apps/chronicle/scripts/summary_dashboard.py
"""
import streamlit as st
import json
from pathlib import Path
import pandas as pd
import datetime



SUMMARY_DIR = Path(__file__).parent.parent.parent / "data/summary"
SUMMARY_HISTORY_DIR = SUMMARY_DIR / "history"
SUMMARY_AGG_DIR = SUMMARY_DIR / "agg"

st.set_page_config(page_title="AGORA 데이터 모니터링 대시보드", layout="wide")

st.title("AGORA 데이터 모니터링 대시보드")

# agg 요약본(연도별) 분석 탭
tab1, tab2 = st.tabs(["월별 상세(raw)", "연도별 집계(agg)"])

with tab2:
    agg_files = list(SUMMARY_AGG_DIR.glob("*.jsonl"))
    if not agg_files:
        st.warning("agg 폴더에 연도별 집계 jsonl 데이터가 없습니다.")
    else:
        agg_years = sorted(set(f.name.split('_')[1].replace('.jsonl','').split('_')[0] for f in agg_files))
        selected_year = st.sidebar.selectbox("agg 연도 선택", agg_years, key="agg_year")
        target_files = sorted([f for f in agg_files if f.name.startswith(f"chronicle_{selected_year}")])
        agg_rows = []
        for f in target_files:
            with open(f, encoding="utf-8") as fin:
                for line in fin:
                    try:
                        agg_rows.append(json.loads(line))
                    except Exception:
                        continue
        if not agg_rows:
            st.warning("해당 연도에 agg 데이터가 없습니다.")
        else:
            # 기간 필터
            dates = sorted({r["date"] for r in agg_rows if "date" in r})
            date_from = st.sidebar.selectbox("agg 시작일", ["전체"] + dates, key="agg_from")
            date_to = st.sidebar.selectbox("agg 종료일", ["전체"] + dates, key="agg_to")
            filtered = agg_rows
            if date_from != "전체":
                filtered = [r for r in filtered if r["date"] >= date_from]
            if date_to != "전체":
                filtered = [r for r in filtered if r["date"] <= date_to]
            st.subheader(f"연도별 agg 통계: {selected_year} ({len(filtered)}일)")
            # 통계
            total_error = sum(r.get("error_count",0) for r in filtered)
            total_status = sum(r.get("status_change_count",0) for r in filtered)
            st.metric("에러 합계", total_error)
            st.metric("비정상 합계", total_status)
            # Top N 에러 메시지
            if filtered and "top_error_msgs" in filtered[0]:
                st.subheader("Top N 에러 메시지")
                top_msgs = filtered[0]["top_error_msgs"]
                if top_msgs:
                    for msg, cnt in top_msgs:
                        st.write(f"{msg} : {cnt}회")
                else:
                    st.write("(에러 없음)")
            # 최다 에러 일자
            if filtered and "max_error_day" in filtered[0]:
                st.subheader("최다 에러 발생 일자")
                maxd = filtered[0]["max_error_day"]
                st.write(f"{maxd['date']} : {maxd['error_count']}건")
            # 일별 에러/비정상 추이 그래프
            df = pd.DataFrame(filtered)
            if not df.empty:
                st.line_chart(df.set_index("date")[ ["error_count", "status_change_count"] ])
            # 상세 테이블
            st.dataframe(df)



# 도메인/월 선택
jsonl_files = list(SUMMARY_HISTORY_DIR.glob("*.jsonl"))
if not jsonl_files:
    st.warning("summary/history 폴더에 월별 jsonl 데이터가 없습니다.")
    st.stop()

domain_months = sorted(set(f.name.split('_')[0] + '_' + f.name.split('_')[1].replace('.jsonl','') for f in jsonl_files))
selected_dm = st.sidebar.selectbox("도메인_월 선택", domain_months)
domain, month = selected_dm.split('_')

# 해당 월의 모든 파일 읽기 (분할된 경우도 포함)
target_files = sorted([f for f in jsonl_files if f.name.startswith(f"{domain}_{month}")])
all_summaries = []
for f in target_files:
    with open(f, encoding="utf-8") as fin:
        for line in fin:
            try:
                all_summaries.append(json.loads(line))
            except Exception:
                continue

if not all_summaries:
    st.warning("해당 월에 summary 데이터가 없습니다.")
    st.stop()

# 날짜별 필터
dates = sorted({s.get("summary_time","")[:10] for s in all_summaries if s.get("summary_time")})
selected_date = st.sidebar.selectbox("날짜(YYYY-MM-DD) 필터", ["전체"] + dates)
filtered = [s for s in all_summaries if selected_date=="전체" or (s.get("summary_time") and s["summary_time"].startswith(selected_date))]

st.header(f"도메인: {domain} | 월: {month}")
st.caption(f"총 {len(filtered)}건 | 날짜: {selected_date}")

# 통계 집계
total_state = sum(len(s.get("state",[])) for s in filtered)
total_status_changes = sum(len(s.get("status_changes",[])) for s in filtered)
total_error_events = sum(len(s.get("error_events",[])) for s in filtered)

col1, col2, col3 = st.columns(3)
col1.metric("상태 변화", total_state)
col2.metric("비정상 상태", total_status_changes)
col3.metric("에러/실패 로그", total_error_events)

# 상세 테이블(비정상 상태/에러)
status_rows = []
error_rows = []
for s in filtered:
    for row in s.get("status_changes", []):
        row = dict(row)
        row["summary_time"] = s.get("summary_time")
        status_rows.append(row)
    for row in s.get("error_events", []):
        row = dict(row)
        row["summary_time"] = s.get("summary_time")
        error_rows.append(row)

if status_rows:
    st.subheader(":red[비정상 상태 상세]")
    st.dataframe(pd.DataFrame(status_rows))

if error_rows:
    st.subheader(":red[에러/실패 로그 상세]")
    st.dataframe(pd.DataFrame(error_rows))

# 검색/필터(키워드)
search_kw = st.sidebar.text_input("키워드 검색(상태/로그/메시지)")
if search_kw:
    filtered_rows = [r for r in status_rows+error_rows if any(search_kw.lower() in str(v).lower() for v in r.values())]
    st.subheader(f"검색 결과({search_kw})")
    st.dataframe(pd.DataFrame(filtered_rows))

st.caption("© 2026 AGORA 데이터 파이프라인 모니터링")

st.caption("© 2026 AGORA 데이터 파이프라인 모니터링")
