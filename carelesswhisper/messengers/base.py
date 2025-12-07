from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Coroutine, Any


class ReceiptTimeoutError(Exception):
    ...


@dataclass
class BaseReceiptReport:
    phone_number: str
    sent_at: datetime
    delivered_at: datetime
    
    @property
    def delay(self) -> float:
        return (self.delivered_at - self.sent_at).total_seconds() * 1000  # milliseconds

class BaseMessenger(ABC):
    @abstractmethod
    async def start(self) -> None:
        """
        Initialize and start the messenger connection.
        This may run indefinitely handling connection and events.
        """
        raise NotImplementedError("Subclasses must implement this method")
    
    @abstractmethod
    async def get_rtt(self, phone_number: str, timeout: int = 5) -> BaseReceiptReport:
        """
        Returns the time it takes for the recipients phone to receive the message (not actually read it).
        """
        raise NotImplementedError("Subclasses must implement this method")
    
    @abstractmethod
    async def is_on_platform(self, phone_number: str) -> bool:
        """
        Returns whether the given phone number is registered on the messaging platform.
        """
        raise NotImplementedError("Subclasses must implement this method")
    
    @abstractmethod
    async def wait_until_ready(self) -> None:
        """
        Waits until the messenger connection is fully established and ready to send messages.
        """
        raise NotImplementedError("Subclasses must implement this method")

