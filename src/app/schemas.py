from pydantic import BaseModel, constr
from datetime import datetime

class BookIn(BaseModel):
    title: str
    author: str | None = None

class BookOut(BaseModel):
    id: str
    title: str
    author: str | None

class BookListItem(BaseModel):
    id: str
    title: str
    author: str | None
    copies_available: int
    copies_total: int

class CopyIn(BaseModel):
    barcode: constr(pattern=r'^\d{10}$')
    location: str

class CopyOut(BaseModel):
    id: str
    book_id: str
    barcode: str
    status: str
    location: str

class ReservationIn(BaseModel):
    book_id: str
    name: str 
    email: str

class ReservationOut(BaseModel):
    id: str
    book_id: str
    copy_id: str
    user_email: str
    status: str
    due_date: datetime

class RenewalIn(BaseModel):
    barcode: constr(pattern=r'^\d{10}$')
    email: str
    name: str 

class ReservationOut(BaseModel):
    id: str
    book_id: str
    copy_id: str
    user_email: str
    status: str
    due_date: datetime

class CancelIn(BaseModel):
    barcode: constr(pattern=r'^\d{10}$')
    email: str