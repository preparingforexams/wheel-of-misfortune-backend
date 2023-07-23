import logging
import os
from dataclasses import dataclass
from typing import Optional, Any, Self

import sentry_sdk


def _non_probe_sampler(context: dict[str, Any]) -> float:
    transaction = context["transaction_context"]
    path = transaction.get("path")
    if (
        transaction["op"] == "http.server"
        and path is not None
        and path.startswith("/probe/")
    ):
        return 0.0

    return 1.0


def _get_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Missing environment variable: {key}")
    return value


@dataclass
class Config:
    api_url: str
    app_version: str
    internal_token: str
    telegram_token: str
    wheel_token: str
    sentry_dsn: Optional[str]

    @classmethod
    def from_env(cls) -> Self:
        return cls(
            api_url=os.getenv("API_URL", "https://api.bembel.party"),
            app_version=os.getenv("APP_VERSION") or "dev",
            internal_token=_get_env("INTERNAL_TOKEN"),
            sentry_dsn=os.getenv("SENTRY_DSN"),
            telegram_token=_get_env("TELEGRAM_TOKEN"),
            wheel_token=_get_env("WHEEL_TOKEN"),
        )

    def basic_setup(self) -> None:
        logging.basicConfig()
        logging.getLogger("misfortune").setLevel(logging.DEBUG)
        dsn = self.sentry_dsn
        if dsn:
            sentry_sdk.init(
                dsn=dsn,
                release=self.app_version,
                traces_sampler=_non_probe_sampler,
            )


def init_config() -> Config:
    config = Config.from_env()
    config.basic_setup()
    return config
