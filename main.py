"""
VFS Global Worker — Python
Слушает RabbitMQ, запускает мониторинг в отдельных потоках.
Уведомления передаются через thread-safe очередь обратно в главный loop.
"""
import asyncio
import json
import logging
import os
import queue
import signal
import threading

import aio_pika
import structlog

from worker import TaskWorker

logging.basicConfig(level=logging.INFO)
log = structlog.get_logger()

RABBITMQ_URL = os.environ["RABBITMQ_URL"]
EXCHANGE_TASKS = "visa.tasks"
EXCHANGE_NOTIFICATIONS = "visa.notifications"
QUEUE_TASKS = "core.tasks"

# Активные воркеры
active_workers: dict[str, TaskWorker] = {}
workers_lock = threading.Lock()

# Thread-safe очередь для уведомлений от воркеров → главный loop
notification_queue: queue.Queue = queue.Queue()


async def notification_sender(channel):
    """Читает уведомления из очереди и шлёт в RabbitMQ."""
    exchange = await channel.declare_exchange(
        EXCHANGE_NOTIFICATIONS, aio_pika.ExchangeType.DIRECT, durable=True
    )
    while True:
        # Проверяем очередь без блокировки
        try:
            payload = notification_queue.get_nowait()
            body = json.dumps(payload).encode()
            await exchange.publish(
                aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                routing_key="notifications",
            )
            log.info("notification.sent", ev=payload.get("event"), task_id=payload.get("task_id"))
        except queue.Empty:
            await asyncio.sleep(0.1)
        except Exception as e:
            log.error("notification_dispatch_failed", error_msg=str(e))
            await asyncio.sleep(1)


def make_notify(task_id: str):
    """Создаёт функцию уведомления для воркера — просто кладёт в очередь."""
    async def notify(payload: dict):
        notification_queue.put(payload)
    return notify


async def handle_message(message: aio_pika.IncomingMessage):
    async with message.process(requeue=False):
        try:
            data = json.loads(message.body)
        except Exception:
            log.error("message.parse_error")
            return

        task_id = data.get("task_id")
        action = data.get("action")
        log.info("task.received", task_id=task_id, action=action)

        if action == "start":
            with workers_lock:
                if task_id in active_workers:
                    log.warning("task.already_running", task_id=task_id)
                    return

            notify = make_notify(task_id)

            try:
                worker = TaskWorker(data, notify)
            except Exception as e:
                log.error("task.init_error", task_id=task_id, error=str(e))
                notification_queue.put({
                    "event": "task_error",
                    "task_id": task_id,
                    "user_id": data.get("user_id"),
                    "message": f"❌ Ошибка создания задачи: {e}",
                })
                return

            with workers_lock:
                active_workers[task_id] = worker

            def run_worker():
                try:
                    asyncio.run(worker.run())
                except Exception as e:
                    log.error("worker.crashed", task_id=task_id, error=str(e))
                    notification_queue.put({
                        "event": "task_error",
                        "task_id": task_id,
                        "user_id": data.get("user_id"),
                        "message": f"❌ Воркер упал: {e}",
                    })
                finally:
                    with workers_lock:
                        active_workers.pop(task_id, None)

            thread = threading.Thread(
                target=run_worker, daemon=True, name=f"worker-{task_id[:8]}"
            )
            thread.start()
            log.info("worker.started", task_id=task_id)

        elif action == "stop":
            with workers_lock:
                worker = active_workers.get(task_id)
            if worker:
                worker.stop()
                log.info("worker.stop_requested", task_id=task_id)


async def main():
    log.info("visa-worker: starting")

    # Ждём RabbitMQ
    connection = None
    for attempt in range(30):
        try:
            connection = await aio_pika.connect_robust(RABBITMQ_URL, timeout=10, fail_fast=True)
            break
        except Exception as e:
            log.warning(f"rabbitmq not ready, attempt {attempt+1}/30: {e}")
            await asyncio.sleep(5)
    if connection is None:
        raise RuntimeError("Cannot connect to RabbitMQ after 30 attempts")

    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)

    exchange = await channel.declare_exchange(
        EXCHANGE_TASKS, aio_pika.ExchangeType.DIRECT, durable=True
    )
    queue_obj = await channel.declare_queue(QUEUE_TASKS, durable=True)
    await queue_obj.bind(exchange, routing_key="tasks")

    log.info("visa-worker: ready, waiting for tasks")

    # Запускаем отправщик уведомлений в фоне
    asyncio.create_task(notification_sender(channel))

    await queue_obj.consume(handle_message)

    # Ждём сигнала
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, stop_event.set)
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)

    await stop_event.wait()

    log.info("visa-worker: shutting down")
    with workers_lock:
        for w in active_workers.values():
            w.stop()
    await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
