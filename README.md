# Careless Whisper - Delivery Receipt Timing Exploit Analyzer

The exploit abuses delivery receipts in end-to-end encrypted messaging applications. Because delivery receipts are generated only after a message is successfully decrypted, their timing can be analyzed to infer user activity—for example, whether a device is online or offline. The attack can be carried out silently, without triggering any visible notifications, because insufficient server-side validation allows an attacker to send “reaction” messages referencing non-existent message IDs within a chat. Using the same mechanism, the attacker can also cause a denial-of-service condition by repeatedly triggering operations that consume device resources such as CPU, battery, and able to drain 13.3 GB per hour of mobile data.

> [!NOTE]
> This repository contains a proof-of-concept implementation of the Careless Whisper attack in Python. It is intended for educational and research purposes only. Please ensure you have permission to test against any target phone numbers and comply with all applicable laws and regulations. All credits for the discovery of this exploit go to the original authors listed in the [Credits section](#credits).

> [!TIP]
> This attack is known to work on WhatsApp and Signal as of December 2025.

## Setup

1. Clone the repository:

    ```sh
    git clone https://github.com/ctrlsam/careless-whisper-python.git
    cd careless-whisper-python
    ```

2. Install the required dependencies:

    ```sh
    pip install .
    ```

## Tools

- [Fingerprint Tool](./carelesswhisper/tools/fingerprint/README.md)): Analyzing delivery receipt timings to infer user activity.
- [DoS Tool](./carelesswhisper/tools/dos/README.md)): Demonstrating the denial-of-service attack by draining device resources.
- [CLI Tool](./carelesswhisper/tools/cli/README.md)): A command-line interface for interacting with the exploit functionalities.

### CLI

To use the CLI tool, run the following command:

```sh
python -m carelesswhisper.tools.cli
```

## Supported Messengers

- WhatsApp
- Signal (coming soon)

## Exporters

- CSV
- Prometheus

## Grafana Dashboard

A Grafana dashboard is available for visualizing the read receipt delays.
To access the dashboard locally, run:

```sh
docker-compose -f docker/docker-compose.yml up
# Wait for the services to start
# Access Grafana at http://localhost:3000
```

<img src="docs/grafana_dashboard.jpg" alt="Grafana Dashboard" width="500"/>

> The default login credentials are `admin` for both username and password.

## Credits

This exploit was discovered by Gabriel Karl Gegenhuber, Maximilian Günther, Markus Maier, Aljosha Judmayer, Florian Holzbauer, Philipp É Frenzel, and Johanna Ullrich in their paper "Careless Whisper: Exploiting Silent Delivery Receipts to Monitor Users on Mobile Instant Messengers" (2025).

```bibtex
@article{gegenhuber2025careless,
  title={Careless Whisper: Exploiting Silent Delivery Receipts to Monitor Users on Mobile Instant Messengers},
  author={Gegenhuber, Gabriel Karl and G{\"u}nther, Maximilian and Maier, Markus and Judmayer, Aljosha and Holzbauer, Florian and Frenzel, Philipp {\'E} and Ullrich, Johanna},
  year={2025}
}
```
