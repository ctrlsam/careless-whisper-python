import asyncio
import logging
from datetime import datetime

from .base import BaseMessenger, BaseReceiptReport, ReceiptTimeoutError

from neonize.utils import build_jid
from neonize.aioze.events import ReceiptEv, ConnectedEv
from neonize.aioze.client import NewAClient

logger = logging.getLogger(__name__)


def get_neonize_event_loop_runner():
    """
    Returns neonize's event loop runner.
    
    Neonize manages its own event loop via NewAClient.
    This function provides access to that loop without needing to instantiate the messenger.
    """
    client = NewAClient("careless-whisper.db")
    return lambda coro: client.loop.run_until_complete(coro)


class WhatsAppMessenger(BaseMessenger):
    def __init__(self):
        self.client: NewAClient = NewAClient("careless-whisper.db")
        self.message_send_times: dict[str, datetime] = {}  # Map message ID to send time
        self.delivery_times: dict[str, datetime] = {}      # Map message ID to delivery time
        self.connected = asyncio.Event()                   # Event to signal when connected

    async def is_on_platform(self, phone_number: str) -> bool:
        result = await self.client.is_on_whatsapp(phone_number)
        return result[0].IsIn

    async def start(self):
        @self.client.event(ConnectedEv)
        async def on_connected(_: NewAClient, event: ConnectedEv):
            logger.info("WhatsApp client connected successfully")
            self.connected.set()

        @self.client.event(ReceiptEv)
        async def on_receipt(_: NewAClient, receipt: ReceiptEv):
            await self._handle_message_delivery_receipt(receipt)

        # Start the client connection
        logger.info("Starting WhatsApp client connection...")
        logger.info("📱 Check your terminal for the QR code, scan it with WhatsApp on your phone")

        # Connect and start event processing
        # idle() is necessary to keep receiving events from the backend
        await self.client.connect()
        await self.client.idle()

    async def wait_until_ready(self) -> None:
        """
        Waits until the WhatsApp client is connected and ready.
        The ConnectedEv event fires after authentication, so we use a timeout
        to allow the connection to establish even if the event doesn't fire immediately.
        """
        try:
            # Wait for up to 30 seconds for the connection event
            await asyncio.wait_for(self.connected.wait(), timeout=30)
        except asyncio.TimeoutError:
            logger.debug("Connection event not received yet, waiting a moment...")
            await asyncio.sleep(2)

    async def _handle_message_delivery_receipt(self, receipt: ReceiptEv):
        # Filter for delivery receipts only
        if receipt.Type != receipt.ReceiptType.DELIVERED:
            return

        # Log the receipt and record delivery time
        logger.info(f"Received delivery receipt: {receipt}")
        message_id = receipt.MessageIDs[0]
        if message_id in self.message_send_times:
            #self.delivery_times[message_id] = receipt.Timestamp
            self.delivery_times[message_id] = datetime.now()

    async def get_rtt(self, phone_number: str, timeout: int = 5) -> BaseReceiptReport:
        # Send a silent message to trigger delivery receipt
        msg_id = await self._send_silent_message(phone_number)
        logger.info(f"Sent silent message to {phone_number} to trigger delivery receipt (ID: {msg_id})")
        
        # Record the send time
        self.message_send_times[msg_id] = datetime.now()

        # Wait for delivery receipt with timeout
        start_wait = datetime.now()
        while msg_id not in self.delivery_times:
            if (datetime.now() - start_wait).total_seconds() > timeout:
                self.message_send_times.pop(msg_id, None)  # Clean up entries on timeout
                raise ReceiptTimeoutError(f"Timeout waiting for delivery receipt for message {msg_id}")
            await asyncio.sleep(0.1)

        # Pop both entries to clean up
        delivery_time = self.delivery_times.pop(msg_id)
        sent_time = self.message_send_times.pop(msg_id)

        return BaseReceiptReport(
            phone_number=phone_number,
            sent_at=sent_time,
            delivered_at=delivery_time
        )

    async def _send_silent_message(self, phone_number: str) -> str: #tuple[str, int]:
        # Send a reaction message to a non-existent message ID to avoid user notification
        chat = build_jid(phone_number)
        sender = build_jid('64221406809') # str(self.client.jid)

        logger.info(f"Sending silent pin message to {chat} from {str(self.client.jid)}")
        msg_id = await self.client.generate_message_id()
        response = await self.client.pin_message(chat_jid=chat, sender_jid=sender, message_id=msg_id, seconds=1)

        return response.ID#, response.Timestamp  # type: ignore
