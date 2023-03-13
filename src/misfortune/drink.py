import uuid
from typing import Self

from pydantic import BaseModel


class Drink(BaseModel):
    id: str
    name: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
        }

    @classmethod
    def create(cls, name: str) -> Self:
        return cls(
            id=str(uuid.uuid4()),
            name=name,
        )

    @classmethod
    def from_dict(cls, doc: dict) -> Self:
        return cls(
            id=doc["id"],
            name=doc["name"],
        )
