# reports/ – 생성된 분석 보고서

이 디렉토리는 analyzer 스크립트가 생성한 **정적 보고서(HTML, PDF, 마크다운)**를 저장합니다.

## 목적

- 분석 결과의 영구적 보관
- 팀 내 공유 및 검토
- 대시보드 호스팅을 위한 정적 파일 제공
- 보고서 버전 관리

## 파일 명명 규칙

```
<분석주제>-<타임스탬프>.<확장자>
예시:
  deployment-success-rate-20260418T142345.html
  anomaly-detection-20260418-weekly.pdf
  weekly-summary-2026-W16.md
```

## 보고서 유형

| 확장자 | 내용 | 생성 도구 |
|--------|------|-----------|
| `.html` | 인터랙티브 Plotly/D3 차트 포함 | Plotly, D3.js |
| `.pdf`  | 인쇄용 고정 레이아웃 보고서 | WeasyPrint, Pandoc |
| `.md`   | 간단한 텍스트 요약 | Python, Bash |
| `.json` | 기계 판독용 분석 결과 | 모든 스크립트 |

## 관리 규칙

1. **자동 정리**: 보고서는 30일이 지나면 자동으로 삭제될 수 있습니다(보관 정책에 따름).
2. **버전 유지**: 동일한 주제의 새로운 보고서는 기존 파일을 덮어쓰지 않습니다.
3. **인덱스**: `index.html`을 업데이트하여 최신 보고서 목록을 제공할 수 있습니다.

## 샘플 보고서

- `deployment-success-rate-20260418T142345.html` – 배포 성공률 추이 (Plotly)
- `weekly-summary-2026-W16.md` – 주간 요약 마크다운
- `container-app-response-times.pdf` – 컨테이너 앱 응답 시간 분포

## 보고서 보기

로컬에서 HTML 보고서를 보려면:

```bash
open analyzer/reports/deployment-success-rate-20260418T142345.html
```

또는 Python으로 간단한 HTTP 서버를 실행:

```bash
cd analyzer/reports && python3 -m http.server 8080
```

그런 다음 브라우저에서 `http://localhost:8080`으로 접속합니다.

---

*이 디렉토리는 점진적 도입(시나리오 A)의 일부로 2026‑04‑18에 생성되었습니다.*