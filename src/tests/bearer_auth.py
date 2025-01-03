from collections.abc import Generator

import httpx
from httpx import Request, Response


class BearerAuth(httpx.Auth):
    def __init__(self, token: str):
        self._token = token

    def auth_flow(self, request: Request) -> Generator[Request, Response]:
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request
