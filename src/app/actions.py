from __future__ import annotations
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, delete

from app.models import (
    Book, BookCopy, EmailUser, Reservation,
    CopyStatus, ReservationStatus
)

DEFAULT_LOAN_DAYS = 30

def _ok(msg: str, **data):    return {"ok": True,  "message": msg, **({"data": data} if data else {})}
def _err(msg: str, code="", **data): return {"ok": False, "message": msg, "code": code, **({"data": data} if data else {})}

async def _get_or_create_user(session: AsyncSession, email: str, name: Optional[str]) -> EmailUser:
    email_norm = (email or "").strip().lower()
    res = await session.execute(select(EmailUser).where(EmailUser.email == email_norm))
    user = res.scalar_one_or_none()
    if user:
        return user
    user = EmailUser(email=email_norm, name=(name or "").strip() or None)
    session.add(user)
    await session.flush()
    return user

async def _find_book_by_id_or_title(session: AsyncSession, book_id: Optional[str], title: Optional[str]) -> Optional[Book]:
    if book_id:
        r = await session.execute(select(Book).where(Book.id == book_id))
        b = r.scalar_one_or_none()
        if b:
            return b
    if title:
        t = title.strip()
        r = await session.execute(select(Book).where(Book.title == t))
        b = r.scalars().first()
        if b:
            return b
    return None

async def list_books(session: AsyncSession) -> Dict[str, Any]:
    books: List[Book] = (await session.execute(select(Book))).scalars().all()
    if not books:
        return _ok("No hay libros registrados aún.", items=[])
    q_avail = (
        select(BookCopy.book_id, func.count().label("available"))
        .where(BookCopy.status == CopyStatus.AVAILABLE)
        .group_by(BookCopy.book_id)
    )
    avail_map = {row.book_id: int(row.available) for row in (await session.execute(q_avail))}
    q_total = select(BookCopy.book_id, func.count().label("total")).group_by(BookCopy.book_id)
    total_map = {row.book_id: int(row.total) for row in (await session.execute(q_total))}
    items = [{
        "book_id": b.id,
        "title": b.title,
        "author": b.author,
        "copies_available": avail_map.get(b.id, 0),
        "copies_total": total_map.get(b.id, 0),
    } for b in books]
    return _ok("Listado de libros disponible.", items=items)

async def register_book(session: AsyncSession, *, title: str, author: Optional[str]) -> Dict[str, Any]:
    if not title:
        return _err("Falta el título del libro.", code="MISSING_TITLE")
    b = Book(title=title.strip(), author=(author or None))
    session.add(b)
    await session.commit()
    await session.refresh(b)
    return _ok("Libro registrado exitosamente.", book_id=b.id, title=b.title, author=b.author)

async def register_copy(session: AsyncSession, *, book_id: str, barcode: str, location: str) -> Dict[str, Any]:
    if not (book_id and barcode and location):
        return _err("Faltan datos para registrar la copia (book_id, barcode, location).", code="MISSING_FIELDS")
    r = await session.execute(select(Book).where(Book.id == book_id))
    if not r.scalar_one_or_none():
        return _err("El libro indicado no existe.", code="BOOK_NOT_FOUND")
    r2 = await session.execute(select(BookCopy).where(BookCopy.barcode == barcode))
    if r2.scalar_one_or_none():
        return _err("El código de barras ya existe.", code="BARCODE_EXISTS")
    c = BookCopy(book_id=book_id, barcode=barcode, location=location, status=CopyStatus.AVAILABLE)
    session.add(c)
    await session.commit()
    await session.refresh(c)
    return _ok("Copia registrada exitosamente.", copy_id=c.id, book_id=c.book_id, barcode=c.barcode, location=c.location)

async def reserve(session: AsyncSession, *, book_id: Optional[str], book_title: Optional[str], name: Optional[str], email: str) -> Dict[str, Any]:
    if not email:
        return _err("Falta el email del solicitante.", code="MISSING_EMAIL")
    book = await _find_book_by_id_or_title(session, book_id, book_title)
    if not book:
        return _err("No encontré el libro solicitado (id/título).", code="BOOK_NOT_FOUND")
    r_copy = await session.execute(
        select(BookCopy).where(and_(BookCopy.book_id == book.id, BookCopy.status == CopyStatus.AVAILABLE)).limit(1)
    )
    copy = r_copy.scalar_one_or_none()
    if not copy:
        return _err("No hay copias disponibles para ese libro.", code="NO_AVAILABLE_COPIES")
    user = await _get_or_create_user(session, email=email, name=name)
    copy.status = CopyStatus.RESERVED
    due = datetime.utcnow() + timedelta(days=DEFAULT_LOAN_DAYS)
    res = Reservation(
        email_user_id=user.id, book_id=book.id, copy_id=copy.id,
        status=ReservationStatus.ACTIVE, due_date=due
    )
    session.add(res)
    await session.commit()
    await session.refresh(res)
    return _ok(
        "La reservación se realizó exitosamente.",
        reservation_id=res.id, book_id=book.id, copy_id=copy.id,
        user_email=user.email, due_date=res.due_date.isoformat()
    )

