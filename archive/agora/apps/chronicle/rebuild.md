# 🏗️ Agora 프로젝트 현업 수준 종합 설계 문서 (Production-Ready Architecture)

이 문서는 Agora 프로젝트를 확장 가능하고 유지보수성이 뛰어난 현업 스타일의 시스템으로 재구성하는 **최종 설계도**입니다.  
**Core(공용 라이브러리)**, **Notifier(알림 서비스)**, **TelegramBot(사용자 봇)**, **Chronicle(데이터 파이프라인)** 의 4개 주요 영역으로 구성되며, 각 영역은 독립적으로 개발/배포 가능하고 표준화된 통신 방식을 통해 느슨하게 결합됩니다.

---

## 1. 프로젝트 개요 및 철학

- **목표**: 여러 독립적인 앱들이 느슨하게 연결된 시스템 구축  
- **핵심 원칙**:
  - **설정은 환경변수로** (Pydantic Settings, 3-Tier Rule)
  - **로그는 JSONL 형식**으로 통일 (구조화된 로깅)
  - **앱 간 통신은 HTTP API 또는 Redis Queue**로만 연결
  - **공통 기능은 Core 패키지**로 분리 (재사용성)
  - **각 앱은 독립적**으로 실행 가능 (자체 requirements.txt, README)
  - **운영은 PM2**로 통합 관리 (ecosystem.config.js)

---

## 2. 전체 디렉토리 구조

```
agora/
├── core/                               # 공용 모듈 (패키지화 지향)
│   ├── ai/
│   │   ├── gemini.py                   # Gemini API 래퍼
│   │   ├── semantic_cache.py            # FAISS 기반 유사도 캐시
│   │   └── token_utils.py               # 토큰 최적화 유틸리티
│   ├── kernel/
│   │   ├── base_service.py              # 서비스 기본 클래스 (로깅 설정)
│   │   ├── base_config.py               # Pydantic 기반 설정 기본 클래스
│   │   └── logger.py                     # JSONL 로거 설정
│   ├── utils/
│   │   ├── file_io.py                    # 파일 읽기/쓰기 (비동기, 원자적 쓰기)
│   │   ├── encryption.py                  # 암호화/복호화
│   │   ├── network.py                     # HTTP 클라이언트 공통 (Notifier 연동)
│   │   └── decorators.py                  # 공통 데코레이터 (재시도, 알림)
│   └── pyproject.toml                    # (향후) 내부 PyPI 패키지화
│
├── apps/
│   ├── notifier/                         # [서비스 A] 알림 허브 (FastAPI)
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py                  # /v1/notify, /health
│   │   │   └── schemas.py                  # Pydantic 모델
│   │   ├── providers/
│   │   │   ├── __init__.py                 # Provider 동적 로딩
│   │   │   ├── base.py                      # NotificationProvider 추상 클래스
│   │   │   ├── telegram.py                  # TelegramProvider
│   │   │   ├── email.py                     # EmailProvider
│   │   │   └── slack.py                     # (미래) SlackProvider
│   │   ├── core/
│   │   │   ├── security.py                  # API Key 인증
│   │   │   └── logging.py                    # 앱 로깅 설정
│   │   ├── config.py                        # Pydantic Settings
│   │   ├── main.py                           # FastAPI 앱 진입점
│   │   ├── requirements.txt
│   │   └── .env.example
│   │
│   ├── telegrambot/                         # [서비스 B] 사용자 인터랙션 봇
│   │   ├── services/
│   │   │   ├── usage_manager.py              # 사용량 모니터링
│   │   │   ├── conversation.py                # 대화 흐름 관리
│   │   │   └── command_handler.py             # 명령어 처리
│   │   ├── core/
│   │   │   └── bot.py                         # python-telegram-bot 래퍼
│   │   ├── config.py
│   │   ├── main.py                             # 봇 실행 (Polling 방식)
│   │   ├── requirements.txt
│   │   └── .env.example
│   │
│   └── chronicle/                          # [서비스 C] 데이터 ETL 및 동기화
│       ├── services/
│       │   ├── processor.py                  # raw → processed 변환
│       │   ├── sync_manager.py                # Google Drive/OneDrive 동기화
│       │   ├── optimizer.py                    # vacuum, merge, unknown 재분류
│       │   └── analyzer.py                     # unknown 토큰 분석
│       ├── workers/
│       │   ├── realtime_logger.py              # 실시간 raw 수집 데몬
│       │   ├── processor_worker.py             # 주기적 raw 처리
│       │   ├── daily_finalizer.py               # 일배치 (daily snapshot)
│       │   ├── optimizer_worker.py              # 주기적 최적화
│       │   └── onedrive_sync_worker.py          # OneDrive 업로드/정리
│       ├── models/
│       │   ├── turn.py                          # Turn 데이터 모델 (Pydantic)
│       │   └── state.py                          # 상태 관리 모델
│       ├── config.py
│       ├── main.py                              # (선택) CLI 진입점
│       ├── requirements.txt
│       └── .env.example
│
├── data/                                    # 영구 데이터 (앱별 격리)
│   ├── chronicle/
│   │   ├── raw/
│   │   ├── processed/
│   │   ├── refined/
│   │   ├── state/
│   │   └── exchange/                           # 앱 간 파일 교환
│   ├── notifier/
│   │   └── logs/                                 # (선택) API 로그
│   └── telegrambot/
│       ├── usage_count.json
│       └── session_logs/
│
├── logs/                                     # 개발 환경 로그 (각 앱 심볼릭 링크)
├── temp/                                     # 임시 파일
├── ecosystem.config.js                        # PM2 통합 설정
├── .env.example                               # 공통 환경변수 예제
├── .gitignore
├── .stignore
└── README.md
```

