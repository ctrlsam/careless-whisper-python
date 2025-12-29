"""
Terminal UI components for the Careless Whisper CLI tool.
Uses Rich for terminal rendering and live updates.
"""

from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable
import threading
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.layout import Layout
from rich.live import Live

from carelesswhisper.messengers.base import BaseReceiptReport
from carelesswhisper.fingerprint import PhoneState, FingerprintAnalysis, OnlineStatus


@dataclass
class DataPoint:
    """Represents a single data point in the RTT plot."""

    timestamp: float  # Seconds since start
    rtt_ms: float


class RTTPlotter:
    """Handles plotting of RTT data over time."""

    def __init__(self, max_points: int = 50):
        self.max_points = max_points
        self.data_points: list[DataPoint] = []
        self.start_time: Optional[float] = None
        self._lock = threading.Lock()

    def add_report(self, report: BaseReceiptReport) -> None:
        """Adds a new report to the plotter."""
        with self._lock:
            if self.start_time is None:
                self.start_time = report.sent_at.timestamp()

            timestamp = report.sent_at.timestamp() - self.start_time
            self.data_points.append(DataPoint(timestamp, report.delay))

            # Keep only the last N points
            if len(self.data_points) > self.max_points:
                self.data_points = self.data_points[-self.max_points :]

    def render(self, width: int = 80, height: int = 15) -> str:
        """Renders the RTT plot as a string using ASCII art with axis labels.

        Args:
            width: Width of the plot in characters
            height: Height of the plot in characters
        """
        with self._lock:
            if not self.data_points:
                return "Waiting for data..."

            try:
                # Get data
                y_values = [p.rtt_ms for p in self.data_points]
                x_values = [p.timestamp for p in self.data_points]

                # Create plot with axis
                return self._create_ascii_plot(x_values, y_values, width, height)

            except Exception as e:
                return f"Error rendering plot: {e}"

    def _create_ascii_plot(
        self, x: list[float], y: list[float], width: int, height: int
    ) -> str:
        """Creates a simple ASCII plot with axis labels."""
        if not y:
            return "No data to plot"

        # Get min/max for scaling
        min_y = min(y)
        max_y = max(y)
        min_x = min(x)
        max_x = max(x)

        # Prevent division by zero
        y_range = max_y - min_y if max_y > min_y else 1
        x_range = max_x - min_x if max_x > min_x else 1

        # Leave room for axis labels
        plot_width = width - 3  # Left side for Y-axis labels
        plot_height = height - 3  # Bottom for X-axis labels

        if plot_width < 20 or plot_height < 5:
            return "Terminal too small for plot"

        # Create plot area
        plot = [[" " for _ in range(plot_width)] for _ in range(plot_height)]

        # Plot points
        for xi, yi in zip(x, y):
            # Normalize to plot area
            x_pos = (
                int(((xi - min_x) / x_range) * (plot_width - 1)) if x_range > 0 else 0
            )
            y_pos = (
                int(((yi - min_y) / y_range) * (plot_height - 1)) if y_range > 0 else 0
            )

            # Clamp to bounds
            x_pos = max(0, min(plot_width - 1, x_pos))
            y_pos = max(0, min(plot_height - 1, y_pos))

            # Invert y (top is high value)
            y_pos = plot_height - 1 - y_pos

            plot[y_pos][x_pos] = "●"

        # Build output string
        lines = []

        # Y-axis label
        max_y_str = f"{max_y:.0f}"
        lines.append(f"{max_y_str:>10}┌" + "─" * plot_width + "┐")

        # Plot rows with Y-axis
        for i, row in enumerate(plot):
            if i == plot_height // 2:
                mid_y = (min_y + max_y) / 2
                y_label = f"{mid_y:.0f}"
            elif i == plot_height - 1:
                y_label = f"{min_y:.0f}"
            else:
                y_label = ""

            y_label = f"{y_label:>10}"
            lines.append(y_label + "│" + "".join(row) + "│")

        # X-axis
        lines.append(" " * 10 + "└" + "─" * plot_width + "┘")

        # X-axis labels
        x_label_str = f"{'Time (s)':>10}{min_x:.1f}{' ' * (plot_width - 10)}{max_x:.1f}"
        lines.append(x_label_str)
        lines.append(f"{'RTT (ms)':>10}")

        return "\n".join(lines)


