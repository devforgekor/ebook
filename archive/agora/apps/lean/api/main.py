
from fastapi import FastAPI
from .routes import router
from apps.lean.config_settings import settings
from core.utils.logger import setup_logger
from pathlib import Path


# 공통 로거 설정
logger = setup_logger(
	name="lean_api",
	log_dir=Path(settings.LOG_DIR),
	level="DEBUG" if settings.DEBUG else "INFO"
)

app = FastAPI(title="Lean Token Optimization API")
app.include_router(router)

@app.on_event("startup")
async def on_startup():
	logger.info("[시작] Lean API 서버 시작")

@app.on_event("shutdown")
async def on_shutdown():
	logger.info("[종료] Lean API 서버 종료")

# uvicorn api.main:app --reload --port 8002
