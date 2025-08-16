# app/database.py

import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@127.0.0.1:5432/resale_v051")

# Асинхронный движок
engine = create_async_engine(SQLALCHEMY_DATABASE_URL)

# Асинхронный генератор сессий
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Новая асинхронная функция для получения сессии
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session