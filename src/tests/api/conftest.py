from fastapi.testclient import TestClient
from pytest import fixture

from misfortune.config import Config


@fixture()
def config() -> Config:
    return Config(
        api_url="",
        app_version="",
        internal_token="abc",
        sentry_dsn="",
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
