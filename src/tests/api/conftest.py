from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient
from pytest import fixture

from misfortune.config import Config
from tests.bearer_auth import BearerAuth


@fixture()
def config() -> Config:
    return Config(
        api_url="",
        app_version="",
        drinks_collection="test_drinks",
        google_service_account_key=None,
        internal_token="abc",
        sentry_dsn=None,
        telegram_token="",
        wheel_token="def",
    )


@fixture()
def client(config, mocker) -> TestClient:  # type: ignore
    mocker.patch("misfortune.config.init_config", return_value=config)
    from misfortune.api import app

    client = TestClient(app, follow_redirects=False)
    yield client
    client.close()


@fixture
def wheel_auth(config) -> httpx.Auth:
    return BearerAuth(token=config.wheel_token)


@fixture
def internal_auth(config) -> httpx.Auth:
    return BearerAuth(token=config.internal_token)


@fixture
def spin_auth_factory() -> Callable[[], httpx.Auth]:
    def _generate() -> httpx.Auth:
        from misfortune.api import observable_state

        state = observable_state.value
        return BearerAuth(token=state.code)

    return _generate
