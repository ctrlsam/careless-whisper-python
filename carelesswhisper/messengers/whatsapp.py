import random
import logging
from time import sleep, time

from .base import BaseMessenger, BaseReceiptReport, ReceiptTimeoutError

from neonize.utils import build_jid
from neonize.events import ReceiptEv
from neonize.client import ClientFactory, NewClient

logger = logging.getLogger(__name__)


class WhatsAppMessenger(BaseMessenger):
    def __init__(self):
        self.client_factory: ClientFactory = ClientFactory()
        self.client = self.client_factory.new_client(uuid="test")

        self.message_send_times: dict[str, int] = {}  # Map message ID to send time
        self.delivery_times: dict[str, int] = {}      # Map message ID to delivery time

    def is_on_platform(self, phone_number: str) -> bool:
        return self.client.is_on_whatsapp(phone_number)[0].IsIn

    def start(self):
        # Set up event handler for delivery receipts
        @self.client.event(ReceiptEv)
        def on_receipt(_: NewClient, receipt: ReceiptEv):
            self._handle_message_delivery_receipt(receipt)

        # Start the client in a separate thread
        self.client_factory.run()
        while not self.client.is_logged_in or not self.client.is_connected:
            logger.info("Waiting for WhatsApp Web login...")
            sleep(2)

    def _handle_message_delivery_receipt(self, receipt: ReceiptEv):
        # Filter for delivery receipts only
        if receipt.Type != receipt.ReceiptType.DELIVERED:
            return

        # Log the receipt and record delivery time
        logger.info(f"Received delivery receipt: {receipt}")
        message_id = receipt.MessageIDs[0]
        if message_id in self.message_send_times:
            self.delivery_times[message_id] = receipt.Timestamp

    def get_delivery_delay(self, phone_number: str, timeout: int = 5) -> BaseReceiptReport:
        # Send a silent message to trigger delivery receipt
        msg_id, sent_timestamp = self._send_silent_message(phone_number)
        logger.info(f"Sent silent message to {phone_number} to trigger delivery receipt (ID: {msg_id})")
        
        # Record the send time
        self.message_send_times[msg_id] = sent_timestamp

        # Wait for delivery receipt
        start_wait = time()
        while msg_id not in self.delivery_times:
            if time() - start_wait > timeout:
                self.message_send_times.pop(msg_id, None) # Clean up entries on timeout
                raise ReceiptTimeoutError(f"Timeout waiting for delivery receipt for message {msg_id}")
            sleep(0.1)

        # Pop both entries to clean up
        delivery_time = self.delivery_times.pop(msg_id)
        sent_time = self.message_send_times.pop(msg_id)

        return BaseReceiptReport(
            phone_number=phone_number,
            sent_at=sent_time,
            delieverd_at=delivery_time
        )

    def _send_silent_message(self, phone_number: str) -> tuple[str, int]:
        # Send a reaction message to a non-existent message ID to avoid user notification
        jid = build_jid(phone_number)
        reaction = random.choice(["👍", "👎", "😂", "❤️", "😮", "😢", "🙏", "🔥", "💯"])
        response = self.client.send_message(jid, reaction)

        return response.ID, response.Timestamp
