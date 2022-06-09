from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    internal_token: str
    wheel_token: str

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            internal_token=os.getenv("INTERNAL_TOKEN"),
            wheel_token=os.getenv("WHEEL_TOKEN"),
        )
