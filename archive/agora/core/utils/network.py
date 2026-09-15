import httpx
from typing import Optional

async def send_alert(message: str, channel: str = "telegram", settings=None) -> bool:
    """모든 앱에서 알림을 보낼 때 이 함수를 사용 (Notifier API 호출)"""
    if settings is None:
        raise ValueError("settings 인스턴스를 반드시 전달해야 합니다.")
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
