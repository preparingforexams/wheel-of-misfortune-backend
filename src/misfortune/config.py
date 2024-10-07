import base64
import json
import logging
from dataclasses import dataclass
from typing import Self

import sentry_sdk
from bs_config import Env


@dataclass
class Config:
    api_url: str
    app_version: str
    drinks_collection: str
    google_service_account_key: dict | None
    internal_token: str
    telegram_token: str
    wheel_token: str
    sentry_dsn: str | None

    @staticmethod
    def _decode_gsa_key(key: str | None) -> dict | None:
        if key is None:
            return None

        return json.loads(base64.standard_b64decode(key).decode("utf-8"))

    @classmethod
    def from_env(cls, env: Env) -> Self:
        gsa_key = cls._decode_gsa_key(env.get_string("SERVICE_ACCOUNT_JSON"))
        return cls(
            api_url=env.get_string("API_URL", default="https://api.bembel.party"),
            app_version=env.get_string("APP_VERSION", default="dev"),
            drinks_collection=env.get_string(
                "FIRESTORE_DRINKS_COLLECTION",
                default="drinks",
            ),
            google_service_account_key=gsa_key,
            internal_token=env.get_string("INTERNAL_TOKEN", required=True),
            sentry_dsn=env.get_string("SENTRY_DSN"),
            telegram_token=env.get_string("TELEGRAM_TOKEN", required=True),
            wheel_token=env.get_string("WHEEL_TOKEN", required=True),
        )

    def basic_setup(self) -> None:
        logging.basicConfig()
        logging.getLogger("misfortune").setLevel(logging.DEBUG)
        dsn = self.sentry_dsn
        if dsn:
            sentry_sdk.init(
                dsn=dsn,
                release=self.app_version,
            )


def init_config() -> Config:
    env = Env.load(include_default_dotenv=True)
    config = Config.from_env(env)
    config.basic_setup()
    return config