---

## 3. Core 패키지 상세

`core/`는 모든 앱이 공통으로 사용하는 순수 비즈니스 로직과 인프라 유틸리티를 모아놓은 곳입니다.  
**핵심 원칙**: `core` 내부 모듈은 특정 앱에 종속되지 않으며, 외부 의존성은 최소화합니다.

### 3.1 `core/ai/gemini.py`
```python
import logging
from google import genai

logger = logging.getLogger(__name__)

class GeminiAgent:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-lite"):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def generate(self, prompt: str) -> str:
        logger.debug(f"GeminiAgent.generate called with prompt: {prompt}")
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt
            )
            return response.text
        except Exception as e:
            logger.error(f"GeminiAgent.generate error: {e}", exc_info=True)
            raise
```

### 3.2 `core/ai/semantic_cache.py` (FAISS 기반 캐시)
```python
import numpy as np
import faiss
import pickle
from pathlib import Path
from sentence_transformers import SentenceTransformer

class SemanticCache:
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2', cache_dir: Path = Path("./cache")):
        self.model = SentenceTransformer(model_name)
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = cache_dir / "index.faiss"
        self.metadata_path = cache_dir / "metadata.pkl"
        self._load_or_create_index()

    def _load_or_create_index(self):
        if self.index_path.exists() and self.metadata_path.exists():
            self.index = faiss.read_index(str(self.index_path))
            with open(self.metadata_path, 'rb') as f:
                self.metadata = pickle.load(f)
        else:
            self.index = faiss.IndexFlatL2(384)  # MiniLM-L6-v2 dimension
            self.metadata = []

    def search(self, query: str, threshold: float = 0.8):
        query_vec = self.model.encode([query])
        distances, indices = self.index.search(query_vec, 1)
        if len(indices[0]) > 0 and distances[0][0] < threshold:
            return self.metadata[indices[0][0]]
        return None

    def add(self, text: str, data):
        vec = self.model.encode([text])
        self.index.add(vec)
        self.metadata.append(data)
        faiss.write_index(self.index, str(self.index_path))
        with open(self.metadata_path, 'wb') as f:
            pickle.dump(self.metadata, f)
```

### 3.3 `core/ai/token_utils.py`
```python
import re
import unicodedata
from typing import List, Dict, Any

def clean_text(text: str) -> str:
    """텍스트 정규화 및 공백 정리"""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize('NFC', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

try:
    import tiktoken
    def count_tokens(messages: List[Dict[str, Any]], model: str = "gpt-3.5-turbo") -> int:
        try:
            enc = tiktoken.encoding_for_model(model)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")
        total = 0
        for msg in messages:
            text = f"{msg.get('role', '')}: {msg.get('content', '')}"
            total += len(enc.encode(text))
        return total
except ImportError:
    def count_tokens(messages: List[Dict[str, Any]], model: str = None) -> int:
        total = 0
        for msg in messages:
            text = f"{msg.get('role', '')}: {msg.get('content', '')}"
            total += len(text.split())
        return total
```

### 3.4 `core/kernel/base_config.py`
```python
from pydantic_settings import BaseSettings
from pathlib import Path
import os

class BaseAppConfig(BaseSettings):
    # 공통 설정
    LOG_LEVEL: str = "INFO"
    LOG_DIR: Path = Path(os.getenv("LOG_DIR", "/var/log/agora"))
    TEMP_DIR: Path = Path(os.getenv("TEMP_DIR", "/var/tmp/agora"))
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "/data/agora"))

    # Notifier 연동
    NOTIFIER_URL: str = "http://localhost:8001"
    NOTIFIER_API_KEY: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
```

### 3.5 `core/kernel/logger.py`
```python
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler

class JSONLFormatter(logging.Formatter):
    def __init__(self, app_name: str):
        super().__init__()
        self.app_name = app_name

    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "app": self.app_name,
            "module": record.module,
            "message": record.getMessage(),
        }
        if hasattr(record, 'extra'):
            log_entry.update(record.extra)
        if record.exc_info:
            log_entry['exc_info'] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)

def setup_logger(name: str, log_dir: Path, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 이미 핸들러가 설정되어 있으면 중복 추가 방지
    if logger.handlers:
        return logger

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "service.jsonl"

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(JSONLFormatter(name))
    logger.addHandler(file_handler)

    # 콘솔 핸들러 (개발/디버그용)
    if level == logging.DEBUG:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(console)

    logger.propagate = False
    return logger
```

### 3.6 `core/kernel/base_service.py`
```python
from core.kernel.logger import setup_logger

class KernelService:
    def __init__(self, name: str, log_dir, temp_dir=None, data_dir=None):
        self.name = name
        self.log_dir = log_dir
        self.temp_dir = temp_dir
        self.data_dir = data_dir
        self.logger = setup_logger(name, log_dir)

    def log(self, level: str, message: str, **extra):
        getattr(self.logger, level)(message, extra=extra)
```

