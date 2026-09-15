import httpx

from neisync.core.config import settings


async def send_alert(message: str, level: str = 'error', channel: str = 'telegram'):
    """Phase 3에서 구현: Notifier API로 알림 전송"""
    if not settings.notifier_enabled:
        return
    payload = {
        'message': message,
        'level': level,
        'channel': channel
    }
    headers = {'Authorization': f'Bearer {settings.notifier_api_key}'}
    try:
        async with httpx.AsyncClient() as client:
            await client.post(settings.notifier_url, json=payload, headers=headers, timeout=5)
    except Exception:
        # 알림 실패 시 로깅 또는 무시
        pass
