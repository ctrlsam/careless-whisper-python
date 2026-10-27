from datetime import datetime

from carelesswhisper.fingerprint import (
    AppState,
    DeviceType,
    FingerprintAnalysis,
    OnlineStatus,
    PhoneState,
)
from carelesswhisper.metrics import Metrics


def test_analysis_metrics_publish_inferred_state_and_impact():
    metrics = Metrics()
    analysis = FingerprintAnalysis(
        analyzed_at=datetime.now(),
        phone_state=PhoneState.SCREEN_ON,
        app_state=AppState.APP_FOREGROUND,
        total_data_used_bytes=600,
        estimated_data_rate_bytes_per_second=300,
        estimated_battery_drain_pct_per_hour_min=1,
        estimated_battery_drain_pct_per_hour_max=5,
        device_type=DeviceType.IPHONE,
        avg_rtt_ms=125,
        median_rtt_ms=125,
        rtt_stdev_ms=5,
        total_requests=2,
        online_status=OnlineStatus.ONLINE,
        confidence_scores={"overall": 0.8},
    )

    metrics.report_analysis("123456789", analysis)

    assert (
        metrics.registry.get_sample_value(
            "carelesswhisper_phone_state",
            {"phone_number": "123456789", "state": "SCREEN_ON"},
        )
        == 1
    )
    assert (
        metrics.registry.get_sample_value(
            "carelesswhisper_app_state",
            {"phone_number": "123456789", "state": "APP_FOREGROUND"},
        )
        == 1
    )
    assert (
        metrics.registry.get_sample_value(
            "carelesswhisper_analysis_confidence",
            {"phone_number": "123456789", "inference": "overall"},
        )
        == 0.8
    )
    assert (
        metrics.registry.get_sample_value(
            "carelesswhisper_estimated_data_used_bytes",
            {"phone_number": "123456789"},
        )
        == 600
    )
    assert (
        metrics.registry.get_sample_value(
            "carelesswhisper_estimated_battery_drain_pct_per_hour",
            {"phone_number": "123456789", "bound": "max"},
        )
        == 5
    )
    assert (
        metrics.registry.get_sample_value(
            "carelesswhisper_device_info",
            {
                "phone_number": "123456789",
                "device_type": "iPhone",
                "platform": "Unknown",
                "messenger": "Unknown",
                "delivery_receipt_handling": "Unknown",
                "read_receipt_handling": "Unknown",
                "receipt_ordering": "Unknown",
            },
        )
        == 1
    )
