import pathlib
from dataclasses import dataclass

from .base import BaseExporter
from carelesswhisper.messengers.base import BaseReceiptReport


@dataclass
class CSVExporter(BaseExporter):
    save_directory: str = "./exports/csv"
    file_name: str | None = None

    def __post_init__(self):
        pathlib.Path(self.save_directory).mkdir(parents=True, exist_ok=True)

    def save_receipt_report(self, receipt_report: BaseReceiptReport) -> None:
        with open(self.file_path, "a") as f:
            f.write(f"{receipt_report.sent_at},{receipt_report.delay}\n")

    @property
    def file_path(self) -> str:
        file_name = self.file_name or f"{self.target_phone_number}_delays.csv"
        return str(pathlib.Path(self.save_directory) / file_name)
