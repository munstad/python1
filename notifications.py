"""
Handles inbound notifications from Go core via RabbitMQ.
Sends Telegram messages to users.
"""
import uuid

from aiogram import Bot

from services.database import AsyncSessionFactory, update_task_status, log_event
from models import TaskStatus


async def handle_notification(bot: Bot, data: dict):
    """
    Expected payload fields:
      - event: "slot_found" | "booked" | "error" | "captcha_required"
      - task_id: str (UUID)
      - user_id: int
      - message: str (human-readable)
      - booking_ref: str (optional, on booked)
      - captcha_image: str (optional base64, on captcha_required)
    """
    event = data.get("event")
    task_id = data.get("task_id")
    user_id = data.get("user_id")
    msg_text = data.get("message", "")

    if not (event and task_id and user_id):
        return

    task_uuid = uuid.UUID(task_id)

    async with AsyncSessionFactory() as session:
        await log_event(session, task_uuid, event, data)

        if event == "slot_found":
            await update_task_status(session, task_uuid, TaskStatus.slot_found)
            await bot.send_message(
                user_id,
                f"🎯 <b>Найден подходящий слот!</b>\n\n{msg_text}\n\nВыполняю бронирование…",
                parse_mode="HTML",
            )

        elif event == "booked":
            booking_ref = data.get("booking_ref", "—")
            await update_task_status(session, task_uuid, TaskStatus.booked, booking_ref=booking_ref)
            await bot.send_message(
                user_id,
                f"✅ <b>Слот забронирован!</b>\n\n"
                f"🔖 Номер записи: <code>{booking_ref}</code>\n\n{msg_text}",
                parse_mode="HTML",
            )

        elif event == "error":
            await update_task_status(session, task_uuid, TaskStatus.error, error_message=msg_text)
            await bot.send_message(
                user_id,
                f"❌ <b>Ошибка бронирования</b>\n\n{msg_text}\n\nПопробуйте запустить поиск заново.",
                parse_mode="HTML",
            )

        elif event == "captcha_required":
            # Manual CAPTCHA fallback — send image to user
            captcha_image = data.get("captcha_image")
            if captcha_image:
                import base64
                img_bytes = base64.b64decode(captcha_image)
                await bot.send_photo(
                    user_id,
                    photo=img_bytes,
                    caption=(
                        "🤖 <b>Требуется решение капчи</b>\n\n"
                        f"Задача: <code>{task_id[:8]}…</code>\n\n"
                        "Введите текст с картинки командой:\n"
                        f"<code>/captcha {task_id} ТЕКСТ</code>"
                    ),
                    parse_mode="HTML",
                )
            else:
                await bot.send_message(
                    user_id,
                    f"🤖 <b>Требуется решение капчи</b>\n\n{msg_text}",
                    parse_mode="HTML",
                )
