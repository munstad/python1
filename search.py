"""
Search task creation and management.
Пользователь вводит логин/пароль от визового центра прямо в боте.
Они шифруются и передаются в Go-ядро вместе с задачей.
"""
import re
import uuid
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states.states import SearchTaskStates
from services.database import (
    AsyncSessionFactory, get_user_profile, create_task,
    get_user_tasks, update_task_status, decrypt_profile
)
from services.broker import BrokerService
from services.encryption import EncryptionService
from keyboards.keyboards import (
    visa_type_keyboard, category_keyboard, confirm_keyboard,
    task_actions_keyboard, main_menu, visa_center_keyboard
)
from models import TaskStatus
from config import settings

router = Router()
DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")

enc = EncryptionService(settings.encryption_key)

_broker: BrokerService | None = None


def set_broker(broker: BrokerService):
    global _broker
    _broker = broker


# ── Запуск поиска ─────────────────────────────────────────────────────────────

@router.message(Command("start_search"))
@router.message(F.text == "🔍 Начать поиск")
async def cmd_start_search(message: Message, state: FSMContext):
    async with AsyncSessionFactory() as session:
        profile = await get_user_profile(session, message.from_user.id)
    if not profile:
        return await message.answer("⚠️ Сначала заполните личные данные: /register")

    await state.set_state(SearchTaskStates.visa_center)
    await message.answer(
        "🔍 <b>Новая задача поиска</b>\n\n"
        "Шаг 1/7 — Выберите визовый центр:",
        parse_mode="HTML",
        reply_markup=visa_center_keyboard(),
    )


@router.callback_query(SearchTaskStates.visa_center, F.data.startswith("vc:"))
async def task_visa_center(cb: CallbackQuery, state: FSMContext):
    center = cb.data.split(":", 1)[1]
    await state.update_data(visa_center=center)
    await state.set_state(SearchTaskStates.vfs_email)
    await cb.message.edit_text(
        f"🏢 Выбран: <b>{center}</b>\n\n"
        "Шаг 2/7 — Введите ваш <b>email</b> от личного кабинета на сайте визового центра\n"
        f"(регистрация: visa.vfsglobal.com)\n\n"
        "📧 Email:",
        parse_mode="HTML",
    )


@router.message(SearchTaskStates.vfs_email)
async def task_vfs_email(message: Message, state: FSMContext):
    email = message.text.strip()
    if "@" not in email:
        return await message.answer("❌ Введите корректный email (например: name@mail.ru)")
    # Шифруем сразу
    await state.update_data(vfs_email_enc=enc.encrypt(email))
    await state.set_state(SearchTaskStates.vfs_password)

    # Удаляем сообщение с email для безопасности
    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(
        "Шаг 3/7 — Введите <b>пароль</b> от личного кабинета визового центра\n\n"
        "🔒 Пароль (сообщение будет удалено автоматически):",
        parse_mode="HTML",
    )


@router.message(SearchTaskStates.vfs_password)
async def task_vfs_password(message: Message, state: FSMContext):
    password = message.text.strip()
    # Шифруем сразу
    await state.update_data(vfs_password_enc=enc.encrypt(password))

    # Удаляем сообщение с паролем немедленно
    try:
        await message.delete()
    except Exception:
        pass

    await state.set_state(SearchTaskStates.visa_type)
    await message.answer(
        "✅ Данные сохранены (зашифрованы)\n\n"
        "Шаг 4/7 — Выберите тип визы:",
        reply_markup=visa_type_keyboard(),
    )


@router.callback_query(SearchTaskStates.visa_type, F.data.startswith("vtype:"))
async def task_visa_type(cb: CallbackQuery, state: FSMContext):
    vtype = cb.data.split(":")[1]
    await state.update_data(visa_type=vtype)
    await state.set_state(SearchTaskStates.category)
    await cb.message.edit_text(
        "Шаг 5/7 — Выберите категорию:",
        reply_markup=category_keyboard(),
    )


@router.callback_query(SearchTaskStates.category, F.data.startswith("cat:"))
async def task_category(cb: CallbackQuery, state: FSMContext):
    cat = cb.data.split(":")[1]
    await state.update_data(category=cat)
    await state.set_state(SearchTaskStates.date_from)
    await cb.message.edit_text("Шаг 6/7 — Начало периода поиска (ДД.ММ.ГГГГ):")


