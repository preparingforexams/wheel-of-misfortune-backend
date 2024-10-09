import asyncio
import base64
import logging
import random
import secrets
import uuid
from collections.abc import Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Self

import jwt
import pendulum
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.cloud import firestore
from pydantic import ValidationError
from pydantic_core import Url

from .config import init_config
from .observable import Observable, observable
from .shared_model import (
    MisfortuneModel,
    TelegramWheel,
    TelegramWheels,
)

_LOG = logging.getLogger(__name__)

auth_token = HTTPBearer()


class Wheel(MisfortuneModel):
    id: uuid.UUID
    name: str
    owner: int
    drinks: list[str]

    @classmethod
    def create(cls, owner: int, name: str) -> Self:
        return cls(
            name=name,
            owner=owner,
            id=uuid.uuid4(),
            drinks=[],
        )


class WheelLogin(MisfortuneModel):
    token: str | None


class WheelRegistrationInfo(MisfortuneModel):
    registration_id: uuid.UUID
    telegram_url: Url

    @classmethod
    def create(cls, registration_id: uuid.UUID) -> Self:
        bot_name = config.telegram_bot_name
        encoded_id = base64.urlsafe_b64encode(registration_id.bytes).decode()
        return cls(
            registration_id=registration_id,
            telegram_url=Url.build(
                scheme="https",
                host="t.me",
                path=f"/{bot_name}",
                query=f"start={encoded_id}",
            ),
        )


class WheelCredentials(MisfortuneModel):
    token: str


class State(MisfortuneModel):
    drinks: Sequence[str]
    wheel_name: str
    code: str
    owner: int
    drinking_age: datetime | None = None
    is_locked: bool = False
    current_drink: int = 0
    speed: float = 0.0

    @classmethod
    def initial(cls, wheel: Wheel) -> Self:
        return cls(
            drinks=wheel.drinks,
            wheel_name=wheel.name,
            code=generate_code(),
            owner=wheel.owner,
        )

    def is_accessible(self, user_id: int) -> bool:
        return user_id == self.owner

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


async def fetch_wheels(client: firestore.AsyncClient) -> list[Wheel]:
    wheels = []
    for doc in await client.collection(config.firestore.wheels).get():
        wheel = Wheel.model_validate(doc.to_dict())
        wheels.append(wheel)

    return wheels


async def _client():
    client = firestore.AsyncClient()
    try:
        yield client
    finally:
        client.close()


pending_wheel_clients: dict[uuid.UUID, Observable[uuid.UUID]] = {}
observable_states: dict[uuid.UUID, Observable[State]] = {}

config = init_config()


@asynccontextmanager
async def lifespan(_):
    client = firestore.AsyncClient()
    try:
        wheels = await fetch_wheels(client)
        for wheel in wheels:
            observable_states[wheel.id] = observable(State.initial(wheel))
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


def _verify_access(
    *,
    user: int,
    wheel: uuid.UUID,
    require_owner: bool = False,
) -> Observable[State]:
    state = observable_states.get(wheel)
    if state is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    if require_owner and state.value.owner != user:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    if not require_owner and not state.value.is_accessible(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    return state


@app.get("/user/{user_id}/wheel")
async def list_wheels(
    user_id: int,
    token: HTTPAuthorizationCredentials = Depends(auth_token),
) -> TelegramWheels:
    if token.credentials != config.internal_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    return TelegramWheels(
        wheels=[
            TelegramWheel(
                id=wheel_id,
                name=state.value.wheel_name,
                is_owned=state.value.owner == user_id,
            )
            for wheel_id, state in observable_states.items()
            if state.value.is_accessible(user_id)
        ],
    )


@app.post(
    "/user/{user_id}/wheel",
    status_code=status.HTTP_201_CREATED,
)
async def create_wheel(
    user_id: int,
    name: str,
    token: HTTPAuthorizationCredentials = Depends(auth_token),
    client: firestore.AsyncClient = Depends(_client),
) -> TelegramWheel:
    if token.credentials != config.internal_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    owned_wheels = sum(
        1 for state in observable_states.values() if state.value.owner == user_id
    )
    if owned_wheels >= config.max_user_wheels:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED)

    wheel = Wheel.create(
        owner=user_id,
        name=name,
    )
    await (
        client.collection(config.firestore.wheels)
        .document(str(wheel.id))
        .create(wheel.model_dump(mode="json"))
    )
    observable_states[wheel.id] = observable(State.initial(wheel))
    return TelegramWheel(
        id=wheel.id,
        name=wheel.name,
        is_owned=True,
    )


