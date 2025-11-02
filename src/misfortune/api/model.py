import base64
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Self

from pydantic_core import Url

from misfortune.shared_model import Drink, MisfortuneModel


class WheelLogin(MisfortuneModel):
    token: str | None


class WheelRegistrationInfo(MisfortuneModel):
    registration_id: uuid.UUID
    telegram_url: Url

    @classmethod
    def create(cls, *, bot_name: str, registration_id: uuid.UUID) -> Self:
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
    drinks: Sequence[Drink]
    wheel_name: str
    code: str
    owner: int
    drinking_age: datetime | None = None
    is_locked: bool = False
    current_drink: int = 0
    speed: float = 0.0

    @classmethod
    def initial(cls, *, wheel: InternalWheel, code: str) -> Self:
        return cls(
            drinks=wheel.drinks,
            wheel_name=wheel.name,
            code=code,
            owner=wheel.owner,
        )

    def is_accessible(self, user_id: int) -> bool:
        return user_id == self.owner

    def is_old(self) -> bool:
        drinking_age = self.drinking_age
        if drinking_age is None:
            return True

        now = datetime.now(tz=UTC)
        delta = now - drinking_age
        return delta > timedelta(minutes=1)

    def replace(self, **kwargs) -> Self:
        return self.model_validate(self.model_copy(update=kwargs))


class InternalWheel(MisfortuneModel):
    id: uuid.UUID
    name: str
    owner: int
    drinks: list[Drink]

    @classmethod
    def create(cls, owner: int, name: str) -> Self:
        return cls(
            name=name,
            owner=owner,
            id=uuid.uuid4(),
            drinks=[],
        )
