import abc
import uuid

from pydantic import BaseModel, ConfigDict


class MisfortuneModel(BaseModel, abc.ABC):
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )


class TelegramWheel(MisfortuneModel):
    name: str
    id: uuid.UUID
    is_owned: bool


class TelegramWheels(MisfortuneModel):
    wheels: list[TelegramWheel]