@router.message(SearchTaskStates.date_from)
async def task_date_from(message: Message, state: FSMContext):
    if not DATE_RE.match(message.text.strip()):
        return await message.answer("❌ Неверный формат. Введите ДД.ММ.ГГГГ")
    await state.update_data(date_from=message.text.strip())
    await state.set_state(SearchTaskStates.date_to)
    await message.answer("Конец периода поиска (ДД.ММ.ГГГГ):")


@router.message(SearchTaskStates.date_to)
async def task_date_to(message: Message, state: FSMContext):
    if not DATE_RE.match(message.text.strip()):
        return await message.answer("❌ Неверный формат. Введите ДД.ММ.ГГГГ")
    await state.update_data(date_to=message.text.strip())
    await state.set_state(SearchTaskStates.applicant_count)
    await message.answer("Шаг 7/7 — Количество заявителей (число):")


@router.message(SearchTaskStates.applicant_count)
async def task_applicant_count(message: Message, state: FSMContext):
    if not message.text.strip().isdigit() or int(message.text.strip()) < 1:
        return await message.answer("❌ Введите целое число >= 1")
    count = int(message.text.strip())
    await state.update_data(applicant_count=count)
    data = await state.get_data()
    await state.set_state(SearchTaskStates.confirm)

    visa_type_names = {
        "tourist": "🏖 Туристическая",
        "business": "💼 Деловая",
        "guest": "👥 Гостевая",
        "student": "🎓 Учебная",
        "other": "Другой",
    }
    cat_names = {"standard": "🐢 Стандартный", "urgent": "⚡ Срочный"}

    await message.answer(
        f"✅ <b>Параметры поиска:</b>\n\n"
        f"🏢 Центр: <b>{data['visa_center']}</b>\n"
        f"🪪 Тип: <b>{visa_type_names.get(data['visa_type'], data['visa_type'])}</b>\n"
        f"⚡ Категория: <b>{cat_names.get(data['category'], data['category'])}</b>\n"
        f"📅 Период: <b>{data['date_from']} — {data['date_to']}</b>\n"
        f"👥 Заявителей: <b>{count}</b>\n"
        f"🔐 Логин VFS: <b>✓ сохранён (зашифрован)</b>",
        parse_mode="HTML",
        reply_markup=confirm_keyboard("task_confirm:yes", "task_confirm:no"),
    )


