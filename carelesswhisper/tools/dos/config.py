from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings for the DoS tool.

    Can be used with cli_parse_args=True for standalone CLI usage,
    or without it when used as a library or from another CLI tool.
    """

    phone_number: str = Field(
        ...,
        description="Target phone number to flood with silent messages.",
        alias="phone-number",
    )

    provider: str = Field(
        default="whatsapp", description="Messenger provider to use (e.g., whatsapp)."
    )

    concurrent_requests: int = Field(
        default=10,
        description="Number of concurrent flood workers.",
        alias="concurrent",
    )
    delay_between_requests: float = Field(
        default=0.0,
        description="Delay between each silent message per worker in seconds.",
    )

    duration: float | None = Field(
        default=None,
        description="Stop after this many seconds. Runs indefinitely when unset.",
    )
    max_messages: int | None = Field(
        default=None,
        description="Stop after sending this many messages. Unlimited when unset.",
    )

    payload_size: int = Field(
        default=1024 * 1024,
        description=(
            "Size in bytes of each reaction payload. Larger payloads force the "
            "target device to download and decrypt more data per message."
        ),
        alias="payload-size",
    )
    report_interval: float = Field(
        default=5.0,
        description="How often to log flood progress in seconds.",
    )

    ignore_unregistered_warning: bool = Field(
        default=False, description="Ignore warning for unregistered phone numbers."
    )

    class Config:
        populate_by_name = True  # Allow using field names and aliases