async def renew(session: AsyncSession, *, barcode: str, email: str) -> Dict[str, Any]:
    if not (barcode and email):
        return _err("Faltan datos para renovar (barcode, email).", code="MISSING_FIELDS")
    email_norm = email.strip().lower()
    r_user = await session.execute(select(EmailUser).where(EmailUser.email == email_norm))
    user = r_user.scalar_one_or_none()
    if not user:
        return _err("No encontré al usuario.", code="USER_NOT_FOUND")
    r_copy = await session.execute(select(BookCopy).where(BookCopy.barcode == barcode))
    copy = r_copy.scalar_one_or_none()
    if not copy:
        return _err("No encontré la copia indicada.", code="COPY_NOT_FOUND")
    r_res = await session.execute(
        select(Reservation).where(
            and_(Reservation.email_user_id == user.id, Reservation.copy_id == copy.id, Reservation.status == ReservationStatus.ACTIVE)
        )
    )
    reservation = r_res.scalar_one_or_none()
    if not reservation:
        return _err("No encontré una reservación activa para esos datos.", code="ACTIVE_RESERVATION_NOT_FOUND")
    if reservation.due_date < datetime.utcnow():
        return _err("La reservación ya está vencida, no se puede renovar.", code="RESERVATION_EXPIRED")
    reservation.due_date = reservation.due_date + timedelta(days=DEFAULT_LOAN_DAYS)
    reservation.renewed_cnt += 1
    await session.commit()
    await session.refresh(reservation)
    return _ok(
        "La reservación fue renovada exitosamente.",
        reservation_id=reservation.id, due_date=reservation.due_date.isoformat()
    )

async def cancel(session: AsyncSession, *, barcode: str, email: str) -> Dict[str, Any]:
    if not (barcode and email):
        return _err("Faltan datos para cancelar (barcode, email).", code="MISSING_FIELDS")
    email_norm = email.strip().lower()
    r_user = await session.execute(select(EmailUser).where(EmailUser.email == email_norm))
    user = r_user.scalar_one_or_none()
    if not user:
        return _err("No encontré al usuario.", code="USER_NOT_FOUND")
    r_copy = await session.execute(select(BookCopy).where(BookCopy.barcode == barcode))
    copy = r_copy.scalar_one_or_none()
    if not copy:
        return _err("No encontré la copia indicada.", code="COPY_NOT_FOUND")
    r = await session.execute(
        select(Reservation).where(
            and_(Reservation.email_user_id == user.id, Reservation.copy_id == copy.id, Reservation.status == ReservationStatus.ACTIVE)
        )
    )
    resv = r.scalar_one_or_none()
    if not resv:
        return _err("No encontré una reservación activa para esos datos.", code="ACTIVE_RESERVATION_NOT_FOUND")
    resv.status = ReservationStatus.CANCELED
    resv.canceled_at = datetime.utcnow()
    if copy.status != CopyStatus.AVAILABLE:
        copy.status = CopyStatus.AVAILABLE
    await session.commit()
    await session.refresh(resv)
    return _ok(
        "La reservación fue cancelada exitosamente.",
        reservation_id=resv.id
    )

async def delete_book(session: AsyncSession, *, book_id: str) -> Dict[str, Any]:
    if not book_id:
        return _err("Falta el id del libro.", code="MISSING_ID")
    r_book = await session.execute(select(Book).where(Book.id == book_id))
    book = r_book.scalar_one_or_none()
    if not book:
        return _err("No encontré el libro solicitado.", code="BOOK_NOT_FOUND")
    r_res_ids = await session.execute(
        select(Reservation.id).where(
            (Reservation.book_id == book_id)
        )
    )
    res_ids = [row[0] for row in r_res_ids]
    if res_ids:
        await session.execute(delete(Reservation).where(Reservation.id.in_(res_ids)))
    r_copy_ids = await session.execute(select(BookCopy.id).where(BookCopy.book_id == book_id))
    copy_ids = [row[0] for row in r_copy_ids]
    if copy_ids:
        await session.execute(delete(BookCopy).where(BookCopy.id.in_(copy_ids)))
    await session.execute(delete(Book).where(Book.id == book_id))
    await session.commit()
    return _ok("Libro eliminado exitosamente.", book_id=book_id, removed_copies=len(copy_ids), removed_reservations=len(res_ids))