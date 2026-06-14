from __future__ import annotations

from functools import lru_cache

import redis

from .settings import Settings, get_settings


class RedisJobQueue:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

    def enqueue(self, task_id: str) -> None:
        self.client.rpush(self.settings.task_queue_name, task_id)

    def dequeue(self, timeout_seconds: int | None = None) -> str | None:
        timeout = self.settings.worker_poll_seconds if timeout_seconds is None else timeout_seconds
        result = self.client.blpop(self.settings.task_queue_name, timeout=timeout)
        if result is None:
            return None
        _, task_id = result
        return task_id

    def size(self) -> int:
        return int(self.client.llen(self.settings.task_queue_name))

    def ping(self) -> bool:
        return bool(self.client.ping())


@lru_cache(maxsize=1)
def get_queue() -> RedisJobQueue:
    return RedisJobQueue(get_settings())


def enqueue_task(task_id: str, settings: Settings | None = None) -> None:
    queue = RedisJobQueue(settings or get_settings())
    queue.enqueue(task_id)


def queue_size(settings: Settings | None = None) -> int:
    queue = RedisJobQueue(settings or get_settings())
    return queue.size()
