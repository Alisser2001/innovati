from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.deps import get_session
from app.models import Book, BookCopy, CopyStatus
from app.schemas import BookIn, BookOut, BookListItem, CopyIn, CopyOut, ReservationIn, ReservationOut, RenewalIn, CancelIn

router = APIRouter()

DEFAULT_LOAN_DAYS = 30

#Creacion de Libros
@router.post("/book", response_model=BookOut)
async def create_book(payload: BookIn, session: AsyncSession = Depends(get_session)):
    b = Book(title=payload.title, author=payload.author)
    session.add(b)
    await session.commit()
    await session.refresh(b)
    return BookOut(id=b.id, title=b.title, author=b.author)

#Creacion de Copia de Libro
@router.post("/book/{book_id}/copies", response_model=CopyOut)
async def create_copy(book_id: str, payload: CopyIn, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(Book).where(Book.id == book_id))
    b = res.scalar_one_or_none()
    if not b:
        raise HTTPException(status_code=404, detail="BOOK_NOT_FOUND")

    res2 = await session.execute(select(BookCopy).where(BookCopy.barcode == payload.barcode))
    if res2.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="BARCODE_ALREADY_EXISTS")

    c = BookCopy(
        book_id=book_id,
        barcode=payload.barcode,
        location=payload.location,
        status=CopyStatus.AVAILABLE,
    )
    session.add(c)
    await session.commit()
    await session.refresh(c)

    return CopyOut(
        id=c.id,
        book_id=c.book_id,
        barcode=c.barcode,
        status=c.status.value,
        location=c.location,
    )

#Traer las Copias de un Libro
@router.get("/book/{book_id}/copies", response_model=list[CopyOut])
async def list_copies(book_id: str, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(Book).where(Book.id == book_id))
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="BOOK_NOT_FOUND")

    res2 = await session.execute(select(BookCopy).where(BookCopy.book_id == book_id))
    copies = res2.scalars().all()
    return [
        CopyOut(
            id=c.id,
            book_id=c.book_id,
            barcode=c.barcode,
            status=c.status.value,
            location=c.location,
        )
        for c in copies
    ]

#Traer un Listado de los Libros Disponibles
@router.get("/book/available", response_model=list[BookListItem])
async def list_books(session: AsyncSession = Depends(get_session)):
    books = (await session.execute(select(Book))).scalars().all()
    if not books:
        return []
    q_avail = (
        select(BookCopy.book_id, func.count().label("available"))
        .where(BookCopy.status == CopyStatus.AVAILABLE)
        .group_by(BookCopy.book_id)
    )
    avail_map = {row.book_id: int(row.available) for row in (await session.execute(q_avail))}
    q_total = (
        select(BookCopy.book_id, func.count().label("total"))
        .group_by(BookCopy.book_id)
    )
    total_map = {row.book_id: int(row.total) for row in (await session.execute(q_total))}

    out: list[BookListItem] = []
    for b in books:
        out.append(BookListItem(
            id=b.id,
            title=b.title,
            author=b.author,
            copies_available=avail_map.get(b.id, 0),
            copies_total=total_map.get(b.id, 0),
        ))
    return out

#Reservar un Libro
@router.post("/book/reserve", response_model=ReservationOut)
async def create_reservation(payload: ReservationIn, session: AsyncSession = Depends(get_session)):
    res_book = await session.execute(select(Book).where(Book.id == payload.book_id))
    book = res_book.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="BOOK_NOT_FOUND")

    email_norm = payload.email.lower().strip()
    res_user = await session.execute(select(EmailUser).where(EmailUser.email == email_norm))
    user = res_user.scalar_one_or_none()
    if not user:
        user = EmailUser(email=email_norm, name=payload.name.strip())
        session.add(user)
        await session.flush()

    res_copy = await session.execute(
        select(BookCopy).where(
            and_(BookCopy.book_id == book.id, BookCopy.status == CopyStatus.AVAILABLE)
        ).limit(1)
    )
    copy = res_copy.scalar_one_or_none()
    if not copy:
        raise HTTPException(status_code=409, detail="NO_AVAILABLE_COPIES")

    copy.status = CopyStatus.RESERVED
    due = datetime.utcnow() + timedelta(days=DEFAULT_LOAN_DAYS)

    reservation = Reservation(
        email_user_id=user.id,
        book_id=book.id,
        copy_id=copy.id,
        status=ReservationStatus.ACTIVE,
        due_date=due,
    )
    session.add(reservation)

    await session.commit()
    await session.refresh(reservation)

    return ReservationOut(
        id=reservation.id,
        book_id=reservation.book_id,
        copy_id=reservation.copy_id,
        user_email=email_norm,
        status=reservation.status.value,
        due_date=reservation.due_date,
    )

