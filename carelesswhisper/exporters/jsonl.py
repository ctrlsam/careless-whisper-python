import json
import pathlib
from dataclasses import dataclass

from carelesswhisper.fingerprint import FingerprintAnalysis
from carelesswhisper.messengers.base import BaseReceiptReport, ReceiptEvent, SentMessage

from .base import (
    BaseExporter,
    safe_target_identifier,
    serialize_analysis,
    serialize_receipt_event,
    serialize_sent_message,
)


@dataclass
class JSONLinesExporter(BaseExporter):
    save_directory: str = "./exports/jsonl"

    def __post_init__(self) -> None:
        pathlib.Path(self.save_directory).mkdir(parents=True, exist_ok=True)

    def save_rtt(self, receipt_report: BaseReceiptReport) -> None:
        record = {
            "type": "receipt",
            "msg_id": receipt_report.msg_id,
            "phone_number": receipt_report.phone_number,
            "sent_at": receipt_report.sent_at.isoformat(),
            "delivered_at": receipt_report.delivered_at.isoformat(),
            "rtt_ms": receipt_report.delay,
        }
        self._append(record)

    def save_analysis(self, analysis: FingerprintAnalysis) -> None:
        self._append({"type": "analysis", **serialize_analysis(analysis)})

    def save_receipt_event(self, receipt: ReceiptEvent) -> None:
        self._append(serialize_receipt_event(receipt))

    def save_sent_message(self, message: SentMessage) -> None:
        self._append(serialize_sent_message(message))

    def _append(self, record: dict) -> None:
        with self.file_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, separators=(",", ":")) + "\n")

    @property
    def file_path(self) -> pathlib.Path:
        target_identifier = safe_target_identifier(self.target_phone_number)
        return pathlib.Path(self.save_directory) / (
            f"{target_identifier}_analysis.jsonl"
        )
