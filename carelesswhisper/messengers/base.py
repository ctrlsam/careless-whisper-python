from abc import ABC, abstractmethod
from dataclasses import dataclass


class ReceiptTimeoutError(Exception):
    ...


@dataclass
class BaseReceiptReport:
    phone_number: str
    sent_at: int
    delieverd_at: int
    
    @property
    def delay(self) -> float:
        print("sent_at:", self.sent_at, "delieverd_at:", self.delieverd_at)
        return (self.delieverd_at - self.sent_at) * 1000  # milliseconds


class BaseMessenger(ABC):
    @abstractmethod
    def get_delivery_delay(self, phone_number: str, timeout: int = 5) -> BaseReceiptReport:
        """
        Returns the time it takes for the recipients phone to receive the message (not actually read it).
        """
        raise NotImplementedError("Subclasses must implement this method")
    
    @abstractmethod
    def is_on_platform(self, phone_number: str) -> bool:
        """
        Returns whether the given phone number is registered on the messaging platform.
        """
        raise NotImplementedError("Subclasses must implement this method")

