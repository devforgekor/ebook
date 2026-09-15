# collector/ – 데이터 수집 모듈

이 디렉토리는 Papertrail 방법론에서 **외부 시스템으로부터 데이터를 수집하는 스크립트와 유틸리티**를 담습니다.

## 목적

- 배포 환경의 로그, 메트릭, 이벤트 수집
- 학교 데이터베이스, API, 파일 시스템에서의 데이터 추출
- 수집된 데이터의 정규화 및 임시 저장
- 수집 파이프라인의 구성과 모니터링

## 디렉토리 구조

```
collector/
├── scripts/              # 실행 가능한 수집 스크립트 (Bash, Python, Node.js)
├── config/               # 수집 대상별 설정 파일 (YAML, JSON)
├── utils/                # 수집 공통 유틸리티 (예: 인증, 재시도, 포맷 변환)
├── adapters/             # 소스별 어댑터 (Azure, AWS, 로컬 파일, DB)
└── README.md             # 이 파일
```

## 사용 예시

### Azure Monitor 로그 수집
`scripts/log‑collector.sh`는 Azure Log Analytics에서 컨테이너 앱 로그를 쿼리하여 JSON 파일로 저장합니다.

### 학교 데이터베이스 덤프
`scripts/school‑db‑dump.py`는 Cosmos DB의 학교 문서를 주기적으로 백업합니다.

### 파일 시스템 변경 감시
`scripts/file‑watch.sh`는 특정 디렉토리에 새로 업로드된 PDF 파일을 감지하고 analyzer에 전달합니다.

## 규칙

- **의존성**: collector는 `infrastructure/azure/`의 Azure CLI 헬퍼와 `core/`의 유틸리티를 사용할 수 있습니다.
- **출력 형식**: 수집된 데이터는 `collected/` 디렉토리(자동 생성)에 JSON, CSV, 또는 원시 텍스트로 저장합니다.
- **설정 분리**: 수집 대상별 파라미터는 `config/` 아래 YAML 파일로 관리합니다.
- **에러 처리**: 일시적 오류는 재시도, 영구적 오류는 알림 후 중단합니다.

## 관련 모듈

- **infrastructure/azure/** – Azure 리소스 접근을 위한 헬퍼 함수
- **core/** – 로깅, 검증, 설정 로드 유틸리티
- **analyzer/** – collector가 수집한 데이터를 분석하는 모듈

## 통합 흐름

1. collector 스크립트가 주기적으로 또는 이벤트 기반으로 실행됩니다.
2. 수집된 데이터는 `collected/`에 타임스탬프와 소스 정보를 포함해 저장됩니다.
3. analyzer 스크립트는 `collected/`의 파일을 읽어 분석을 수행합니다.
4. 필요시 collector는 직접 analyzer를 호출할 수 있습니다.

---

*이 디렉토리는 점진적 도입(시나리오 A)의 일부로 2026‑04‑18에 생성되었습니다.*