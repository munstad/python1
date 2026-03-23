"""
Registration flow — collects and encrypts user personal data.
"""
import re
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states.states import RegistrationStates
from services.database import AsyncSessionFactory, get_or_create_user, save_user_profile
from services.encryption import EncryptionService
from keyboards.keyboards import skip_keyboard, confirm_keyboard, main_menu
from config import settings

router = Router()
enc = EncryptionService(settings.encryption_key)

DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")


@router.message(Command("register"))
@router.message(F.text == "✏️ Редактировать данные")
async def cmd_register(message: Message, state: FSMContext):
    await state.set_state(RegistrationStates.full_name)
    await message.answer(
        "📝 <b>Шаг 1/8 — Полное имя</b>\n\n"
        "Введите ФИО <b>точно как в загранпаспорте</b> (латиницей).\n"
        "Пример: <code>IVANOV IVAN IVANOVICH</code>",
        parse_mode="HTML",
    )


@router.message(RegistrationStates.full_name)
async def reg_full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip().upper())
    await state.set_state(RegistrationStates.birth_date)
    await message.answer(
        "📅 <b>Шаг 2/8 — Дата рождения</b>\n\nФормат: <code>ДД.ММ.ГГГГ</code>",
        parse_mode="HTML",
    )


@router.message(RegistrationStates.birth_date)
async def reg_birth_date(message: Message, state: FSMContext):
    if not DATE_RE.match(message.text.strip()):
        return await message.answer("❌ Неверный формат. Введите дату в формате ДД.ММ.ГГГГ")
    await state.update_data(birth_date=message.text.strip())
    await state.set_state(RegistrationStates.citizenship)
    await message.answer(
        "🌍 <b>Шаг 3/8 — Гражданство</b>\n\nПример: <code>RUSSIA</code>",
        parse_mode="HTML",
    )


@router.message(RegistrationStates.citizenship)
async def reg_citizenship(message: Message, state: FSMContext):
    await state.update_data(citizenship=message.text.strip().upper())
    await state.set_state(RegistrationStates.passport_no)
    await message.answer(
        "🛂 <b>Шаг 4/8 — Номер загранпаспорта</b>\n\nПример: <code>700123456</code>",
        parse_mode="HTML",
    )


@router.message(RegistrationStates.passport_no)
async def reg_passport_no(message: Message, state: FSMContext):
    await state.update_data(passport_no=message.text.strip().upper())
    await state.set_state(RegistrationStates.passport_exp)
    await message.answer(
        "📅 <b>Шаг 5/8 — Срок действия паспорта</b>\n\nФормат: <code>ДД.ММ.ГГГГ</code>",
        parse_mode="HTML",
    )


@router.message(RegistrationStates.passport_exp)
async def reg_passport_exp(message: Message, state: FSMContext):
    if not DATE_RE.match(message.text.strip()):
        return await message.answer("❌ Неверный формат. Введите дату в формате ДД.ММ.ГГГГ")
    await state.update_data(passport_exp=message.text.strip())
    await state.set_state(RegistrationStates.passport_country)
    await message.answer(
        "🏳️ <b>Шаг 6/8 — Страна выдачи паспорта</b>\n\nПример: <code>RUSSIA</code>",
        parse_mode="HTML",
    )


@router.message(RegistrationStates.passport_country)
async def reg_passport_country(message: Message, state: FSMContext):
    await state.update_data(passport_country=message.text.strip().upper())
    await state.set_state(RegistrationStates.phone)
    await message.answer(
        "📱 <b>Шаг 7/8 — Номер телефона</b> (необязательно)\n\n"
        "Формат: <code>+79001234567</code>",
        parse_mode="HTML",
        reply_markup=skip_keyboard(),
    )


@router.message(RegistrationStates.phone)
async def reg_phone(message: Message, state: FSMContext):
    phone = None if message.text == "Пропустить" else message.text.strip()
    await state.update_data(phone=phone)
    await state.set_state(RegistrationStates.email)
    await message.answer(
        "📧 <b>Шаг 8/8 — Email</b> (необязательно)",
        parse_mode="HTML",
        reply_markup=skip_keyboard(),
    )


@router.message(RegistrationStates.email)
async def reg_email(message: Message, state: FSMContext):
    email = None if message.text == "Пропустить" else message.text.strip()
    data = await state.get_data()
    data["email"] = email

    summary = (
        f"✅ <b>Проверьте данные:</b>\n\n"
        f"👤 ФИО: <code>{data['full_name']}</code>\n"
        f"📅 Дата рождения: <code>{data['birth_date']}</code>\n"
        f"🌍 Гражданство: <code>{data['citizenship']}</code>\n"
        f"🛂 Паспорт: <code>{data['passport_no']}</code>\n"
        f"📅 Действителен до: <code>{data['passport_exp']}</code>\n"
        f"🏳️ Страна выдачи: <code>{data['passport_country']}</code>\n"
        f"📱 Телефон: <code>{data.get('phone') or '—'}</code>\n"
        f"📧 Email: <code>{data.get('email') or '—'}</code>"
    )
    await state.update_data(email=email)
    await state.set_state(RegistrationStates.confirm)
    await message.answer(
        summary,
        parse_mode="HTML",
        reply_markup=confirm_keyboard("reg_confirm:yes", "reg_confirm:no"),
    )


@router.callback_query(RegistrationStates.confirm, F.data == "reg_confirm:yes")
async def reg_confirm_yes(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    async with AsyncSessionFactory() as session:
        await get_or_create_user(session, cb.from_user.id, cb.from_user.username)
        await save_user_profile(
            session, cb.from_user.id, enc,
            full_name=data["full_name"],
            birth_date=data["birth_date"],
            citizenship=data["citizenship"],
            passport_no=data["passport_no"],
            passport_exp=data["passport_exp"],
            passport_country=data["passport_country"],
            phone=data.get("phone"),
            email=data.get("email"),
        )
    await state.clear()
    await cb.message.edit_text("✅ <b>Данные сохранены!</b>\nТеперь вы можете запустить поиск.", parse_mode="HTML")
    await cb.message.answer("Используйте меню:", reply_markup=main_menu())


@router.callback_query(RegistrationStates.confirm, F.data == "reg_confirm:no")
async def reg_confirm_no(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Регистрация отменена. Введите /register чтобы начать заново.")
