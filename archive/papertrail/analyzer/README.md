# analyzer/ – 데이터 분석 및 보고 모듈

이 디렉토리는 Papertrail 방법론에서 **수집된 데이터를 분석하고 인사이트를 생성하는 스크립트와 보고서**를 담습니다.

## 목적

- 배포 로그, 메트릭, 이벤트의 통계 분석
- 추세 감지 및 이상 탐지
- 자동화된 보고서 생성 (HTML, PDF, 마크다운)
- 시각화 (차트, 대시보드) 제공
- 분석 결과를 도메인 의사결정에 활용

## 디렉토리 구조

```
analyzer/
├── scripts/              # 분석 스크립트 (Python, R, Node.js)
├── reports/              # 생성된 보고서 (정적 HTML/PDF)
├── models/               # 분석 모델 (머신러닝, 통계)
├── visualizations/       # 시각화 스크립트 (Plotly, D3, matplotlib)
└── README.md             # 이 파일
```

## 사용 예시

### 배포 성공률 추이 분석
`scripts/trend‑analysis.py`는 collector가 수집한 로그를 읽어 일별 배포 성공률을 계산하고 선 그래프를 생성합니다.

### 이상 탐지
`scripts/anomaly‑detection.js`는 컨테이너 앱의 응답 시간을 모니터링하여 갑작스러운 지연을 감지하고 알림을 발생시킵니다.

### 주간 보고서 생성
`scripts/weekly‑report.sh`는 지난주 수집된 모든 데이터를 집계하여 `reports/weekly‑YYYY‑MM‑DD.html`을 생성합니다.

## 규칙

- **입력 데이터**: analyzer는 `collector/collected/` 디렉토리의 파일을 기본 입력으로 사용합니다.
- **출력**: 분석 결과는 `reports/` 또는 `visualizations/`에 저장하며, 필요시 `domain/` 모듈에 전달할 수 있습니다.
- **의존성**: analyzer는 `core/` 유틸리티와 `domain/` 비즈니스 규칙을 참조할 수 있습니다.
- **재현성**: 분석 스크립트는 동일한 입력에 대해 항상 동일한 출력을 생성해야 합니다(랜덤 시드 고정).

## 관련 모듈

- **collector/** – 분석할 데이터를 제공합니다.
- **domain/** – 비즈니스 컨텍스트를 제공하여 분석 결과를 해석합니다.
- **core/** – 로깅, 설정 로드, 파일 유틸리티.

## 통합 흐름

1. collector가 데이터를 `collected/`에 저장합니다.
2. analyzer 스크립트는 주기적(크론) 또는 이벤트 기반(파일 감시)으로 실행됩니다.
3. 분석 결과는 `reports/`에 저장되고 필요시 Slack/Teams로 공유됩니다.
4. 보고서는 정적 웹 서버에 호스팅되어 팀이 볼 수 있습니다.

## 예시 워크플로우

```bash
# 1. collector가 로그 수집
./collector/scripts/log-collector.sh

# 2. analyzer가 수집된 로그 분석
python3 analyzer/scripts/trend-analysis.py collected/logs-20260418T142345.json

# 3. 보고서 생성
open analyzer/reports/deployment-success-rate.html
```

---

*이 디렉토리는 점진적 도입(시나리오 A)의 일부로 2026‑04‑18에 생성되었습니다.*