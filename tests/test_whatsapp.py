import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from neonize.exc import GetJIDFromStoreError, IsOnWhatsAppError
from neonize.aioze.events import MessageEv, ReceiptEv
from neonize.proto.Neonize_pb2 import JID, MessageInfo, MessageSource

import carelesswhisper.messengers.whatsapp as whatsapp_module
from carelesswhisper.messengers.base import BaseMessenger
from carelesswhisper.messengers.whatsapp import (
    WhatsAppMessenger,
    _silence_retry_receipt_noise,
    normalize_phone_number,
)


def test_retry_receipt_noise_is_filtered_without_dropping_other_errors():
    _silence_retry_receipt_noise()
    client_logger = logging.getLogger("whatsmeow.Client")

    noise = client_logger.makeRecord(
        client_logger.name,
        logging.ERROR,
        __file__,
        0,
        "Failed to handle retry receipt for a/b from c: couldn't find message b",
        None,
        None,
    )
    real_error = client_logger.makeRecord(
        client_logger.name,
        logging.ERROR,
        __file__,
        0,
        "server returned error 479",
        None,
        None,
    )

    assert not client_logger.filter(noise)
    assert client_logger.filter(real_error)


def test_silence_retry_receipt_noise_is_idempotent():
    client_logger = logging.getLogger("whatsmeow.Client")
    _silence_retry_receipt_noise()
    _silence_retry_receipt_noise()
    from carelesswhisper.messengers.whatsapp import _RetryReceiptNoiseFilter

    assert (
        sum(
            isinstance(existing, _RetryReceiptNoiseFilter)
            for existing in client_logger.filters
        )
        == 1
    )


@pytest.mark.parametrize(
    ("phone_number", "expected"),
    [
        ("+6422500155", "6422500155"),
        ("64 22 500 155", "6422500155"),
        ("+64 (22) 500-155", "6422500155"),
    ],
)
def test_normalize_phone_number(phone_number, expected):
    assert normalize_phone_number(phone_number) == expected


@pytest.mark.parametrize("phone_number", ["", "+", "64abc", "64.225"])
def test_normalize_phone_number_rejects_invalid_input(phone_number):
    with pytest.raises(ValueError, match="international number"):
        normalize_phone_number(phone_number)


def test_is_on_platform_uses_normalized_number():
    messenger = object.__new__(WhatsAppMessenger)
    messenger.client = SimpleNamespace(
        loop=None, is_on_whatsapp=AsyncMock(return_value=[SimpleNamespace(IsIn=True)])
    )

    async def run_test():
        messenger.client.loop = asyncio.get_running_loop()
        return await messenger.is_on_platform("+6422500155")

    result = asyncio.run(run_test())

    assert result is True
    messenger.client.is_on_whatsapp.assert_awaited_once_with("+6422500155")


def test_is_on_platform_treats_empty_neonize_response_as_unregistered():
    messenger = object.__new__(WhatsAppMessenger)
    messenger.client = SimpleNamespace(
        loop=None,
        is_on_whatsapp=AsyncMock(
            side_effect=IsOnWhatsAppError("Function returned nothing.")
        ),
    )

    async def run_test():
        messenger.client.loop = asyncio.get_running_loop()
        return await messenger.is_on_platform("+6422500155")

    assert asyncio.run(run_test()) is False


def test_all_message_ids_in_stacked_receipt_are_recorded():
    recorded_ids = []

    async def on_delivered(message_id: str) -> None:
        recorded_ids.append(message_id)

    messenger = object.__new__(WhatsAppMessenger)
    BaseMessenger.__init__(messenger, on_delivered)
    delivered_type = object()
    receipt = SimpleNamespace(
        Type=delivered_type,
        ReceiptType=SimpleNamespace(
            DELIVERED=delivered_type,
            INACTIVE=9,
            Name=lambda value: "DELIVERED",
        ),
        MessageIDs=["message-1", "message-2"],
    )

    asyncio.run(messenger._handle_message_delivery_receipt(receipt))

    assert recorded_ids == ["message-1", "message-2"]


