from typing import TYPE_CHECKING

from google.cloud import firestore

from misfortune.bot.model import UserState

if TYPE_CHECKING:
    from misfortune.config import FirestoreConfig


class Repository:
    def __init__(self, config: FirestoreConfig) -> None:
        self._config = config
        self._client = firestore.AsyncClient()
        self._user_states = self._client.collection(config.user_states)

    async def load_user_states(self) -> dict[int, UserState]:
        result = {}

        async for doc in self._user_states.stream():
            result[int(doc.id)] = UserState.model_validate(doc.to_dict())

        return result

    async def update_user_state(self, user_id: int, state: UserState) -> None:
        await self._user_states.document(str(user_id)).set(
            state.model_dump(mode="json")
        )

    async def close(self) -> None:
        self._client.close()
