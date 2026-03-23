"""
RabbitMQ interface for the Python bot side.
- Publishes tasks to Go core (exchange: visa.tasks)
- Consumes notifications from Go core (queue: visa.notifications)
"""
from __future__ import annotations

import json
import asyncio
import uuid
from typing import Callable, Awaitable

import aio_pika
import structlog

from config import settings

log = structlog.get_logger()

EXCHANGE_TASKS = "visa.tasks"
EXCHANGE_NOTIFICATIONS = "visa.notifications"
QUEUE_NOTIFICATIONS = "bot.notifications"


class BrokerService:
    def __init__(self):
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange_tasks: aio_pika.abc.AbstractExchange | None = None

    async def connect(self):
        self._connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=100)
        self._exchange_tasks = await self._channel.declare_exchange(
            EXCHANGE_TASKS, aio_pika.ExchangeType.DIRECT, durable=True
        )
        log.info("broker.connected")

    async def publish_task(self, task_id: uuid.UUID, action: str, payload: dict = None):
        """Send command to Go core (start/stop monitoring)."""
        body = json.dumps({
            "task_id": str(task_id),
            "action": action,
            **(payload or {}),
        }).encode()
        await self._exchange_tasks.publish(
            aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key="tasks",
        )
        log.info("broker.task_published", task_id=str(task_id), action=action)

    async def start_consuming(self, handler: Callable[[dict], Awaitable[None]]):
        """Listen for notifications from Go core and call handler."""
        exchange_notif = await self._channel.declare_exchange(
            EXCHANGE_NOTIFICATIONS, aio_pika.ExchangeType.DIRECT, durable=True
        )
        queue = await self._channel.declare_queue(QUEUE_NOTIFICATIONS, durable=True)
        await queue.bind(exchange_notif, routing_key="notifications")

        async def _on_message(message: aio_pika.IncomingMessage):
            async with message.process(requeue=True):
                try:
                    data = json.loads(message.body)
                    await handler(data)
                except Exception as e:
                    log.error("broker.consume_error", error=str(e))

        await queue.consume(_on_message)
        log.info("broker.consuming_started", queue=QUEUE_NOTIFICATIONS)

    async def close(self):
        if self._connection:
            await self._connection.close()
