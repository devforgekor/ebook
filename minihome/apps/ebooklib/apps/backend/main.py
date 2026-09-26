#!/usr/bin/env python3
# Status: experimental
# Path: none — 초기 구현
"""FastAPI 백엔드 - 웹소설 리더 API"""

import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


class _RedactSecretsFilter(logging.Filter):
    """[WHY] 쿼리스트링의 비밀번호는 uvicorn access log에 평문으로 남는다 — 마스킹.

    본문(JSON) 인증이 기본이어도 구형 클라이언트/스크립트가 query로 보내면
    로그에 남으므로 로그 단위에서 한 번 더 차단한다.
    """

    _PATTERN = re.compile(
        r"(?i)([?&](?:password|passwd|token|secret|api[_-]?key)=)[^&\s\"']+"
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        redacted = self._PATTERN.sub(r"\1***", msg)
        if redacted != msg:
            record.msg, record.args = redacted, None
        return True


logging.getLogger("uvicorn.access").addFilter(_RedactSecretsFilter())

# 환경 변수 로드
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

from routers import novels, chapters, metadata, pipeline
from lib.database import init_db

# SQLite 초기화
init_db()

app = FastAPI(
    title="eBook API",
    description="웹소설 리더를 위한 API",
    version="0.1.0",
)

# CORS 설정 (KV EBOOK-CORS-ORIGINS 우선, 로컬 개발은 .env/CORS_ORIGINS)
cors_origins_str = os.getenv("EBOOK_CORS_ORIGINS") or os.getenv("CORS_ORIGINS", '["http://localhost:3000"]')
import json

cors_origins = json.loads(cors_origins_str)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 - 표지 이미지
COVERS_DIR = Path("/opt/ai_data/flaresolverr/covers")
COVERS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/api/covers", StaticFiles(directory=str(COVERS_DIR)), name="covers")

# 정적 파일 - 웹툰/만화 챕터 이미지 (로컬 다운로드분)
WEBTOON_IMAGES_DIR = Path("/opt/ai_data/flaresolverr/webtoon_images")
WEBTOON_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/api/webtoon_images",
    StaticFiles(directory=str(WEBTOON_IMAGES_DIR)),
    name="webtoon_images",
)

# 라우터 등록
app.include_router(novels.router, prefix="/api", tags=["novels"])
app.include_router(chapters.router, prefix="/api", tags=["chapters"])
app.include_router(metadata.router, prefix="/api", tags=["metadata"])
app.include_router(pipeline.router, prefix="/api", tags=["pipeline"])


@app.get("/")
async def root():
    return {"message": "eBook API"}


@app.get("/health")
async def health():
    return {"status": "ok"}
