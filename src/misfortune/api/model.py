import uuid
from typing import Self

from misfortune.shared_model import Drink, MisfortuneModel


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