@router.callback_query(SearchTaskStates.confirm, F.data == "task_confirm:yes")
async def task_confirm_yes(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    date_from = datetime.strptime(data["date_from"], "%d.%m.%Y").date()
    date_to = datetime.strptime(data["date_to"], "%d.%m.%Y").date()

    # Получаем персональные данные пользователя для передачи в Go
    async with AsyncSessionFactory() as session:
        profile = await get_user_profile(session, cb.from_user.id)
        profile_data = decrypt_profile(profile, enc) if profile else {}

        task = await create_task(
            session,
            user_id=cb.from_user.id,
            visa_center=data["visa_center"],
            visa_type=data["visa_type"],
            category=data["category"],
            date_from=date_from,
            date_to=date_to,
            applicant_count=data["applicant_count"],
        )
        await update_task_status(session, task.id, TaskStatus.running,
                                 started_at=datetime.utcnow())

    task_id_str = str(task.id)

    if _broker:
        # Расшифровываем VFS credentials только для передачи в Go-ядро
        # Go-ядро использует их один раз и не хранит
        vfs_email = enc.decrypt(data["vfs_email_enc"])
        vfs_password = enc.decrypt(data["vfs_password_enc"])

        await _broker.publish_task(task.id, "start", {
            "user_id": cb.from_user.id,
            "visa_center": data["visa_center"],
            "visa_type": data["visa_type"],
            "category": data["category"],
            "date_from": data["date_from"],
            "date_to": data["date_to"],
            "applicant_count": data["applicant_count"],
            # Учётные данные визового центра
            "vfs_email": vfs_email,
            "vfs_password": vfs_password,
            # Персональные данные для заполнения формы
            "full_name": profile_data.get("full_name", ""),
            "birth_date": profile_data.get("birth_date", ""),
            "passport_no": profile_data.get("passport_no", ""),
            "passport_exp": profile_data.get("passport_exp", ""),
            "phone": profile_data.get("phone", ""),
            "email": profile_data.get("email", ""),
        })

    await state.clear()
    await cb.message.edit_text(
        f"🚀 <b>Поиск запущен!</b>\n\n"
        f"ID задачи: <code>{task_id_str}</code>\n\n"
        f"Бот мониторит сайт и запишет вас автоматически, "
        f"как только появится свободный слот.\n\n"
        f"Вы получите уведомление с подтверждением.",
        parse_mode="HTML",
        reply_markup=task_actions_keyboard(task_id_str),
    )


@router.callback_query(SearchTaskStates.confirm, F.data == "task_confirm:no")
async def task_confirm_no(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Поиск отменён.")


# ── Stop / Status ─────────────────────────────────────────────────────────────

@router.message(Command("stop_search"))
@router.message(F.text == "⏹ Остановить поиск")
async def cmd_stop_search(message: Message):
    async with AsyncSessionFactory() as session:
        tasks = await get_user_tasks(session, message.from_user.id)
        active = [t for t in tasks if t.status == TaskStatus.running]

    if not active:
        return await message.answer("Нет активных задач поиска.")

    for task in active:
        async with AsyncSessionFactory() as session:
            await update_task_status(session, task.id, TaskStatus.cancelled)
        if _broker:
            await _broker.publish_task(task.id, "stop")

    await message.answer(f"⏹ Остановлено задач: {len(active)}", reply_markup=main_menu())


@router.message(Command("status"))
@router.message(F.text == "📋 Статус")
async def cmd_status(message: Message):
    async with AsyncSessionFactory() as session:
        tasks = await get_user_tasks(session, message.from_user.id)

    if not tasks:
        return await message.answer("У вас нет задач. Начните поиск: /start_search")

    STATUS_EMOJI = {
        "pending": "⏳", "running": "🔄", "paused": "⏸",
        "slot_found": "🎯", "booking": "📝", "booked": "✅",
        "error": "❌", "cancelled": "🚫",
    }
    lines = ["📊 <b>Ваши задачи:</b>\n"]
    for t in tasks[:5]:
        emoji = STATUS_EMOJI.get(t.status.value, "❓")
        task_id_str = str(t.id)
        lines.append(
            f"{emoji} <code>{task_id_str[:8]}…</code> | {t.visa_center}\n"
            f"   {t.visa_type} | {t.status.value}\n"
            f"   📅 {t.date_from} — {t.date_to}"
        )
    await message.answer("\n\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data == "show_status")
async def cb_show_status(cb: CallbackQuery):
    async with AsyncSessionFactory() as session:
        tasks = await get_user_tasks(session, cb.from_user.id)

    if not tasks:
        return await cb.answer("У вас нет задач.", show_alert=True)

    STATUS_EMOJI = {
        "pending": "⏳", "running": "🔄", "paused": "⏸",
        "slot_found": "🎯", "booking": "📝", "booked": "✅",
        "error": "❌", "cancelled": "🚫",
    }
    lines = ["📊 <b>Ваши задачи:</b>\n"]
    for t in tasks[:10]:
        emoji = STATUS_EMOJI.get(t.status.value, "❓")
        lines.append(
            f"{emoji} <code>{str(t.id)[:8]}…</code> | {t.visa_center}\n"
            f"   {t.visa_type} | <b>{t.status.value}</b>\n"
            f"   📅 {t.date_from} — {t.date_to}"
        )
    await cb.message.answer("\n\n".join(lines), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("stop:"))
async def cb_stop_task(cb: CallbackQuery):
    task_id = cb.data.split(":")[1]
    async with AsyncSessionFactory() as session:
        await update_task_status(session, uuid.UUID(task_id), TaskStatus.cancelled)
    if _broker:
        await _broker.publish_task(uuid.UUID(task_id), "stop")
    await cb.message.edit_text(f"⏹ Задача {task_id[:8]}… остановлена.")
