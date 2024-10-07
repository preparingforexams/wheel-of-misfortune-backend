from __future__ import annotations

import abc
import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

_LOG = logging.getLogger(__name__)

type Listener[T] = Callable[[T], Awaitable[None]]


class Observable[T](abc.ABC):
    @property
    @abc.abstractmethod
    def value(self) -> T:
        pass

    @abc.abstractmethod
    async def update(self, value: T) -> None:
        pass

    @abc.abstractmethod
    @asynccontextmanager
    def atomic(self) -> AsyncIterator[Observable[T]]:
        pass

    @abc.abstractmethod
    def add_listener(self, listener: Listener[T]) -> None:
        pass

    @abc.abstractmethod
    def remove_listener(self, listener: Listener[T]) -> bool:
        pass


def observable[T](value: T) -> Observable[T]:
    return _ObservableImpl(value)


class _ObservableImpl[T](Observable[T]):
    def __init__(self, value: T):
        self._update_lock = asyncio.Lock()
        self._unsafe = _UnsafeObservableImpl(value)

    @property
    def value(self) -> T:
        return self._unsafe.value

    @asynccontextmanager
    async def atomic(self) -> AsyncIterator[Observable[T]]:
        async with self._update_lock:
            yield self._unsafe

    async def update(self, value: T) -> None:
        async with self._update_lock:
            await self._unsafe.update(value)

    def add_listener(self, listener: Listener[T]) -> None:
        self._unsafe.add_listener(listener)

    def remove_listener(self, listener: Listener[T]) -> bool:
        return self._unsafe.remove_listener(listener)


class _UnsafeObservableImpl[T](Observable[T]):
    def __init__(self, value: T):
        self._value = value

        self._listeners: list[Listener[T]] = []
        self._value = value

    @property
    def value(self) -> T:
        return self._value

    @staticmethod
    async def _notify(listener: Listener[T], value: T) -> None:
        try:
            await listener(value)
        except Exception as e:
            _LOG.error("Received exception from listener", exc_info=e)
            raise asyncio.CancelledError from e

    @asynccontextmanager
    async def atomic(self) -> AsyncIterator[Observable[T]]:
        yield self

    async def update(self, value: T) -> None:
        if self._value == value:
            return

        self._value = value
        async with asyncio.TaskGroup() as task_group:
            for listener in self._listeners:
                task_group.create_task(self._notify(listener, value))

    def add_listener(self, listener: Listener[T]) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: Listener[T]) -> bool:
        try:
            self._listeners.remove(listener)
        except ValueError:
            return False
        else:
            return True
