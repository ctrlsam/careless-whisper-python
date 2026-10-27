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
    elif exporter == "jsonl":
        from carelesswhisper.exporters.jsonl import JSONLinesExporter

        return JSONLinesExporter(target_phone_number)
    elif exporter == "sqlite":
        from carelesswhisper.exporters.sqlite import SQLiteExporter

        return SQLiteExporter(target_phone_number)
    else:
        raise ValueError(
            f"Unsupported exporter: {exporter}. Choose csv, jsonl, or sqlite."
        )


async def confirm_number(
    phone_number: str,
    messenger: BaseMessenger,
    ignore_unregistered_warning: bool = False,
) -> None:
    is_registered = await messenger.is_on_platform(phone_number)
    if is_registered is None:
        logger.warning(
            "Could not verify whether %s is registered on the platform.",
            phone_number,
        )
    elif not is_registered:
        logger.warning(
            f"The phone number {phone_number} is not registered on the platform."
        )

        if not ignore_unregistered_warning:
            raise ValueError(
                "Phone number is not registered on the platform. "
                "Use --ignore-unregistered-warning to override."
            )
    else:
        logger.info(f"The phone number {phone_number} is registered on the platform.")
