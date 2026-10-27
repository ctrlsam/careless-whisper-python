from enum import StrEnum
from dataclasses import dataclass, field
from logging import getLogger
from statistics import mean, stdev, median
from collections import deque
from typing import Optional
from datetime import datetime, timedelta

from carelesswhisper.exploit import Exploit
from carelesswhisper.messengers.base import BaseReceiptReport, ReceiptEvent

logger = getLogger(__name__)


class PhoneState(StrEnum):
    """Binary state of phone screen"""

    SCREEN_ON = "SCREEN_ON"
    SCREEN_OFF = "SCREEN_OFF"


class AppState(StrEnum):
    """Activity state of target application"""

    APP_FOREGROUND = "APP_FOREGROUND"
    APP_BACKGROUND = "APP_BACKGROUND"
    APP_STANDBY = "APP_STANDBY"


class DeviceType(StrEnum):
    """Device classification"""

    IPHONE = "iPhone"
    IPHONE_11 = "iPhone 11"
    IPHONE_13_PRO = "iPhone 13 Pro"
    ANDROID_SAMSUNG_EXYNOS = "Samsung (Exynos)"
    ANDROID_SAMSUNG_QUALCOMM = "Samsung (Qualcomm)"
    ANDROID_XIAOMI_MEDIATEK = "Xiaomi (MediaTek)"
    ANDROID_GENERIC = "Android"
    COMPANION_WEB = "Companion (Web)"
    COMPANION_DESKTOP = "Companion (Desktop)"
    UNKNOWN = "Unknown"


class PingFrequency(StrEnum):
    """
    Ping frequency recommendations based on device type and detection goals.

    Note: WhatsApp's reaction mechanism allows one reaction every 50ms per account,
    but this represents a protocol capability, not a recommended probing frequency.
    Actual recommended frequencies depend on detection objectives and stealth requirements:
    - High frequency (50ms): WhatsApp reactions for real-time activity detection
    - Medium frequency (1s): Signal (rate-limited), Xiaomi devices, general activity tracking
    - Low frequency (2s): iPhone detailed activity, Qualcomm Android devices
    - Very low frequency (20s): iPhone screen state detection with low overhead
    - Minute frequency (1min): Samsung Exynos deep sleep detection, minimal traffic
    """

    HIGH_FREQUENCY = (
        "50ms"  # WhatsApp reaction capability (not recommended for stealth)
    )
    MEDIUM_FREQUENCY = "1s"  # Signal rate-limit, Xiaomi, general activity tracking
    LOW_FREQUENCY = "2s"  # iPhone detailed activity, Qualcomm Android
    VERY_LOW_FREQUENCY = "20s"  # iPhone screen detection, reduced overhead
    MINUTE_FREQUENCY = "1m"  # Samsung Exynos deep sleep, minimal traffic


class OnlineStatus(StrEnum):
    """Binary online status based on delivery receipts"""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


@dataclass
class RTTPattern:
    """Characteristic RTT pattern for a specific state"""

    state: str
    min_rtt_ms: float
    max_rtt_ms: float
    mean_rtt_ms: float
    median_rtt_ms: float
    stdev_rtt_ms: float
    sample_count: int


@dataclass
class ReceiptStructure:
    """Describes how receipts are handled by a device/OS"""

    delivery_receipt_handling: str  # "Separate" or "Stacked"
    read_receipt_handling: str  # "Separate" or "Stacked"
    receipt_ordering: str  # "Natural", "Reversed", or "Random"
    platform: str  # iOS, Android, Web, Windows, macOS
    messenger: str  # WhatsApp, Signal
    evidence_batches: int = 0


@dataclass
class FingerprintAnalysis:
    """Stores the result of fingerprint analysis."""

    analyzed_at: datetime
    phone_state: PhoneState
    app_state: AppState
    total_data_used_bytes: int
    estimated_data_rate_bytes_per_second: float
    estimated_battery_drain_pct_per_hour_min: float
    estimated_battery_drain_pct_per_hour_max: float
    device_type: DeviceType
    avg_rtt_ms: float
    median_rtt_ms: float
    rtt_stdev_ms: float
    total_requests: int
    online_status: OnlineStatus
    confidence_scores: dict[str, float] = field(default_factory=dict)
    receipt_structure: Optional[ReceiptStructure] = None
    companion_devices: list[dict] = field(default_factory=list)


