from typing import Self
from uuid import UUID

from pydantic import ConfigDict

from misfortune.shared_model import MisfortuneModel, TelegramWheel


class UserState(MisfortuneModel):
    model_config = ConfigDict(frozen=False)

    active_wheel: TelegramWheel | None
    drinks_message: int | None
    pending_registration_id: UUID | None

    @classmethod
    def create(cls) -> Self:
        return cls(
            active_wheel=None,
            drinks_message=None,
            pending_registration_id=None,
        )
