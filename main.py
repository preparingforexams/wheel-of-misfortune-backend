from __future__ import annotations

import os
import random
from dataclasses import dataclass
from http import HTTPStatus
from typing import List

from fastapi import FastAPI, Depends
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

auth_token = APIKeyHeader(name="Authorization")


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


class State(BaseModel):
    drinks: List[Drink]
    is_locked = False
    current_drink: int = 0


state = State(
    drinks=[
        Drink(name="Korn"),
        Drink(name="Bier"),
    ],
)

config = Config.from_env()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://bembel.party",
        "https://wheel.bembel.party",
        "http://localhost",
    ], allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/state")
async def get_state(token: str = Depends(auth_token)) -> State:
    if token != config.wheel_token:
        raise HTTPException(HTTPStatus.FORBIDDEN)

    return state


@app.post("/spin", response_class=Response)
async def spin():
    if state.is_locked:
        raise HTTPException(HTTPStatus.CONFLICT)
    state.is_locked = True
    state.current_drink = random.randrange(0, len(state.drinks))


@app.put("/unlock", response_class=Response)
async def unlock(token: str = Depends(auth_token)):
    if token != config.wheel_token:
        raise HTTPException(HTTPStatus.FORBIDDEN)

    state.is_locked = False