#Renovar una Reservación
@router.post("/book/renew", response_model=ReservationOut)
async def renew_reservation(payload: RenewalIn, session: AsyncSession = Depends(get_session)):
    email_norm = payload.email.strip().lower()
    res_user = await session.execute(select(EmailUser).where(EmailUser.email == email_norm))
    user = res_user.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

    res_copy = await session.execute(select(BookCopy).where(BookCopy.barcode == payload.barcode))
    copy = res_copy.scalar_one_or_none()
    if not copy:
        raise HTTPException(status_code=404, detail="COPY_NOT_FOUND")

    res_res = await session.execute(
        select(Reservation).where(
            and_(
                Reservation.email_user_id == user.id,
                Reservation.copy_id == copy.id,
                Reservation.status == ReservationStatus.ACTIVE,
            )
        )
    )
    reservation = res_res.scalar_one_or_none()
    if not reservation:
        raise HTTPException(status_code=404, detail="ACTIVE_RESERVATION_NOT_FOUND")

    if reservation.due_date < datetime.utcnow():
        raise HTTPException(status_code=409, detail="RESERVATION_EXPIRED")

    reservation.due_date = reservation.due_date + timedelta(days=DEFAULT_LOAN_DAYS)
    reservation.renewed_cnt += 1

    await session.commit()
    await session.refresh(reservation)

    return ReservationOut(
        id=reservation.id,
        book_id=reservation.book_id,
        copy_id=reservation.copy_id,
        user_email=email_norm,
        status=reservation.status.value,
        due_date=reservation.due_date,
    )

# Cancelar por ID de reserva
@router.delete("/book/reserve/{reservation_id}", response_model=ReservationOut)
async def cancel_reservation_by_id(reservation_id: str, session: AsyncSession = Depends(get_session)):
    r = await session.get(Reservation, reservation_id)
    if not r:
        raise HTTPException(status_code=404, detail="RESERVATION_NOT_FOUND")

    if r.status != ReservationStatus.CANCELED:
        r.status = ReservationStatus.CANCELED
        r.canceled_at = datetime.utcnow()

    c = await session.get(BookCopy, r.copy_id)
    if c and c.status != CopyStatus.AVAILABLE:
        c.status = CopyStatus.AVAILABLE

    await session.commit()
    await session.refresh(r)

    return ReservationOut(
        id=r.id,
        book_id=r.book_id,
        copy_id=r.copy_id,
        user_email=(await session.get(EmailUser, r.email_user_id)).email,  
        status=r.status.value,
        due_date=r.due_date,
    )

# Cancelar por Barcode + Email
@router.post("/book/reserve/cancel", response_model=ReservationOut)
async def cancel_reservation_by_barcode(payload: CancelIn, session: AsyncSession = Depends(get_session)):
    email_norm = payload.email.strip().lower()

    q_user = await session.execute(select(EmailUser).where(EmailUser.email == email_norm))
    user = q_user.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

    q_copy = await session.execute(select(BookCopy).where(BookCopy.barcode == payload.barcode))
    copy = q_copy.scalar_one_or_none()
    if not copy:
        raise HTTPException(status_code=404, detail="COPY_NOT_FOUND")

    q_res = await session.execute(
        select(Reservation).where(
            and_(
                Reservation.email_user_id == user.id,
                Reservation.copy_id == copy.id,
                Reservation.status == ReservationStatus.ACTIVE,
            )
        )
    )
    r = q_res.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="ACTIVE_RESERVATION_NOT_FOUND")

    r.status = ReservationStatus.CANCELED
    r.canceled_at = datetime.utcnow()
    if copy.status != CopyStatus.AVAILABLE:
        copy.status = CopyStatus.AVAILABLE

    await session.commit()
    await session.refresh(r)

    return ReservationOut(
        id=r.id,
        book_id=r.book_id,
        copy_id=r.copy_id,
        user_email=email_norm,
        status=r.status.value,
        due_date=r.due_date,
    )

#Eliminar un Libro
@router.delete("/book/{book_id}")
async def delete_book(book_id: str, session: AsyncSession = Depends(get_session)):
    book = await session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="BOOK_NOT_FOUND")

    await session.delete(book)
    await session.commit()

    return {"detail": f"Book {book_id} deleted successfully (copies also removed)"}