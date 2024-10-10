import abc
import uuid
from collections.abc import Sequence
from typing import Self

from pydantic import BaseModel, ConfigDict


class MisfortuneModel(BaseModel, abc.ABC):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )


class Drink(MisfortuneModel):
    name: str
    id: uuid.UUID

    @classmethod
    def create(cls, name: str) -> Self:
        return cls(
            name=name,
            id=uuid.uuid4(),
        )


class TelegramWheel(MisfortuneModel):
    name: str
    id: uuid.UUID
    is_owned: bool


class TelegramWheels(MisfortuneModel):
    wheels: Sequence[TelegramWheel]


class TelegramWheelState(MisfortuneModel):
    wheel: TelegramWheel
    drinks: Sequence[Drink]
