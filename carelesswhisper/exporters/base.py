from abc import ABC, abstractmethod
from dataclasses import dataclass

from carelesswhisper.messengers.base import BaseReceiptReport


@dataclass
class BaseExporter(ABC):
    target_phone_number: str

    @abstractmethod
    def save_rtt(self, receipt_report: BaseReceiptReport) -> None:
        """
        Saves the read delivery delay for the target phone number.
        """
        raise NotImplementedError("Subclasses must implement this method")
