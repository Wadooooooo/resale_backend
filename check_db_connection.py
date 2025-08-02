# check_db_connection.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine

# --- ВАЖНО: Вставьте сюда ваши данные ---
# Если база данных на компьютере друга, замените 127.0.0.1 на его IP-адрес.
# Также замените user и password на настоящие.
DATABASE_URL = "postgresql+asyncpg://user:password@127.0.0.1:5432/resale29051332"

async def check_connection():
    """
    Пытается установить соединение с базой данных и сообщает о результате.
    """
    print(f"Попытка подключения к базе данных по адресу: {DATABASE_URL.split('@')[-1]}")
    try:
        # Создаем асинхронный движок
        engine = create_async_engine(DATABASE_URL)

        # Пытаемся установить соединение
        async with engine.connect() as connection:
            # Если эта строка выполнилась, соединение успешно
            print("✅ Соединение с базой данных успешно установлено!")

    except Exception as e:
        print("❌ Ошибка подключения к базе данных:")
        print(f"   Детали ошибки: {e}")

if __name__ == "__main__":
    asyncio.run(check_connection())