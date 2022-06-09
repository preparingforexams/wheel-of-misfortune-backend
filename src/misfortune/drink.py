from __future__ import annotations

import uuid

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
    def create(cls, name: str) -> Drink:
        return Drink(
            id=str(uuid.uuid4()),
            name=name,
        )

    @classmethod
    def from_dict(cls, doc: dict) -> Drink:
        return Drink(
            id=doc["id"],
            name=doc["name"],
        )