class FingerprintDisplay:
    """Renders fingerprint analysis results."""

    def __init__(self):
        self.analysis: Optional[FingerprintAnalysis] = None
        self._lock = threading.Lock()

    def update(self, analysis: FingerprintAnalysis) -> None:
        """Updates the fingerprint analysis data."""
        with self._lock:
            self.analysis = analysis

    def render(self) -> Panel:
        """Renders the fingerprint analysis as a Rich panel."""
        with self._lock:
            if self.analysis is None:
                return Panel(
                    "No analysis data yet",
                    title="Fingerprint Analysis",
                    style="dim",
                )

            table = Table(show_header=False, box=None)

            # Phone state with color coding
            state_color = (
                "green"
                if self.analysis.phone_state == PhoneState.SCREEN_ON
                else "yellow"
            )
            table.add_row(
                Text("Phone State:", style="bold"),
                Text(self.analysis.phone_state.value, style=state_color),
            )

            table.add_row(
                Text("Device Type:", style="bold"),
                self.analysis.device_type.value,
            )

            table.add_row(
                Text("App State:", style="bold"),
                self.analysis.app_state.value,
            )

            table.add_row(
                Text("Online Status:", style="bold"),
                self.analysis.online_status.value,
            )

            table.add_row(
                Text("Total Requests:", style="bold"),
                str(self.analysis.total_requests),
            )

            table.add_row(
                Text("Avg RTT:", style="bold"),
                f"{self.analysis.avg_rtt_ms:.2f} ms",
            )

            table.add_row(
                Text("Median RTT:", style="bold"),
                f"{self.analysis.median_rtt_ms:.2f} ms",
            )

            table.add_row(
                Text("Est. Data Used:", style="bold"),
                f"{self.analysis.total_data_used_bytes / 1024:.2f} KB",
            )

            return Panel(
                table,
                title="Fingerprint Analysis",
                style="blue",
            )


