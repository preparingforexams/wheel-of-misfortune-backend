import logging
from dataclasses import dataclass
from typing import Self

import sentry_sdk
from bs_config import Env


@dataclass
class FirestoreConfig:
    user_states: str
    wheels: str

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            user_states=env.get_string(
                "FIRESTORE_USER_STATES_COLLECTION",
                default="active_user_wheel",
            ),
            wheels=env.get_string(
                "FIRESTORE_WHEELS_COLLECTION",
                default="wheels",
            ),
        )


@dataclass
class Config:
    api_url: str
    app_version: str
    firestore: FirestoreConfig
    internal_token: str
    jwt_secret: str
    max_user_wheels: int
    max_wheel_name_length: int
    telegram_token: str
    telegram_bot_name: str
    sentry_dsn: str | None

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            api_url=env.get_string("API_URL", default="https://api.bembel.party"),
            app_version=env.get_string("APP_VERSION", default="dev"),
            firestore=FirestoreConfig.from_env(env),
            internal_token=env.get_string("INTERNAL_TOKEN", required=True),
            jwt_secret=env.get_string("JWT_SECRET", required=True),
            max_user_wheels=env.get_int("MAX_USER_WHEELS", default=5),
            max_wheel_name_length=env.get_int("MAX_WHEEL_NAME_LENGTH", default=64),
            sentry_dsn=env.get_string("SENTRY_DSN"),
            telegram_bot_name=env.get_string(
                "TELEGRAM_BOT_NAME",
                default="misfortune_bot",
            ),
            telegram_token=env.get_string("TELEGRAM_TOKEN", required=True),
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
