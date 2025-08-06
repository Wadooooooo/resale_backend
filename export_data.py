import json
import os
from decimal import Decimal
from datetime import datetime, date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

# Импортируем все твои модели из файла models.py
from app import models

# --- НАСТРОЙКИ ---
DATABASE_URL = "postgresql://user:password@127.0.0.1:5432/resale29051332"
OUTPUT_DIR = "spravochniki_export"

# Список моделей-справочников, которые нужно выгрузить
REFERENCE_MODELS = [
    models.Accounts,
    models.CategoryAccessories,
    models.ChecklistItems,
    models.Colors,
    models.Counterparties,
    models.Currency,
    models.ModelName,
    # VVV НАЧАЛО ИЗМЕНЕНИЙ VVV
    models.Models,  # <-- ДОБАВЛЕНА ТАБЛИЦА models В ОСНОВНОЙ СПИСОК
    # ^^^ КОНЕЦ ИЗМЕНЕНИЙ ^^^
    models.OperationCategories,
    models.Permissions,
    models.ProductType,
    models.Roles,
    models.Shops,
    models.Storage,
    models.TrafficSource,
]

# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ---
def alchemy_encoder(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

# --- ОСНОВНАЯ ЛОГИКА СКРИПТА ---
def export_references():
    print("Начинаем экспорт справочников...")

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"Создана директория: ./{OUTPUT_DIR}/")

    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        for model in REFERENCE_MODELS:
            table_name = model.__tablename__
            print(f"  Выгрузка таблицы '{table_name}'...", end="")
            
            query = select(model)
            results = session.execute(query).scalars().all()
            
            data_to_export = []
            for item in results:
                item_dict = {c.name: getattr(item, c.name) for c in item.__table__.columns}
                data_to_export.append(item_dict)

            file_path = os.path.join(OUTPUT_DIR, f"{table_name}.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_export, f, ensure_ascii=False, indent=4, default=alchemy_encoder)
            
            print(f" Успешно! ({len(data_to_export)} записей)")
        
        print(f"\n✅ Экспорт завершен. Все файлы сохранены в папке '{OUTPUT_DIR}'.")

    finally:
        session.close()

if __name__ == "__main__":
    export_references()