# core.utils 모듈

공통 유틸리티 함수 및 데코레이터, 네트워크, 로깅 기능을 제공합니다.

## 파일 구성
- `file_io.py`: JSON/JSONL 파일 입출력, 원자적 쓰기 지원
- `decorators.py`: 실패 알림 데코레이터 등 공통 데코레이터
- `network.py`: Notifier API 등 네트워크 유틸리티
- `logger.py`: JSONL 포맷 공통 로거 설정 함수
- `http_client.py`: HTTP 요청 표준화(재시도, 회로 차단기)
### 5. HTTP 클라이언트 (재시도 + 회로 차단기)
```python
from core.utils.http_client import http_request, CircuitBreaker
cb = CircuitBreaker(fail_max=3, reset_timeout=60)
resp = await http_request(
    "GET", "https://api.example.com/data",
    retries=2, timeout=5.0, circuit_breaker=cb
)
data = resp.json()
```
- `__init__.py`: 패키지 인식용

## 사용 예시

### 1. 파일 입출력
```python
from core.utils.file_io import read_jsonl, append_jsonl
rows = read_jsonl(Path('data.jsonl'))
append_jsonl(Path('data.jsonl'), [{"foo": 1}])
```

### 2. 실패 알림 데코레이터
```python
from core.utils.decorators import notify_on_fail

@notify_on_fail("작업명")
def my_worker():
    ...
```

### 3. Notifier 알림 전송
```python
from core.utils.network import send_alert
await send_alert("메시지", settings=settings)
```

### 4. 공통 로거 설정
```python
from core.utils.logger import setup_logger
logger = setup_logger("myapp", Path("logs/myapp"))
logger.info("로그 메시지")
```