def test_inactive_receipts_are_recorded():
    recorded_ids = []

    async def on_delivered(message_id: str) -> None:
        recorded_ids.append(message_id)

    messenger = object.__new__(WhatsAppMessenger)
    BaseMessenger.__init__(messenger, on_delivered)
    inactive_type = 9
    receipt = SimpleNamespace(
        Type=inactive_type,
        ReceiptType=SimpleNamespace(
            DELIVERED=1,
            INACTIVE=inactive_type,
            Name=lambda value: "INACTIVE",
        ),
        MessageIDs=["message-1"],
    )

    asyncio.run(messenger._handle_message_delivery_receipt(receipt))

    assert recorded_ids == ["message-1"]


def test_silent_message_uses_reaction_to_nonexistent_message():
    messenger = object.__new__(WhatsAppMessenger)
    messenger.client = SimpleNamespace(
        me=SimpleNamespace(JID=SimpleNamespace(User="64221406809")),
        generate_message_id=AsyncMock(return_value="referenced-message"),
        build_reaction=AsyncMock(return_value="reaction-message"),
        send_message=AsyncMock(return_value=SimpleNamespace(ID="reaction-operation")),
    )

    result = asyncio.run(messenger._send_silent_message("64225001550"))

    assert result == "reaction-operation"
    messenger.client.build_reaction.assert_awaited_once()
    reaction_call = messenger.client.build_reaction.await_args.kwargs
    assert reaction_call["chat"].User == "64225001550"
    assert reaction_call["sender"].User == "64225001550"
    assert reaction_call["message_id"] == "referenced-message"
    assert reaction_call["reaction"] == "👍"
    messenger.client.send_message.assert_awaited_once()


def test_wait_until_ready_clears_stale_session_and_retries(monkeypatch):
    messenger = object.__new__(WhatsAppMessenger)
    messenger.connected = asyncio.Event()
    messenger._reset_stale_session = AsyncMock()

    async def start_with_fresh_qr():
        messenger.connected.set()

    messenger.start = AsyncMock(side_effect=start_with_fresh_qr)
    monkeypatch.setattr(whatsapp_module, "CONNECTION_TIMEOUT_SECONDS", 0.01)

    asyncio.run(messenger.wait_until_ready())

    messenger._reset_stale_session.assert_awaited_once()
    messenger.start.assert_awaited_once()


def test_wait_until_ready_fails_after_single_retry(monkeypatch):
    messenger = object.__new__(WhatsAppMessenger)
    messenger.connected = asyncio.Event()
    messenger._reset_stale_session = AsyncMock()
    messenger.start = AsyncMock()
    monkeypatch.setattr(whatsapp_module, "CONNECTION_TIMEOUT_SECONDS", 0.01)

    try:
        asyncio.run(messenger.wait_until_ready())
    except TimeoutError as error:
        assert "after clearing the saved session" in str(error)
    else:
        raise AssertionError("Expected login retry to time out")

    messenger._reset_stale_session.assert_awaited_once()
    messenger.start.assert_awaited_once()


def test_clear_session_files_removes_sqlite_sidecars(tmp_path):
    messenger = object.__new__(WhatsAppMessenger)
    messenger.session_path = tmp_path / "whatsapp.db"
    session_files = [
        messenger.session_path,
        Path(f"{messenger.session_path}-shm"),
        Path(f"{messenger.session_path}-wal"),
    ]
    for session_file in session_files:
        session_file.touch()

    messenger._clear_session_files()

    assert all(not session_file.exists() for session_file in session_files)


def receipt_messenger():
    messenger = object.__new__(WhatsAppMessenger)
    BaseMessenger.__init__(messenger, AsyncMock())
    messenger.receipt_target = "+123456789"
    messenger.on_receipt = AsyncMock()
    messenger.on_message_sent = AsyncMock()
    return messenger


def target_source(device=0):
    return MessageSource(
        Chat=JID(User="123456789", Server="s.whatsapp.net"),
        Sender=JID(User="123456789", Server="s.whatsapp.net", Device=device),
    )


@pytest.mark.parametrize("kind", ["DELIVERED", "INACTIVE", "READ"])
def test_protocol_receipt_preserves_batch_order_and_device(kind):
    messenger = receipt_messenger()
    receipt = ReceiptEv(
        MessageSource=target_source(device=7),
        MessageIDs=["third", "first", "second"],
        Type=ReceiptEv.ReceiptType.Value(kind),
    )

    asyncio.run(messenger._handle_message_delivery_receipt(receipt))

    event = messenger.on_receipt.await_args.args[0]
    assert event.message_ids == ("third", "first", "second")
    assert event.receipt_type == kind
    assert event.device_id == 7
    assert event.sender_jid == "123456789:7@s.whatsapp.net"
    assert event.phone_number == "123456789"
    assert messenger.on_delivered.await_count == (0 if kind == "READ" else 3)


