from abc import ABC, abstractmethod
from dataclasses import dataclass

from carelesswhisper.messengers.base import BaseReceiptReport


@dataclass
class BaseExporter(ABC):
    target_phone_number: str

    @abstractmethod
    def save_receipt_report(self, receipt_report: BaseReceiptReport) -> None:
        """
        Saves the read receipt delay for the target phone number.
        """
        raise NotImplementedError("Subclasses must implement this method")
