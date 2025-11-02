from typing import TYPE_CHECKING
from uuid import UUID

from bs_nats_updater import NatsConfig
from fastapi.testclient import TestClient
from pytest import fixture

from misfortune.config import Config, FirestoreConfig
from tests.bearer_auth import BearerAuth

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx


@fixture()
def config() -> Config:
    return Config(
        api_url="",
        app_version="",
        firestore=FirestoreConfig(
            user_states="test_users",
            wheels="test_wheels",
        ),
        jwt_secret="test",
        max_user_wheels=3,
        max_wheel_name_length=64,
        nats=NatsConfig("", "", "", "", ""),
        internal_token="abc",
        run_signal_file=None,
        sentry_dsn=None,
        telegram_bot_name="localpheasntestbot",
        telegram_token="",
    )


@fixture()
def client(config, mocker) -> TestClient:  # type: ignore
    mocker.patch("misfortune.config.init_config", return_value=config)
    from misfortune.api.main import app

    client = TestClient(app, follow_redirects=False)
    yield client
    client.close()


@fixture
def internal_auth(config) -> httpx.Auth:
    return BearerAuth(token=config.internal_token)


@fixture
def spin_auth_factory() -> Callable[[], httpx.Auth]:
    def _generate() -> httpx.Auth:
        from misfortune.api.main import observable_states

        observable_state = observable_states[UUID(int=0)]

        state = observable_state.value
        return BearerAuth(token=state.code)

    return _generate
