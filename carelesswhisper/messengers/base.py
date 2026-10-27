from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Coroutine, Any


@dataclass(frozen=True)
class SentMessage:
    msg_id: str
    phone_number: str
    sent_at: datetime


@dataclass(frozen=True)
class ReceiptEvent:
    """One protocol receipt; message_ids retain the original batch order."""

    phone_number: str
    sender_jid: str
    device_id: int
    receipt_type: str
    message_ids: tuple[str, ...]
    received_at: datetime


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
        self.receipt_target: str | None = None
        self.on_receipt: Callable[[ReceiptEvent], Coroutine[Any, Any, None]] | None = (
            None
        )
        self.on_message_sent: (
            Callable[[SentMessage], Coroutine[Any, Any, None]] | None
        ) = None

    @abstractmethod
    async def start(self) -> None:
        """
        Initialize and start the messenger connection.
        This may run indefinitely handling connection and events.
        """
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    async def send_silent_message(
        self, phone_number: str, reaction: str | None = None
    ) -> str:
        """
        Returns the time it takes for the recipients phone to receive the message (not actually read it).

        An optional reaction payload overrides the default emoji, which the DoS
        tool uses to send oversized reaction payloads.
        """
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    async def is_on_platform(self, phone_number: str) -> bool | None:
        """
        Returns whether the phone number is registered, or None if inconclusive.
        """
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    async def wait_until_ready(self) -> None:
        """
        Waits until the messenger connection is fully established and ready to send messages.
        """
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    async def stop(self) -> None:
        """Stops the messenger connection and releases its resources."""
        raise NotImplementedError("Subclasses must implement this method")

    async def record_delivery(self, msg_id: str) -> None:
        """
        Records the delivery time for a given message ID and triggers the on_delivered callback.
        """
        await self.on_delivered(msg_id)
