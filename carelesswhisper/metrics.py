from prometheus_client import CollectorRegistry, Gauge, Info, Summary, Counter

from carelesswhisper.fingerprint import (
    AppState,
    FingerprintAnalysis,
    OnlineStatus,
    PhoneState,
)
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

        self.gauge_phone_state = Gauge(
            "carelesswhisper_phone_state",
            "Current inferred phone screen state (1 for active state)",
            ["phone_number", "state"],
            registry=self.registry,
        )
        self.gauge_app_state = Gauge(
            "carelesswhisper_app_state",
            "Current inferred application state (1 for active state)",
            ["phone_number", "state"],
            registry=self.registry,
        )
        self.gauge_online_status = Gauge(
            "carelesswhisper_online_status",
            "Current inferred online status (1 for active state)",
            ["phone_number", "state"],
            registry=self.registry,
        )
        self.info_device = Info(
            "carelesswhisper_device",
            "Latest inferred device and receipt profile",
            ["phone_number"],
            registry=self.registry,
        )
        self.gauge_analysis_confidence = Gauge(
            "carelesswhisper_analysis_confidence",
            "Heuristic confidence score for each inference from 0 to 1",
            ["phone_number", "inference"],
            registry=self.registry,
        )
        self.gauge_companion_devices = Gauge(
            "carelesswhisper_companion_devices",
            "Number of inferred companion devices",
            ["phone_number"],
            registry=self.registry,
        )
        self.gauge_estimated_data_used = Gauge(
            "carelesswhisper_estimated_data_used_bytes",
            "Estimated cumulative data used by probing",
            ["phone_number"],
            registry=self.registry,
        )
        self.gauge_estimated_data_rate = Gauge(
            "carelesswhisper_estimated_data_rate_bytes_per_second",
            "Estimated probing data rate",
            ["phone_number"],
            registry=self.registry,
        )
        self.gauge_estimated_battery_drain = Gauge(
            "carelesswhisper_estimated_battery_drain_pct_per_hour",
            "Paper-derived estimated battery drain range",
            ["phone_number", "bound"],
            registry=self.registry,
        )

    def report_rtt(self, receipt_report: BaseReceiptReport) -> None:
        rtt_ms = receipt_report.delay
        phone_number = receipt_report.phone_number

        # Update the last RTT gauge
        self.gauge_last_rtt.labels(phone_number=phone_number).set(rtt_ms)

        # Observe the RTT in the summary
        self.summary_rtt.labels(phone_number=phone_number).observe(rtt_ms)

    def report_ran_ping(self, phone_number: str) -> None:
        self.counter_pings.labels(phone_number=phone_number).inc()

    def report_analysis(self, phone_number: str, analysis: FingerprintAnalysis) -> None:
        self._set_enum_state(
            self.gauge_phone_state,
            phone_number,
            PhoneState,
            analysis.phone_state,
        )
        self._set_enum_state(
            self.gauge_app_state,
            phone_number,
            AppState,
            analysis.app_state,
        )
        self._set_enum_state(
            self.gauge_online_status,
            phone_number,
            OnlineStatus,
            analysis.online_status,
        )

        receipt_structure = analysis.receipt_structure
        self.info_device.labels(phone_number=phone_number).info(
            {
                "device_type": analysis.device_type.value,
                "platform": (
                    receipt_structure.platform if receipt_structure else "Unknown"
                ),
                "messenger": (
                    receipt_structure.messenger if receipt_structure else "Unknown"
                ),
                "delivery_receipt_handling": (
                    receipt_structure.delivery_receipt_handling
                    if receipt_structure
                    else "Unknown"
                ),
                "read_receipt_handling": (
                    receipt_structure.read_receipt_handling
                    if receipt_structure
                    else "Unknown"
                ),
                "receipt_ordering": (
                    receipt_structure.receipt_ordering
                    if receipt_structure
                    else "Unknown"
                ),
            }
        )

        for inference, confidence in analysis.confidence_scores.items():
            self.gauge_analysis_confidence.labels(
                phone_number=phone_number,
                inference=inference,
            ).set(confidence)

        self.gauge_companion_devices.labels(phone_number=phone_number).set(
            len(analysis.companion_devices)
        )
        self.gauge_estimated_data_used.labels(phone_number=phone_number).set(
            analysis.total_data_used_bytes
        )
        self.gauge_estimated_data_rate.labels(phone_number=phone_number).set(
            analysis.estimated_data_rate_bytes_per_second
        )
        self.gauge_estimated_battery_drain.labels(
            phone_number=phone_number, bound="min"
        ).set(analysis.estimated_battery_drain_pct_per_hour_min)
        self.gauge_estimated_battery_drain.labels(
            phone_number=phone_number, bound="max"
        ).set(analysis.estimated_battery_drain_pct_per_hour_max)

    @staticmethod
    def _set_enum_state(gauge, phone_number, enum_type, active_value) -> None:
        for state in enum_type:
            gauge.labels(phone_number=phone_number, state=state.value).set(
                1 if state == active_value else 0
            )

    def start_server(self, port: int = 8000) -> None:
        from prometheus_client import start_http_server

        start_http_server(port, registry=self.registry)
