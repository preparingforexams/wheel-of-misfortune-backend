import asyncio
from typing import TYPE_CHECKING

from redis.asyncio import Redis

from misfortune.bot.model import UserState

if TYPE_CHECKING:
    from misfortune.config import RepoConfig


class Repository:
    def __init__(self, config: RepoConfig) -> None:
        self._client = Redis(
            host=config.host,
            username=config.username,
            password=config.password,
            protocol=3,
        )
        self._prefix = f"{config.username}:bot"

    async def __fetch_state(self, user_id: int) -> UserState:
        raw = await self._client.get(f"{self._prefix}:user_state:{user_id}")
        if raw is None:
            raise RuntimeError(f"No state for user {user_id}")

        return UserState.model_validate_json(raw)

    async def load_user_states(self) -> dict[int, UserState]:
        user_ids = set()
        async for key in self._client.scan_iter(match=f"{self._prefix}:user_state:*"):
            user_ids.add(int(key))

        result = {}

        async with asyncio.TaskGroup() as tg:
            for user_id in user_ids:
                result[user_id] = tg.create_task(self.__fetch_state(user_id))

        return {user_id: task.result() for user_id, task in result.items()}

    async def update_user_state(self, user_id: int, state: UserState) -> None:
        await self._client.set(
            f"{self._prefix}:user_state:{user_id}", state.model_dump_json()
        )

    async def close(self) -> None:
        await self._client.aclose()
