import asyncio
import logging
from logging import getLogger
from argparse import ArgumentParser
import sys

from carelesswhisper.tools.cli.ui import CLIDisplay
from carelesswhisper.messengers.base import BaseReceiptReport
from carelesswhisper.fingerprint import FingerprintAnalysis


logger = getLogger(__name__)


class CLIApplication:
    """Main CLI application controller that uses the fingerprint tool with UI callbacks."""

    def __init__(self, settings):
        """
        Initialize the CLI application.

        Args:
            settings: Settings object from fingerprint tool (SettingsProtocol compatible)
        """
        self.display = CLIDisplay()
        self.running = False
        self.settings = settings

    async def run(self):
        """
        Runs the main CLI application using the fingerprint tool.
        """
        self.running = True
        self.display.start()

        try:
            # Create callbacks for UI updates
            async def on_report(report: BaseReceiptReport):
                """Callback for when a new report is received."""
                logger.debug(f"Report received: {report.delay}ms delay")
                self.display.add_report(report)

            async def on_analysis(analysis: FingerprintAnalysis):
                """Callback for when fingerprint analysis is updated."""
                logger.debug(f"Fingerprint analysis updated")
                self.display.update_fingerprint(analysis)

            # Import the fingerprint tool
            from carelesswhisper.tools.fingerprint.main import main as fingerprint_main

            # Start UI update loop and fingerprint tool concurrently
            try:
                await asyncio.gather(
                    self._run_ui_loop(),
                    fingerprint_main(
                        settings=self.settings,
                        on_report=on_report,
                        on_analysis=on_analysis,
                    ),
                    return_exceptions=True,
                )
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                self.running = False

        except asyncio.CancelledError:
            self.running = False
        except Exception as e:
            logger.error(f"Error in CLI application: {e}", exc_info=True)
            raise
        finally:
            self.display.stop()

    async def _run_ui_loop(self):
        """Runs the main UI update loop with live rendering."""
        from rich.live import Live

        try:
            with Live(
                self.display.render_full_ui(),
                refresh_per_second=2,
                screen=True,
            ) as live:
                while self.running:
                    try:
                        live.update(self.display.render_full_ui())
                        await asyncio.sleep(0.5)
                    except KeyboardInterrupt:
                        self.running = False
                        break
        except KeyboardInterrupt:
            self.running = False
        except Exception as e:
            logger.error(f"Error in UI loop: {e}")
            raise


async def fingerprint_command(args):
    """
    Handle the fingerprint subcommand with UI.
    """
    from carelesswhisper.tools.fingerprint.config import Settings

    # Build settings from arguments
    settings_kwargs = {
        "phone_number": args.phone_number,
        "provider": args.provider,
        "delay_between_requests": args.delay,
        "concurrent_requests": args.concurrent,
        "metrics": args.metrics,
        "metrics_port": args.metrics_port,
        "exporter": args.exporter,
        "ignore_unregistered_warning": args.ignore_unregistered,
    }

    # Create settings from parsed arguments
    try:
        settings = Settings(**settings_kwargs)
    except Exception as e:
        logger.error(f"Error parsing settings: {e}")
        sys.exit(1)

    # Run the CLI application
    app = CLIApplication(settings)
    await app.run()


def main():
    """Main entry point for the CLI."""
    parser = ArgumentParser(
        description="Careless Whisper - Read Receipt Timing Analysis CLI",
        prog="carelesswhisper",
    )

    # Add global options
    parser.add_argument(
        "--log-level",
        type=str,
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: WARNING)",
    )

    # Create subparsers for commands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Fingerprint command
    fingerprint_parser = subparsers.add_parser(
        "fingerprint",
        help="Run fingerprinting analysis with interactive UI",
    )

    fingerprint_parser.add_argument(
        "--phone-number",
        "-p",
        type=str,
        required=True,
        help="Target phone number for fingerprinting",
    )
    fingerprint_parser.add_argument(
        "--provider",
        type=str,
        default="whatsapp",
        help="Messenger provider to use (default: whatsapp)",
    )
    fingerprint_parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between requests in seconds (default: 1.0)",
    )
    fingerprint_parser.add_argument(
        "--concurrent",
        type=int,
        default=5,
        help="Number of concurrent requests (default: 5)",
    )
    fingerprint_parser.add_argument(
        "--exporter",
        type=str,
        help="Exporter to use for saving results (e.g., csv)",
    )
    fingerprint_parser.add_argument(
        "--metrics",
        action="store_true",
        help="Enable Prometheus metrics server",
    )
    fingerprint_parser.add_argument(
        "--metrics-port",
        type=int,
        default=8000,
        help="Port for the Prometheus metrics server (default: 8000)",
    )
    fingerprint_parser.add_argument(
        "--ignore-unregistered",
        action="store_true",
        help="Ignore warning for unregistered phone numbers",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        # Handle commands
        if args.command == "fingerprint":
            asyncio.run(fingerprint_command(args))
        else:
            # No command provided, show help
            parser.print_help()
            sys.exit(0)

    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