@pytest.mark.parametrize(
    "variant", ["other", "group", "self", "read_self", "no_sender"]
)
def test_receipt_evidence_excludes_unrelated_or_ambiguous_sources(variant):
    messenger = receipt_messenger()
    source = target_source()
    kind = ReceiptEv.ReceiptType.READ
    if variant == "other":
        source.Chat.User = source.Sender.User = "987654321"
    elif variant == "group":
        source.IsGroup = True
    elif variant == "self":
        source.IsFromMe = True
    elif variant == "read_self":
        kind = ReceiptEv.ReceiptType.READ_SELF
    else:
        source.ClearField("Sender")
    receipt = ReceiptEv(
        MessageSource=source, MessageIDs=["third", "second", "first"], Type=kind
    )

    asyncio.run(messenger._handle_message_delivery_receipt(receipt))

    messenger.on_receipt.assert_not_awaited()
    messenger.on_delivered.assert_not_awaited()


@pytest.mark.parametrize("chat_server", ["lid", "s.whatsapp.net"])
def test_lid_receipts_use_alias_or_local_store_mapping(chat_server):
    messenger = receipt_messenger()
    source = MessageSource(
        Chat=JID(
            User="opaque-id" if chat_server == "lid" else "123456789",
            Server=chat_server,
        ),
        Sender=JID(User="opaque-id", Server="lid", Device=0),
        SenderAlt=JID(User="123456789", Server="s.whatsapp.net"),
    )
    receipt = ReceiptEv(
        MessageSource=source,
        MessageIDs=["third", "second", "first"],
        Type=ReceiptEv.ReceiptType.READ,
    )
    asyncio.run(messenger._handle_message_delivery_receipt(receipt))
    assert messenger.on_receipt.await_args.args[0].sender_jid == "opaque-id:0@lid"

    messenger.on_receipt.reset_mock()
    receipt.MessageSource.ClearField("SenderAlt")
    messenger.client = SimpleNamespace(
        loop=None,
        get_pn_from_lid=AsyncMock(
            return_value=JID(User="123456789", Server="s.whatsapp.net")
        ),
    )

    async def receive():
        messenger.client.loop = asyncio.get_running_loop()
        await messenger._handle_message_delivery_receipt(receipt)

    asyncio.run(receive())
    assert messenger.on_receipt.await_args.args[0].sender_jid == "opaque-id:0@lid"
    messenger.client.get_pn_from_lid.assert_awaited_once()

    messenger.on_receipt.reset_mock()
    messenger.client.get_pn_from_lid.return_value = JID(
        User="987654321", Server="s.whatsapp.net"
    )
    asyncio.run(receive())
    messenger.on_receipt.assert_not_awaited()


@pytest.mark.parametrize("lookup_error", [False, True])
def test_unresolved_lid_is_reported_without_losing_rtt_delivery(caplog, lookup_error):
    messenger = receipt_messenger()
    messenger.client = SimpleNamespace(
        loop=None,
        get_pn_from_lid=AsyncMock(
            return_value=JID(),
            side_effect=GetJIDFromStoreError("lookup failed") if lookup_error else None,
        ),
    )
    receipt = ReceiptEv(
        MessageSource=MessageSource(
            Chat=JID(User="opaque-id", Server="lid"),
            Sender=JID(User="opaque-id", Server="lid", Device=0),
        ),
        MessageIDs=["message-1"],
        Type=ReceiptEv.ReceiptType.DELIVERED,
    )

    async def receive():
        messenger.client.loop = asyncio.get_running_loop()
        await messenger._handle_message_delivery_receipt(receipt)

    asyncio.run(receive())
    messenger.on_receipt.assert_not_awaited()
    messenger.on_delivered.assert_awaited_once_with("message-1")
    assert "LID" in caplog.text


