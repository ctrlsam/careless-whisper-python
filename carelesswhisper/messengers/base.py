from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Coroutine, Any


@dataclass
class BaseReceiptReport:
    msg_id: str
    phone_number: str
    sent_at: datetime
    delivered_at: datetime

    @property
    def delay(self) -> float:
        return (self.delivered_at - self.sent_at).total_seconds() * 1000  # milliseconds


class BaseMessenger(ABC):
    def __init__(self, on_delivered: Callable[[str], Coroutine[Any, Any, None]]):
        self.on_delivered = on_delivered

    @abstractmethod
    async def start(self) -> None:
        """
        Initialize and start the messenger connection.
        This may run indefinitely handling connection and events.
        """
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    async def send_silent_message(self, phone_number: str) -> str:
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

    async def record_delivery(self, msg_id: str) -> None:
        """
        Records the delivery time for a given message ID and triggers the on_delivered callback.
        """
        await self.on_delivered(msg_id)
