from abc import ABC, abstractmethod

class NotificationProvider(ABC):
    @abstractmethod
    async def send(self, text: str) -> bool:
        """알림 전송, 성공 여부 반환"""
        pass
