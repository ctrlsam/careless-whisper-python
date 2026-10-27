import asyncio

import pytest

from carelesswhisper.tools.util import confirm_number


class RegistrationMessenger:
    def __init__(self, registered: bool | None):
        self.registered = registered

    async def is_on_platform(self, phone_number: str) -> bool | None:
        return self.registered


def test_unregistered_number_raises_without_override():
    messenger = RegistrationMessenger(registered=False)

    with pytest.raises(ValueError, match="not registered"):
        asyncio.run(confirm_number("123456789", messenger))


def test_unregistered_number_is_allowed_with_override():
    messenger = RegistrationMessenger(registered=False)

    asyncio.run(
        confirm_number(
            "123456789",
            messenger,
            ignore_unregistered_warning=True,
        )
    )


def test_inconclusive_registration_check_is_allowed():
    messenger = RegistrationMessenger(registered=None)

    asyncio.run(confirm_number("123456789", messenger))
