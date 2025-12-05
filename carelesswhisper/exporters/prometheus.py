from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

from .base import BaseExporter
from carelesswhisper.messengers.base import BaseReceiptReport


class PrometheusExporter(BaseExporter):
    def __init__(self, target_phone_number: str, pushgateway_address: str = "localhost:9091"):
        super().__init__(target_phone_number)

        self.pushgateway_address = pushgateway_address
        self.registry = CollectorRegistry()
        self.gauge = Gauge(
            "carelesswhisper_read_receipt_delay_milliseconds",
            "Read receipt delay in milliseconds",
            ["phone_number"],
            registry=self.registry
        )

    def save_receipt_report(self, receipt_report: BaseReceiptReport) -> None:
        self.gauge.labels(phone_number=receipt_report.phone_number).set(receipt_report.delay)
        push_to_gateway(self.pushgateway_address, job="careless_whisper", registry=self.registry)
