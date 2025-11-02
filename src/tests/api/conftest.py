from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from bs_config import Env
from fastapi.testclient import TestClient
from pytest import fixture

from misfortune.config import Config
from tests.bearer_auth import BearerAuth

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx


@fixture(scope="session")
def config() -> Config:
    env = Env.load(
        include_default_dotenv=True,
        toml_configs=[
            Path("config-test.toml"),
        ],
    )
    return Config.from_env(env)


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