### 3.7 `core/utils/file_io.py`
```python
import json
import tempfile
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """JSONL 파일 읽기"""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def append_jsonl(path: Path, rows: List[Dict[str, Any]]):
    """JSONL 파일에 행 추가"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

def atomic_write_jsonl(path: Path, rows: List[Dict[str, Any]]):
    """원자적 쓰기: 임시 파일에 쓴 후 교체"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', delete=False, dir=path.parent, encoding='utf-8') as tf:
        for row in rows:
            tf.write(json.dumps(row, ensure_ascii=False) + '\n')
        temp_name = tf.name
    os.replace(temp_name, path)  # Unix에서 원자적 교체

def read_json(path: Path, default: Optional[Dict] = None) -> Dict:
    if not path.exists():
        return default or {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default or {}

def write_json(path: Path, data: Dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
```

### 3.8 `core/utils/network.py`
```python
import httpx
from core.config import settings  # 주의: settings는 각 앱에서 주입해야 함
from typing import Optional

async def send_alert(message: str, channel: str = "telegram") -> bool:
    """모든 앱에서 알림을 보낼 때 이 함수를 사용 (Notifier API 호출)"""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{settings.NOTIFIER_URL}/v1/notify",
                json={"text": message, "channel": channel},
                headers={"Authorization": f"Bearer {settings.NOTIFIER_API_KEY}"}
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            # 로깅은 호출한 쪽에서 처리
            return False
```

### 3.9 `core/utils/decorators.py`
```python
import functools
import asyncio
from core.utils import network

def notify_on_fail(task_name: str):
    """워커 함수 실패 시 Notifier로 알림 전송"""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                await network.send_alert(f"🚨 [{task_name}] 실패: {str(e)}")
                raise
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                asyncio.run(network.send_alert(f"🚨 [{task_name}] 실패: {str(e)}"))
                raise
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator
```

---

## 4. 앱별 상세 설계

### 4.1 Notifier 앱 (알림 허브)

#### `apps/notifier/config.py`
```python
from pydantic_settings import BaseSettings
from pathlib import Path

class NotifierSettings(BaseSettings):
    NOTIFIER_API_KEY: str
    NOTIFIER_HOST: str = "127.0.0.1"
    NOTIFIER_PORT: int = 8001

    # Telegram
    TELEGRAM_NOTICE_TOKEN: str
    TELEGRAM_CHAT_ID: str

    # Email (optional)
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 465
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAIL_FROM: str | None = None
    EMAIL_TO: str | None = None

    DEBUG: bool = False
    LOG_DIR: Path = Path("/var/log/agora/notifier")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8"
    }

settings = NotifierSettings()
```

#### `apps/notifier/core/logging.py`
```python
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
from .config import settings

def setup_logging():
    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "api.log"

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=2 * 1024 * 1024,
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    if settings.DEBUG:
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG)
        console.setFormatter(formatter)
        root_logger.addHandler(console)
```

#### `apps/notifier/core/security.py`
```python
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import settings

security = HTTPBearer()

async def verify_api_key(auth: HTTPAuthorizationCredentials = Security(security)):
    if auth.credentials != settings.NOTIFIER_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API Key")
    return auth.credentials
```

#### `apps/notifier/providers/base.py`
```python
from abc import ABC, abstractmethod

class NotificationProvider(ABC):
    @abstractmethod
    async def send(self, text: str) -> bool:
        """알림 전송, 성공 여부 반환"""
        pass
```

#### `apps/notifier/providers/telegram.py`
```python
import logging
from telegram import Bot
from ..core.config import settings
from .base import NotificationProvider

logger = logging.getLogger(__name__)

class TelegramProvider(NotificationProvider):
    def __init__(self):
        self.bot = Bot(token=settings.TELEGRAM_NOTICE_TOKEN)
        self.chat_id = settings.TELEGRAM_CHAT_ID

    async def send(self, text: str) -> bool:
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=text)
            logger.info(f"Telegram message sent to {self.chat_id}")
            return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False
```

#### `apps/notifier/providers/email.py`
```python
import logging
import aiosmtplib
from email.message import EmailMessage
from ..core.config import settings
from .base import NotificationProvider

logger = logging.getLogger(__name__)

class EmailProvider(NotificationProvider):
    async def send(self, text: str) -> bool:
        if not all([
            settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD,
            settings.EMAIL_FROM, settings.EMAIL_TO
        ]):
            logger.error("Email credentials not fully configured")
            return False
        msg = EmailMessage()
        msg["From"] = settings.EMAIL_FROM
        msg["To"] = settings.EMAIL_TO
        msg["Subject"] = "알림"
        msg.set_content(text)
        try:
            send_kwargs = dict(
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
            )
            if settings.SMTP_PORT == 465:
                send_kwargs["use_tls"] = True
            else:
                send_kwargs["start_tls"] = True
            await aiosmtplib.send(msg, **send_kwargs)
            logger.info(f"Email sent to {settings.EMAIL_TO}")
            return True
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False
```

#### `apps/notifier/providers/__init__.py`
```python
from .telegram import TelegramProvider
from .email import EmailProvider

_providers = {
    "telegram": TelegramProvider(),
    "email": EmailProvider(),
}

def get_provider(channel: str):
    return _providers.get(channel)
```

