import csv
from decimal import Decimal, InvalidOperation
from datetime import datetime, date # <--- VVV Добавлен импорт date
from collections import defaultdict
import re

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models

# --- НАСТРОЙКИ ---
DATABASE_URL = "postgresql://user:password@127.0.0.1:5432/resale29051332"
CSV_FILE_PATH = "Re_Sale Заказы - Заказы.csv"
DEFAULT_SUPPLIER_NAME = "Старый поставщик (из импорта)" # Для заказов в промежутке дат

# --- ОСНОВНАЯ ЛОГИКА ---
def import_data():
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        print("Шаг 1: Загрузка справочников из БД...")
        suppliers = {s.name.lower(): s.id for s in session.query(models.Supplier).all()}
        model_names = {mn.name.lower(): mn.id for mn in session.query(models.ModelName).all()}
        storages = {s.storage: s.id for s in session.query(models.Storage).all()}
        colors = {c.color_name.lower(): c.id for c in session.query(models.Colors).all()}
        existing_models = {
            (m.model_name_id, m.storage_id, m.color_id): m.id
            for m in session.query(models.Models).all()
        }

        # VVV НАЧАЛО ИЗМЕНЕНИЙ: Проверка наличия ключевых поставщиков VVV
        existing_supplier_ids = {s.id for s in session.query(models.Supplier).all()}
        if 1 not in existing_supplier_ids or 3 not in existing_supplier_ids:
            print("\n[КРИТИЧЕСКАЯ ОШИБКА] В базе данных нет поставщиков с ID 1 и 3. Пожалуйста, создайте их перед импортом.")
            return
        # ^^^ КОНЕЦ ИЗМЕНЕНИЙ ^^^

        print("Шаг 2: Чтение и группировка заказов из CSV...")
        orders_by_date = defaultdict(list)
        
        with open(CSV_FILE_PATH, mode='r', encoding='cp1251') as csvfile:
            header_line = next(csvfile)
            headers = [h.strip() for h in header_line.split(',')]
            reader = csv.DictReader(csvfile, fieldnames=headers)
            for row in reader:
                order_date_str = row.get('Дата')
                if order_date_str:
                    try:
                        order_date = datetime.strptime(order_date_str.strip(), '%d.%m.%Y').date()
                        orders_by_date[order_date].append(row)
                    except (ValueError, TypeError):
                        continue

        print(f"Найдено {len(orders_by_date)} уникальных заказов (по датам).")
        print("Шаг 3: Импорт данных в базу...")

        # VVV НАЧАЛО ИЗМЕНЕНИЙ: Логика выбора поставщика по дате VVV
        cutoff_date_supplier_3 = date(2024, 12, 2)
        cutoff_date_supplier_1 = date(2024, 12, 10)
        default_supplier_id = None
        # ^^^ КОНЕЦ ИЗМЕНЕНИЙ ^^^
        
        for order_date, items in orders_by_date.items():
            print(f"  -- Импорт заказа от {order_date.strftime('%Y-%m-%d')} --")

            # VVV НАЧАЛО ИЗМЕНЕНИЙ: Определяем ID поставщика для этого заказа VVV
            supplier_id = None
            if order_date <= cutoff_date_supplier_3:
                supplier_id = 3
            elif order_date >= cutoff_date_supplier_1:
                supplier_id = 1
            else:
                # Для заказов в промежутке используем поставщика по умолчанию
                if not default_supplier_id: # Создаем его только при необходимости
                    if DEFAULT_SUPPLIER_NAME.lower() not in suppliers:
                        print(f" -> Создание поставщика по умолчанию: '{DEFAULT_SUPPLIER_NAME}'")
                        new_supplier = models.Supplier(name=DEFAULT_SUPPLIER_NAME, contact_info="Импортировано из CSV")
                        session.add(new_supplier)
                        session.flush()
                        default_supplier_id = new_supplier.id
                        suppliers[DEFAULT_SUPPLIER_NAME.lower()] = default_supplier_id
                    else:
                        default_supplier_id = suppliers[DEFAULT_SUPPLIER_NAME.lower()]
                supplier_id = default_supplier_id
            # ^^^ КОНЕЦ ИЗМЕНЕНИЙ ^^^

            new_order = models.SupplierOrders(
                supplier_id=supplier_id,
                order_date=order_date,
                status=models.StatusDelivery.ПОЛУЧЕН,
                payment_status=models.OrderPaymentStatus.ОПЛАЧЕН
            )
            session.add(new_order)
            session.flush()

            for item in items:
                model_name_str = item.get('Модель', '').strip()

                # VVV НАЧАЛО ИЗМЕНЕНИЙ: Пропускаем строки с "грязными" данными VVV
                if len(model_name_str.split()) > 5:
                    print(f"    [Пропуск] Строка похожа на старый формат с S/N: '{model_name_str}'")
                    continue
                # ^^^ КОНЕЦ ИЗМЕНЕНИЙ ^^^

                storage_str = item.get('Память', '').strip()
                color_str = item.get('Цвет', '').strip()
                
                if not all([model_name_str, storage_str, color_str]):
                    print(f"    [Пропуск] Неполные данные для позиции: {item}")
                    continue

                if model_name_str.lower() not in model_names:
                    new_mn = models.ModelName(name=model_name_str)
                    session.add(new_mn); session.flush()
                    model_names[model_name_str.lower()] = new_mn.id
                model_name_id = model_names[model_name_str.lower()]

                storage_val = int(re.sub(r'\D', '', storage_str))
                if storage_val not in storages:
                    new_storage = models.Storage(storage=storage_val)
                    session.add(new_storage); session.flush()
                    storages[storage_val] = new_storage.id
                storage_id = storages[storage_val]

                if color_str.lower() not in colors:
                    new_color = models.Colors(color_name=color_str)
                    session.add(new_color); session.flush()
                    colors[color_str.lower()] = new_color.id
                color_id = colors[color_str.lower()]

                model_key = (model_name_id, storage_id, color_id)
                if model_key not in existing_models:
                    new_model = models.Models(model_name_id=model_name_id, storage_id=storage_id, color_id=color_id)
                    session.add(new_model); session.flush()
                    existing_models[model_key] = new_model.id
                final_model_id = existing_models[model_key]

                try:
                    price = Decimal(item.get('Цена', '0'))
                    quantity = int(float(item.get('Количество', '0')))
                    if quantity > 0:
                        order_detail = models.SupplierOrderDetails(
                            supplier_order_id=new_order.id, model_id=final_model_id,
                            quantity=quantity, price=price
                        )
                        session.add(order_detail)
                except (InvalidOperation, ValueError):
                    print(f"    [Пропуск] Некорректная цена или количество для: {item}")
                    continue
        
        print("Шаг 4: Сохранение всех данных в базу...")
        session.commit()
        print(f"\n✅ Импорт успешно завершен!")

    except FileNotFoundError:
        print(f"Ошибка: Файл '{CSV_FILE_PATH}' не найден.")
    except Exception as e:
        print(f"Произошла критическая ошибка: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    import_data()