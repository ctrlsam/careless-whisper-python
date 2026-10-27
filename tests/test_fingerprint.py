import asyncio
from datetime import datetime, timedelta

import pytest

from carelesswhisper.exploit import Exploit
from carelesswhisper.fingerprint import Fingerprint, PhoneState, AppState, DeviceType
from carelesswhisper.messengers.base import BaseReceiptReport, ReceiptEvent, SentMessage


def make_report(index: int) -> BaseReceiptReport:
    sent_at = datetime.now()
    return BaseReceiptReport(
        msg_id=str(index),
        phone_number="123456789",
        sent_at=sent_at,
        delivered_at=sent_at + timedelta(milliseconds=index + 1),
    )


def make_report_with_delay(index: int, delay_ms: float) -> BaseReceiptReport:
    sent_at = datetime.now()
    return BaseReceiptReport(
        msg_id=str(index),
        phone_number="123456789",
        sent_at=sent_at,
        delivered_at=sent_at + timedelta(milliseconds=delay_ms),
    )


def _fingerprint_with_delays(delays: list[float]) -> Fingerprint:
    exploit = Exploit("123456789")
    fingerprint = Fingerprint(exploit)
    for index, delay_ms in enumerate(delays):
        report = make_report_with_delay(index, delay_ms)
        exploit._reports.append(report)
        fingerprint.register_report(report)
    return fingerprint


def test_screen_on_with_high_but_steady_rtt():
    # Regression: a steady ~1.8s baseline (above the old hard-coded 1500ms
    # iPhone cut-off) must read SCREEN_ON because detection is relative.
    fingerprint = _fingerprint_with_delays([1800.0] * 30)
    state = asyncio.run(fingerprint.get_phone_screen_state())
    assert state == PhoneState.SCREEN_ON


def test_screen_off_when_rtt_doubles_above_baseline():
    # ~1s active baseline, then a sustained ~2x elevation -> screen off.
    delays = [1000.0] * 30 + [2100.0] * 12
    fingerprint = _fingerprint_with_delays(delays)
    state = asyncio.run(fingerprint.get_phone_screen_state())
    assert state == PhoneState.SCREEN_OFF


def test_screen_on_with_insufficient_samples():
    fingerprint = _fingerprint_with_delays([1000.0] * 3)
    state = asyncio.run(fingerprint.get_phone_screen_state())
    assert state == PhoneState.SCREEN_ON


def test_app_foreground_with_high_but_steady_rtt():
    # Regression: a steady ~900ms baseline (above the old 500/800ms absolute
    # cut-offs) must read APP_FOREGROUND because detection is relative.
    fingerprint = _fingerprint_with_delays([900.0] * 30)
    state = asyncio.run(fingerprint.get_app_state())
    assert state == AppState.APP_FOREGROUND


def test_app_standby_when_rtt_triples_above_baseline():
    # ~350ms foreground baseline, then a sustained ~2.8x elevation -> standby.
    delays = [350.0] * 30 + [1000.0] * 12
    fingerprint = _fingerprint_with_delays(delays)
    state = asyncio.run(fingerprint.get_app_state())
    assert state == AppState.APP_STANDBY


def test_app_background_when_rtt_moderately_elevated():
    # ~350ms baseline, then a sustained ~1.5x elevation -> background band.
    delays = [350.0] * 30 + [520.0] * 12
    fingerprint = _fingerprint_with_delays(delays)
    state = asyncio.run(fingerprint.get_app_state())
    assert state == AppState.APP_BACKGROUND


def test_app_foreground_with_insufficient_samples():
    fingerprint = _fingerprint_with_delays([350.0] * 3)
    state = asyncio.run(fingerprint.get_app_state())
    assert state == AppState.APP_FOREGROUND


def test_analyze_does_not_duplicate_rolling_window():
    exploit = Exploit("123456789")
    fingerprint = Fingerprint(exploit)

    for index in range(120):
        report = make_report(index)
        exploit._reports.append(report)
        fingerprint.register_report(report)

    expected_window = list(fingerprint._rtt_window)

    analysis = asyncio.run(fingerprint.analyze())
    asyncio.run(fingerprint.analyze())

    assert list(fingerprint._rtt_window) == expected_window
    assert analysis.analyzed_at
    assert 0 <= analysis.confidence_scores["overall"] <= 1
    assert analysis.estimated_data_rate_bytes_per_second > 0


