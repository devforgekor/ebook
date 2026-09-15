# draft/ – 설계 초안 및 프로토타입

이 디렉토리는 Papertrail 방법론의 **초기 설계 단계**에서 발생하는 문서, 스케치, 프로토타입 스크립트를 보관합니다.

## 목적

- 아키텍처 결정 기록 (Architecture Decision Records)
- 회의록 및 브레인스토밍 결과
- 빠른 검증을 위한 임시 스크립트
- 아이디어 수집 및 우선순위 정리

## 디렉토리 구조

```
draft/
├── architecture/          # 아키텍처 다이어그램, ADR
├── prototypes/           # 실행 가능한 프로토타입 코드
├── meetings/             # 회의록 (YYYY‑MM‑DD‑주제.md)
├── ideas.md              # 자유 형식의 아이디어 목록
└── README.md             # 이 파일
```

## 사용 예시

### 아키텍처 결정 기록 작성
`architecture/2026‑04‑18‑container‑apps‑vs‑functions.md` 파일을 생성하여 기술 선택 이유를 기록합니다.

### 프로토타입 스크립트
`prototypes/deploy‑monitor‑mock.sh`를 작성하여 배포 모니터링 로직을 빠르게 테스트합니다.

### 회의록
`meetings/2026‑04‑18‑weekly‑sync.md`에 논의된 항목과 결론을 정리합니다.

## 규칙

- **임시성**: draft/에 있는 콘텐츠는 검증 후 적절한 모듈(`core/`, `infrastructure/`, `domain/`)로 이동하거나 삭제됩니다.
- **문서화**: 각 파일은 목적과 상태를 명시하는 헤더 주석을 포함해야 합니다.
- **정리**: 주기적으로 오래된 draft를 검토하여 정리합니다.

## 관련 모듈

- **collector/**: draft에서 확정된 데이터 수집 로직이 이동할 대상
- **analyzer/**: draft에서 확정된 분석 로직이 이동할 대상
- **core/**: draft에서 검증된 순수 유틸리티가 이동할 대상

---

*이 디렉토리는 점진적 도입(시나리오 A)의 일부로 2026‑04‑18에 생성되었습니다.*