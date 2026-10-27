from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any, TYPE_CHECKING

from carelesswhisper.messengers.base import BaseReceiptReport, ReceiptEvent, SentMessage

if TYPE_CHECKING:
    from carelesswhisper.fingerprint import FingerprintAnalysis


@dataclass
class BaseExporter(ABC):
    target_phone_number: str

    @abstractmethod
    def save_rtt(self, receipt_report: BaseReceiptReport) -> None:
        """
        Saves the read delivery delay for the target phone number.
        """
        raise NotImplementedError("Subclasses must implement this method")

    def save_analysis(self, analysis: "FingerprintAnalysis") -> None:
        """Saves an analysis snapshot when supported by the exporter."""

    def save_receipt_event(self, receipt: ReceiptEvent) -> None:
        raise NotImplementedError("This exporter does not support receipt evidence")

    def save_sent_message(self, message: SentMessage) -> None:
        raise NotImplementedError("This exporter does not support send-order evidence")


def serialize_receipt_event(receipt: ReceiptEvent) -> dict[str, Any]:
    return {
        "type": "receipt_event",
        **asdict(receipt),
        "message_ids": list(receipt.message_ids),
        "received_at": receipt.received_at.isoformat(),
    }


def serialize_sent_message(message: SentMessage) -> dict[str, Any]:
    return {
        "type": "sent_message",
        **asdict(message),
        "sent_at": message.sent_at.isoformat(),
    }


def serialize_analysis(analysis: "FingerprintAnalysis") -> dict[str, Any]:
    """Converts an analysis snapshot into JSON-compatible values."""

    def normalize(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    return normalize(asdict(analysis))


def safe_target_identifier(target_phone_number: str) -> str:
    """Returns a filename-safe target identifier."""
    identifier = "".join(
        (
            character
            if character.isascii() and (character.isalnum() or character in "-_")
            else "_"
        )
        for character in target_phone_number
    )
    return identifier or "unknown"
