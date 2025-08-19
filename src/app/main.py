import asyncio
from fastapi import FastAPI
from app.config import settings
from app.db import init_db
from app.api.router import router

app = FastAPI(title=settings.APP_NAME)
app.include_router(router)

@app.on_event("startup")
async def on_startup():
    await init_db()
