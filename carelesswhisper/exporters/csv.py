import pathlib
import json
from dataclasses import dataclass

from .base import (
    BaseExporter,
    safe_target_identifier,
    serialize_receipt_event,
    serialize_sent_message,
)
from carelesswhisper.messengers.base import BaseReceiptReport, ReceiptEvent, SentMessage


@dataclass
class CSVExporter(BaseExporter):
    save_directory: str = "./exports/csv"
    file_name: str | None = None

    def __post_init__(self):
        pathlib.Path(self.save_directory).mkdir(parents=True, exist_ok=True)

    def save_rtt(self, receipt_report: BaseReceiptReport) -> None:
        with open(self.file_path, "a") as f:
            f.write(f"{receipt_report.sent_at},{receipt_report.delay}\n")

    def save_receipt_event(self, receipt: ReceiptEvent) -> None:
        self._append_evidence(serialize_receipt_event(receipt))

    def save_sent_message(self, message: SentMessage) -> None:
        self._append_evidence(serialize_sent_message(message))

    def _append_evidence(self, record: dict) -> None:
        with self.evidence_file_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, separators=(",", ":")) + "\n")

    @property
    def evidence_file_path(self) -> pathlib.Path:
        return pathlib.Path(self.file_path).with_suffix(".receipts.jsonl")

    @property
    def file_path(self) -> str:
        target_identifier = safe_target_identifier(self.target_phone_number)
        file_name = self.file_name or f"{target_identifier}_delays.csv"
        return str(pathlib.Path(self.save_directory) / file_name)
