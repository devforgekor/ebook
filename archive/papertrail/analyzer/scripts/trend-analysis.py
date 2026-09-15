#!/usr/bin/env python3
"""
analyzer/scripts/trend‑analysis.py – 배포 성공률 추이 분석
입력: collector가 수집한 로그 JSON 파일
출력: reports/deployment‑success‑rate.html (Plotly 그래프)
"""

import json
import sys
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.io as pio

# 출력 디렉토리
REPORTS_DIR = Path(__file__).parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

def load_logs(log_path: str) -> pd.DataFrame:
    """JSON 로그 파일을 DataFrame으로 로드"""
    with open(log_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # 예시 형식: 각 레코드에 TimeGenerated, ContainerAppName, Log 필드가 있다고 가정
    df = pd.json_normalize(data)
    # 성공/실패 추출 (실제 로그 형식에 맞게 수정 필요)
    # 여기서는 Log 필드에 "SUCCESS" 또는 "FAIL"이 포함되었다고 가정
    df['success'] = df['Log'].str.contains('SUCCESS', case=False, na=False)
    df['timestamp'] = pd.to_datetime(df['TimeGenerated'])
    return df

def compute_daily_success_rate(df: pd.DataFrame) -> pd.DataFrame:
    """일별 성공률 계산"""
    df['date'] = df['timestamp'].dt.date
    daily = df.groupby('date')['success'].agg(['count', 'sum']).reset_index()
    daily['success_rate'] = daily['sum'] / daily['count']
    return daily

def generate_report(daily_df: pd.DataFrame, output_html: str) -> None:
    """Plotly 선 그래프 생성"""
    fig = px.line(daily_df, x='date', y='success_rate',
                  title='배포 성공률 추이 (일별)',
                  labels={'date': '날짜', 'success_rate': '성공률'},
                  markers=True)
    fig.update_layout(yaxis_tickformat='.0%')
    pio.write_html(fig, output_html)
    print(f"보고서 생성 완료: {output_html}")

def main():
    if len(sys.argv) < 2:
        print("사용법: python trend-analysis.py <로그 JSON 파일>")
        sys.exit(1)
    log_path = Path(sys.argv[1])
    if not log_path.exists():
        print(f"파일을 찾을 수 없습니다: {log_path}")
        sys.exit(1)
    
    # 데이터 로드 및 분석
    df = load_logs(log_path)
    daily = compute_daily_success_rate(df)
    
    # 보고서 생성
    output_file = REPORTS_DIR / f"deployment-success-rate-{log_path.stem}.html"
    generate_report(daily, output_file)
    
    # 콘솔 요약 출력
    print("=== 분석 요약 ===")
    print(f"전체 레코드 수: {len(df)}")
    print(f"성공률: {df['success'].mean():.1%}")
    print(f"분석 기간: {daily['date'].min()} ~ {daily['date'].max()}")
    print(f"최고 성공률: {daily['success_rate'].max():.1%}")

if __name__ == '__main__':
    main()