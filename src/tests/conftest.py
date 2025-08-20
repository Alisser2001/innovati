import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.db import Base
from app import models  

@pytest_asyncio.fixture(scope="session")
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()

@pytest_asyncio.fixture
async def session(async_engine):
    SessionLocal = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    async with SessionLocal() as s:
        try:
            yield s
        finally:
            await s.rollback()