#### `apps/notifier/api/schemas.py`
```python
from pydantic import BaseModel

class NotifyRequest(BaseModel):
    text: str
    channel: str = "telegram"

class HealthResponse(BaseModel):
    status: str
    services: dict
```

#### `apps/notifier/api/routes.py`
```python
from fastapi import APIRouter, HTTPException, Depends
from ..providers import get_provider
from ..core.security import verify_api_key
from .schemas import NotifyRequest

router = APIRouter()

@router.post("/v1/notify")
async def send_notification(
    request: NotifyRequest,
    _=Depends(verify_api_key)
):
    provider = get_provider(request.channel)
    if not provider:
        raise HTTPException(400, f"Unsupported channel: {request.channel}")
    try:
        result = await provider.send(request.text)
        if result:
            return {"status": "ok", "channel": request.channel}
        else:
            return {"status": "fail", "channel": request.channel}
    except Exception as e:
        return {"status": "error", "channel": request.channel, "message": str(e)}

@router.get("/health")
async def health():
    # 간단한 헬스 체크 (향후 DB/Redis 체크 추가 가능)
    return {"status": "ok", "services": {}}
```

#### `apps/notifier/main.py`
```python
from fastapi import FastAPI
from .api.routes import router
from .core.config import settings
from .core.logging import setup_logging

setup_logging()
app = FastAPI(title="Notifier API", version="1.0.0")
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host=settings.NOTIFIER_HOST, port=settings.NOTIFIER_PORT, reload=True)
```

---

### 4.2 TelegramBot 앱 (사용자 봇)

#### `apps/telegrambot/config.py`
```python
from pydantic_settings import BaseSettings
from pathlib import Path
import os

class TelegramBotConfig(BaseSettings):
    TELEGRAM_TOKEN: str | None = None
    TELEGRAM_TEST_TOKEN: str | None = None
    ADMIN_CHAT_ID: str
    GEMINI_KEY: str
    TOTAL_QUOTA: int = 1000
    LOG_LEVEL: str = "WARNING"
    BOT_NAME: str = "mesids_bot"

    # 경로
    LOG_DIR: Path = Path("/var/log/agora/telegrambot")
    TEMP_DIR: Path = Path("/var/tmp/agora/telegrambot")
    DATA_DIR: Path = Path("/data/agora/telegrambot")

    # Notifier 연동
    NOTIFIER_URL: str = "http://localhost:8001"
    NOTIFIER_API_KEY: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }

    def get_token(self, env: str = "development"):
        if env == "production":
            return self.TELEGRAM_TOKEN
        return self.TELEGRAM_TEST_TOKEN or self.TELEGRAM_TOKEN

config = TelegramBotConfig()
```

#### `apps/telegrambot/core/bot.py`
```python
from core.kernel.base_service import KernelService
from telegram import Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import pytz
import datetime
import asyncio

class TelegramBotService(KernelService):
    def __init__(self, name, token, ai_agent, log_dir, temp_dir=None, data_dir=None):
        super().__init__(name, log_dir, temp_dir, data_dir)
        self.token = token
        self.ai_agent = ai_agent
        self.application = Application.builder().token(self.token).build()
        self._register_handlers()

    def _register_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def start(self, update, context):
        await update.message.reply_text(f"안녕하세요! {self.name}입니다. 무엇을 도와드릴까요?")

    async def handle_message(self, update, context):
        user_text = update.message.text
        self.logger.info(f"Received message: {user_text}")

        try:
            response = self.ai_agent.generate(user_text)
            await update.message.reply_text(response)
            self.logger.info(f"Sent response: {response[:100]}")
        except Exception as e:
            self.logger.error(f"Gemini error: {e}", exc_info=True)
            error_msg = "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
            await update.message.reply_text(error_msg)

        # UsageCounter는 별도 서비스로 분리 (서비스 계층에서 호출)
        # await self.usage_counter.increment()

    async def cleanup_temp(self, context):
        if not self.temp_dir or not self.temp_dir.exists():
            return
        now = time.time()
        for f in self.temp_dir.iterdir():
            if f.is_file() and f.stat().st_mtime < now - 86400:
                try:
                    f.unlink()
                except Exception as e:
                    self.logger.error(f"Temp cleanup error: {e}")

    def run(self):
        self.logger.info(f"{self.name} starting...")
        kst = pytz.timezone('Asia/Seoul')
        job_queue = self.application.job_queue
        job_queue.run_daily(self.cleanup_temp, time=datetime.time(hour=0, minute=0, tzinfo=kst))
        self.application.run_polling()

    async def send_message_async(self, chat_id, text):
        await self.application.bot.send_message(chat_id=chat_id, text=text)

    def send_message(self, chat_id, text):
        asyncio.run(self.send_message_async(chat_id, text))
```

