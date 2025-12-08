from argparse import ArgumentParser, BooleanOptionalAction

parser = ArgumentParser(
    description="Careless Whisper - Read receipt timing exploit analyzer"
)
parser.add_argument(
    "--provider", type=str, help="Messenger provider to use", default="whatsapp"
)
parser.add_argument(
    "--phone-number", "-p", type=str, help="Phone number to test read receipt delay"
)
parser.add_argument(
    "--exporter",
    "-e",
    type=str,
    help="Exporter to save read receipt delays",
    default="csv",
)
parser.add_argument(
    "--metrics", action=BooleanOptionalAction, help="Enable Prometheus metrics server"
)
parser.add_argument(
    "--ignore-unregistered-warning",
    action="store_true",
    help="Ignore warning if phone number is not registered on the platform",
)
parser.add_argument(
    "--delay-between-requests",
    type=float,
    default=1.0,
    help="Delay between requests in seconds",
)
parser.add_argument(
    "--concurrent",
    type=int,
    default=1,
    help="Number of concurrent requests to send (default: 1 for synchronous)",
)

args = parser.parse_args()
