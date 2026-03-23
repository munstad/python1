from __future__ import annotations

import enum
import uuid
from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import (
    BigInteger, Boolean, String, Text, Date,
    DateTime, SmallInteger, ForeignKey,
    func, Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)

    profile: Mapped[Optional["UserProfile"]] = relationship("UserProfile", back_populates="user", uselist=False)
    tasks: Mapped[List["SearchTask"]] = relationship("SearchTask", back_populates="user")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    full_name_enc: Mapped[str] = mapped_column(Text, nullable=False)
    birth_date_enc: Mapped[str] = mapped_column(Text, nullable=False)
    citizenship_enc: Mapped[str] = mapped_column(Text, nullable=False)
    passport_no_enc: Mapped[str] = mapped_column(Text, nullable=False)
    passport_exp_enc: Mapped[str] = mapped_column(Text, nullable=False)
    passport_country_enc: Mapped[str] = mapped_column(Text, nullable=False)
    phone_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    email_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="profile")


class TaskStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    paused = "paused"
    slot_found = "slot_found"
    booking = "booking"
    booked = "booked"
    error = "error"
    cancelled = "cancelled"


class SearchTask(Base):
    __tablename__ = "search_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    # FIX: explicitly name the enum type to match PostgreSQL
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status", create_type=False),
        default=TaskStatus.pending
    )
    visa_center: Mapped[str] = mapped_column(String(128), nullable=False)
    visa_type: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="standard")
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    applicant_count: Mapped[int] = mapped_column(SmallInteger, default=1)
    booked_slot: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    booking_ref: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="tasks")
    events: Mapped[List["TaskEvent"]] = relationship("TaskEvent", back_populates="task")


class TaskEvent(Base):
    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("search_tasks.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped["SearchTask"] = relationship("SearchTask", back_populates="events")
