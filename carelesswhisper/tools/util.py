import logging
import asyncio
from typing import Any, Callable, Coroutine

from carelesswhisper.messengers.base import BaseMessenger
from carelesswhisper.exporters.base import BaseExporter


logger = logging.getLogger(__name__)


async def get_messenger(
    provider: str, on_delivered: Callable[[str], Coroutine[Any, Any, None]]
) -> BaseMessenger:
    if provider == "whatsapp":
        from carelesswhisper.messengers.whatsapp import WhatsAppMessenger

        return WhatsAppMessenger(on_delivered=on_delivered)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def get_exporter(exporter: str, target_phone_number: str) -> BaseExporter:
    if exporter == "csv":
        from carelesswhisper.exporters.csv import CSVExporter

        return CSVExporter(target_phone_number)
    else:
        raise ValueError(f"Unsupported exporter: {exporter}")


async def confirm_number(
    phone_number: str,
    messenger: BaseMessenger,
    ignore_unregistered_warning: bool = False,
) -> None:
    is_registered = await messenger.is_on_platform(phone_number)
    if not is_registered:
        logger.warning(
            f"The phone number {phone_number} is not registered on the platform."
        )

        if not ignore_unregistered_warning:
            logger.info(
                "Exiting due to unregistered phone number. Use --ignore-unregistered-warning to override."
            )
            exit(1)
    else:
        logger.info(f"The phone number {phone_number} is registered on the platform.")
