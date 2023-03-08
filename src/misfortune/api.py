from __future__ import annotations

import logging
import random
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import List, Optional

import pendulum
from fastapi import FastAPI, Depends
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.responses import Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.cloud import firestore
from pydantic import BaseModel

from .config import Config
from .drink import Drink

_LOG = logging.getLogger(__name__)

auth_token = HTTPBearer()


class State(BaseModel):
    drinks: List[Drink]
    code: str
    drinking_age: Optional[datetime] = None
    is_locked = False
    current_drink: int = 0
    speed: float = 0.0

    def is_old(self) -> bool:
        drinking_age = self.drinking_age
        if drinking_age is None:
            return True

        now = pendulum.now()
        delta = now - drinking_age
        return delta > timedelta(minutes=1)


def generate_code() -> str:
    return secrets.token_urlsafe(16)


async def fetch_drinks(client: firestore.AsyncClient) -> List[Drink]:
    drinks = []
    for doc in await client.collection("drinks").get():
        drink = Drink.from_dict(doc.to_dict())
        drinks.append(drink)

    return drinks


async def _client():
    client = firestore.AsyncClient()
    try:
        yield client
    finally:
        client.close()


state = State(
    drinks=[],
    code=generate_code(),
)

config = Config.from_env()
config.basic_setup()


@asynccontextmanager
async def lifespan(_: FastAPI):
    client = firestore.AsyncClient()
    try:
        state.drinks = await fetch_drinks(client)
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
async def redirect_to_docs():
    return RedirectResponse("/docs")


@app.get("/probe/live")
async def liveness_probe():
    return {"status": "ok"}


@app.get("/state")
async def get_state(token: HTTPAuthorizationCredentials = Depends(auth_token)) -> State:
    if token.credentials not in [
        config.internal_token,
        config.wheel_token,
    ]:
        raise HTTPException(HTTPStatus.FORBIDDEN)

    return state


@app.post("/spin", response_class=Response, status_code=204)
async def spin(speed: float, token: HTTPAuthorizationCredentials = Depends(auth_token)):
    if token.credentials != state.code:
        raise HTTPException(HTTPStatus.FORBIDDEN)

    if state.is_locked:
        raise HTTPException(HTTPStatus.CONFLICT)
    state.is_locked = True
    state.speed = speed
    state.current_drink = random.randrange(0, len(state.drinks))


@app.put("/unlock", response_class=Response, status_code=204)
async def unlock(token: HTTPAuthorizationCredentials = Depends(auth_token)):
    if token.credentials != config.wheel_token:
        raise HTTPException(HTTPStatus.FORBIDDEN)

    state.is_locked = False
    state.code = generate_code()


@app.post("/drink", response_class=Response, status_code=201)
async def add_drink(
    name: str,
    client: firestore.AsyncClient = Depends(_client),
    token: HTTPAuthorizationCredentials = Depends(auth_token),
):
    if token.credentials != config.internal_token:
        raise HTTPException(HTTPStatus.FORBIDDEN)

    if name not in (d.name for d in state.drinks):
        drink = Drink.create(name)
        await client.collection("drinks").document(drink.id).set(drink.to_dict())
        state.drinks.append(drink)


@app.delete("/drink", response_class=Response, status_code=201)
async def delete_drink(
    drink_id: str,
    client: firestore.AsyncClient = Depends(_client),
    token: HTTPAuthorizationCredentials = Depends(auth_token),
):
    if token.credentials != config.internal_token:
        raise HTTPException(HTTPStatus.FORBIDDEN)

    await client.collection("drinks").document(drink_id).delete()
    state.drinks = [d for d in state.drinks if d.id != drink_id]
