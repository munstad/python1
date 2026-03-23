"""
Database access layer — async SQLAlchemy + asyncpg.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, update

from models import Base, User, UserProfile, SearchTask, TaskEvent, TaskStatus
from services.encryption import EncryptionService
from config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_size=10, max_overflow=20)
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── User helpers ──────────────────────────────────────────────────────────────

async def get_or_create_user(session: AsyncSession, tg_id: int, username: Optional[str] = None) -> User:
    result = await session.execute(select(User).where(User.id == tg_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(id=tg_id, username=username)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_user_profile(session: AsyncSession, tg_id: int) -> Optional[UserProfile]:
    result = await session.execute(select(UserProfile).where(UserProfile.user_id == tg_id))
    return result.scalar_one_or_none()


async def save_user_profile(
    session: AsyncSession,
    tg_id: int,
    enc: EncryptionService,
    full_name: str,
    birth_date: str,
    citizenship: str,
    passport_no: str,
    passport_exp: str,
    passport_country: str,
    phone: Optional[str] = None,
    email: Optional[str] = None,
) -> UserProfile:
    profile = await get_user_profile(session, tg_id)
    data = dict(
        full_name_enc=enc.encrypt(full_name),
        birth_date_enc=enc.encrypt(birth_date),
        citizenship_enc=enc.encrypt(citizenship),
        passport_no_enc=enc.encrypt(passport_no),
        passport_exp_enc=enc.encrypt(passport_exp),
        passport_country_enc=enc.encrypt(passport_country),
        phone_enc=enc.encrypt(phone) if phone else None,
        email_enc=enc.encrypt(email) if email else None,
    )
    if profile:
        for k, v in data.items():
            setattr(profile, k, v)
    else:
        profile = UserProfile(user_id=tg_id, **data)
        session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


def decrypt_profile(profile: UserProfile, enc: EncryptionService) -> dict:
    """Расшифровывает все поля профиля и возвращает словарь."""
    return {
        "full_name": enc.decrypt(profile.full_name_enc),
        "birth_date": enc.decrypt(profile.birth_date_enc),
        "citizenship": enc.decrypt(profile.citizenship_enc),
        "passport_no": enc.decrypt(profile.passport_no_enc),
        "passport_exp": enc.decrypt(profile.passport_exp_enc),
        "passport_country": enc.decrypt(profile.passport_country_enc),
        "phone": enc.decrypt(profile.phone_enc) if profile.phone_enc else "",
        "email": enc.decrypt(profile.email_enc) if profile.email_enc else "",
    }


# ── Task helpers ──────────────────────────────────────────────────────────────

async def create_task(
    session: AsyncSession,
    user_id: int,
    visa_center: str,
    visa_type: str,
    category: str,
    date_from: date,
    date_to: date,
    applicant_count: int = 1,
) -> SearchTask:
    task = SearchTask(
        user_id=user_id,
        visa_center=visa_center,
        visa_type=visa_type,
        category=category,
        date_from=date_from,
        date_to=date_to,
        applicant_count=applicant_count,
        status=TaskStatus.pending,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def get_user_tasks(session: AsyncSession, user_id: int) -> List[SearchTask]:
    result = await session.execute(
        select(SearchTask).where(SearchTask.user_id == user_id).order_by(SearchTask.created_at.desc())
    )
    return result.scalars().all()


async def get_task(session: AsyncSession, task_id: uuid.UUID) -> Optional[SearchTask]:
    result = await session.execute(select(SearchTask).where(SearchTask.id == task_id))
    return result.scalar_one_or_none()


async def update_task_status(
    session: AsyncSession, task_id: uuid.UUID, status: TaskStatus, **kwargs
) -> None:
    await session.execute(
        update(SearchTask).where(SearchTask.id == task_id).values(status=status, **kwargs)
    )
    await session.commit()


async def log_event(
    session: AsyncSession, task_id: uuid.UUID, event_type: str, payload: dict = None
) -> None:
    event = TaskEvent(task_id=task_id, event_type=event_type, payload=payload)
    session.add(event)
    await session.commit()