class CLIDisplay:
    """Main CLI display manager for the fancy UI."""

    def __init__(self):
        self.console = Console()
        self.rtt_plotter = RTTPlotter(max_points=50)
        self.fingerprint_display = FingerprintDisplay()
        self.is_running = False
        self._stats_lock = threading.Lock()
        self.last_update_time = time.time()
        self.update_count = 0

    def add_report(self, report: BaseReceiptReport) -> None:
        """Adds a new report to the display."""
        self.rtt_plotter.add_report(report)
        with self._stats_lock:
            self.update_count += 1
            self.last_update_time = time.time()

    def update_fingerprint(self, analysis: FingerprintAnalysis) -> None:
        """Updates the fingerprint display."""
        self.fingerprint_display.update(analysis)

    def render_full_ui(self) -> Layout:
        """Renders the complete UI layout with graph, stats, and analytics."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="graph", size=18),
            Layout(name="primary_stats", size=6),
            Layout(name="advanced_stats", size=7),
            Layout(name="footer", size=3),
        )

        # Header
        layout["header"].update(
            Panel(
                Text(
                    "Careless Whisper - Delivery Receipt Timing Analysis",
                    justify="center",
                    style="bold magenta",
                ),
                style="cyan",
            )
        )

        # Calculate dimensions for the graph panel (full width)
        from rich.console import Console as ConsoleClass

        console = ConsoleClass()
        available_width = console.width - 15  # Subtract for borders and padding
        graph_height = 14  # Height of the graph area

        # Graph section - full width
        plot_text = self.rtt_plotter.render(width=available_width, height=graph_height)
        layout["graph"].update(
            Panel(
                plot_text,
                title="RTT Analysis",
                border_style="green",
            )
        )

        # Primary stats section (device info and basic metrics)
        primary_panel = self._render_primary_stats_panel()
        layout["primary_stats"].update(primary_panel)

        # Advanced analytics section (receipt structure, companion devices, network)
        advanced_panel = self._render_advanced_stats_panel()
        layout["advanced_stats"].update(advanced_panel)

        # Footer with stats
        with self._stats_lock:
            footer_text = f"Total Updates: {self.update_count} | Last Update: {datetime.now().strftime('%H:%M:%S')} | Press Ctrl+C to stop"

        layout["footer"].update(
            Panel(
                Text(footer_text, justify="center", style="dim"),
                style="cyan",
            )
        )

        return layout

    def _render_stats_panel(self) -> Panel:
        """Renders the statistics panel with fingerprint data."""
        if self.fingerprint_display.analysis is None:
            return Panel(
                "Waiting for fingerprint analysis...",
                title="Fingerprint Analysis",
                style="blue",
                height=4,
            )

        analysis = self.fingerprint_display.analysis

        # Create a horizontal layout of stats as tags
        stats_text = Text()

        # Phone state with color
        state_color = (
            "green" if analysis.phone_state == PhoneState.SCREEN_ON else "yellow"
        )
        stats_text.append("Screen: ", style="bold")
        stats_text.append(f"{analysis.phone_state.value}", style=state_color)
        stats_text.append("  |  ", style="dim")

        # Device type
        stats_text.append("Device: ", style="bold")
        stats_text.append(f"{analysis.device_type.value}")
        stats_text.append("  |  ", style="dim")

        # App state
        stats_text.append("App: ", style="bold")
        stats_text.append(f"{analysis.app_state.value}")
        stats_text.append("  |  ", style="dim")

        # Total requests
        stats_text.append("Requests: ", style="bold")
        stats_text.append(f"{analysis.total_requests}")
        stats_text.append("  |  ", style="dim")

        # RTT stats
        stats_text.append("Avg RTT: ", style="bold")
        stats_text.append(f"{analysis.avg_rtt_ms:.2f}ms")
        stats_text.append("  |  ", style="dim")

        stats_text.append("Median RTT: ", style="bold")
        stats_text.append(f"{analysis.median_rtt_ms:.2f}ms")
        stats_text.append("  |  ", style="dim")

        stats_text.append("Data Used: ", style="bold")
        stats_text.append(f"{analysis.total_data_used_bytes / 1024:.2f}KB")

        return Panel(
            stats_text,
            title="Fingerprint Analysis",
            style="blue",
        )

    def _render_primary_stats_panel(self) -> Panel:
        """Renders primary statistics panel with device info and basic metrics."""
        if self.fingerprint_display.analysis is None:
            return Panel(
                "Waiting for fingerprint analysis...",
                title="Device Status",
                style="blue",
            )

        analysis = self.fingerprint_display.analysis

        # Create a table for primary stats
        table = Table(show_header=False, box=None, padding=(0, 1))

        # Phone state with color
        state_color = (
            "green" if analysis.phone_state == PhoneState.SCREEN_ON else "yellow"
        )
        table.add_row(
            Text("Screen:", style="bold cyan"),
            Text(analysis.phone_state.value, style=state_color),
            Text("Online:", style="bold cyan"),
            Text(
                analysis.online_status.value,
                style="green"
                if analysis.online_status == OnlineStatus.ONLINE
                else "red",
            ),
        )

        # Device and App state
        table.add_row(
            Text("Device:", style="bold cyan"),
            Text(analysis.device_type.value),
            Text("App State:", style="bold cyan"),
            Text(analysis.app_state.value),
        )

        # RTT metrics
        table.add_row(
            Text("Avg RTT:", style="bold cyan"),
            Text(f"{analysis.avg_rtt_ms:.2f} ms"),
            Text("Median RTT:", style="bold cyan"),
            Text(f"{analysis.median_rtt_ms:.2f} ms"),
        )

        # Data and requests
        table.add_row(
            Text("Total Requests:", style="bold cyan"),
            Text(str(analysis.total_requests)),
            Text("Data Used:", style="bold cyan"),
            Text(f"{analysis.total_data_used_bytes / 1024:.2f} KB"),
        )

        return Panel(
            table,
            title="Device Status & Metrics",
            style="blue",
            padding=(0, 1),
        )

    def _render_advanced_stats_panel(self) -> Panel:
        """Renders advanced analytics panel with receipt structure and companion devices."""
        if self.fingerprint_display.analysis is None:
            return Panel(
                "Waiting for data...",
                title="Advanced Analytics",
                style="magenta",
            )

        analysis = self.fingerprint_display.analysis
        content = Text()

        # Receipt structure information
        if analysis.receipt_structure:
            rs = analysis.receipt_structure
            content.append("📋 Receipt Structure\n", style="bold magenta")
            content.append(
                f"  Platform: {rs.platform} | Messenger: {rs.messenger}\n", style="dim"
            )
            content.append(
                f"  Delivery: {rs.delivery_receipt_handling} | ", style="dim"
            )
            content.append(f"Read: {rs.read_receipt_handling} | ", style="dim")
            content.append(f"Order: {rs.receipt_ordering}\n\n", style="dim")
        else:
            content.append("📋 Receipt Structure: Analyzing...\n", style="dim")
            content.append("\n")

        # Companion devices information
        if analysis.companion_devices:
            content.append("🌐 Companion Devices\n", style="bold magenta")
            for i, device in enumerate(analysis.companion_devices):
                device_idx = device.get("device_index", i)
                device_type = device.get("type", "Unknown")
                network = device.get("network", "Unknown")
                activity = device.get("activity", "Unknown")
                avg_rtt = device.get("avg_rtt_ms", 0)
                samples = device.get("sample_count", 0)
                switching = device.get("switching_detected", False)

                # Color code activity
                activity_color = (
                    "green"
                    if activity == "Active"
                    else "yellow"
                    if activity == "Inactive"
                    else "red"
                )

                content.append(f"  [{device_idx}] {device_type}\n", style="bold")
                content.append(f"      Network: {network} | ", style="dim")
                content.append(f"Activity: {activity} | ", style=activity_color)
                content.append(
                    f"RTT: {avg_rtt:.0f}ms | Samples: {samples}\n", style="dim"
                )
                if switching:
                    content.append(
                        f"      ⚠️  Device Switching Detected\n", style="yellow"
                    )
        else:
            content.append("🌐 Companion Devices: None detected yet\n", style="dim")

        return Panel(
            content,
            title="Advanced Analytics",
            style="magenta",
            padding=(0, 1),
        )

    def start(self) -> None:
        """Starts the display."""
        self.is_running = True
        self.console.clear()

    def stop(self) -> None:
        """Stops the display."""
        self.is_running = False
