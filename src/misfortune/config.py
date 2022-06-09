from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import sentry_sdk


@dataclass
class Config:
    api_url: str
    internal_token: str
    telegram_token: str
    wheel_token: str
    sentry_dsn: Optional[str]

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            api_url=os.getenv("API_URL", "https://api.bembel.party"),
            internal_token=os.getenv("INTERNAL_TOKEN"),
            sentry_dsn=os.getenv("SENTRY_DSN"),
            telegram_token=os.getenv("TELEGRAM_TOKEN"),
            wheel_token=os.getenv("WHEEL_TOKEN"),
        )

    def basic_setup(self):
        logging.basicConfig()
        logging.getLogger("misfortune").setLevel(logging.DEBUG)
        dsn = self.sentry_dsn
        if dsn:
            sentry_sdk.init(dsn=dsn)
