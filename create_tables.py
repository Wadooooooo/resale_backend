# create_tables.py
import asyncio
from app.database import engine  # Импортируем наш движок
from app.models import Base     # Импортируем Base из файла с моделями

async def create_db_and_tables():
    print("Начинаем создание таблиц...")
    async with engine.begin() as conn:
        # Эта команда удаляет все существующие таблицы (если нужно начать с чистого листа)
        # await conn.run_sync(Base.metadata.drop_all)

        # Эта команда создает все таблицы по описанию из models.py
        await conn.run_sync(Base.metadata.create_all)
    print("Таблицы успешно созданы.")

if __name__ == "__main__":
    asyncio.run(create_db_and_tables())