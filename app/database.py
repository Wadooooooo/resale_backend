import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

load_dotenv() # Загружает переменные из файла .env

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(SQLALCHEMY_DATABASE_URL)

# Асинхронный генератор сессий
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Новая асинхронная функция для получения сессии
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session