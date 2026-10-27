import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from carelesswhisper.exporters.csv import CSVExporter
from carelesswhisper.exporters.jsonl import JSONLinesExporter
from carelesswhisper.exporters.sqlite import SQLiteExporter
from carelesswhisper.fingerprint import (
    AppState,
    DeviceType,
    FingerprintAnalysis,
    OnlineStatus,
    PhoneState,
    ReceiptStructure,
)
from carelesswhisper.messengers.base import BaseReceiptReport, ReceiptEvent, SentMessage


def make_report() -> BaseReceiptReport:
    sent_at = datetime.now()
    return BaseReceiptReport(
        msg_id="message-1",
        phone_number="123456789",
        sent_at=sent_at,
        delivered_at=sent_at + timedelta(milliseconds=125),
    )


def make_analysis() -> FingerprintAnalysis:
    return FingerprintAnalysis(
        analyzed_at=datetime.now(),
        phone_state=PhoneState.SCREEN_ON,
        app_state=AppState.APP_FOREGROUND,
        total_data_used_bytes=600,
        estimated_data_rate_bytes_per_second=300,
        estimated_battery_drain_pct_per_hour_min=1,
        estimated_battery_drain_pct_per_hour_max=5,
        device_type=DeviceType.IPHONE,
        avg_rtt_ms=125,
        median_rtt_ms=125,
        rtt_stdev_ms=5,
        total_requests=2,
        online_status=OnlineStatus.ONLINE,
        confidence_scores={"overall": 0.8, "device_type": 0.8},
        receipt_structure=ReceiptStructure(
            delivery_receipt_handling="Separate",
            read_receipt_handling="Stacked (Reversed)",
            receipt_ordering="Reversed",
            platform="iOS",
            messenger="WhatsApp",
        ),
        companion_devices=[
            {
                "device_index": 0,
                "type": "Web",
                "last_seen": datetime.now(),
            }
        ],
    )


def test_jsonl_exporter_saves_receipts_and_analysis(tmp_path):
    exporter = JSONLinesExporter("123456789", save_directory=str(tmp_path))

    exporter.save_rtt(make_report())
    exporter.save_analysis(make_analysis())

    records = [json.loads(line) for line in exporter.file_path.read_text().splitlines()]
    assert records[0]["type"] == "receipt"
    assert records[0]["rtt_ms"] == 125
    assert records[1]["type"] == "analysis"
    assert records[1]["device_type"] == "iPhone"
    assert records[1]["companion_devices"][0]["last_seen"]


def test_exporter_filename_does_not_allow_target_path_traversal(tmp_path):
    exporter = JSONLinesExporter("../../target", save_directory=str(tmp_path))

    assert exporter.file_path.parent == tmp_path
    assert exporter.file_path.name == "______target_analysis.jsonl"


def test_sqlite_exporter_saves_queryable_analysis(tmp_path):
    exporter = SQLiteExporter("123456789", save_directory=str(tmp_path))

    exporter.save_rtt(make_report())
    exporter.save_analysis(make_analysis())

    with sqlite3.connect(exporter.file_path) as database:
        receipt = database.execute("SELECT msg_id, rtt_ms FROM receipts").fetchone()
        analysis = database.execute(
            "SELECT device_type, confidence, payload_json FROM analyses"
        ).fetchone()

    assert receipt == ("message-1", 125.0)
    assert analysis[0:2] == ("iPhone", 0.8)
    assert json.loads(analysis[2])["phone_state"] == "SCREEN_ON"


@pytest.mark.parametrize(
    "exporter_type", [CSVExporter, JSONLinesExporter, SQLiteExporter]
)
def test_exporter_preserves_receipt_batches_and_send_order(tmp_path, exporter_type):
    exporter = exporter_type("123456789", save_directory=str(tmp_path))
    sent = SentMessage("z", "123456789", datetime(2026, 1, 1))
    event = ReceiptEvent(
        phone_number="123456789",
        sender_jid="123456789:0@s.whatsapp.net",
        device_id=0,
        receipt_type="READ",
        message_ids=("m", "a", "z"),
        received_at=datetime(2026, 1, 1, 0, 0, 10),
    )

    exporter.save_sent_message(sent)
    exporter.save_receipt_event(event)
    exporter.save_rtt(make_report())

    if isinstance(exporter, SQLiteExporter):
        with sqlite3.connect(exporter.file_path) as database:
            stored_sent = database.execute(
                "SELECT msg_id, sent_at FROM sent_messages"
            ).fetchone()
            stored_event = json.loads(
                database.execute("SELECT payload_json FROM receipt_events").fetchone()[
                    0
                ]
            )
        assert stored_sent == ("z", sent.sent_at.isoformat())
    else:
        path = (
            exporter.evidence_file_path
            if isinstance(exporter, CSVExporter)
            else exporter.file_path
        )
        records = [json.loads(line) for line in path.read_text().splitlines()]
        assert records[0]["sent_at"] == sent.sent_at.isoformat()
        stored_event = records[1]
    assert stored_event["message_ids"] == ["m", "a", "z"]
    assert stored_event["sender_jid"] == event.sender_jid
    assert stored_event["device_id"] == 0
    assert stored_event["receipt_type"] == "READ"
    if isinstance(exporter, CSVExporter):
        assert len(Path(exporter.file_path).read_text().strip().split(",")) == 2