#### `apps/telegrambot/services/usage_counter.py`
```python
import json
import asyncio
from datetime import date
from pathlib import Path
import aiofiles
from core.utils import notifier

class UsageCounter:
    def __init__(self, data_dir: Path, admin_chat_id: str, total_quota: int, logger):
        self.data_dir = data_dir
        self.admin_chat_id = admin_chat_id
        self.total_quota = total_quota
        self.logger = logger
        self.usage_file = data_dir / 'usage_count.json'
        self.notify_file = data_dir / 'notified.json'
        self._lock = asyncio.Lock()

    async def _read_usage(self):
        today = str(date.today())
        if self.usage_file.exists():
            try:
                async with aiofiles.open(self.usage_file, 'r') as f:
                    data = json.loads(await f.read())
                    if data.get('date') == today:
                        return data.get('count', 0)
            except Exception as e:
                self.logger.error(f"UsageCounter read error: {e}")
        return 0

    async def _write_usage(self, count):
        today = str(date.today())
        try:
            async with aiofiles.open(self.usage_file, 'w') as f:
                await f.write(json.dumps({'date': today, 'count': count}))
        except Exception as e:
            self.logger.error(f"UsageCounter write error: {e}")

    async def _has_notified(self, threshold):
        today = str(date.today())
        if self.notify_file.exists():
            try:
                async with aiofiles.open(self.notify_file, 'r') as f:
                    data = json.loads(await f.read())
                    if data.get('date') == today:
                        return threshold in data.get('notified', [])
            except Exception:
                pass
        return False

    async def _mark_notified(self, threshold):
        today = str(date.today())
        async with self._lock:
            try:
                if self.notify_file.exists():
                    async with aiofiles.open(self.notify_file, 'r') as f:
                        data = json.loads(await f.read())
                else:
                    data = {}
                if data.get('date') != today:
                    data = {'date': today, 'notified': []}
                if threshold not in data['notified']:
                    data['notified'].append(threshold)
                    async with aiofiles.open(self.notify_file, 'w') as f:
                        await f.write(json.dumps(data))
            except Exception as e:
                self.logger.error(f"Mark notified error: {e}")

    async def increment(self):
        async with self._lock:
            try:
                current = await self._read_usage()
                new_count = current + 1
                await self._write_usage(new_count)
                self.logger.info(f"Usage count updated: {new_count}")

                percent_left = ((self.total_quota - new_count) / self.total_quota) * 100
                thresholds = [50, 20, 10]
                for th in thresholds:
                    if percent_left <= th and not await self._has_notified(th):
                        msg = f"⚠️ Gemini API 사용량 경고: {th}% 미만 남음 (현재 {new_count}/{self.total_quota} 사용)"
                        self.logger.warning(msg)
                        await notifier.send_alert(msg)
                        await self._mark_notified(th)

                if new_count >= self.total_quota and not await self._has_notified('exceeded'):
                    msg = f"❌ Gemini API 일일 사용량 초과! ({new_count}/{self.total_quota})"
                    self.logger.error(msg)
                    await notifier.send_alert(msg)
                    await self._mark_notified('exceeded')

                return new_count
            except Exception as e:
                self.logger.error(f"UsageCounter.increment error: {e}", exc_info=True)
                return None
```

#### `apps/telegrambot/main.py`
```python
import sys
import logging
from core.ai.gemini import GeminiAgent
from core.kernel.agents.manager import get_ai_agent
from .config import config
from .core.bot import TelegramBotService

logger = logging.getLogger("telegrambot")

if __name__ == "__main__":
    # AI 에이전트 생성
    ai_agent = get_ai_agent("gemini", config.GEMINI_KEY)

    # 토큰 선택 (환경변수 ENV=production 등으로 구분 가능)
    env = os.getenv("ENV", "development")
    token = config.get_token(env)
    if not token:
        logger.error("토큰이 설정되지 않았습니다.")
        sys.exit(1)

    bot = TelegramBotService(
        name=config.BOT_NAME,
        token=token,
        ai_agent=ai_agent,
        log_dir=config.LOG_DIR,
        temp_dir=config.TEMP_DIR,
        data_dir=config.DATA_DIR
    )

    # CLI 전송 모드 (--send)
    if len(sys.argv) > 2 and sys.argv[1] == "--send":
        msg = sys.argv[2]
        chat_id = config.ADMIN_CHAT_ID
        asyncio.run(bot.send_message_async(chat_id, msg))
        sys.exit(0)

    bot.run()
```

---

### 4.3 Chronicle 앱 (데이터 파이프라인)

#### `apps/chronicle/models/turn.py` (Pydantic 모델)
```python
from pydantic import BaseModel
from typing import List, Optional

class Turn(BaseModel):
    session_id: str
    turn_index: int
    timestamp: Optional[str] = None
    user_ko: str
    assistant_ko: str
    tool_ids: List[str] = []
    file_refs: List[str] = []
```

