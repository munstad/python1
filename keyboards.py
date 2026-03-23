from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Начать поиск"), KeyboardButton(text="⏹ Остановить поиск")],
            [KeyboardButton(text="📋 Статус"), KeyboardButton(text="✏️ Редактировать данные")],
        ],
        resize_keyboard=True,
    )


def visa_center_keyboard() -> InlineKeyboardMarkup:
    centers = [
        ("🇳🇱 VFS Global — Нидерланды (Москва)", "VFS Global Netherlands Moscow"),
        ("🇩🇪 VFS Global — Германия (Москва)", "VFS Global Germany Moscow"),
        ("🇫🇷 VFS Global — Франция (Москва)", "VFS Global France Moscow"),
        ("🇮🇹 VFS Global — Италия (Москва)", "VFS Global Italy Moscow"),
        ("🇪🇸 VFS Global — Испания (Москва)", "VFS Global Spain Moscow"),
        ("✏️ Ввести вручную", "custom"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"vc:{value}")]
            for label, value in centers
        ]
    )


def confirm_keyboard(yes_data: str, no_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=yes_data),
        InlineKeyboardButton(text="❌ Отмена", callback_data=no_data),
    ]])


def skip_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def visa_type_keyboard() -> InlineKeyboardMarkup:
    types = [
        ("🏖 Туристическая", "tourist"),
        ("💼 Деловая", "business"),
        ("👥 Гостевая", "guest"),
        ("🎓 Учебная", "student"),
        ("📋 Другой", "other"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=f"vtype:{d}")] for t, d in types]
    )


def category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🐢 Стандартный", callback_data="cat:standard")],
        [InlineKeyboardButton(text="⚡ Срочный", callback_data="cat:urgent")],
    ])


def task_actions_keyboard(task_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏹ Остановить", callback_data=f"stop:{task_id}")],
        [InlineKeyboardButton(text="📊 Статус всех задач", callback_data="show_status")],
    ])
