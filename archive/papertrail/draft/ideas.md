# 아이디어 목록

이 파일은 Papertrail 프로젝트에서 고려할 수 있는 향후 기능, 개선점, 실험 아이디어를 자유롭게 기록합니다.

## 데이터 파이프라인

### 1. 실시간 배포 알림
- **개요**: 배포가 실패할 때 Slack/MS Teams로 알림 발송
- **관련 모듈**: `infrastructure/azure/deploy_monitor.sh`, `collector/`
- **우선순위**: 중

### 2. 배포 기록 대시보드
- **개요**: 각 학교별 배포 이력을 시각화하는 내부 대시보드 구축
- **기술 스택**: React + FastAPI + Cosmos DB
- **관련 모듈**: `analyzer/`, `infrastructure/azure/js/cosmos.js`
- **우선순위**: 낮음

### 3. AI 기반 배포 실패 원인 분석
- **개요**: 배포 실패 로그를 GPT-4o에 전달하여 근본 원인 추천
- **관련 모듈**: `infrastructure/azure/js/aiUtils.js`, `analyzer/`
- **우선순위**: 중

## 모듈 개선

### 4. core/validator.sh에 학교 코드 자동 완성
- **개요**: 학교 토큰 입력 시 17개 교육청 코드를 자동 제안
- **방법**: `select_from_list` 함수 확장
- **우선순위**: 높음

### 5. runners/deploy-app.sh에 롤백 기능 추가
- **개요**: 앱 배포 실패 시 이전 리비전으로 자동 롤백
- **관련 모듈**: `infrastructure/azure/containerapps.sh`
- **우선순위**: 중

### 6. Bash 모듈 단위 테스트 자동화
- **개요**: Bats 프레임워크 도입으로 각 모듈의 함수 단위 테스트 작성
- **관련 모듈**: `core/`, `infrastructure/azure/`
- **우선순위**: 높음

## 통합

### 7. schooldocs 프로젝트와 papertrail의 양방향 동기화
- **개요**: papertrail에서 수정된 스크립트를 schooldocs에 자동 반영하는 Git 하위 모듈 구성
- **우선순위**: 낮음

### 8. CI/CD 파이프라인에서 papertrail 모듈 직접 호출
- **개요**: `azure-pipelines.yml`이 `runners/deploy.sh`를 직접 실행하도록 변경
- **우선순위**: 중

## 실험

### 9. Container Apps의 다중 리비전을 이용한 카나리아 배포
- **개요**: 트래픽의 10%만 새 버전에 라우팅하여 위험 감소
- **관련 모듈**: `infrastructure/azure/containerapps.sh`
- **우선순위**: 낮음

### 10. PDF 파싱 성능 비교 (Ghostscript vs pdf-parse)
- **개요**: 두 라이브러리의 속도, 정확도, 메모리 사용량 측정
- **관련 모듈**: `infrastructure/azure/js/pdfUtils.js`
- **우선순위**: 중

---

## 아이디어 추가 방법
1. 새로운 아이디어는 적당한 카테고리 아래에 추가합니다.
2. **개요**, **관련 모듈**, **우선순위** 필드를 채웁니다.
3. 아이디어가 구현되면 상태를 '완료'로 변경하고 결과 링크를 첨부합니다.

## 상태 표기
- [제안] 아직 검토 전
- [검토중] 팀 논의 진행
- [채택] 구현 예정
- [완료] 구현 완료
- [보류] 당장 구현하지 않음

*이 파일은 2026-04-18에 생성되었습니다.*
