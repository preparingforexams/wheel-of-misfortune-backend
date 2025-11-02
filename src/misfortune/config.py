import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import sentry_sdk
from bs_config import Env
from bs_nats_updater import NatsConfig


@dataclass
class FirestoreConfig:
    user_states: str
    wheels: str

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            user_states=env.get_string(
                "user-states-collection",
                default="active_user_wheel",
            ),
            wheels=env.get_string(
                "wheels-collection",
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
    nats: NatsConfig
    run_signal_file: Path | None
    sentry_dsn: str | None
    telegram_token: str
    telegram_bot_name: str

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            api_url=env.get_string("api-url", default="https://api.bembel.party"),
            app_version=env.get_string("app-version", default="dev"),
            firestore=FirestoreConfig.from_env(env / "firestore"),
            internal_token=env.get_string("internal-token", required=True),
            jwt_secret=env.get_string("jwt-secret", required=True),
            max_user_wheels=env.get_int("max-user-wheels", default=5),
            max_wheel_name_length=env.get_int("max-wheel-name-length", default=64),
            nats=NatsConfig.from_env(env / "nats"),
            run_signal_file=env.get_string("run-signal-file", transform=Path),
            sentry_dsn=env.get_string("sentry-dsn"),
            telegram_bot_name=env.get_string(
                "telegram-bot-name",
                default="misfortune_bot",
            ),
            telegram_token=env.get_string("telegram-token", required=True),
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
