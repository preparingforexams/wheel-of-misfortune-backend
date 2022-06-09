from __future__ import annotations

import os
import random
import secrets
from asyncio import Lock
from dataclasses import dataclass
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

auth_token = HTTPBearer()


@dataclass
class Config:
    wheel_token: str

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            wheel_token=os.getenv("WHEEL_TOKEN"),
        )


class Drink(BaseModel):
    name: str

    @classmethod
    def from_doc(cls, doc: dict) -> Drink:
        return Drink(
            name=doc["name"],
        )


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


state = State(
    drinks=[],
    code=generate_code(),
)

config = Config.from_env()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://bembel.party",
        "https://wheel.bembel.party",
        "http://localhost",
        "http://localhost:8080",
    ], allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=RedirectResponse)
async def redirect_to_docs():
    return RedirectResponse("/docs")


async def refresh_drinks():
    client = firestore.Client()
    drinks = []
    for doc in client.collection("drinks").stream():
        drink = Drink.from_doc(doc.to_dict())
        drinks.append(drink)

    state.drinks = drinks
    state.drinking_age = pendulum.now()


lock = Lock()


@app.get("/state")
async def get_state(token: HTTPAuthorizationCredentials = Depends(auth_token)) -> State:
    if token.credentials != config.wheel_token:
        raise HTTPException(HTTPStatus.FORBIDDEN)

    if state.is_old():
        if not lock.locked():
            async with lock:
                if not state.is_old():
                    await refresh_drinks()

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
