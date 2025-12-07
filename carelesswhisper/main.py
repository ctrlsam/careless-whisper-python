import logging
import asyncio

from carelesswhisper.messengers.base import BaseMessenger, ReceiptTimeoutError
from carelesswhisper.exporters.base import BaseExporter
from carelesswhisper.context import ApplicationContext


logger = logging.getLogger(__name__)


async def get_messenger(provider: str) -> BaseMessenger:
    if provider == "whatsapp":
        from carelesswhisper.messengers.whatsapp import WhatsAppMessenger
        return WhatsAppMessenger()
    else:
        raise ValueError(f"Unsupported provider: {provider}")  


def get_exporter(exporter: str, target_phone_number: str) -> BaseExporter:
    if exporter == "csv":
        from carelesswhisper.exporters.csv import CSVExporter
        return CSVExporter(target_phone_number)
    else:
        raise ValueError(f"Unsupported exporter: {exporter}")
    

async def confirm_number(phone_number: str, ctx: ApplicationContext) -> None:
    is_registered = await ctx.messenger.is_on_platform(phone_number)
    if not is_registered:
        logger.warning(f"The phone number {phone_number} is not registered on the platform.")

        if not ctx.ignore_unregistered_warning:
            logger.info("Exiting due to unregistered phone number. Use --ignore-unregistered-warning to override.")
            exit(1)
    else:
        logger.info(f"The phone number {phone_number} is registered on the platform.")


async def start(phone_number: str, ctx: ApplicationContext) -> None:
    await confirm_number(phone_number, ctx)

    # Create a semaphore to limit concurrent requests
    logger.info(f"Using concurrency level: {ctx.concurrent_requests}")
    semaphore = asyncio.Semaphore(ctx.concurrent_requests)

    async def send_request_with_semaphore():
        """Send a single request while respecting the concurrency limit."""
        async with semaphore:
            try:
                report = await ctx.messenger.get_rtt(phone_number)
            except ReceiptTimeoutError as e:
                logger.warning(str(e))
                return

            logger.info(f"Read receipt delay: {report.delay} milliseconds")

            if ctx.exporter:
                ctx.exporter.save_rtt(report)

            if ctx.metrics:
                ctx.metrics.report_ran_ping(phone_number)
                ctx.metrics.report_rtt(report)

    async def concurrent_worker():
        """Worker that continuously sends requests."""
        while True:
            await send_request_with_semaphore()
            await asyncio.sleep(ctx.delay_between_requests)

    # Create multiple concurrent workers
    tasks = [asyncio.create_task(concurrent_worker()) for _ in range(ctx.concurrent_requests)]
    
    # Wait for all tasks to complete (they run indefinitely)
    await asyncio.gather(*tasks)


async def main():
    from carelesswhisper.args import args

    phone_number = args.phone_number
    if not phone_number:
        phone_number = input("Enter phone number to test read receipt delay: ")

    messenger = await get_messenger(args.provider)
    exporter = get_exporter(args.exporter, phone_number) if args.exporter else None
    metrics = None
    if args.metrics:
        logger.info("Prometheus metrics server started on port 8000")
        from carelesswhisper.metrics import Metrics
        metrics = Metrics()
        metrics.start_server(port=8000)

    ctx = ApplicationContext(
        messenger=messenger,
        exporter=exporter,
        metrics=metrics,
        ignore_unregistered_warning=args.ignore_unregistered_warning,
        delay_between_requests=args.delay_between_requests,
        concurrent_requests=args.concurrent
    )
    
    logger.info(
        f"Starting to scan {phone_number} on the {args.provider.capitalize()} "
        f"messenger provider and export results with {args.exporter} exporter."
    )

    # Start connection in background task
    connection_task = asyncio.create_task(messenger.start())
    
    # Wait for the messenger to be ready before starting the scanning task
    await messenger.wait_until_ready()
    
    # Start scanning in another background task
    scanning_task = asyncio.create_task(start(phone_number, ctx))
    
    # Wait for both tasks to complete (they run indefinitely)
    await asyncio.gather(connection_task, scanning_task)


if __name__ == "__main__":
    import sys
    from carelesswhisper.args import args
    
    try:
        # Get the appropriate event loop runner for this provider
        if args.provider == "whatsapp":
            from carelesswhisper.messengers.whatsapp import get_neonize_event_loop_runner
            event_loop_runner = get_neonize_event_loop_runner()
            event_loop_runner(main())
        else:
            # Use asyncio's default event loop for other providers
            asyncio.run(main())
            
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
