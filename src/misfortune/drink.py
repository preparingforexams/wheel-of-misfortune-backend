from __future__ import annotations

from pydantic import BaseModel


class Drink(BaseModel):
    name: str

    @classmethod
    def from_doc(cls, doc: dict) -> Drink:
        return Drink(
            name=doc["name"],
        )
