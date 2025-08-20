from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.deps import get_session

from app.schemas import (
    BookIn, BookOut, BookListItem,
    CopyIn, CopyOut,
    ReservationIn, ReservationOut,
    RenewalIn, CancelIn,
)

from app.actions import (
    list_books, register_book, register_copy,
    reserve, renew, cancel, delete_book
)

router = APIRouter()

@router.get("/books", response_model=list[BookListItem])
async def http_list_books(session: AsyncSession = Depends(get_session)):
    r = await list_books(session)
    items = (r.get("data") or {}).get("items") or []
    return [
        BookListItem(
            id=it["book_id"],
            title=it["title"],
            author=it.get("author"),
            copies_total=it.get("copies_total", 0),
            copies_available=it.get("copies_available", 0),
        )
        for it in items
    ]

@router.post("/book", response_model=BookOut)
async def http_create_book(payload: BookIn, session: AsyncSession = Depends(get_session)):
    r = await register_book(session, title=payload.title, author=payload.author)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["message"])
    d = r["data"]
    return BookOut(id=d["book_id"], title=d["title"], author=d.get("author"))

@router.post("/copy", response_model=CopyOut)
async def http_register_copy(payload: CopyIn, session: AsyncSession = Depends(get_session)):
    r = await register_copy(
        session,
        book_id=payload.book_id,
        barcode=payload.barcode,
        location=payload.location,
    )
    if not r["ok"]:
        code = r.get("code")
        status = 404 if code in {"BOOK_NOT_FOUND"} else 409 if code in {"BARCODE_EXISTS"} else 400
        raise HTTPException(status_code=status, detail=r["message"])
    d = r["data"]
    return CopyOut(
        id=d["copy_id"],
        book_id=d["book_id"],
        barcode=d["barcode"],
        status="AVAILABLE",           
        location=d["location"],
    )

@router.post("/reservation", response_model=ReservationOut)
async def http_create_reservation(payload: ReservationIn, session: AsyncSession = Depends(get_session)):
    r = await reserve(
        session,
        book_id=getattr(payload, "book_id", None),
        book_title=getattr(payload, "title", None) or getattr(payload, "book_title", None),
        name=getattr(payload, "name", None),
        email=payload.email,
    )
    if not r["ok"]:
        code = r.get("code")
        status = (
            404 if code in {"BOOK_NOT_FOUND", "USER_NOT_FOUND", "COPY_NOT_FOUND", "ACTIVE_RESERVATION_NOT_FOUND"}
            else 409 if code in {"NO_AVAILABLE_COPIES", "RESERVATION_EXPIRED"}
            else 400
        )
        raise HTTPException(status_code=status, detail=r["message"])
    d = r["data"]
    return ReservationOut(
        id=d["reservation_id"],
        book_id=d["book_id"],
        copy_id=d["copy_id"],
        user_email=d["user_email"],
        status="ACTIVE",
        due_date=d["due_date"],
    )

@router.post("/reservation/renewal")
async def http_renew_reservation(payload: RenewalIn, session: AsyncSession = Depends(get_session)):
    r = await renew(session, barcode=payload.barcode, email=payload.email)
    if not r["ok"]:
        code = r.get("code")
        status = (
            404 if code in {"USER_NOT_FOUND", "COPY_NOT_FOUND", "ACTIVE_RESERVATION_NOT_FOUND"}
            else 409 if code in {"RESERVATION_EXPIRED"}
            else 400
        )
        raise HTTPException(status_code=status, detail=r["message"])
    return {"detail": r["message"], **(r.get("data") or {})}

@router.post("/reservation/cancel")
async def http_cancel_reservation(payload: CancelIn, session: AsyncSession = Depends(get_session)):
    r = await cancel(session, barcode=payload.barcode, email=payload.email)
    if not r["ok"]:
        code = r.get("code")
        status = (
            404 if code in {"USER_NOT_FOUND", "COPY_NOT_FOUND", "ACTIVE_RESERVATION_NOT_FOUND"}
            else 400
        )
        raise HTTPException(status_code=status, detail=r["message"])
    return {"detail": r["message"], **(r.get("data") or {})}

@router.delete("/book/{book_id}")
async def http_delete_book(book_id: str, session: AsyncSession = Depends(get_session)):
    r = await delete_book(session, book_id=book_id)
    if not r["ok"]:
        code = r.get("code")
        status = 404 if code == "BOOK_NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail=r["message"])
    return {"detail": r["message"], **(r.get("data") or {})}