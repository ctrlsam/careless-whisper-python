import json
import pathlib
import sqlite3
from dataclasses import dataclass

from carelesswhisper.fingerprint import FingerprintAnalysis
from carelesswhisper.messengers.base import BaseReceiptReport, ReceiptEvent, SentMessage

from .base import (
    BaseExporter,
    safe_target_identifier,
    serialize_analysis,
    serialize_receipt_event,
)


@dataclass
class SQLiteExporter(BaseExporter):
    save_directory: str = "./exports/sqlite"

    def __post_init__(self) -> None:
        pathlib.Path(self.save_directory).mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.executescript("""
                CREATE TABLE IF NOT EXISTS receipts (
                    msg_id TEXT PRIMARY KEY,
                    phone_number TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    delivered_at TEXT NOT NULL,
                    rtt_ms REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analyzed_at TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    phone_state TEXT NOT NULL,
                    app_state TEXT NOT NULL,
                    online_status TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    total_requests INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sent_messages (
                    msg_id TEXT PRIMARY KEY,
                    phone_number TEXT NOT NULL,
                    sent_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS receipt_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    received_at TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    device_id INTEGER NOT NULL,
                    receipt_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """)

    def save_sent_message(self, message: SentMessage) -> None:
        with self._connect() as database:
            database.execute(
                """
                INSERT OR REPLACE INTO sent_messages (msg_id, phone_number, sent_at)
                VALUES (?, ?, ?)
                """,
                (message.msg_id, message.phone_number, message.sent_at.isoformat()),
            )

    def save_receipt_event(self, receipt: ReceiptEvent) -> None:
        with self._connect() as database:
            database.execute(
                """
                INSERT INTO receipt_events (
                    received_at, phone_number, device_id, receipt_type, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    receipt.received_at.isoformat(),
                    receipt.phone_number,
                    receipt.device_id,
                    receipt.receipt_type,
                    json.dumps(serialize_receipt_event(receipt), separators=(",", ":")),
                ),
            )

    def save_rtt(self, receipt_report: BaseReceiptReport) -> None:
        with self._connect() as database:
            database.execute(
                """
                INSERT OR REPLACE INTO receipts (
                    msg_id, phone_number, sent_at, delivered_at, rtt_ms
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    receipt_report.msg_id,
                    receipt_report.phone_number,
                    receipt_report.sent_at.isoformat(),
                    receipt_report.delivered_at.isoformat(),
                    receipt_report.delay,
                ),
            )

    def save_analysis(self, analysis: FingerprintAnalysis) -> None:
        payload = serialize_analysis(analysis)
        with self._connect() as database:
            database.execute(
                """
                INSERT INTO analyses (
                    analyzed_at, phone_number, phone_state, app_state,
                    online_status, device_type, confidence, total_requests,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis.analyzed_at.isoformat(),
                    self.target_phone_number,
                    analysis.phone_state.value,
                    analysis.app_state.value,
                    analysis.online_status.value,
                    analysis.device_type.value,
                    analysis.confidence_scores.get("overall", 0.0),
                    analysis.total_requests,
                    json.dumps(payload, separators=(",", ":")),
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.file_path)

    @property
    def file_path(self) -> pathlib.Path:
        target_identifier = safe_target_identifier(self.target_phone_number)
        return pathlib.Path(self.save_directory) / (f"{target_identifier}_analysis.db")
