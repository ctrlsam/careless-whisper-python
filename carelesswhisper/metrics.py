from prometheus_client import CollectorRegistry, Gauge, Summary, Counter

from carelesswhisper.messengers.base import BaseReceiptReport


class Metrics:
    def __init__(self):
        self.registry = CollectorRegistry()

        # Counter to track total number of pings sent
        self.counter_pings = Counter(
            "carelesswhisper_pings_total",
            "Total number of pings sent",
            ["phone_number"],
            registry=self.registry,
        )

        # Gauge to track current activity (optional, for real-time monitoring)
        self.gauge_last_rtt = Gauge(
            "carelesswhisper_last_delivery_rtt_ms",
            "Last recorded Round-trip Time for a delivery receipt in milliseconds",
            ["phone_number"],
            registry=self.registry,
        )

        # Track the RTT and datetime for scatter plotting
        self.summary_rtt = Summary(
            "carelesswhisper_delivery_rtt_ms",
            "Summary of Round-trip Time for delivery receipts in milliseconds",
            ["phone_number"],
            registry=self.registry,
        )

        # Internal counter for request IDs
        self._request_id_counter = 0
        # TODO: Add metric for estimated data used by attack for the victim

    def report_rtt(self, receipt_report: BaseReceiptReport) -> None:
        rtt_ms = receipt_report.delay
        phone_number = receipt_report.phone_number

        # Update the last RTT gauge
        self.gauge_last_rtt.labels(phone_number=phone_number).set(rtt_ms)

        # Observe the RTT in the summary
        self.summary_rtt.labels(phone_number=phone_number).observe(rtt_ms)

    def report_ran_ping(self, phone_number: str) -> None:
        self.counter_pings.labels(phone_number=phone_number).inc()

    def start_server(self, port: int = 8000) -> None:
        from prometheus_client import start_http_server

        start_http_server(port, registry=self.registry)
