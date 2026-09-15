# src/notifier/base.py
from abc import ABC, abstractmethod
from src.core_event import CoreEvent

class Notifier(ABC):
    @abstractmethod
    def notify(self, event: CoreEvent) -> None:
        """
        CoreEvent를 외부로 전달한다.
        """
        pass
    