from typing import TYPE_CHECKING

from httpx import Auth

if TYPE_CHECKING:
    from collections.abc import Generator

    from httpx import Request, Response


class BearerAuth(Auth):
    def __init__(self, token: str):
        self._token = token

    def auth_flow(self, request: Request) -> Generator[Request, Response]:
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request
