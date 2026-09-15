# core/kernel/services/usage_counter.py

import os
import json
import asyncio
from datetime import date
import aiofiles


class UsageCounter:
    def __init__(self, bot_application, logger, admin_chat_id, total_quota, data_dir):
        self.bot_app = bot_application
        self.logger = logger
        self.admin_chat_id = admin_chat_id
        self.total_quota = total_quota
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.usage_file = os.path.join(self.data_dir, 'usage_count.json')
        self.notify_file = os.path.join(self.data_dir, 'notified.json')
        self._lock = asyncio.Lock()
        self.logger.info(f"UsageCounter initialized: {self.usage_file}")

    async def get_count(self) -> int:
        """
        오늘 날짜의 누적 사용량을 '증가 없이' 조회합니다.
        파일이 없거나 문제가 있어도 0을 반환합니다.
        """
        try:
            return await self._read_usage()
        except Exception as e:
            self.logger.error(f"UsageCounter.get_count error: {e}", exc_info=True)
            return 0

    async def _read_usage(self) -> int:
        today = str(date.today())
        if os.path.exists(self.usage_file):
            try:
                async with aiofiles.open(self.usage_file, 'r') as f:
                    content = await f.read()
                    data = json.loads(content)
                    if data.get('date') == today:
                        return data.get('count', 0)
            except Exception as e:
                self.logger.error(f"UsageCounter _read_usage error: {e}")
        return 0

    async def _write_usage(self, count: int):
        today = str(date.today())
        try:
            async with aiofiles.open(self.usage_file, 'w') as f:
                await f.write(json.dumps({'date': today, 'count': count}))
            self.logger.debug(f"UsageCounter wrote usage: {count}")
        except Exception as e:
            self.logger.error(f"UsageCounter _write_usage error: {e}")

    async def _has_notified(self, threshold) -> bool:
        today = str(date.today())
        if os.path.exists(self.notify_file):
            try:
                async with aiofiles.open(self.notify_file, 'r') as f:
                    content = await f.read()
                    data = json.loads(content)
                    if data.get('date') == today:
                        return threshold in data.get('notified', [])
            except Exception:
                pass
        return False

    async def _mark_notified(self, threshold):
        today = str(date.today())
        async with self._lock:
            try:
                if os.path.exists(self.notify_file):
                    async with aiofiles.open(self.notify_file, 'r') as f:
                        content = await f.read()
                        data = json.loads(content)
                else:
                    data = {}
                if data.get('date') != today:
                    data = {'date': today, 'notified': []}
                if threshold not in data['notified']:
                    data['notified'].append(threshold)
                    async with aiofiles.open(self.notify_file, 'w') as f:
                        await f.write(json.dumps(data))
            except Exception as e:
                self.logger.error(f"UsageCounter _mark_notified error: {e}")

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
                        msg = (
                            f"⚠️ Gemini API 사용량 경고: {th}% 미만 남음 "
                            f"(현재 {new_count}/{self.total_quota} 사용)"
                        )
                        self.logger.warning(msg)
                        await self.send_admin_alert(msg)
                        await self._mark_notified(th)

                # 사용량 초과 시 별도 알림
                if new_count >= self.total_quota and not await self._has_notified('exceeded'):
                    msg = f"❌ Gemini API 일일 사용량 초과! ({new_count}/{self.total_quota})"
                    self.logger.error(msg)
                    await self.send_admin_alert(msg)
                    await self._mark_notified('exceeded')

                return new_count
            except Exception as e:
                self.logger.error(f"UsageCounter.increment error: {e}", exc_info=True)
                return None

    async def send_admin_alert(self, text):
        try:
            await self.bot_app.bot.send_message(chat_id=self.admin_chat_id, text=text)
        except Exception as e:
            self.logger.error(f"Failed to send admin alert: {e}")