#### `apps/chronicle/services/processor.py`
```python
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict

from core.utils.file_io import read_jsonl, append_jsonl, read_json, write_json
from core.utils.token_utils import clean_text, count_tokens
from ..models.turn import Turn

SYSTEM_PROMPT = "You are a helpful and concise assistant."

def extract_turns_from_rows(rows: List[Dict], fallback_session_id="unknown") -> List[Turn]:
    turns = []
    for idx, row in enumerate(rows):
        v = row.get("v", {}) if isinstance(row, dict) else {}
        session_id = v.get("sessionId", fallback_session_id)
        requests = v.get("requests", [])
        for req in requests:
            user = req.get("message", [{}])[0].get("text", "")
            assistant = req.get("response", [{}])[0].get("text", "")
            timestamp = str(req.get("timestamp", ""))
            turns.append(Turn(
                session_id=session_id,
                turn_index=idx,
                timestamp=timestamp,
                user_ko=user,
                assistant_ko=assistant,
                tool_ids=[],
                file_refs=[]
            ))
    return turns

def parse_raw_snapshot(path: Path) -> List[Turn]:
    try:
        payload = read_json(path, default={})
    except Exception:
        return []
    files = payload.get("files", [])
    if not isinstance(files, list):
        return []
    turns = []
    for item in files:
        if not isinstance(item, dict):
            continue
        rel = item.get("relative_path", "unknown")
        content = item.get("content", "")
        rows = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except:
                continue
        fallback = Path(rel).stem
        turns.extend(extract_turns_from_rows(rows, fallback_session_id=fallback))
    return turns

def split_by_time_gap(turns_list: List[Dict[str, Any]], max_gap: int = 10) -> List[List[Dict[str, Any]]]:
    if not turns_list:
        return []
    # turn_index 순으로 정렬
    turns_list.sort(key=lambda x: (int(x.get("turn_index") or 0), x.get("timestamp") or ""))
    sectors = []
    current = [turns_list[0]]

    def parse_ts(ts):
        if not ts: return 0
        try:
            if 'T' in ts:
                return datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
            return float(ts)
        except:
            return 0

    for i in range(1, len(turns_list)):
        prev_ts = parse_ts(turns_list[i-1].get("timestamp"))
        curr_ts = parse_ts(turns_list[i].get("timestamp"))
        if curr_ts - prev_ts > max_gap and prev_ts > 0 and curr_ts > 0:
            sectors.append(current)
            current = [turns_list[i]]
        else:
            current.append(turns_list[i])
    if current:
        sectors.append(current)
    return sectors

def process_raw_turns(turns: List[Turn], output_dir: Path, seen_hashes_path: Path) -> Dict[str, Any]:
    now_iso = datetime.now().astimezone().isoformat()
    # session별 그룹화
    sessions = defaultdict(list)
    for t in turns:
        sessions[t.session_id].append(t.dict())

    new_output_rows = []
    new_hashes = []
    seen_hashes = set()
    if seen_hashes_path.exists():
        with seen_hashes_path.open("r") as f:
            seen_hashes = set(line.strip() for line in f if line.strip())

    for session_id, session_turns in sessions.items():
        sectors = split_by_time_gap(session_turns)
        for sector_idx, sector in enumerate(sectors):
            messages = []
            if SYSTEM_PROMPT:
                messages.append({"role": "system", "content": SYSTEM_PROMPT})
            for turn in sector:
                if turn.get("user_ko"):
                    messages.append({"role": "user", "content": clean_text(turn["user_ko"])})
                if turn.get("assistant_ko"):
                    messages.append({"role": "assistant", "content": clean_text(turn["assistant_ko"])})
            if not messages:
                continue
            msg_json = json.dumps(messages, sort_keys=True)
            dedup_hash = hashlib.sha256(msg_json.encode()).hexdigest()
            if dedup_hash in seen_hashes:
                continue
            seen_hashes.add(dedup_hash)
            new_hashes.append(dedup_hash)

            # sector timestamp 추출 (첫 번째 turn의 timestamp)
            sector_timestamp = next((t["timestamp"] for t in sector if t.get("timestamp")), None)

            output_obj = {
                "messages": messages,
                "timestamp": sector_timestamp,
                "created_at": now_iso,
                "metadata": {
                    "session_id": session_id,
                    "sector_idx": sector_idx,
                    "turn_count": len(sector),
                    "token_count": count_tokens(messages),
                    "dedup_hash": dedup_hash,
                }
            }
            new_output_rows.append(output_obj)

    # 파일에 추가
    out_path = output_dir / "chat_ko_review.jsonl"
    append_jsonl(out_path, new_output_rows)
    # seen hashes 저장
    with seen_hashes_path.open("a") as f:
        for h in new_hashes:
            f.write(h + "\n")

    return {
        "new_sectors": len(new_output_rows),
        "new_hashes": len(new_hashes),
        "output_file": str(out_path),
    }
```

#### `apps/chronicle/workers/processor_worker.py`
```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "core"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.utils.file_io import read_json, write_json
from core.kernel.logger import setup_logger
from ..config import settings
from ..services.processor import parse_raw_snapshot, process_raw_turns

logger = setup_logger("processor_worker", settings.LOG_DIR)

def main():
    raw_dir = settings.RAW_DIR
    processed_dir = settings.PROCESSED_DIR
    state_file = settings.STATE_DIR / "raw_process_state.json"

    if not raw_dir.exists():
        logger.error(f"Raw directory not found: {raw_dir}")
        return 1

    state = read_json(state_file, default={"processed": {}})
    processed_map = state["processed"]

    raw_files = sorted(raw_dir.glob("raw_*.json"))
    raw_paths = {str(p) for p in raw_files}

    all_turns = []
    new_count = 0

    for raw_file in raw_files:
        stat = raw_file.stat()
        key = str(raw_file)
        marker = f"{stat.st_mtime}:{stat.st_size}"
        if processed_map.get(key, {}).get("marker") == marker:
            continue
        turns = parse_raw_snapshot(raw_file)
        if turns:
            all_turns.extend(turns)
            processed_map[key] = {
                "marker": marker,
                "processed_at": datetime.now().astimezone().isoformat(),
            }
            new_count += 1

    # stale entries cleanup
    for k in list(processed_map.keys()):
        if k not in raw_paths:
            del processed_map[k]

    if all_turns:
        seen_hashes_path = settings.PROCESSED_DIR / ".seen_hashes.jsonl"
        result = process_raw_turns(all_turns, settings.PROCESSED_DIR, seen_hashes_path)
        logger.info(f"Processed {new_count} raw files, {result['new_sectors']} new sectors, {result['new_hashes']} new hashes")
    else:
        logger.info("No new raw files to process")

    write_json(state_file, state)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

#### `apps/chronicle/workers/realtime_logger.py` (축약)
```python
#!/usr/bin/env python3
import time
import signal
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
# ... (생략) 실시간 파일 감지 및 스냅샷 저장 로직
```

#### `apps/chronicle/workers/daily_finalizer.py`
```python
#!/usr/bin/env python3
import sys
from datetime import datetime
from core.utils.file_io import read_jsonl, write_jsonl, write_json
from ..config import settings

