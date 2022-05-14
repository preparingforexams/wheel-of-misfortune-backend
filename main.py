from __future__ import annotations

import os
import random
import secrets
from dataclasses import dataclass
from http import HTTPStatus
from typing import List

from fastapi import FastAPI, Depends
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.responses import Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
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


class State(BaseModel):
    drinks: List[Drink]
    code: str
    is_locked = False
    current_drink: int = 0
    speed: float = 0.0


def generate_code() -> str:
    return secrets.token_urlsafe(16)


drink_names = [
    "Würgengel",
    "Fichtenfeuer",
    "Schnaps von der Marille",
    "Schachtwasser",
    "Stolperknabe",
    "Butzelmann",
    "Bierlikör",
    "Anreischke",
    "Föhrer Manhattan",
    "Bibergeil",
    "Erich's Rache",
    "Adler-Tropfen",
    "Limoncello",
    "Moselfeuer",
    "Alter Heidejäger",
    "Burgenkümmel",
    "Absinth",
    "Tequila",
    "Bärwurz",
    "Gude Nacht",
    "Batida de Coco",
    "Bacardi Razz",
    "Berentzen Waldfrucht",
    "Ouzo",
    "Orange",
    "Quitte",
    "Pfeffi",
]


state = State(
    drinks=[
        Drink(name=name) for name in drink_names
    ],
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


@app.get("/state")
async def get_state(token: HTTPAuthorizationCredentials = Depends(auth_token)) -> State:
    if token.credentials != config.wheel_token:
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
