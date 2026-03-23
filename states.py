from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    full_name = State()
    birth_date = State()
    citizenship = State()
    passport_no = State()
    passport_exp = State()
    passport_country = State()
    phone = State()
    email = State()
    confirm = State()


class SearchTaskStates(StatesGroup):
    visa_center = State()
    vfs_email = State()       # логин от личного кабинета VFS
    vfs_password = State()    # пароль от личного кабинета VFS
    visa_type = State()
    category = State()
    date_from = State()
    date_to = State()
    applicant_count = State()
    confirm = State()


class CaptchaStates(StatesGroup):
    waiting_for_solution = State()
