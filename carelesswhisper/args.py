from argparse import ArgumentParser

parser = ArgumentParser(description="Careless Whisper - Read receipt timing exploit analyzer")
parser.add_argument("--provider", type=str, help="Messenger provider to use", default="whatsapp")
parser.add_argument("--phone-number", "-p", type=str, help="Phone number to test read receipt delay")
parser.add_argument("--exporter", "-e", type=str, help="Exporter to save read receipt delays", default="csv")

args = parser.parse_args()
