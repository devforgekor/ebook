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
