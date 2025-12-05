import logging
from time import sleep

from carelesswhisper.messengers.base import BaseMessenger, ReceiptTimeoutError


logger = logging.getLogger(__name__)


def get_messager(provider: str) -> BaseMessenger:
    if provider == "whatsapp":
        from carelesswhisper.messengers.whatsapp import WhatsAppMessenger
        whatsapp = WhatsAppMessenger()
        whatsapp.start()
        return whatsapp
    else:
        raise ValueError(f"Unsupported provider: {provider}")  


def get_exporter(exporter: str, target_phone_number: str):
    if exporter == "csv":
        from carelesswhisper.exporters.csv import CSVExporter
        return CSVExporter(target_phone_number)
    elif exporter == "prometheus":
        from carelesswhisper.exporters.prometheus import PrometheusExporter
        return PrometheusExporter(target_phone_number)
    else:
        raise ValueError(f"Unsupported exporter: {exporter}")


def start(messenger: BaseMessenger, exporter, phone_number: str, delay_between_requests: float = 1):
    request_count = 0

    if not messenger.is_on_platform(phone_number):
        logger.warning(f"⚠️ The phone number {phone_number} is not registered on the platform.")
    else:
        logger.info(f"✅ The phone number {phone_number} is registered on the platform.")

    while True:
        try:
            report = messenger.get_delivery_delay(phone_number)
        except ReceiptTimeoutError as e:
            logger.warning(str(e))
            continue
        finally:
            request_count += 1

        logger.info(f"Read receipt delay: {report.delay} milliseconds")
        exporter.save_receipt_report(report)
        sleep(delay_between_requests)


if __name__ == "__main__":
    from carelesswhisper.args import args

    phone_number = args.phone_number
    if not phone_number:
        phone_number = input("Enter phone number to test read receipt delay: ")

    messenger = get_messager(args.provider)
    exporter = get_exporter(args.exporter, phone_number)
    
    logger.info(
        f"Starting to scan {phone_number} on the {args.provider.capitalize()} messenger provider."
        f" Using exporter: {args.exporter}"
        )

    start(messenger, exporter, phone_number)
