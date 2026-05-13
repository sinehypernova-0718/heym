"""In-memory broadcast registry for background dashboard chat streams."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

ChatEvent = str | dict[str, Any]


@dataclass
class ChatTaskState:
    events: list[ChatEvent] = field(default_factory=list)
    subscribers: set[asyncio.Queue[ChatEvent | None]] = field(default_factory=set)
    done: bool = False


_tasks: dict[str, ChatTaskState] = {}


def create_task(conv_id: str) -> None:
    """Create and register a fresh stream state for a conversation."""
    _tasks[conv_id] = ChatTaskState()


def has_task(conv_id: str) -> bool:
    """Return whether a stream state exists for a conversation."""
    return conv_id in _tasks


def remove_task(conv_id: str) -> None:
    """Remove a stream state."""
    _tasks.pop(conv_id, None)


async def publish(conv_id: str, event: ChatEvent) -> None:
    """Broadcast an event to all current subscribers and keep it for replay."""
    state = _tasks.get(conv_id)
    if state is None:
        return
    state.events.append(event)
    for queue in list(state.subscribers):
        await queue.put(event)


async def finish(conv_id: str) -> None:
    """Mark a stream as complete and wake all current subscribers."""
    state = _tasks.get(conv_id)
    if state is None:
        return
    state.done = True
    for queue in list(state.subscribers):
        await queue.put(None)
    _remove_if_idle(conv_id)


def subscriber_count(conv_id: str) -> int:
    """Return the current number of active SSE subscribers."""
    state = _tasks.get(conv_id)
    return len(state.subscribers) if state is not None else 0


def _remove_if_idle(conv_id: str) -> None:
    state = _tasks.get(conv_id)
    if state is not None and state.done and not state.subscribers:
        remove_task(conv_id)


@asynccontextmanager
async def subscribe(conv_id: str) -> AsyncGenerator[asyncio.Queue[ChatEvent | None] | None, None]:
    """Subscribe to a stream, replaying events that were emitted before connection."""
    state = _tasks.get(conv_id)
    if state is None:
        yield None
        return

    queue: asyncio.Queue[ChatEvent | None] = asyncio.Queue()
    for event in state.events:
        await queue.put(event)
    if state.done:
        await queue.put(None)
    state.subscribers.add(queue)
    try:
        yield queue
    finally:
        state.subscribers.discard(queue)
        _remove_if_idle(conv_id)
