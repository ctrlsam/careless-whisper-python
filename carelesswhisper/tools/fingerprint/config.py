from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings for the fingerprint tool.

    Can be used with cli_parse_args=True for standalone CLI usage,
    or without it when used as a library or from another CLI tool.
    """

    phone_number: str = Field(
        ...,
        description="Target phone number to test read receipt delay.",
        alias="phone-number",
    )

    provider: str = Field(
        default="whatsapp", description="Messenger provider to use (e.g., whatsapp)."
    )
    exporter: str | None = Field(
        default=None, description="Exporter to use for saving results (e.g., csv)."
    )

    metrics: bool = Field(
        default=False, description="Enable Prometheus metrics server."
    )
    metrics_port: int = Field(
        default=8000, description="Port for the Prometheus metrics server."
    )

    ignore_unregistered_warning: bool = Field(
        default=False, description="Ignore warning for unregistered phone numbers."
    )
    delay_between_requests: float = Field(
        default=1.0, description="Delay between each read receipt request in seconds."
    )
    concurrent_requests: int = Field(
        default=5,
        description="Number of concurrent read receipt requests.",
        alias="concurrent",
    )

    class Config:
        populate_by_name = True  # Allow using field names and aliases
