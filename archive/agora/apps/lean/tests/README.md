# Lean 앱 테스트 가이드

## 테스트 실행 방법

가상환경 활성화 후 아래 명령어로 전체 테스트를 실행하세요.

```bash
cd apps/lean
pytest
```

## 테스트 목록
- `test_api.py`: FastAPI API 통합 테스트
- `test_token_utils.py`: 토큰 최적화 유틸리티 테스트
- `test_http_client.py`: HTTP 클라이언트(재시도/회로 차단기) 테스트

## 참고
- 외부 API 호출 테스트는 httpbin.org 등 공개 테스트 서버를 사용합니다.
- 테스트는 모두 독립적으로 실행 가능해야 하며, side effect가 없어야 합니다.
