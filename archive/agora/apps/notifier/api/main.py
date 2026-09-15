
from fastapi import FastAPI
from apps.notifier.api.routes import router
from apps.notifier.core.config import settings
from apps.notifier.core.logging import setup_logging


setup_logging()  # 앱 시작 시 로깅 설정
app = FastAPI(title="Notifier API", version="1.0.0")
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host=settings.NOTIFIER_HOST, port=settings.NOTIFIER_PORT, reload=True)