async def receipt_fingerprint(
    read_batches=(),
    delivery_batches=(("z",), ("a",), ("m",)),
    device_id=0,
    sent_offsets=(0, 1, 2),
):
    fingerprint = Fingerprint(Exploit("123456789"))
    sent_at = datetime(2026, 1, 1)
    for msg_id, seconds in zip(("z", "a", "m"), sent_offsets):
        await fingerprint.exploit.observe_sent_message(
            SentMessage(msg_id, "123456789", sent_at + timedelta(seconds=seconds))
        )
    for receipt_type, batches in (
        ("DELIVERED", delivery_batches),
        ("READ", read_batches),
    ):
        for batch in batches:
            await fingerprint.exploit.on_receipt(
                ReceiptEvent(
                    phone_number="123456789",
                    sender_jid=f"123456789:{device_id}@s.whatsapp.net",
                    device_id=device_id,
                    receipt_type=receipt_type,
                    message_ids=batch,
                    received_at=sent_at + timedelta(seconds=10),
                )
            )
    return fingerprint


@pytest.mark.parametrize(
    ("read_order", "expected"),
    [
        (("m", "a", "z"), DeviceType.IPHONE),
        (("z", "a", "m"), DeviceType.ANDROID_GENERIC),
    ],
)
def test_device_os_uses_observed_read_order_not_ids_or_rtt(read_order, expected):
    fingerprint = asyncio.run(receipt_fingerprint(read_batches=(read_order,)))
    analysis = asyncio.run(fingerprint.analyze())
    assert analysis.device_type == expected
    assert analysis.receipt_structure.delivery_receipt_handling == "Separate"
    assert analysis.receipt_structure.evidence_batches == 1
    assert analysis.total_requests == 0
    assert 0 < analysis.confidence_scores["device_type"] < 1

    for i, delay in enumerate([15000, 6000, 1000, 13000, 500]):
        report = make_report_with_delay(i, delay)
        fingerprint.exploit._reports.append(report)
        fingerprint.register_report(report)
    noisy_analysis = asyncio.run(fingerprint.analyze())
    assert noisy_analysis.device_type == expected
    assert noisy_analysis.confidence_scores["device_type"] == (
        analysis.confidence_scores["device_type"]
    )


@pytest.mark.parametrize("delays", [[350.0] * 30, [1000, 2000, 15000] * 10])
def test_rtt_only_never_establishes_device_os_or_receipt_structure(delays):
    analysis = asyncio.run(_fingerprint_with_delays(delays).analyze())
    assert analysis.device_type == DeviceType.UNKNOWN
    assert analysis.receipt_structure is None
    assert analysis.confidence_scores["device_type"] == 0


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"read_batches": (("m", "a"),)},
        {"read_batches": (("m", "missing", "z"),)},
        {"read_batches": (("m", "m", "z"),)},
        {"read_batches": (("a", "m", "z"),)},
        {"read_batches": (("m", "a", "z"), ("z", "a", "m"))},
        {"read_batches": (("m", "a", "z"),), "sent_offsets": (0, 0, 2)},
        {"read_batches": (("m", "a", "z"),), "delivery_batches": (("z",),)},
        {"read_batches": (("m", "a", "z"),), "delivery_batches": (("z", "a", "m"),)},
        {"read_batches": (("m", "a", "z"),), "device_id": 9},
    ],
)
def test_missing_ambiguous_or_companion_evidence_leaves_phone_unknown(options):
    fingerprint = asyncio.run(receipt_fingerprint(**options))
    analysis = asyncio.run(fingerprint.analyze())
    assert analysis.device_type == DeviceType.UNKNOWN
    assert analysis.confidence_scores["device_type"] == 0


def test_duplicate_read_receipts_do_not_inflate_evidence():
    fingerprint = asyncio.run(
        receipt_fingerprint(read_batches=(("m", "a", "z"), ("m", "a", "z")))
    )
    analysis = asyncio.run(fingerprint.analyze())
    assert analysis.device_type == DeviceType.IPHONE
    assert analysis.receipt_structure.evidence_batches == 1


def test_read_batch_is_reconsidered_when_send_metadata_arrives_late():
    fingerprint = asyncio.run(receipt_fingerprint(read_batches=(("m", "a", "z"),)))
    message = fingerprint.exploit._sent_messages.pop("a")
    assert asyncio.run(fingerprint.analyze()).device_type == DeviceType.UNKNOWN
    asyncio.run(fingerprint.exploit.observe_sent_message(message))
    assert asyncio.run(fingerprint.analyze()).device_type == DeviceType.IPHONE