def main():
    today = datetime.now().date().isoformat()
    input_file = settings.PROCESSED_DIR / "chat_ko_review.jsonl"
    daily_dir = settings.PROCESSED_DIR / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    output_file = daily_dir / f"chat_ko_review_{today}.jsonl"
    meta_file = daily_dir / f"chat_daily_{today}.json"

    rows = read_jsonl(input_file)
    # 오늘 날짜에 해당하는 행만 필터링 (timestamp 기준)
    filtered = [r for r in rows if r.get("timestamp", "").startswith(today)]
    write_jsonl(output_file, filtered)

    meta = {
        "date": today,
        "count": len(filtered),
        "generated_at": datetime.now().isoformat()
    }
    write_json(meta_file, meta)
    print(f"Daily snapshot saved: {output_file} ({len(filtered)} rows)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

#### `apps/chronicle/workers/optimizer_worker.py`
```python
#!/usr/bin/env python3
import sys
from ..services.optimizer import vacuum, merge_files, retry_unknown
from ..config import settings
from core.kernel.logger import setup_logger

logger = setup_logger("optimizer_worker", settings.LOG_DIR)

def main():
    # 예: 전체 파일 merge 후 vacuum
    title_list = settings.TITLE_LIST  # config에 추가 필요
    for title in title_list:
        merged = merge_files(title)
        cleaned = vacuum(merged)
        save_jsonl(title, cleaned)  # save_jsonl 함수 필요
        logger.info(f"Optimized {title}: {len(cleaned)} rows")
    # unknown retry
    unknown_data = retry_unknown(merge_files("unknown"), title_list)
    for obj in unknown_data[:5]:
        # Notifier로 전송
        from core.utils.network import send_alert
        send_alert(f"[unknown] {obj.get('user', '')[:50]}...")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

---

## 5. 앱 간 통신 방식

### 5.1 HTTP API (Notifier)
- **용도**: 동기적 알림 전송 (즉시 전송 필요 시)
- **인증**: Bearer Token (`NOTIFIER_API_KEY`)
- **호출 예**:
  ```python
  from core.utils.network import send_alert
  await send_alert("중요 알림", channel="telegram")
  ```

### 5.2 Redis Queue (비동기 작업)
- **용도**: 장기 실행 작업, 실패 시 재시도, 이벤트 기반 처리
- **구성**:
  - `telegram:queue` : Notifier 컨슈머가 메시지 소비
  - `chronicle:process` : 데이터 처리 요청
- **미래 확장**: 현재는 HTTP 동기 방식이지만, 필요 시 Redis로 전환

### 5.3 파일 교환 (`data/exchange/`)
- **용도**: 대용량 데이터 교환 (예: lean → chronicle)
- **규칙**:
  - 파일명: `{source}_to_{target}_{timestamp}.json`
  - 교환 완료 시 Redis에 알림 발행 (예: `exchange:new`)
  - 읽은 파일은 처리 후 백업 또는 삭제

---

## 6. 설정 관리 (Pydantic Settings + 계층화)

- **우선순위**: 시스템 환경변수 > `.env` 파일 > 기본값
- **각 앱의 `config.py`**는 `core.kernel.base_config.BaseAppConfig`를 상속받아 확장
- **운영 환경**: `.env` 파일을 두지 않고 시스템 환경변수로 직접 주입 (예: PM2의 `env` 섹션)

**예: TelegramBot 설정 상속**
```python
from core.kernel.base_config import BaseAppConfig

class TelegramBotConfig(BaseAppConfig):
    TELEGRAM_TOKEN: str | None = None
    TELEGRAM_TEST_TOKEN: str | None = None
    ...
```

---

## 7. 로깅 및 모니터링

### 7.1 JSONL 로깅
- 모든 앱은 `core.kernel.logger.setup_logger`를 사용하여 `service.jsonl`에 JSON 형식으로 로그 기록
- 로그 예시:
  ```json
  {"timestamp": "2026-03-20T10:00:00Z", "level": "INFO", "app": "telegrambot", "module": "bot", "message": "Bot started"}
  ```

### 7.2 로그 로테이션 (logrotate)
`/etc/logrotate.d/agora`:
```
/var/log/agora/*/service.jsonl {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 agora agora
    sharedscripts
}
```

### 7.3 헬스 체크 엔드포인트
- HTTP 앱(Notifier)은 `/health` 엔드포인트 제공
- 워커는 `data/state/`에 마지막 실행 시간 기록 (예: `last_heartbeat`)

---

## 8. 운영 관리 (PM2 Ecosystem)

`ecosystem.config.js` (전체 통합 관리)
```javascript
const commonEnv = {
  NODE_ENV: 'production',
  NOTIFIER_URL: 'http://localhost:8001',
  NOTIFIER_API_KEY: process.env.NOTIFIER_API_KEY,
  REDIS_URL: process.env.REDIS_URL || 'redis://localhost:6379'
};

module.exports = {
  apps: [
    {
      name: 'notifier-api',
      script: './apps/notifier/main.py',
      interpreter: 'python3',
      cwd: './apps/notifier',
      env: {
        ...commonEnv,
        PORT: 8001,
        LOG_DIR: '/var/log/agora/notifier',
        TEMP_DIR: '/var/tmp/agora/notifier',
        DATA_DIR: '/data/agora/notifier'
      },
      instances: 2,
      exec_mode: 'fork',
      max_memory_restart: '300M',
      error_file: '/dev/null',
      out_file: '/dev/null'
    },
    {
      name: 'telegram-bot',
      script: './apps/telegrambot/main.py',
      interpreter: 'python3',
      cwd: './apps/telegrambot',
      env: { ...commonEnv },
      instances: 1,
      max_memory_restart: '200M',
      watch: false,
      autorestart: true
    },
    {
      name: 'chronicle-realtime',
      script: './apps/chronicle/workers/realtime_logger.py',
      interpreter: 'python3',
      cwd: './apps/chronicle',
      env: { ...commonEnv },
      watch: false,
      autorestart: true
    },
    {
      name: 'chronicle-processor',
      script: './apps/chronicle/workers/processor_worker.py',
      interpreter: 'python3',
      cwd: './apps/chronicle',
      cron_restart: '*/5 * * * *',
      autorestart: false,
      watch: false
    },
    {
      name: 'chronicle-daily',
      script: './apps/chronicle/workers/daily_finalizer.py',
      interpreter: 'python3',
      cwd: './apps/chronicle',
      cron_restart: '0 2 * * *',
      autorestart: false,
      watch: false
    },
    {
      name: 'chronicle-optimizer',
      script: './apps/chronicle/workers/optimizer_worker.py',
      interpreter: 'python3',
      cwd: './apps/chronicle',
      cron_restart: '0 3 * * *',
      autorestart: false,
      watch: false
    }
  ]
};
```

**실행 명령어**:
- 개발: `pm2 start ecosystem.config.js`
- 운영: `NOTIFIER_API_KEY=xxx pm2 start ecosystem.config.js --env production`

---

## 9. 보안 체크리스트

- [ ] 모든 민감 정보(토큰, API 키)는 환경변수로만 전달. `.env` 파일 Git에 커밋 금지.
- [ ] 운영 서버에서는 `.env` 파일을 사용하지 않고 시스템 환경변수로 관리.
- [ ] 디렉토리 권한: `data/`, `logs/`는 `750`, 파일은 `640`, 소유자는 서비스 계정(예: `agora`).
- [ ] Redis는 `bind 127.0.0.1`, `requirepass` 설정, 방화벽 차단.
- [ ] API 인증: Notifier는 Bearer Token 필수.
- [ ] 로그 마스킹: 민감 정보(토큰)는 로그에서 `***` 처리.

---

## 10. 단계별 마이그레이션 계획

### Phase 1: Core 패키지 구축 (1~2주)
- `core/` 디렉토리 생성 및 공통 유틸 이전 (`file_io`, `token_utils`, `logger`, `base_config`, `decorators`)
- 기존 스크립트에서 `import core.xxx`로 변경

### Phase 2: Notifier 서비스 분리 (1주)
- `apps/notifier/` 구조 생성, FastAPI 구현
- 기존 `telegram_api.py` 로직을 `providers/`로 이전
- PM2에 등록

### Phase 3: TelegramBot 리팩토링 (1주)
- `apps/telegrambot/` 구조로 이전, `config.py` 적용, `KernelService` 상속
- UsageCounter를 서비스로 분리, Notifier 연동

### Phase 4: Chronicle 서비스화 (2~3주)
- `apps/chronicle/` 구조 생성
- `services/processor.py` 구현
- `workers/realtime_logger.py`, `processor_worker.py`, `daily_finalizer.py` 작성
- PM2에 워커 등록
- `services/sync_manager.py` (Google Drive, OneDrive) 구현 및 워커화

### Phase 5: 통합 및 운영 환경 적용 (1주)
- 모든 앱의 설정을 Pydantic Settings로 일원화
- `.env.example` 업데이트
- 운영 서버 환경변수 설정 스크립트 작성
- PM2 ecosystem 파일로 전체 관리 전환

### Phase 6: 모니터링 및 알림 체계 구축 (2주, 선택)
- 헬스 체크 엔드포인트 추가
- Prometheus + Grafana 도입 검토
- 장애 알림 Notifier 연동

---

이 문서는 Agora 프로젝트를 현업 수준으로 업그레이드하는 **완전한 청사진**입니다.  
각 단계를 순차적으로 실행하면 서비스 중단 없이 안정적으로 전환할 수 있습니다.  
궁금한 점이나 구체적인 구현에 대한 논의가 필요하면 언제든지 문의하세요. 😊
