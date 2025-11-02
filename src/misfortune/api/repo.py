from typing import TYPE_CHECKING

from google.cloud import firestore

from .model import InternalWheel

if TYPE_CHECKING:
    from uuid import UUID

    from misfortune.config import FirestoreConfig
    from misfortune.shared_model import Drink


class Repository:
    def __init__(self, config: FirestoreConfig) -> None:
        self._config = config
        self._client = firestore.AsyncClient()

    async def fetch_wheels(self) -> list[InternalWheel]:
        client = self._client

        wheels = []

        for doc in await client.collection(self._config.wheels).get():
            doc_dict = doc.to_dict()
            wheel = InternalWheel.model_validate(doc_dict)
            wheels.append(wheel)

        return wheels

    async def create_wheel(self, wheel: InternalWheel) -> None:
        await (
            self._client.collection(self._config.wheels)
            .document(str(wheel.id))
            .create(wheel.model_dump(mode="json"))
        )

    async def update_wheel_name(self, wheel_id: UUID, /, *, name: str) -> None:
        await (
            self._client.collection(self._config.wheels)
            .document(str(wheel_id))
            .update(
                dict(name=name),
            )
        )

    async def update_wheel_drinks(
        self, wheel_id: UUID, /, *, drinks: list[Drink]
    ) -> None:
        await (
            self._client.collection(self._config.wheels)
            .document(str(wheel_id))
            .update(
                dict(drinks=[d.model_dump(mode="json") for d in drinks]),
            )
        )

    async def delete_wheel(self, wheel_id: UUID, /) -> None:
        await (
            self._client.collection(self._config.wheels)
            .document(str(wheel_id))
            .delete()
        )

    async def close(self) -> None:
        self._client.close()
