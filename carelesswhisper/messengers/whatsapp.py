import asyncio
from collections.abc import Callable
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Coroutine, TypeVar
import threading

from .base import BaseMessenger, ReceiptEvent, SentMessage

from neonize.utils import build_jid
from neonize.aioze.events import ReceiptEv, ConnectedEv, MessageEv
from neonize.aioze.client import NewAClient
from neonize.exc import GetJIDFromStoreError, IsOnWhatsAppError
from neonize.proto.Neonize_pb2 import JID, MessageSource

logger = logging.getLogger(__name__)

CONNECTION_TIMEOUT_SECONDS = 30
CLIENT_STOP_TIMEOUT_SECONDS = 5
DEFAULT_REACTION = "👍"
T = TypeVar("T")


class _RetryReceiptNoiseFilter(logging.Filter):
    """Drops whatsmeow retry-receipt errors for unknown message IDs.

    Silent reactions reference message IDs that never existed, so the target's
    retry requests can never be satisfied and whatsmeow logs one ERROR per
    request. The noise is inherent to the technique and carries no diagnostic
    value, so it is filtered out of the whatsmeow.Client logger.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not (
            "Failed to handle retry receipt" in message
            and "couldn't find message" in message
        )


def _silence_retry_receipt_noise() -> None:
    client_logger = logging.getLogger("whatsmeow.Client")
    if not any(
        isinstance(existing, _RetryReceiptNoiseFilter)
        for existing in client_logger.filters
    ):
        client_logger.addFilter(_RetryReceiptNoiseFilter())


def normalize_phone_number(phone_number: str) -> str:
    """Returns a digits-only international number accepted by WhatsApp."""
    number = phone_number.strip()
    if number.startswith("+"):
        number = number[1:]

    for separator in (" ", "-", "(", ")"):
        number = number.replace(separator, "")

    if not number or not number.isascii() or not number.isdigit():
        raise ValueError(
            "Phone number must be an international number containing only digits, "
            "optionally prefixed with '+'."
        )

    return number


class WhatsAppMessenger(BaseMessenger):
    def __init__(
        self,
        on_delivered: Callable[[str], Coroutine[Any, Any, None]],
        session_path: str | Path = "careless-whisper.db",
    ):
        super().__init__(on_delivered=on_delivered)

        _silence_retry_receipt_noise()

        self.session_path = Path(session_path)
        self.client: NewAClient = self._create_client()

        self.message_send_times: dict[str, datetime] = {}  # Map message ID to send time
        self.delivery_times: dict[str, datetime] = {}  # Map message ID to delivery time
        self.connected = asyncio.Event()  # Event to signal when connected
        self._thread: threading.Thread | None = None
        self._setup_complete = False

    def _create_client(self) -> NewAClient:
        return NewAClient(str(self.session_path))

    async def _run_on_client_loop(self, coroutine: Coroutine[Any, Any, T]) -> T:
        client_loop = self.client.loop
        if client_loop is None or not client_loop.is_running():
            coroutine.close()
            raise RuntimeError("WhatsApp client is not connected.")

        if asyncio.get_running_loop() is client_loop:
            return await coroutine

        future = asyncio.run_coroutine_threadsafe(coroutine, client_loop)
        return await asyncio.wrap_future(future)

    async def is_on_platform(self, phone_number: str) -> bool | None:
        normalized_number = normalize_phone_number(phone_number)
        lookup_number = f"+{normalized_number}"
        try:
            result = await self._run_on_client_loop(
                self.client.is_on_whatsapp(lookup_number)
            )
        except IsOnWhatsAppError as exc:
            if str(exc) == "Function returned nothing.":
                logger.warning(
                    "WhatsApp returned no registration entry for %s.",
                    lookup_number,
                )
                return False
            raise RuntimeError(
                "WhatsApp could not check whether "
                f"{lookup_number} is registered: {exc}"
            ) from exc

        if not result:
            logger.warning(
                "WhatsApp returned no registration entry for %s.",
                lookup_number,
            )
            return False

        return result[0].IsIn

    async def start(self):
        """Starts the WhatsApp messenger by running neonize in a separate thread."""
        # Get the current event loop for cross-thread communication
        loop = asyncio.get_running_loop()

        # Define the startup function that will run in the event loop
        def run_loop():
            @self.client.event(ConnectedEv)
            async def on_connected(_: NewAClient, event: ConnectedEv):
                logger.info("WhatsApp client connected successfully")
                # Signal to asyncio that we're connected
                asyncio.run_coroutine_threadsafe(self._signal_connected(), loop)

            @self.client.event(ReceiptEv)
            async def on_receipt(_: NewAClient, receipt: ReceiptEv):
                future = asyncio.run_coroutine_threadsafe(
                    self._handle_message_delivery_receipt(receipt), loop
                )
                await asyncio.wrap_future(future)

            @self.client.event(MessageEv)
            async def on_message(_: NewAClient, message: MessageEv):
                future = asyncio.run_coroutine_threadsafe(
                    self._handle_sent_message(message), loop
                )
                await asyncio.wrap_future(future)

            # Start the client connection
            logger.info("Starting WhatsApp client connection...")
            logger.info(
                "📱 Check your terminal for the QR code, scan it with WhatsApp on your phone"
            )

            # Connect and start event processing.
            # neonize's connect() calls asyncio.get_running_loop() internally and
            # only populates client.loop once connected, so we need a running loop
            # in this thread. idle() keeps receiving events from the backend.
            async def _connect_and_idle():
                await self.client.connect()
                await self.client.idle()

            client_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(client_loop)
            client_loop.run_until_complete(_connect_and_idle())

        # Run neonize in a separate thread so it doesn't block asyncio
        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()

        logger.info("Neonize thread started")

    async def _signal_connected(self):
        """Signal that the connection is ready."""
        self.connected.set()
        self._setup_complete = True

    async def wait_until_ready(self) -> None:
        try:
            await asyncio.wait_for(
                self.connected.wait(), timeout=CONNECTION_TIMEOUT_SECONDS
            )
            return
        except TimeoutError:
            logger.warning(
                "WhatsApp login timed out. Clearing the stale session and retrying "
                "with a fresh QR code."
            )

        await self._reset_stale_session()
        await self.start()

        try:
            await asyncio.wait_for(
                self.connected.wait(), timeout=CONNECTION_TIMEOUT_SECONDS
            )
        except TimeoutError as exc:
            raise TimeoutError(
                "WhatsApp login timed out after clearing the saved session. "
                "Scan the QR code and retry."
            ) from exc

    async def _reset_stale_session(self) -> None:
        await self._stop_client()
        self._clear_session_files()
        self.connected.clear()
        self._setup_complete = False
        self.client = self._create_client()

    async def stop(self) -> None:
        await self._stop_client()

    async def _stop_client(self) -> None:
        client_loop = self.client.loop
        if client_loop and client_loop.is_running():
            stop_future = asyncio.run_coroutine_threadsafe(
                self.client.stop(), client_loop
            )
            try:
                await asyncio.wait_for(
                    asyncio.wrap_future(stop_future),
                    timeout=CLIENT_STOP_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                logger.warning("Timed out while stopping the failed WhatsApp client")
            except Exception:
                logger.exception("Failed to stop the failed WhatsApp client")

        if self._thread and self._thread.is_alive():
            await asyncio.to_thread(self._thread.join, CLIENT_STOP_TIMEOUT_SECONDS)

    def _clear_session_files(self) -> None:
        for suffix in ("", "-shm", "-wal"):
            session_file = Path(f"{self.session_path}{suffix}")
            try:
                session_file.unlink()
            except FileNotFoundError:
                continue

    async def send_silent_message(
        self, phone_number: str, reaction: str | None = None
    ) -> str:
        normalized_number = normalize_phone_number(phone_number)
        return await self._run_on_client_loop(
            self._send_silent_message(normalized_number, reaction)
        )

    async def _send_silent_message(
        self, phone_number: str, reaction: str | None = None
    ) -> str:
        chat = build_jid(phone_number)
        logger.info(
            "Sending silent reaction message to %s from %s",
            chat.User,
            self._get_my_phone_number(),
        )
        referenced_message_id = await self.client.generate_message_id()
        reaction = await self.client.build_reaction(
            chat=chat,
            sender=chat,
            message_id=referenced_message_id,
            reaction=reaction if reaction is not None else DEFAULT_REACTION,
        )
        response = await self.client.send_message(chat, reaction)

        # Delivery receipts refer to the reaction operation, not the
        # non-existent message ID referenced by it.
        return response.ID

    def _get_my_phone_number(self) -> str:
        return str(self.client.me.JID.User)  # type: ignore

    async def _is_target_jid(self, jid: JID, alternate: JID) -> bool:
        if not self.receipt_target or not jid.User:
            return False
        target = normalize_phone_number(self.receipt_target)
        if jid.Server == "s.whatsapp.net":
            return jid.User == target
        if jid.Server != "lid":
            return False
        if alternate.Server == "s.whatsapp.net" and alternate.User:
            return alternate.User == target
        # Receipts may omit sender_pn even when the session already knows the LID.
        try:
            resolved = await self._run_on_client_loop(self.client.get_pn_from_lid(jid))
        except GetJIDFromStoreError as exc:
            logger.warning(
                "Cannot resolve receipt LID from the local session store: %s", exc
            )
            return False
        if not resolved.User:
            logger.warning(
                "No phone-number mapping for LID %s; receipt evidence is not retained.",
                jid.User,
            )
            return False
        return resolved.Server == "s.whatsapp.net" and resolved.User == target

    async def _is_target_chat(self, source: MessageSource, *, outgoing: bool) -> bool:
        if source.IsGroup:
            return False
        alternate = source.RecipientAlt if outgoing else source.SenderAlt
        return await self._is_target_jid(source.Chat, alternate)

    async def _handle_sent_message(self, message: MessageEv) -> None:
        source = message.Info.MessageSource
        target = self.receipt_target
        if (
            self.on_message_sent is None
            or target is None
            or not source.IsFromMe
            or not await self._is_target_chat(source, outgoing=True)
        ):
            return
        if not message.Info.ID or message.Info.Timestamp <= 0:
            logger.warning(
                "Cannot record send order: outgoing message lacks ID or time."
            )
            return
        await self.on_message_sent(
            SentMessage(
                msg_id=message.Info.ID,
                phone_number=normalize_phone_number(target),
                sent_at=datetime.fromtimestamp(message.Info.Timestamp),
            )
        )

    async def _handle_message_delivery_receipt(self, receipt: ReceiptEv):
        received_at = datetime.now()
        logger.debug(
            "Received receipt type %s for message IDs: %s",
            receipt.ReceiptType.Name(receipt.Type),
            list(receipt.MessageIDs),
        )

        # Do not include identity-store lookups or evidence export in probe RTTs.
        if receipt.Type in (
            receipt.ReceiptType.DELIVERED,
            receipt.ReceiptType.INACTIVE,
        ):
            for message_id in receipt.MessageIDs:
                logger.info("Received delivery receipt for message ID: %s", message_id)
                await self.record_delivery(message_id)

        target = self.receipt_target
        event = None
        if (
            target is not None
            and self.on_receipt is not None
            and receipt.Type
            in (
                receipt.ReceiptType.DELIVERED,
                receipt.ReceiptType.INACTIVE,
                receipt.ReceiptType.READ,
            )
        ):
            source = receipt.MessageSource
            if not source.IsFromMe and await self._is_target_chat(
                source, outgoing=False
            ):
                sender = source.Sender
                target = normalize_phone_number(target)
                sender_matches = (
                    sender.User == source.Chat.User
                    and sender.Server == source.Chat.Server
                ) or await self._is_target_jid(sender, source.SenderAlt)
                if sender.User and sender_matches and receipt.MessageIDs:
                    event = ReceiptEvent(
                        phone_number=target,
                        sender_jid=f"{sender.User}:{sender.Device}@{sender.Server}",
                        device_id=sender.Device,
                        receipt_type=receipt.ReceiptType.Name(receipt.Type),
                        message_ids=tuple(receipt.MessageIDs),
                        received_at=received_at,
                    )
                else:
                    logger.debug("Ignoring receipt evidence without target sender IDs.")

        if event is not None and self.on_receipt is not None:
            await self.on_receipt(event)