@app.get("/user/{user_id}/wheel/{wheel_id}")
async def get_wheel_state(
    user_id: int,
    wheel_id: uuid.UUID,
    token: HTTPAuthorizationCredentials = Depends(auth_token),
) -> State:
    if token.credentials != config.internal_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    return _verify_access(user=user_id, wheel=wheel_id).value


@app.patch("/user/{user_id}/wheel/{wheel_id}/name")
async def update_wheel_name(
    user_id: int,
    wheel_id: uuid.UUID,
    name: str,
    token: HTTPAuthorizationCredentials = Depends(auth_token),
    client: firestore.AsyncClient = Depends(_client),
) -> TelegramWheel:
    if token.credentials != config.internal_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    state = _verify_access(user=user_id, wheel=wheel_id, require_owner=True)
    await (
        client.collection(config.firestore.wheels)
        .document(str(wheel_id))
        .update(
            dict(name=name),
        )
    )
    await state.update(state.value.replace(wheel_name=name))
    return TelegramWheel(name=name, id=wheel_id, is_owned=True)


@app.post(
    "/user/{user_id}/wheel/{wheel_id}/registration",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def add_client_registration(
    user_id: int,
    wheel_id: uuid.UUID,
    registration_id: uuid.UUID,
    token: HTTPAuthorizationCredentials = Depends(auth_token),
) -> None:
    if token.credentials != config.internal_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    _verify_access(user=user_id, wheel=wheel_id)
    client_wheel = pending_wheel_clients.get(registration_id)
    if client_wheel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    await client_wheel.update(wheel_id)


@app.delete(
    "/user/{user_id}/wheel/{wheel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_wheel(
    user_id: int,
    wheel_id: uuid.UUID,
    token: HTTPAuthorizationCredentials = Depends(auth_token),
    client: firestore.AsyncClient = Depends(_client),
) -> None:
    if token.credentials != config.internal_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    _verify_access(user=user_id, wheel=wheel_id, require_owner=True)
    await client.collection(config.firestore.wheels).document(str(wheel_id)).delete()
    del observable_states[wheel_id]


@app.post("/wheel/{wheel_id}/is_locked", response_class=Response, status_code=204)
async def spin(
    wheel_id: uuid.UUID,
    speed: float,
    token: HTTPAuthorizationCredentials = Depends(auth_token),
) -> None:
    observable_state = observable_states[wheel_id]

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


def _decode_wheel_token(token: str) -> uuid.UUID:
    payload = jwt.decode(token, config.jwt_secret, algorithms=["HS256"])
    return uuid.UUID(payload["wheelId"])


@app.delete(
    "/wheel/is_locked",
    response_class=Response,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlock(
    token: HTTPAuthorizationCredentials = Depends(auth_token),
) -> None:
    try:
        wheel_id = _decode_wheel_token(token.credentials)
    except ValidationError:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    async with observable_states[wheel_id].atomic() as atom:
        state: State = atom.value

        if not state.is_locked:
            return

        await atom.update(
            state.replace(
                is_locked=False,
                code=generate_code(),
            )
        )


@app.post(
    "/user/{user_id}/wheel/{wheel_id}/drink",
    response_class=Response,
    status_code=status.HTTP_201_CREATED,
)
async def add_drink(
    user_id: int,
    wheel_id: uuid.UUID,
    name: str,
    token: HTTPAuthorizationCredentials = Depends(auth_token),
    client: firestore.AsyncClient = Depends(_client),
) -> None:
    if token.credentials != config.internal_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    observable_state = _verify_access(user=user_id, wheel=wheel_id)

    async with observable_state.atomic() as atom:
        state: State = atom.value

        if name not in state.drinks:
            new_drinks = list(state.drinks)
            new_drinks.append(name)
            await (
                client.collection(config.firestore.wheels)
                .document(str(wheel_id))
                .update(dict(drinks=new_drinks))
            )
            await atom.update(state.replace(drinks=new_drinks))


@app.delete(
    "/user/{user_id}/wheel/{wheel_id}/drink",
    response_class=Response,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_drink(
    user_id: int,
    wheel_id: uuid.UUID,
    name: str,
    client: firestore.AsyncClient = Depends(_client),
    token: HTTPAuthorizationCredentials = Depends(auth_token),
) -> None:
    if token.credentials != config.internal_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    observable_state = _verify_access(user=user_id, wheel=wheel_id)

    async with observable_state.atomic() as atom:
        state = atom.value
        drinks = [drink for drink in state.drinks if drink != name]
        await (
            client.collection(config.firestore.wheels)
            .document(str(wheel_id))
            .update(dict(drinks=drinks))
        )
        await atom.update(state.replace(drinks=drinks))


async def register_wheel_client(websocket: WebSocket) -> uuid.UUID:
    registration_id = uuid.uuid4()
    observable_wheel_id: Observable[uuid.UUID] = observable(None)

    confirmation = asyncio.Event()

    async def __on_confirm(wheel_id: uuid.UUID) -> None:
        token = jwt.encode(
            {
                "exp": datetime.now(tz=UTC) + timedelta(days=1),
                "wheelId": str(wheel_id),
            },
            key=config.jwt_secret,
            algorithm="HS256",
        )
        await websocket.send_text(WheelCredentials(token=token).model_dump_json())
        confirmation.set()

    observable_wheel_id.add_listener(__on_confirm)
    pending_wheel_clients[registration_id] = observable_wheel_id

    try:
        await websocket.send_text(
            WheelRegistrationInfo.create(registration_id).model_dump_json(),
        )
        await asyncio.wait_for(
            confirmation.wait(),
            timedelta(minutes=20).total_seconds(),
        )
    finally:
        del pending_wheel_clients[registration_id]

    return observable_wheel_id.value


async def authenticate_wheel_client(websocket: WebSocket) -> uuid.UUID | None:
    try:
        login = WheelLogin.model_validate_json(
            await asyncio.wait_for(websocket.receive_text(), timeout=10)
        )

        if token := login.token:
            return _decode_wheel_token(token)

        return await register_wheel_client(websocket)
    except jwt.InvalidTokenError:
        _LOG.error("Login attempt with invalid token")
        await websocket.close(status.WS_1008_POLICY_VIOLATION)
    except TimeoutError:
        _LOG.warning("Client did not send auth message")
        await websocket.close(status.WS_1008_POLICY_VIOLATION)
    except ValidationError:
        _LOG.warning("Invalid websocket auth message")
        await websocket.close(status.WS_1003_UNSUPPORTED_DATA)
    except WebSocketDisconnect:
        _LOG.warning("Disconnected ws before auth")
        await websocket.close()

    return None


@app.websocket("/ws")
async def connect_ws(websocket: WebSocket):
    await websocket.accept()

    wheel_id = await authenticate_wheel_client(websocket)
    if not wheel_id:
        return

    observable_state = observable_states[wheel_id]

    async def __on_state(state: State) -> None:
        try:
            await websocket.send_text(state.model_dump_json())
        except WebSocketDisconnect:
            _LOG.warning("Got disconnect during send")

    on_state = __on_state

    try:
        async with observable_state.atomic() as atom:
            await on_state(atom.value)
            atom.add_listener(on_state)

        async for message in websocket.iter_json():
            _LOG.warning("Received unexpected message: %s", message)
    finally:
        observable_state.remove_listener(on_state)
        _LOG.info("Ended websocket connection")
