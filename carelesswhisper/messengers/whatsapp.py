import asyncio
from collections.abc import Callable
import logging
from datetime import datetime
from typing import Any, Coroutine
import threading

from .base import BaseMessenger

from neonize.utils import build_jid
from neonize.aioze.events import ReceiptEv, ConnectedEv
from neonize.aioze.client import NewAClient

logger = logging.getLogger(__name__)


class WhatsAppMessenger(BaseMessenger):
    def __init__(self, on_delivered: Callable[[str], Coroutine[Any, Any, None]]):
        super().__init__(on_delivered=on_delivered)

        self.client: NewAClient = NewAClient("careless-whisper.db")

        self.message_send_times: dict[str, datetime] = {}  # Map message ID to send time
        self.delivery_times: dict[str, datetime] = {}  # Map message ID to delivery time
        self.connected = asyncio.Event()  # Event to signal when connected
        self._thread: threading.Thread | None = None
        self._setup_complete = False

    async def is_on_platform(self, phone_number: str) -> bool:
        result = await self.client.is_on_whatsapp(phone_number)
        return result[0].IsIn

    async def start(self):
        """Starts the WhatsApp messenger by running neonize in a separate thread."""
        # Get the current event loop for cross-thread communication
        loop = asyncio.get_event_loop()

        # Define the startup function that will run in the event loop
        def run_loop():
            @self.client.event(ConnectedEv)
            async def on_connected(_: NewAClient, event: ConnectedEv):
                logger.info("WhatsApp client connected successfully")
                # Signal to asyncio that we're connected
                asyncio.run_coroutine_threadsafe(self._signal_connected(), loop)

            @self.client.event(ReceiptEv)
            async def on_receipt(_: NewAClient, receipt: ReceiptEv):
                await self._handle_message_delivery_receipt(receipt)

            # Start the client connection
            logger.info("Starting WhatsApp client connection...")
            logger.info(
                "📱 Check your terminal for the QR code, scan it with WhatsApp on your phone"
            )

            # Connect and start event processing
            # idle() is necessary to keep receiving events from the backend
            self.client.loop.run_until_complete(self.client.connect())
            self.client.loop.run_until_complete(self.client.idle())

        # Run neonize in a separate thread so it doesn't block asyncio
        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()

        logger.info("Neonize thread started")

    async def _signal_connected(self):
        """Signal that the connection is ready."""
        self.connected.set()
        self._setup_complete = True

    async def wait_until_ready(self) -> None:
        await asyncio.wait_for(self.connected.wait(), timeout=30)

    async def send_silent_message(self, phone_number: str) -> str:
        chat = build_jid(phone_number)
        sender = build_jid(self._get_my_phone_number())

        logger.info(f"Sending silent pin message to {chat.User} from {sender.User}")
        msg_id = await self.client.generate_message_id()
        # Send a reaction message to a non-existent message ID to avoid user notification
        response = await self.client.pin_message(
            chat_jid=chat, sender_jid=sender, message_id=msg_id, seconds=1
        )

        return response.ID

    def _get_my_phone_number(self) -> str:
        return str(self.client.me.JID.User)  # type: ignore

    async def _handle_message_delivery_receipt(self, receipt: ReceiptEv):
        # Filter for delivery receipts only
        if receipt.Type != receipt.ReceiptType.DELIVERED:
            return

        logger.info(
            f"Received delivery receipt for message ID: {receipt.MessageIDs[0]}"
        )
        await self.record_delivery(receipt.MessageIDs[0])
