import pytest
from sqlalchemy import select
from app import models
from app.actions import (
    list_books,
    register_book,
    register_copy,
    reserve,
    renew,
    cancel,
    DEFAULT_LOAN_DAYS,
    delete_book
)

pytestmark = pytest.mark.asyncio

async def _mk_book_with_copy(session, *, title="Clean Code", author="Robert C. Martin",
                             barcode="1234567890", location="A1"):
    r = await register_book(session, title=title, author=author)
    assert r["ok"] is True
    book_id = r["data"]["book_id"]
    r2 = await register_copy(session, book_id=book_id, barcode=barcode, location=location)
    assert r2["ok"] is True
    copy_id = r2["data"]["copy_id"]
    return book_id, copy_id, barcode

async def _get_copy(session, copy_id):
    r = await session.execute(select(models.BookCopy).where(models.BookCopy.id == copy_id))
    return r.scalar_one()

async def _get_reservation(session, reservation_id):
    r = await session.execute(select(models.Reservation).where(models.Reservation.id == reservation_id))
    return r.scalar_one()

async def test_register_and_list_books(session):
    r0 = await list_books(session)
    assert r0["ok"] is True
    assert r0["data"]["items"] == []
    r_book = await register_book(session, title="Design Patterns", author="GoF")
    assert r_book["ok"] is True
    book_id = r_book["data"]["book_id"]
    r_copy = await register_copy(session, book_id=book_id, barcode="0000000001", location="SHELF-01")
    assert r_copy["ok"] is True
    r1 = await list_books(session)
    assert r1["ok"] is True
    items = r1["data"]["items"]
    assert len(items) == 1
    it = items[0]
    assert it["book_id"] == book_id
    assert it["copies_total"] == 1
    assert it["copies_available"] == 1

async def test_reserve_success_and_unavailable(session):
    book_id, copy_id, barcode = await _mk_book_with_copy(session, barcode="1111111111")
    r = await reserve(session, book_id=book_id, book_title=None, name="Alice", email="alice@example.com")
    assert r["ok"] is True
    reservation_id = r["data"]["reservation_id"]
    copy = await _get_copy(session, copy_id)
    assert copy.status == models.CopyStatus.RESERVED
    r2 = await reserve(session, book_id=book_id, book_title=None, name="Bob", email="bob@example.com")
    assert r2["ok"] is False
    assert r2["code"] == "NO_AVAILABLE_COPIES"

async def test_renew_success(session):
    book_id, copy_id, barcode = await _mk_book_with_copy(session, barcode="2222222222")
    r = await reserve(session, book_id=book_id, book_title=None, name="Alice", email="alice@example.com")
    assert r["ok"] is True
    reservation_id = r["data"]["reservation_id"]
    res_before = await _get_reservation(session, reservation_id)
    due_before = res_before.due_date
    r2 = await renew(session, barcode=barcode, email="alice@example.com")
    assert r2["ok"] is True
    res_after = await _get_reservation(session, reservation_id)
    delta_days = (res_after.due_date - due_before).days
    assert delta_days >= DEFAULT_LOAN_DAYS 
    assert res_after.renewed_cnt == 1

async def test_cancel_makes_copy_available_again(session):
    book_id, copy_id, barcode = await _mk_book_with_copy(session, barcode="3333333333")
    r = await reserve(session, book_id=book_id, book_title=None, name="Carol", email="carol@example.com")
    assert r["ok"] is True
    reservation_id = r["data"]["reservation_id"]
    r2 = await cancel(session, barcode=barcode, email="carol@example.com")
    assert r2["ok"] is True
    res = await _get_reservation(session, reservation_id)
    assert res.status == models.ReservationStatus.CANCELED
    copy = await _get_copy(session, copy_id)
    assert copy.status == models.CopyStatus.AVAILABLE

async def test_delete_book_removes_copies_and_reservations(session):
    r_book = await register_book(session, title="The Pragmatic Programmer", author="Hunt & Thomas")
    book_id = r_book["data"]["book_id"]
    r_copy = await register_copy(session, book_id=book_id, barcode="4444444444", location="SHELF-44")
    copy_id = r_copy["data"]["copy_id"]
    r_res = await reserve(session, book_id=book_id, book_title=None, name="Alice", email="alice@example.com")
    assert r_res["ok"]
    r_del = await delete_book(session, book_id=book_id)
    assert r_del["ok"] is True
    assert r_del["data"]["removed_copies"] == 1
    assert r_del["data"]["removed_reservations"] == 1
    r = await session.execute(select(models.Book).where(models.Book.id == book_id))
    assert r.scalar_one_or_none() is None
    r = await session.execute(select(models.BookCopy).where(models.BookCopy.id == copy_id))
    assert r.scalar_one_or_none() is None
    r = await session.execute(select(models.Reservation).where(models.Reservation.book_id == book_id))
    assert r.scalar_one_or_none() is None

async def test_delete_book_not_found(session):
    r = await delete_book(session, book_id="00000000-0000-0000-0000-000000000000")
    assert r["ok"] is False
    assert r["code"] == "BOOK_NOT_FOUND"
