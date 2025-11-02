import asyncio
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from redis.asyncio import Redis

from .model import InternalWheel

if TYPE_CHECKING:
    from misfortune.config import RepoConfig
    from misfortune.shared_model import Drink

_logger = logging.getLogger(__name__)


class Repository:
    def __init__(self, config: RepoConfig) -> None:
        self._client = Redis(
            host=config.host,
            username=config.username,
            password=config.password,
            protocol=3,
        )
        self._prefix = f"{config.username}:api"

    async def fetch_wheel(self, wheel_id: UUID, /) -> InternalWheel:
        raw = await self._client.get(f"{self._prefix}:wheel:{wheel_id}")
        if raw is None:
            raise RuntimeError(f"Did not find wheel {wheel_id}")

        wheel = InternalWheel.model_validate_json(raw)
        return wheel

    async def fetch_wheels(self) -> list[InternalWheel]:
        client = self._client

        wheel_ids = set()
        async for key in client.scan_iter(match=f"{self._prefix}:wheel:*"):
            wheel_ids.add(UUID(key))

        wheels = []

        async with asyncio.TaskGroup() as tg:
            for wheel_id in wheel_ids:
                wheels.append(tg.create_task(self.fetch_wheel(wheel_id)))

        return [task.result() for task in wheels]

    async def create_wheel(self, wheel: InternalWheel) -> None:
        await self._client.set(
            f"{self._prefix}:wheel:{wheel.id}", wheel.model_dump_json()
        )

    async def update_wheel_name(self, wheel_id: UUID, /, *, name: str) -> None:
        old_wheel = await self.fetch_wheel(wheel_id)
        new_wheel = InternalWheel.model_validate(
            old_wheel.model_copy(update={"name": name})
        )
        await self.create_wheel(new_wheel)

    async def update_wheel_drinks(
        self, wheel_id: UUID, /, *, drinks: list[Drink]
    ) -> None:
        old_wheel = await self.fetch_wheel(wheel_id)
        new_wheel = InternalWheel.model_validate(
            old_wheel.model_copy(update={"drinks": drinks})
        )
        await self.create_wheel(new_wheel)

    async def delete_wheel(self, wheel_id: UUID, /) -> None:
        await self._client.delete(f"{self._prefix}:wheel:{wheel_id}")

    async def close(self) -> None:
        await self._client.aclose()
