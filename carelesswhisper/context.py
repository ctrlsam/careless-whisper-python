from dataclasses import dataclass

from carelesswhisper.messengers.base import BaseMessenger
from carelesswhisper.exporters.base import BaseExporter
from carelesswhisper.metrics import Metrics


@dataclass
class ApplicationContext:
    messenger: BaseMessenger
    exporter: BaseExporter | None = None
    metrics: Metrics | None = None

    # Configuration options
    ignore_unregistered_warning: bool = False
    delay_between_requests: float = 1.0
    concurrent_requests: int = 1