def test_outgoing_lid_chat_uses_local_store_without_recipient_alias():
    messenger = receipt_messenger()
    messenger.client = SimpleNamespace(
        loop=None,
        get_pn_from_lid=AsyncMock(
            return_value=JID(User="123456789", Server="s.whatsapp.net")
        ),
    )
    message = MessageEv(
        Info=MessageInfo(
            MessageSource=MessageSource(
                Chat=JID(User="opaque-id", Server="lid"), IsFromMe=True
            ),
            ID="ordinary-message",
            Timestamp=1700000000,
        )
    )

    async def receive():
        messenger.client.loop = asyncio.get_running_loop()
        await messenger._handle_sent_message(message)

    asyncio.run(receive())
    assert messenger.on_message_sent.await_args.args[0].phone_number == "123456789"


def test_outgoing_target_message_records_send_time_without_creating_rtt():
    messenger = receipt_messenger()
    source = target_source()
    source.IsFromMe = True
    message = MessageEv(
        Info=MessageInfo(
            MessageSource=source, ID="ordinary-message", Timestamp=1700000000
        )
    )

    asyncio.run(messenger._handle_sent_message(message))

    observed = messenger.on_message_sent.await_args.args[0]
    assert observed.msg_id == "ordinary-message"
    assert observed.sent_at.timestamp() == 1700000000
    messenger.on_delivered.assert_not_awaited()

    messenger.on_message_sent.reset_mock()
    message.Info.MessageSource.IsFromMe = False
    asyncio.run(messenger._handle_sent_message(message))
    messenger.on_message_sent.assert_not_awaited()

    message.Info.MessageSource.IsFromMe = True
    message.Info.MessageSource.Chat.User = "987654321"
    asyncio.run(messenger._handle_sent_message(message))
    messenger.on_message_sent.assert_not_awaited()


def test_scan_refreshes_analysis_on_read_receipt_and_late_message_echo(tmp_path):
    from carelesswhisper.exploit import Exploit
    from carelesswhisper.exporters.jsonl import JSONLinesExporter
    from carelesswhisper.fingerprint import DeviceType, Fingerprint
    from carelesswhisper.tools.fingerprint.main import start

    messenger = receipt_messenger()
    messenger.is_on_platform = AsyncMock(return_value=True)
    exploit = Exploit("+123456789")
    fingerprint = Fingerprint(exploit)
    exporter = JSONLinesExporter(exploit.phone_number, save_directory=str(tmp_path))
    analyses = []

    async def on_analysis(analysis):
        analyses.append(analysis)

    async def simulate_test_messages(_):
        source = target_source()
        source.IsFromMe = True
        for msg_id, timestamp in (("z", 1700000000), ("m", 1700000002)):
            await messenger._handle_sent_message(
                MessageEv(
                    Info=MessageInfo(
                        MessageSource=source, ID=msg_id, Timestamp=timestamp
                    )
                )
            )
        for msg_id in ("z", "a", "m"):
            await messenger._handle_message_delivery_receipt(
                ReceiptEv(
                    MessageSource=target_source(),
                    MessageIDs=[msg_id],
                    Type=ReceiptEv.ReceiptType.DELIVERED,
                )
            )
        await messenger._handle_message_delivery_receipt(
            ReceiptEv(
                MessageSource=target_source(),
                MessageIDs=["m", "a", "z"],
                Type=ReceiptEv.ReceiptType.READ,
            )
        )
        assert analyses[-1].device_type == DeviceType.UNKNOWN
        await messenger._handle_sent_message(
            MessageEv(
                Info=MessageInfo(MessageSource=source, ID="a", Timestamp=1700000001)
            )
        )
        exploit.running = False
        return "probe-operation"

    messenger.send_silent_message = simulate_test_messages
    settings = SimpleNamespace(
        phone_number=exploit.phone_number,
        provider="whatsapp",
        metrics=False,
        metrics_port=8000,
        concurrent_requests=1,
        delay_between_requests=0,
        ignore_unregistered_warning=False,
    )
    asyncio.run(
        start(
            messenger, exploit, fingerprint, settings, exporter, on_analysis=on_analysis
        )
    )

    assert analyses[-1].device_type == DeviceType.IPHONE
    assert exploit.get_reports() == []
    assert len(exploit.get_receipt_events()) == 4
    assert '"receipt_type":"READ"' in exporter.file_path.read_text()
