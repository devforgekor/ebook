# Papertrail 프로젝트 문서

이 디렉토리는 Papertrail 모듈 분해 작업의 상세 문서를 포함합니다.

## 핵심 문서

- [핸드오버 문서](../핸드오버_문서.md) – 프로젝트 구조, 사용법, 향후 작업
- [압축 핸드오버 요약](../압축_핸드오버_요약.md) – 핵심 내용 요약
- [분해 계획](../분해_계획.md) – 모듈 분해 설계 및 단계
- [파일 매핑 테이블](../파일_매핑_테이블.md) – schooldocs → papertrail 파일 매핑
- [이동 분석](../이동_분석.md) – 의존성 분석 및 이동 옵션

## 모듈 API 문서

- [Core 모듈](core-modules.md) – 리소스명 생성, 검증, 설정 유틸리티
- [Infrastructure/Azure 모듈](infrastructure-modules.md) – Azure 배포 및 관리 함수
- [Domain 모듈](domain-modules.md) – 학교 정보 입력, 배포 선택 로직
- [CLI 모듈](cli-modules.md) – 최종 실행 진입점 (Bash/Python)

## 통합 참조

- [Bash/JavaScript 통합 참조](Bash_JavaScript_통합_참조.md) – Bash와 JavaScript 모듈 상호작용 패턴
- [draft/collector/analyzer 검토 보고서](draft_collector_analyzer_검토_보고서.md) – 새로운 디렉토리 구조 도입 검토

## 방법론

- [비전문가 개발자를 위한 AI 기반 모듈형 개발 참고서](../비전문가 개발자를 위한 AI 기반 모듈형 개발 참고서 (Papertrail 프로젝트 최종판).md) – 프로젝트의 근본 원칙과 규칙

## 테스트

- [테스트 실행 스크립트](../run-tests.sh) – Bats 테스트 일괄 실행
- 테스트 파일은 `tests/` 디렉토리에 위치

## CI/CD

- GitHub Actions 워크플로우: `.github/workflows/`
  - [test.yml](../.github/workflows/test.yml) – 자동화된 테스트
  - [deploy.yml](../.github/workflows/deploy.yml) – 수동 배포 (what‑if 모드)

---

*문서 최종 업데이트: 2026‑04‑18*