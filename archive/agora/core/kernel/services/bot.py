# core/kernel/services/bot.py

import asyncio
import logging
import inspect
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from core.kernel.services.usage_counter import UsageCounter
from core.kernel.logger import setup_logger

# 선택: Gemini/외부 API 예외에 대해 좀 더 친절한 처리
try:
    from google.genai.errors import ClientError as GeminiClientError  # 미설치 시 except로 넘어감
except Exception:  # pragma: no cover
    GeminiClientError = Exception


class TelegramBotService:
    def __init__(
        self,
        name,
        token,
        ai_agent,
        log_dir,
        admin_chat_id,
        total_quota,
        data_dir,
        log_level=logging.INFO,
    ):
        self.name = name
        self.token = token
        self.ai_agent = ai_agent
        self.log_dir = log_dir

        # setup_logger는 문자열 레벨("DEBUG")과 숫자 레벨 모두 지원한다고 가정
        self.logger = setup_logger(self.name, self.log_dir, log_level)

        # python-telegram-bot v20+
        self.application = Application.builder().token(self.token).build()

        self.admin_chat_id = admin_chat_id
        self.usage_counter = UsageCounter(
            self.application,
            self.logger,
            admin_chat_id,
            total_quota,
            data_dir,
        )

        self._register_handlers()

    def _register_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start))
        # ⚠️ 반드시 & (bitwise AND), ~ (bitwise NOT) 사용. HTML 이스케이프(&amp;) 금지!
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        # 헬스체크용 /ping
        self.application.add_handler(CommandHandler("ping", self.ping))

    async def start(self, update, context):
        await update.message.reply_text(f"안녕하세요! {self.name}입니다. 무엇을 도와드릴까요?")

    async def ping(self, update, context):
        self.logger.info(f"/ping from uid={getattr(update.effective_user,'id',None)}")
        await update.message.reply_text("pong 🏓")

    async def handle_message(self, update, context):
        """
        사용자 메시지 수신 → 모델 호출 → 응답 전송 → 사용량 카운트
        """
        user_message = (update.message.text or "").strip()
        self.logger.info(
            f"handle_message: uid={getattr(update.effective_user,'id',None)} text={user_message!r}"
        )

        if not user_message:
            await update.message.reply_text("메시지가 비어 있어요. 다시 입력해 주세요.")
            return

        try:
            # generate가 비동기/동기 모두 안전하게 처리
            if inspect.iscoroutinefunction(self.ai_agent.generate):
                response = await self.ai_agent.generate(user_message)
            else:
                response = self.ai_agent.generate(user_message)

            if not response:
                response = "응답을 생성하지 못했어요. 잠시 후 다시 시도해 주세요."

            # ✅ 사용자에게 응답 전송
            await update.message.reply_text(response)

            # ✅ 성공 시 카운트는 '한 번만' 증가
            new_count = await self.usage_counter.increment()
            if isinstance(new_count, int):
                total = self.usage_counter.total_quota
                left = max(total - new_count, 0)
                percent_left = int((left / total) * 100)
                self.logger.info(
                    f"Usage updated: {new_count}/{total} (left {percent_left}%)"
                )

        except GeminiClientError as e:
            status = getattr(e, "status_code", None)
            self.logger.error(f"Gemini error ({status}): {e}", exc_info=True)

            if status == 429:
                # 1) 사용자 안내
                await update.message.reply_text(
                    "요청이 잠시 많아 제한이 걸렸어요. 10~20초 후 다시 시도해 주세요 🙏"
                )
                # 2) 관리자 알림(증가 없이 조회)
                try:
                    current_count = await self.usage_counter.get_count()
                    total = self.usage_counter.total_quota
                    left = max(total - current_count, 0)
                    percent_left = int((left / total) * 100)
                    msg = (
                        "⚠️ 429 제한 발생(외부 요인)\n"
                        f"📊 현재 내부 카운트: {current_count}/{total} "
                        f"({percent_left}% 남음)\n"
                        f"🤖 봇 이름: {self.name}"
                    )
                    await self.application.bot.send_message(
                        chat_id=self.admin_chat_id, text=msg
                    )
                except Exception as ne:
                    self.logger.error(f"429 admin notify error: {ne}", exc_info=True)
            else:
                await update.message.reply_text(
                    "일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요."
                )

        except Exception as e:
            self.logger.error(f"핸들러 처리 중 예외: {e}", exc_info=True)
            await update.message.reply_text("오류가 발생했어요. 잠시 후 다시 시도해 주세요.")

    def send_message(self, chat_id: str, text: str):
        """run_bot.py --send 옵션과 연동되는 단발성 발송 유틸"""
        async def _send():
            await self.application.bot.send_message(chat_id=chat_id, text=text)

        # Application 객체는 내부적으로 자체 이벤트 루프를 운용하므로,
        # 단발 호출은 별도의 run으로 안전하게 래핑
        asyncio.run(_send())

    def run(self):
        self.logger.info("Starting Telegram bot...")
        try:
            # webhook 잔재로 인해 업데이트 못 받는 이슈 방지 + 모든 타입 허용
            self.application.run_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,
            )
        except KeyboardInterrupt:
            self.logger.info("Telegram bot interrupted by user (KeyboardInterrupt).")
            try:
                self.application.stop()
            except Exception:
                pass
        except Exception as e:
            self.logger.error(f"Telegram bot crashed: {e}", exc_info=True)
            try:
                self.application.stop()
            except Exception:
                pass
            # PM2 자동 재시작을 유도하려면 재전파:
            # raise
        finally:
            self.logger.info("Telegram bot stopped.")
            