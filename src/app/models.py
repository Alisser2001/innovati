import enum, uuid
from datetime import datetime
from sqlalchemy import (
    String, Integer, Enum, ForeignKey, Text, Boolean, func, DateTime
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

class ReservationStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"

class CopyStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    RESERVED  = "RESERVED"
    LOANED    = "LOANED"
    LOST      = "LOST"
    DAMAGED   = "DAMAGED"

class Book(Base):
    __tablename__ = "book"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String, nullable=False, index=True)
    author: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    copies = relationship("BookCopy", back_populates="book")

class BookCopy(Base):
    __tablename__ = "book_copie"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id: Mapped[str] = mapped_column(String, ForeignKey("book.id", ondelete="CASCADE"), nullable=False, index=True) 
    barcode: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    status: Mapped[CopyStatus] = mapped_column(Enum(CopyStatus, native_enum=False), default=CopyStatus.AVAILABLE)
    location: Mapped[str] = mapped_column(String, nullable=False)
    book = relationship("Book", back_populates="copies") 

class EmailUser(Base):
    __tablename__ = "email_user"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String)

class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email_user_id: Mapped[str] = mapped_column(String, ForeignKey("email_user.id", ondelete="RESTRICT"), nullable=False, index=True)
    book_id: Mapped[str] = mapped_column(String, ForeignKey("book.id", ondelete="RESTRICT"), nullable=False, index=True)
    copy_id: Mapped[str] = mapped_column(String, ForeignKey("book_copie.id", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[ReservationStatus] = mapped_column(Enum(ReservationStatus, native_enum=False), default=ReservationStatus.ACTIVE, nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    renewed_cnt: Mapped[int] = mapped_column(Integer, default=0)

class EmailLog(Base):
    __tablename__ = "email_log"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    from_email: Mapped[str] = mapped_column(String, index=True)
    subject: Mapped[str | None] = mapped_column(String)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
