import asyncio

import pytest

from carelesswhisper.tools.dos.config import Settings
from carelesswhisper.tools.dos.main import FloodStats, build_payload, flood


class FakeMessenger:
    def __init__(self, fail_every: int | None = None):
        self.sent = 0
        self.fail_every = fail_every
        self.last_reaction: str | None = None

    async def is_on_platform(self, phone_number: str) -> bool:
        return True

    async def send_silent_message(
        self, phone_number: str, reaction: str | None = None
    ) -> str:
        self.sent += 1
        self.last_reaction = reaction
        if self.fail_every and self.sent % self.fail_every == 0:
            raise RuntimeError("transient send error")
        return f"id-{self.sent}"


def _settings(**overrides) -> Settings:
    base = {
        "phone_number": "123456789",
        "report_interval": 100.0,
        "ignore_unregistered_warning": True,
    }
    base.update(overrides)
    return Settings(**base)


def test_flood_stops_after_max_messages():
    messenger = FakeMessenger()
    settings = _settings(concurrent_requests=4, max_messages=50)

    stats = asyncio.run(flood(messenger, settings))

    assert stats.sent >= 50
    # Workers stop checking once the limit is reached; allow at most one extra
    # in-flight send per worker.
    assert stats.sent <= 50 + settings.concurrent_requests


def test_flood_stops_after_duration():
    messenger = FakeMessenger()
    settings = _settings(
        concurrent_requests=2, duration=0.2, delay_between_requests=0.01
    )

    stats = asyncio.run(flood(messenger, settings))

    assert stats.elapsed() >= 0.2
    assert stats.sent > 0


def test_flood_counts_failures_and_keeps_going():
    messenger = FakeMessenger(fail_every=3)
    settings = _settings(concurrent_requests=1, max_messages=20)

    stats = asyncio.run(flood(messenger, settings))

    assert stats.sent == 20
    assert stats.failed > 0


def test_flood_sends_requested_payload_size():
    messenger = FakeMessenger()
    settings = _settings(concurrent_requests=1, max_messages=1, payload_size=1024)

    asyncio.run(flood(messenger, settings))

    assert messenger.last_reaction is not None
    assert len(messenger.last_reaction.encode()) == 1024


def test_build_payload_matches_byte_size():
    assert len(build_payload(1024 * 1024).encode()) == 1024 * 1024


def test_estimated_gib_uses_bytes_per_message():
    stats = FloodStats(sent=1024 * 1024)

    assert stats.estimated_gib(1024) == pytest.approx(1.0)
