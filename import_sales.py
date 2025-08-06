import csv
from decimal import Decimal, InvalidOperation
from datetime import datetime
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, joinedload
from app import models

# --- НАСТРОЙКИ ---
DATABASE_URL = "postgresql://user:password@127.0.0.1:5432/resale29051332"
CSV_FILE_PATH = "Re_Sale Продажи_Склад - Продажи.csv"

# Сопоставление имен менеджеров из CSV с ID пользователей в БД
USER_MAP = {
    'влад': 1,
    'роман': 2,
}

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (как в прошлых скриптах) ---
def parse_date(date_str: str) -> datetime | None:
    if not date_str or not isinstance(date_str, str): return None
    try:
        return datetime.strptime(date_str.strip(), '%d.%m.%Y')
    except ValueError:
        return None

def parse_price(price_str: str) -> Decimal | None:
    if not price_str or not isinstance(price_str, str): return None
    try:
        cleaned_str = price_str.replace('\xa0', '').replace(',', '.').strip()
        return Decimal(cleaned_str)
    except InvalidOperation:
        return None

# --- ОСНОВНАЯ ЛОГИКА ИМПОРТА ---
def import_data():
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        print("Шаг 1: Загрузка данных из БД для сопоставления...")
        phones_map = {p.serial_number: p for p in session.query(models.Phones).filter(models.Phones.serial_number.isnot(None)).all()}
        accessories_map = {a.name.lower(): a for a in session.query(models.Accessories).all()}
        customers_map = {c.name.lower(): c for c in session.query(models.Customers).all()}
        accounts_map = {a.name.lower(): a.id for a in session.query(models.Accounts).all()}
        
        # Загружаем складские записи в удобную структуру
        warehouse_items = session.query(models.Warehouse).options(joinedload(models.Warehouse.product_type)).all()
        warehouse_map = {(w.product_type_id, w.product_id): w for w in warehouse_items}

        print("Шаг 2: Чтение CSV файла и импорт продаж...")
        with open(CSV_FILE_PATH, mode='r', encoding='utf-8-sig') as csvfile:
            # Первая колонка без имени, даем ей имя 'Дата'
            reader = csv.reader(csvfile)
            header = next(reader)
            header[0] = 'Дата' 
            dict_reader = csv.DictReader(iter([header] + list(reader)))
            
            for index, row in enumerate(dict_reader, start=2):
                sale_date = parse_date(row.get('Дата'))
                if not sale_date:
                    print(f"Строка {index}: [Пропуск] Некорректная дата.")
                    continue

                print(f" -- Обработка строки {index} (Дата: {sale_date.strftime('%Y-%m-%d')}) --")

                # 1. Находим/создаем клиента
                customer_id = None
                customer_name = row.get('ФИО клиента', '').strip()
                if customer_name and customer_name.lower() != 'nan':
                    if customer_name.lower() not in customers_map:
                        print(f"    -> Создание клиента: '{customer_name}'")
                        new_customer = models.Customers(name=customer_name, number=row.get('Номер телефона клиента'))
                        session.add(new_customer)
                        session.flush()
                        customers_map[customer_name.lower()] = new_customer
                    customer_id = customers_map[customer_name.lower()].id

                # 2. Идентифицируем товар (телефон или аксессуар)
                serial_number = row.get('Cерийный номер', '').strip()
                product_name = row.get('Товар', '').strip()
                product_id, product_type_id = None, None
                
                if serial_number and serial_number.lower() != 'nan':
                    # Это телефон
                    phone = phones_map.get(serial_number)
                    if phone:
                        product_id, product_type_id = phone.id, 1
                    else:
                        print(f"    [ОШИБКА] Телефон с S/N '{serial_number}' не найден в БД. Пропуск.")
                        continue
                else:
                    # Это аксессуар
                    accessory = accessories_map.get(product_name.lower())
                    if accessory:
                        product_id, product_type_id = accessory.id, 2
                    else:
                        print(f"    [ОШИБКА] Аксессуар '{product_name}' не найден в БД. Пропуск.")
                        continue
                
                # 3. Находим запись на складе
                warehouse_entry = warehouse_map.get((product_type_id, product_id))
                if not warehouse_entry:
                    print(f"    [ОШИБКА] Товар '{product_name}' (ID: {product_id}) не найден на складе. Пропуск.")
                    continue
                if warehouse_entry.quantity <= 0:
                    print(f"    [ПРЕДУПРЕЖДЕНИЕ] Товар '{product_name}' (ID: {product_id}) уже закончился на складе. Продажа будет создана, но остаток станет отрицательным.")

                # 4. Создаем запись о продаже (Sales)
                price = parse_price(row.get('Цена'))
                manager_name = row.get('Менеджер', '').strip().lower()
                user_id = USER_MAP.get(manager_name)

                payment_method_str = row.get('Способ оплаты', '').strip().lower()
                payment_method_enum = models.EnumPayment.НАЛИЧНЫЕ # по умолчанию
                if 'перевод' in payment_method_str: payment_method_enum = models.EnumPayment.ПЕРЕВОД
                elif 'карт' in payment_method_str: payment_method_enum = models.EnumPayment.КАРТА
                elif 'кредит' in payment_method_str: payment_method_enum = models.EnumPayment.КРЕДИТ_РАССРОЧКА
                
                # Простое определение счета по умолчанию
                account_id = None
                if payment_method_enum == models.EnumPayment.НАЛИЧНЫЕ:
                    account_id = accounts_map.get('наличные')
                else:
                    account_id = accounts_map.get('расчетный счет')


                new_sale = models.Sales(
                    sale_date=sale_date,
                    customer_id=customer_id,
                    payment_method=payment_method_enum,
                    account_id=account_id,
                    payment_status=models.StatusPay.ОПЛАЧЕН,
                    total_amount=price,
                    user_id=user_id,
                )
                session.add(new_sale)
                session.flush()

                # 5. Создаем деталь продажи (SaleDetails)
                new_sale_detail = models.SaleDetails(
                    sale_id=new_sale.id,
                    warehouse_id=warehouse_entry.id,
                    quantity=1,
                    unit_price=price
                )
                session.add(new_sale_detail)

                # 6. Обновляем склад и статус телефона
                warehouse_entry.quantity -= 1
                if product_type_id == 1:
                    phone_to_update = session.get(models.Phones, product_id)
                    phone_to_update.commercial_status = models.CommerceStatus.ПРОДАН
                
                print(f"    -> Продажа №{new_sale.id} для товара '{product_name}' успешно создана.")

        print("Шаг 3: Сохранение всех данных в базу...")
        session.commit()
        print(f"\n✅ Импорт продаж успешно завершен!")

    except FileNotFoundError:
        print(f"Ошибка: Файл '{CSV_FILE_PATH}' не найден.")
    except Exception as e:
        print(f"Произошла критическая ошибка: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    import_data()