import sys
import logging
import os

from apps.telegrambot.config import config
from core.kernel.services.bot import TelegramBotService
from core.kernel.agents.manager import get_ai_agent
from core.kernel.logger import setup_logger


def main():
    logger = setup_logger(config.BOT_NAME, config.log_dir, config.LOG_LEVEL)

    # AI_MODE: "gemini"(default), "rest", "notifier"
    ai_mode = getattr(config, "AI_MODE", None) or os.getenv("AI_MODE", "gemini").lower()
    logger.info(f"AI_MODE: {ai_mode}")

    ai_agent = None

    if ai_mode == "gemini":
        # 코어 에이전트(라이브러리) 사용
        try:
            ai_agent = get_ai_agent("gemini", config.GEMINI_KEY)
            logger.info("AI agent: gemini (core)")
        except Exception as e:
            logger.error(f"AI agent 생성 실패: {e}")
            return

    elif ai_mode == "rest":
        # 경량 REST 클라이언트
        try:
            import httpx
        except Exception as e:
            logger.error(f"httpx 미설치: {e}  (pip install httpx 필요)")
            return

        class GeminiRestAgent:
            def __init__(self, api_url: str):
                self.api_url = api_url

            async def generate(self, prompt: str) -> str:
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.post(f"{self.api_url}/generate", json={"prompt": prompt})
                    resp.raise_for_status()
                    data = resp.json() or {}
                    # 서버 구현에 맞춰 키 이름 조정
                    return data.get("result") or data.get("text") or ""

        rest_url = os.getenv("GEMINI_REST_URL", "http://127.0.0.1:8088")
        ai_agent = GeminiRestAgent(rest_url)
        logger.info(f"AI agent: REST ({rest_url})")

    elif ai_mode == "notifier":
        # 알림 전용 모드: ai_agent=None로 두면 bot.py가 Notifier로 동작
        ai_agent = None
        logger.info("Notifier 모드: AI 비활성화")

    else:
        logger.error(f"지원하지 않는 AI_MODE: {ai_mode}")
        return

    # 토큰 확인
    token = config.TELEGRAM_TEST_TOKEN or config.TELEGRAM_TOKEN
    if not token or not token.strip():
        logger.error("토큰이 설정되지 않았습니다. .env에 TELEGRAM_TOKEN 또는 TELEGRAM_TEST_TOKEN을 설정하세요.")
        return

    source = "테스트 토큰" if token == config.TELEGRAM_TEST_TOKEN else "운영 토큰"
    logger.info(f"{source}(으)로 실행됩니다.")

    # 현재 레포의 TelegramBotService 시그니처에 맞추세요.
    # (아래 인자들은 이전 버전 호환을 위해 남겨둔 예시입니다)
    bot = TelegramBotService(
        name=getattr(config, "BOT_NAME", "telegrambot"),
        token=token,
        ai_agent=ai_agent,
        log_dir=config.log_dir,
        admin_chat_id=config.ADMIN_CHAT_ID,
        total_quota=getattr(config, "TOTAL_QUOTA", 1000),
        data_dir=getattr(config, "data_dir", getattr(config, "DATA_DIR", None))
    )

    # 메시지 전송 CLI 옵션 처리
    if len(sys.argv) > 2 and sys.argv[1] == "--send":
        msg = sys.argv[2]
        chat_id = config.ADMIN_CHAT_ID
        try:
            bot.send_message(chat_id, msg)
            logger.info(f"메시지 전송 완료: {msg}")
        except Exception as e:
            logger.error(f"메시지 전송 실패: {e}")
        return

    # 실행: polling이 포그라운드에서 계속 돌아야 systemd가 running 유지
    try:
        bot.run()
    except Exception as e:
        logger.error(f"봇 실행 중 오류: {e}")


if __name__ == "__main__":
    main()
    