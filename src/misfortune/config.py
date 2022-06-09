from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    api_url: str
    internal_token: str
    telegram_token: str
    wheel_token: str

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            api_url=os.getenv("API_URL", "https://api.bembel.party"),
            internal_token=os.getenv("INTERNAL_TOKEN"),
            telegram_token=os.getenv("TELEGRAM_TOKEN"),
            wheel_token=os.getenv("WHEEL_TOKEN"),
        )