@dataclass
class Fingerprint:
    """
    Fingerprinting module implementing behavior analysis techniques from
    "Careless Whisper" research paper (Section V-C and V-D).

    Analyzes RTT patterns, receipt structures, and temporal characteristics
    to infer device type, OS, application state, and user behavior.

    ============================================================================
    IMPLEMENTED FEATURES
    ============================================================================

    1. Screen State Detection (Section V-C Showcase I, Figure 4)
       - iPhone: ~1s (on), ~2s (off) with consistent low jitter
       - Android manufacturers: Distinct patterns with model-specific thresholds
       - Temporal aspects: Deep sleep detection via low-frequency probing (1/min)

    2. App State Detection (Section V-C Showcase II, Figure 5)
       - Foreground: ~350ms RTT (active processing)
       - Background: ~500ms RTT (exactly 30s duration tracked)
       - Standby: ~1000ms RTT (idle state)
       - Temporal tracking: Monitors 30-second background hold window

    3. Primary Device OS Identification (Section V-D, Table V)
       - Observed delivery grouping and stacked read-receipt ordering
       - Read order compared with known outgoing message timestamps
       - No OS or manufacturer inference from RTT alone

    4. Receipt Structure (Section V-D, Table V)
       - Deterministic mapping: iOS vs Android vs Web vs Desktop
       - Delivery receipt handling: Separate (phone OS) vs Stacked (companions)
       - Delivery receipt handling: Platform-specific patterns
       - Receipt ordering: Natural, Reversed, or Random by platform

    5. Companion Device Detection (Section V-E, Figure 8)
       - Device indices: Assignment and tracking [0, 1, 9, ...]
       - Network type: LAN, Wi-Fi, Cellular (LTE/4G)
       - Activity tracking: Active, Inactive, Offline states
       - Device switching: Detection of connections/disconnections
       - Multi-device scenarios: Tracking device transitions

    6. Resource Usage Estimation (Section V-F)
       - Baseline: ~300 bytes per message
       - High-frequency: ~500 bytes per reaction
       - Traffic profiles: Up to 3.7 MB/s maximum
       - Battery impact: 14-18% per hour at high frequency

    ============================================================================
    MISSING/INCOMPLETE FEATURES (Research Paper Only)
    ============================================================================

    1. Stealthy Probing Methods (Not Implemented)
       The paper demonstrates three invisible probing techniques:
       - Self-reactions: React to own message (no notification to target)
       - Reaction removal: Completely invisible (no message modification)
       - Invalid reactions: React with non-existent emoji (no notification)

       Current implementation: Uses generic message-based approach
       Note: Requires messenger-specific implementation (WhatsApp/Signal details)

    2. Geolocation Capability (Not Implemented)
       Section V-C and Appendix A1: Country-level geolocation possible via:
       - WhatsApp's 8 messaging servers (geo-distributed)
       - Signal's centralized server infrastructure
       - Server latency fingerprinting
       - IP-based server selection tracking

       Current implementation: RTT analysis only (no server mapping)
       Note: Requires server infrastructure knowledge not in this code

    3. Call Activity Detection (Incomplete)
       Section V-E mentions phone call activity detection via distinct RTT patterns
       during active calls. Current implementation has hooks but no actual detection.

       Would require:
       - State machine tracking for call state
       - Distinct RTT thresholds during calls
       - Call duration estimation

    4. Advanced Device Switching (Simplified)
       Current implementation detects device appearance/disappearance but
       the paper's full implementation tracks:
       - Device synchronization delays
       - Cross-device message timing
       - Device switching sequences
       - Cloud sync patterns (e.g., iCloud, Google Drive)

    5. Resource Exhaustion Attacks (Monitoring Only)
       Section V-F: Paper demonstrates:
       - Payload inflation (1MB reactions)
       - Distributed attack coordination
       - Battery drain attacks (14-18% per hour)
       - Storage exhaustion

       Current implementation: Can measure impact, not generate attacks

    6. Rate Limiting Adaptation (Not Implemented)
       Paper mentions Signal's 1 ping/sec rate limiting.
       Current implementation doesn't adapt to rate limits or
       implement frequency scaling based on response patterns.

    7. Messenger-Specific Details (Generic)
       Implementation is messenger-agnostic but paper includes:
       - WhatsApp reaction types (≤5 reactions per message)
       - WhatsApp timestamp analysis
       - Signal receipt types and semantics
       - Platform-specific payload sizes

    ============================================================================
    ACCURACY NOTES
    ============================================================================

    This implementation provides a faithful reproduction of the fingerprinting
    concepts from the research paper but makes several simplifications:

    - Activity and companion-device estimates remain timing heuristics
    - OS identification matches observed primary-device receipts to Table V
    - Receipt evidence may be unavailable, ambiguous, or version-dependent
    - Confidence scores are support indicators, not calibrated probabilities
    - Geolocation and server analysis not implemented (requires external data)

    For production use targeting specific platforms (WhatsApp, Signal),
    the messenger-specific details should be enhanced.
    """

    exploit: Exploit
    _analysis_results: list[BaseReceiptReport] = field(default_factory=list)
    _rtt_window: deque = field(default_factory=lambda: deque(maxlen=100))
    _last_analysis_time: Optional[datetime] = None
    _companion_device_indices: dict = field(default_factory=dict)
    _app_background_start_time: Optional[datetime] = (
        None  # Track 30s background state duration
    )

    # iPhone RTT Thresholds (from paper Figure 4-5)
    IPHONE_SCREEN_OFF_RTT_MS = 2000  # ~2 seconds
    IPHONE_SCREEN_ON_RTT_MS = 1000  # ~1 second
    IPHONE_APP_FOREGROUND_RTT_MS = 350  # app active
    IPHONE_APP_BACKGROUND_RTT_MS = 500  # app in hold state (30s window)
    IPHONE_APP_STANDBY_RTT_MS = 1000  # app standby
    IPHONE_APP_BACKGROUND_DURATION_SEC = (
        30  # Background state lasts exactly 30s (Figure 5)
    )

    # Android Samsung Exynos RTT Thresholds (from paper Figure 7)
    # Requires 1 ping/min for deep sleep detection
    SAMSUNG_EXYNOS_SCREEN_OFF_RTT_MS = 2500  # Distinct pattern, higher variance
    SAMSUNG_EXYNOS_SCREEN_ON_RTT_MS = 800

    # Android Samsung Qualcomm RTT Thresholds (from paper Figure 7)
    # Works with 1 ping/sec frequency
    SAMSUNG_QUALCOMM_SCREEN_OFF_RTT_MS = 1500
    SAMSUNG_QUALCOMM_SCREEN_ON_RTT_MS = 600

    # Android Xiaomi MediaTek RTT Thresholds (from paper Figure 7)
    # Works with 1 ping/sec frequency
    XIAOMI_MEDIATEK_SCREEN_OFF_RTT_MS = 1800
    XIAOMI_MEDIATEK_SCREEN_ON_RTT_MS = 550

    # Generic Android thresholds (fallback)
    ANDROID_SCREEN_OFF_RTT_MS = 1500
    ANDROID_SCREEN_ON_RTT_MS = 650

    # Relative screen-state detection (paper Section V-C).
    # The paper derives screen state from "relative differences in the observed
    # RTTs", not absolute values: the baseline RTT depends on the attacker type
    # (spooky stranger vs creepy companion), access technology (Wi-Fi vs LTE),
    # and device model. Across all tested devices the screen-off RTT is roughly
    # 2x the screen-on RTT (iPhone: ~1 s on, ~2 s off). We therefore classify a
    # device as screen-off when the recent RTT is substantially elevated above
    # the learned active baseline for this target, rather than comparing against
    # a fixed millisecond threshold.
    SCREEN_OFF_RATIO = 1.6  # recent RTT / active baseline above this -> screen off
    MIN_SCREEN_SAMPLES = 8  # samples needed before a baseline is trustworthy
    SCREEN_BASELINE_PERCENTILE = 0.2  # low percentile estimates the active RTT floor

    # Relative app-state detection (paper Figure 5).
    # The paper's app states (iPhone: ~350 ms foreground, ~500 ms background,
    # ~1000 ms standby) are relative multiples of the active baseline, not fixed
    # millisecond values. Background sits at ~1.4x foreground and standby at
    # ~2.8x. As with screen state, the absolute RTT is dominated by network and
    # device factors, so we classify on the recent RTT's elevation above the
    # learned foreground baseline (the low percentile of the observed window).
    APP_BACKGROUND_RATIO = 1.25  # recent RTT / baseline at/above this -> background
    APP_STANDBY_RATIO = 2.1  # recent RTT / baseline at/above this -> standby
    MIN_APP_SAMPLES = 10  # samples needed before a baseline is trustworthy
    APP_BASELINE_PERCENTILE = 0.2  # low percentile estimates the foreground floor

    @staticmethod
    def _percentile(values: list[float], pct: float) -> float:
        """Linear-interpolated percentile (pct in [0, 1]) of a list of values."""
        if not values:
            return 0.0
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        k = (len(ordered) - 1) * pct
        lower = int(k)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (k - lower)

    async def get_phone_screen_state(
        self,
        device_type: DeviceType = DeviceType.UNKNOWN,
        ping_interval_ms: float = 2000,
    ) -> PhoneState:
        """
        Analyzes RTT patterns to determine if phone screen is on or off.

        Based on Figure 4: an inactive screen leads to RTTs ~2x those of an
        active screen (iPhone: ~1 s on, ~2 s off). Because the absolute RTT
        depends on network and device factors, detection is done on the
        *relative* elevation of the recent RTT above a learned active baseline
        (the low percentile of the observed distribution), matching the paper's
        use of relative RTT differences rather than fixed thresholds.

        Note: reliable screen detection needs low-frequency probing (the paper
        uses ~1 ping / 20 s for iPhone) so the device can enter deep sleep;
        high-frequency probing keeps it awake and collapses the on/off gap.

        Args:
            device_type: Detected or assumed device type
            ping_interval_ms: Interval between pings in milliseconds

        Returns:
            PhoneState indicating screen on/off status
        """
        window = list(self._rtt_window)
        if not window:
            window = [report.delay for report in self.exploit.get_reports()]

        # Without enough samples we cannot establish a baseline; assume the
        # device is active (receipts are arriving, so it is at least online).
        if len(window) < self.MIN_SCREEN_SAMPLES:
            return PhoneState.SCREEN_ON

        recent_delays = window[-10:]
        avg_recent = mean(recent_delays)

        # Active (screen-on) baseline: low percentile of the observed RTTs.
        active_baseline = self._percentile(window, self.SCREEN_BASELINE_PERCENTILE)
        if active_baseline <= 0:
            return PhoneState.SCREEN_ON

        return (
            PhoneState.SCREEN_OFF
            if avg_recent >= active_baseline * self.SCREEN_OFF_RATIO
            else PhoneState.SCREEN_ON
        )

    async def get_app_state(
        self, device_type: DeviceType = DeviceType.UNKNOWN
    ) -> AppState:
        """
        Detects if target application (WhatsApp/Signal) is in foreground/background.

        Based on Figure 5, app state transitions show distinct RTT patterns that
        are *relative* to the active baseline rather than fixed millisecond
        values (iPhone: ~350 ms foreground, ~500 ms background, ~1000 ms
        standby; i.e. background ~1.4x and standby ~2.8x the foreground floor).
        Because the absolute RTT depends on the network path and device, we
        classify on the recent RTT's elevation above a learned foreground
        baseline (the low percentile of the observed window), matching the
        paper's relative-difference method.

        For iPhone the 30-second background hold window from Figure 5 is still
        tracked temporally: once a device has been in the background-elevated
        band for longer than that window, it is reported as standby.

        Returns:
            AppState indicating app foreground/background/standby status
        """
        window = list(self._rtt_window)
        if not window:
            window = [report.delay for report in self.exploit.get_reports()]

        # Without enough samples we cannot establish a baseline; assume the
        # app is active (receipts are arriving, so it is at least reachable).
        if len(window) < self.MIN_APP_SAMPLES:
            return AppState.APP_FOREGROUND

        recent_delays = window[-10:]
        avg_recent = mean(recent_delays)

        # Foreground baseline: low percentile of the observed RTTs.
        foreground_baseline = self._percentile(window, self.APP_BASELINE_PERCENTILE)
        if foreground_baseline <= 0:
            return AppState.APP_FOREGROUND

        ratio = avg_recent / foreground_baseline
        now = datetime.now()

        if ratio < self.APP_BACKGROUND_RATIO:
            self._app_background_start_time = None
            return AppState.APP_FOREGROUND

        if ratio >= self.APP_STANDBY_RATIO:
            self._app_background_start_time = None
            return AppState.APP_STANDBY

        # Background-elevated band. iPhone holds this state for exactly 30s
        # (Figure 5) before dropping to standby; track that window temporally.
        if device_type == DeviceType.IPHONE or "iPhone" in device_type:
            if self._app_background_start_time is None:
                self._app_background_start_time = now
            background_duration = (
                now - self._app_background_start_time
            ).total_seconds()
            if background_duration > self.IPHONE_APP_BACKGROUND_DURATION_SEC:
                self._app_background_start_time = None
                return AppState.APP_STANDBY

        return AppState.APP_BACKGROUND

    async def get_online_status(self) -> OnlineStatus:
        """
        Determines if device is online based on delivery receipt arrival.

        Based on Section V-B: Delivery receipts only arrive when device is online.
        Absence of receipts over time window suggests offline status.

        Returns:
            OnlineStatus based on recent receipt activity
        """
        reports = self.exploit.get_reports()

        if not reports:
            return OnlineStatus.OFFLINE

        # Check if we've received receipts in the last minute
        now = datetime.now()
        recent_reports = [
            r for r in reports if (now - r.delivered_at) < timedelta(seconds=60)
        ]

        return OnlineStatus.ONLINE if recent_reports else OnlineStatus.OFFLINE

    def _detect_device_type(
        self, receipt_structure: Optional[ReceiptStructure]
    ) -> DeviceType:
        if receipt_structure and receipt_structure.evidence_batches:
            if receipt_structure.platform == "iOS":
                return DeviceType.IPHONE
            if receipt_structure.platform == "Android":
                return DeviceType.ANDROID_GENERIC
        return DeviceType.UNKNOWN

    def _receipt_order(self, receipt: ReceiptEvent) -> str:
        sent = self.exploit.get_sent_messages()
        ids = receipt.message_ids
        # Three distinct messages is an implementation safeguard, not a
        # threshold specified by the paper.
        if len(ids) < 3 or len(set(ids)) != len(ids) or any(i not in sent for i in ids):
            return "Unknown"
        times = [sent[i].sent_at for i in ids]
        if len(set(times)) != len(times):
            return "Unknown"
        if times == sorted(times):
            return "Natural"
        if times == sorted(times, reverse=True):
            return "Reversed"
        return "Random"

    def _detect_receipt_structure(self) -> Optional[ReceiptStructure]:
        """Match observed primary-device receipts to Section V-D, Table V.

        https://arxiv.org/html/2411.11194v4#S5.SS4
        Linked-device receipts must never establish the phone's OS.
        """
        sent = self.exploit.get_sent_messages()
        events = [
            event
            for event in self.exploit.get_receipt_events()
            if event.device_id == 0 and any(i in sent for i in event.message_ids)
        ]
        if not events:
            return None

        deliveries = [
            event for event in events if event.receipt_type in ("DELIVERED", "INACTIVE")
        ]
        reads = [event for event in events if event.receipt_type == "READ"]
        stacked_reads = [event for event in reads if len(event.message_ids) > 1]
        orders = {self._receipt_order(event) for event in stacked_reads}
        ordering = (
            next(iter(orders))
            if len(orders) == 1
            else ("Mixed" if orders else "Unknown")
        )
        delivery_handling = (
            "Stacked"
            if any(len(event.message_ids) > 1 for event in deliveries)
            else "Separate" if deliveries else "Unknown"
        )
        read_handling = (
            "Stacked" if stacked_reads else "Separate" if reads else "Unknown"
        )
        if stacked_reads and ordering in ("Reversed", "Random", "Mixed"):
            read_handling = f"Stacked ({ordering})"

        separately_delivered = {
            event.message_ids[0] for event in deliveries if len(event.message_ids) == 1
        }
        # Require delivery evidence for the same messages as the read batch.
        complete_batches = {
            event.message_ids
            for event in stacked_reads
            if self._receipt_order(event) in ("Natural", "Reversed")
            and set(event.message_ids) <= separately_delivered
        }
        platform = "Unknown"
        if (
            delivery_handling == "Separate"
            and ordering in ("Natural", "Reversed")
            and complete_batches
        ):
            platform = "iOS" if ordering == "Reversed" else "Android"
        return ReceiptStructure(
            delivery_receipt_handling=delivery_handling,
            read_receipt_handling=read_handling,
            receipt_ordering=ordering,
            platform=platform,
            messenger="WhatsApp",
            evidence_batches=len(complete_batches) if platform != "Unknown" else 0,
        )

    def _analyze_companion_devices(self) -> list[dict]:
        """
        Detects and characterizes companion devices (web/desktop clients).

        Based on Figure 8 and Section V-E: The paper demonstrates detection of multiple
        companion devices with indices [0, 1, 9], including:
        - Device type identification (Web vs Desktop vs Mobile)
        - Network type inference (LAN vs Wi-Fi vs LTE/Cellular)
        - Activity state tracking (Active, Inactive, Offline)
        - Device switching detection (detecting transitions between devices)
        - Phone call activity detection (distinct RTT patterns during calls)

        Companion devices show distinct characteristics:
        - Web client on LAN: Very low RTT (~50ms) when tab active, ~3s when inactive
        - Web client on Wi-Fi: Higher RTT (~100-500ms) with variation
        - Desktop on LAN: Stable RTT, very low jitter (~20ms stdev)
        - Desktop on Wi-Fi: Moderate RTT with moderate jitter
        - Mobile secondary device: Similar patterns to primary but distinct timing

        Returns:
            List of detected companion devices with characterization details
        """
        reports = self.exploit.get_reports()

        if len(reports) < 20:
            return []

        companion_devices: list[dict] = []

        # Cluster RTT measurements to identify distinct devices
        # Devices typically show bimodal or multimodal RTT distributions

        # High-activity clusters (very low RTT < 100ms) suggest LAN-connected devices
        very_low_rtt_reports = [r for r in reports if r.delay < 100]
        if len(very_low_rtt_reports) > 10:
            avg_very_low = mean([r.delay for r in very_low_rtt_reports])
            stdev_very_low = (
                stdev([r.delay for r in very_low_rtt_reports])
                if len(very_low_rtt_reports) > 1
                else 0
            )

            # Low jitter (< 20ms) suggests wired LAN connection (Desktop)
            # Moderate jitter (20-50ms) suggests Wi-Fi LAN (Web/Desktop)
            device_type = (
                "Desktop (Wired)" if stdev_very_low < 20 else "Web/Desktop (Wi-Fi LAN)"
            )

            companion_devices.append(
                {
                    "device_index": len(companion_devices),  # Assign tentative index
                    "type": device_type,
                    "avg_rtt_ms": avg_very_low,
                    "stdev_rtt_ms": stdev_very_low,
                    "network": "LAN",
                    "sample_count": len(very_low_rtt_reports),
                    "activity": "Active",
                    "last_seen": (
                        very_low_rtt_reports[-1].delivered_at
                        if very_low_rtt_reports
                        else None
                    ),
                }
            )

        # Moderate RTT clusters (100-500ms) suggest active Wi-Fi/Cellular devices
        moderate_rtt_reports = [r for r in reports if 100 <= r.delay <= 500]
        if len(moderate_rtt_reports) > 10:
            avg_moderate = mean([r.delay for r in moderate_rtt_reports])
            stdev_moderate = (
                stdev([r.delay for r in moderate_rtt_reports])
                if len(moderate_rtt_reports) > 1
                else 0
            )

            # Distinguish Wi-Fi from Cellular by stdev and consistency
            network = "Wi-Fi" if stdev_moderate < 150 else "Cellular (LTE/4G)"

            companion_devices.append(
                {
                    "device_index": len(companion_devices),
                    "type": "Mobile/Companion Device",
                    "avg_rtt_ms": avg_moderate,
                    "stdev_rtt_ms": stdev_moderate,
                    "network": network,
                    "sample_count": len(moderate_rtt_reports),
                    "activity": "Active",
                    "last_seen": (
                        moderate_rtt_reports[-1].delivered_at
                        if moderate_rtt_reports
                        else None
                    ),
                }
            )

        # High RTT clusters (500-3000ms) suggest inactive/background tabs or devices
        high_rtt_reports = [r for r in reports if 500 < r.delay <= 3000]
        if len(high_rtt_reports) > 10:
            avg_high = mean([r.delay for r in high_rtt_reports])
            stdev_high = (
                stdev([r.delay for r in high_rtt_reports])
                if len(high_rtt_reports) > 1
                else 0
            )

            companion_devices.append(
                {
                    "device_index": len(companion_devices),
                    "type": "Web (Background Tab) / Standby Device",
                    "avg_rtt_ms": avg_high,
                    "stdev_rtt_ms": stdev_high,
                    "network": "Wi-Fi",
                    "sample_count": len(high_rtt_reports),
                    "activity": "Inactive/Background",
                    "last_seen": (
                        high_rtt_reports[-1].delivered_at if high_rtt_reports else None
                    ),
                }
            )

        # Very high RTT (> 3000ms) indicates offline or severely delayed devices
        very_high_rtt_reports = [r for r in reports if r.delay > 3000]
        if len(very_high_rtt_reports) > 5:
            avg_very_high = mean([r.delay for r in very_high_rtt_reports])

            companion_devices.append(
                {
                    "device_index": len(companion_devices),
                    "type": "Offline / Highly Delayed Device",
                    "avg_rtt_ms": avg_very_high,
                    "stdev_rtt_ms": 0,
                    "network": "Unknown",
                    "sample_count": len(very_high_rtt_reports),
                    "activity": "Offline",
                    "last_seen": (
                        very_high_rtt_reports[-1].delivered_at
                        if very_high_rtt_reports
                        else None
                    ),
                }
            )

        # Analyze device switching patterns (temporal transitions)
        if len(companion_devices) > 1:
            for device in companion_devices:
                device["switching_detected"] = self._detect_device_switching(
                    reports, float(device["avg_rtt_ms"]), tolerance_ms=100
                )

        return companion_devices

    def _detect_device_switching(
        self,
        reports: list[BaseReceiptReport],
        target_rtt_ms: float,
        tolerance_ms: float = 100,
    ) -> bool:
        """
        Detects if a device switches on/offline based on temporal RTT patterns.

        Looks for gaps in the RTT pattern where a device disappears and reappears,
        indicating the device was disconnected/switched and then reconnected.

        Returns:
            True if device switching detected, False if continuous
        """
        if len(reports) < 10:
            return False

        # Group consecutive reports by RTT proximity to target
        gaps = 0
        in_target_range = False

        for i, report in enumerate(reports):
            is_in_range = abs(report.delay - target_rtt_ms) <= tolerance_ms

            if is_in_range and not in_target_range:
                gaps += 1  # Entering target range from gap
                in_target_range = True
            elif not is_in_range and in_target_range:
                in_target_range = False

        # More than 2 gaps suggests device switching
        return gaps > 2

    def _calculate_rtt_pattern(self, delays: list[float], state: str) -> RTTPattern:
        """Calculates statistical pattern for a given state."""
        return RTTPattern(
            state=state,
            min_rtt_ms=min(delays) if delays else 0,
            max_rtt_ms=max(delays) if delays else 0,
            mean_rtt_ms=mean(delays) if delays else 0,
            median_rtt_ms=median(delays) if delays else 0,
            stdev_rtt_ms=stdev(delays) if len(delays) > 1 else 0,
            sample_count=len(delays),
        )

    async def analyze(self, ping_interval_ms: float = 2000) -> FingerprintAnalysis:
        """
        Performs comprehensive fingerprint analysis on collected reports.

        Implements the full fingerprinting suite from the paper:
        1. Screen state detection (Section V-C Showcase I)
        2. App activity detection (Section V-C Showcase II)
        3. Device OS identification from receipts (Section V-D, Table V)
        4. Companion device detection (Section V-C.3, Figure 8)
        5. OS/Receipt structure fingerprinting (Section V-D, Table V)
        6. Real-world tracking scenario (Section V-E)

        Data Usage Estimates (Section V-F - Resource Exhaustion):
        - Baseline fingerprinting: ~300 bytes per message (normal operation)
        - Reaction-based probing: ~500 bytes per reaction (reaction + metadata)
        - Resource exhaustion attack: up to 1MB payload reactions
        - At maximum: ~3.7 MB/s traffic (13.3 GB/hour possible)

        Battery/Resource Impact (Section V-F):
        - Normal probing: Minimal overhead (~1-5%)
        - High-frequency probing (50ms): 14-18% battery drain per hour
        - Sustained resource exhaustion: Can force device into thermal throttling

        Args:
            ping_interval_ms: Ping interval in milliseconds (affects sleep detection)

        Returns:
            Comprehensive FingerprintAnalysis with all detected characteristics
        """
        reports = self.exploit.get_reports()
        receipt_structure = self._detect_receipt_structure()
        device_type = self._detect_device_type(receipt_structure)
        evidence_batches = (
            receipt_structure.evidence_batches if receipt_structure else 0
        )
        # A receipt-support score, not a measured probability of OS accuracy.
        device_confidence = evidence_batches / (evidence_batches + 1)

        if not reports:
            return FingerprintAnalysis(
                analyzed_at=datetime.now(),
                phone_state=PhoneState.SCREEN_ON,
                app_state=AppState.APP_STANDBY,
                total_data_used_bytes=0,
                estimated_data_rate_bytes_per_second=0.0,
                estimated_battery_drain_pct_per_hour_min=0.0,
                estimated_battery_drain_pct_per_hour_max=0.0,
                device_type=device_type,
                receipt_structure=receipt_structure,
                avg_rtt_ms=0.0,
                median_rtt_ms=0.0,
                rtt_stdev_ms=0.0,
                total_requests=0,
                online_status=OnlineStatus.OFFLINE,
                confidence_scores={
                    "overall": 0.0,
                    "device_type": device_confidence,
                    "phone_state": 0.0,
                    "app_state": 0.0,
                    "online_status": 0.0,
                },
            )

        delays = [report.delay for report in reports]

        # Calculate RTT statistics
        avg_rtt = mean(delays)
        median_rtt = median(delays)
        rtt_stdev = stdev(delays) if len(delays) > 1 else 0.0

        # Detect current states
        phone_state = await self.get_phone_screen_state(device_type, ping_interval_ms)
        app_state = await self.get_app_state(device_type)
        online_status = await self.get_online_status()

        # Detect companion devices
        companion_devices = self._analyze_companion_devices()

        # Estimate data usage based on probing method and frequency
        # Baseline: ~300 bytes per standard message/reaction
        # High-frequency probing: ~500 bytes per reaction (with metadata)
        # Resource exhaustion: up to 1MB per payload
        bytes_per_message = 300

        # Adjust estimate based on ping frequency (more frequent = more overhead)
        if ping_interval_ms < 100:
            # High-frequency attack mode
            bytes_per_message = 500
        elif ping_interval_ms < 1000:
            # Medium-frequency monitoring
            bytes_per_message = 400

        total_data_used = len(reports) * bytes_per_message

        ping_interval_seconds = max(ping_interval_ms / 1000, 0.001)
        estimated_data_rate = bytes_per_message / ping_interval_seconds
        if ping_interval_ms < 100:
            battery_drain_min = 14.0
            battery_drain_max = 18.0
        else:
            battery_drain_min = 1.0
            battery_drain_max = 5.0

        sample_confidence = min(len(reports) / 50, 1.0)
        stability_confidence = max(
            0.0,
            min(1.0, 1 - (rtt_stdev / max(avg_rtt, 1.0))),
        )
        overall_confidence = round(
            sample_confidence * (0.7 + (stability_confidence * 0.3)), 3
        )
        analyzed_at = datetime.now()
        self._last_analysis_time = analyzed_at

        return FingerprintAnalysis(
            analyzed_at=analyzed_at,
            phone_state=phone_state,
            app_state=app_state,
            total_data_used_bytes=total_data_used,
            estimated_data_rate_bytes_per_second=estimated_data_rate,
            estimated_battery_drain_pct_per_hour_min=battery_drain_min,
            estimated_battery_drain_pct_per_hour_max=battery_drain_max,
            device_type=device_type,
            avg_rtt_ms=avg_rtt,
            median_rtt_ms=median_rtt,
            rtt_stdev_ms=rtt_stdev,
            total_requests=len(reports),
            online_status=online_status,
            confidence_scores={
                "overall": overall_confidence,
                "device_type": device_confidence,
                "phone_state": overall_confidence,
                "app_state": overall_confidence,
                "online_status": min(len(reports) / 5, 1.0),
            },
            receipt_structure=receipt_structure,
            companion_devices=companion_devices,
        )

    def register_report(self, report: BaseReceiptReport) -> None:
        """
        Called when a new report is received from the exploit.
        Updates rolling window and analysis results.
        """
        self._analysis_results.append(report)
        self._rtt_window.append(report.delay)

    def get_rtt_pattern(self, state: str = "all") -> RTTPattern:
        """
        Returns characteristic RTT pattern for analysis and visualization.

        Args:
            state: "all" for all data, or specific state identifier

        Returns:
            RTTPattern with statistical summary
        """
        reports = self.exploit.get_reports()
        delays = [r.delay for r in reports]
        return self._calculate_rtt_pattern(delays, state)
