from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from services.database import AsyncSessionFactory, get_or_create_user, get_user_profile
from keyboards.keyboards import main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    async with AsyncSessionFactory() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.username)
        profile = await get_user_profile(session, user.id)

    if not profile:
        await message.answer(
            "👋 Добро пожаловать в <b>Visa Slot Bot</b>!\n\n"
            "Этот бот автоматически мониторит сайт визового центра и бронирует слот, "
            "как только он появится.\n\n"
            "Для начала нужно заполнить ваши данные. Введите команду /register",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
    else:
        await message.answer(
            "👋 С возвращением! Ваши данные уже сохранены.\n"
            "Используйте меню ниже для управления поиском.",
            reply_markup=main_menu(),
        )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Доступные команды:</b>\n\n"
        "/start — Начало работы\n"
        "/register — Заполнить/обновить персональные данные\n"
        "/start_search — Запустить поиск слота\n"
        "/stop_search — Остановить поиск\n"
        "/status — Статус текущих задач\n"
        "/edit_data — Редактировать данные\n"
        "/help — Эта справка",
        parse_mode="HTML",
    )
