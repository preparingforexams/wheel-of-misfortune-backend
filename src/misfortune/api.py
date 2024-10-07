import abc
import asyncio
import logging
import random
import secrets
from collections.abc import Sequence
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Self

import pendulum
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.cloud import firestore
from pydantic import BaseModel, ConfigDict, ValidationError

from .config import init_config
from .drink import Drink
from .observable import observable

_LOG = logging.getLogger(__name__)


auth_token = HTTPBearer()


class MisfortuneModel(BaseModel, abc.ABC):
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )


class WebsocketAuth(MisfortuneModel):
    token: str


class State(MisfortuneModel):
    drinks: Sequence[Drink]
    code: str
    drinking_age: datetime | None = None
    is_locked: bool = False
    current_drink: int = 0
    speed: float = 0.0

    def is_old(self) -> bool:
        drinking_age = self.drinking_age
        if drinking_age is None:
            return True

        now: datetime = pendulum.now()
        delta = now - drinking_age
        return delta > timedelta(minutes=1)

    def replace(self, **kwargs) -> Self:
        return self.model_validate(self.model_copy(update=kwargs))


def generate_code() -> str:
    return secrets.token_urlsafe(16)


async def fetch_drinks(client: firestore.AsyncClient) -> list[Drink]:
    drinks = []
    for doc in await client.collection(config.drinks_collection).get():
        drink = Drink.from_dict(doc.to_dict())
        drinks.append(drink)

    return drinks


async def _client():
    client = firestore.AsyncClient()
    try:
        yield client
    finally:
        client.close()


observable_state = observable(
    State(
        drinks=[],
        code=generate_code(),
    )
)

config = init_config()


@asynccontextmanager
async def lifespan(_):
    client = firestore.AsyncClient()
    try:
        drinks = await fetch_drinks(client)
        state = observable_state.value.replace(
            drinks=drinks,
        )
        await observable_state.update(state)
    finally:
        client.close()

    yield

    # We don't have any teardown to do


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://bembel.party",
        "https://wheel.bembel.party",
        "http://localhost",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=RedirectResponse)
async def redirect_to_docs() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/probe/live")
async def liveness_probe() -> dict[str, Any]:
    return {"status": "ok"}


@app.get("/state")
async def get_state(
    token: HTTPAuthorizationCredentials = Depends(auth_token),
) -> State:
    if token.credentials not in [
        config.internal_token,
        config.wheel_token,
    ]:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    return observable_state.value


@app.post("/spin", response_class=Response, status_code=204)
async def spin(
    speed: float,
    token: HTTPAuthorizationCredentials = Depends(auth_token),
) -> None:
    async with observable_state.atomic() as atom:
        state: State = atom.value
        if token.credentials != state.code:
            raise HTTPException(status.HTTP_403_FORBIDDEN)

        if state.is_locked:
            raise HTTPException(status.HTTP_409_CONFLICT)

        await atom.update(
            state.replace(
                is_locked=True,
                speed=speed,
                current_drink=random.randrange(0, len(state.drinks)),
            )
        )


@app.put("/unlock", response_class=Response, status_code=204)
async def unlock(
    token: HTTPAuthorizationCredentials = Depends(auth_token),
) -> None:
    if token.credentials != config.wheel_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    async with observable_state.atomic() as atom:
        state: State = atom.value

        if not state.is_locked:
            return

        await atom.update(
            state.replace(
                is_locked=False,
                code=generate_code(),
            )
        )


@app.post("/drink", response_class=Response, status_code=201)
async def add_drink(
    name: str,
    client: firestore.AsyncClient = Depends(_client),
    token: HTTPAuthorizationCredentials = Depends(auth_token),
) -> None:
    if token.credentials != config.internal_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    async with observable_state.atomic() as atom:
        state: State = atom.value

        if name not in (d.name for d in state.drinks):
            drink = Drink.create(name)
            await (
                client.collection(config.drinks_collection)
                .document(drink.id)
                .set(drink.to_dict())
            )
            new_drinks = list(state.drinks)
            new_drinks.append(drink)
            await atom.update(state.replace(drinks=new_drinks))


@app.delete("/drink", response_class=Response, status_code=201)
async def delete_drink(
    drink_id: str | None,
    client: firestore.AsyncClient = Depends(_client),
    token: HTTPAuthorizationCredentials = Depends(auth_token),
) -> None:
    if token.credentials != config.internal_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    if drink_id:
        await client.collection(config.drinks_collection).document(drink_id).delete()
        state = observable_state.value
        await observable_state.update(
            state.replace(
                drinks=[d for d in state.drinks if d.id != drink_id],
            )
        )
    else:
        _LOG.warning("Clearing all drinks")
        async for doc in client.collection(config.drinks_collection).stream():
            await doc.reference.delete()


async def authenticate_websocket(websocket: WebSocket) -> bool:
    try:
        auth_message = WebsocketAuth.model_validate_json(
            await asyncio.wait_for(websocket.receive_text(), timeout=10)
        )

        if auth_message.token == config.wheel_token:
            return True

        _LOG.error("Login attempt with invalid token")
        await websocket.close(status.WS_1008_POLICY_VIOLATION)
    except TimeoutError:
        _LOG.warning("Client did not send auth message")
        await websocket.close(status.WS_1008_POLICY_VIOLATION)
    except ValidationError as e:
        _LOG.warning("Invalid websocket auth message", exc_info=e)
        await websocket.close(status.WS_1003_UNSUPPORTED_DATA)
    except WebSocketDisconnect:
        _LOG.warning("Disconnected ws before auth")
        await websocket.close()

    return False


@app.websocket("/ws")
async def connect_ws(websocket: WebSocket):
    await websocket.accept()
    if not await authenticate_websocket(websocket):
        return

    async def __on_state(state: State) -> None:
        try:
            await websocket.send_json(state)
        except WebSocketDisconnect:
            _LOG.warning("Got disconnect during send")

    on_state = __on_state

    try:
        async with observable_state.atomic() as atom:
            await on_state(atom.value)
            atom.add_listener(on_state)

        async for message in websocket.iter_json():
            _LOG.error("Received unexpected message: %s", message)
    finally:
        observable_state.remove_listener(on_state)
