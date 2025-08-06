import csv
import os
from decimal import Decimal, InvalidOperation
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Импортируем твои модели
from app import models

# --- НАСТРОЙКИ ---
DATABASE_URL = "postgresql://user:password@127.0.0.1:5432/resale29051332"
CSV_FILE_PATH = "_[НФ] ДДС —  Re_Sale  - ДДС_ месяц.csv" # Убедись, что файл лежит в той же папке

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def parse_date(date_str: str) -> datetime | None:
    """Преобразует строку с датой в объект datetime."""
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        return datetime.strptime(date_str.strip(), '%d.%m.%Y')
    except ValueError:
        print(f"  [Предупреждение] Не удалось распознать дату: '{date_str}'")
        return None

def parse_amount(amount_str: str) -> Decimal | None:
    """Преобразует строку с суммой в Decimal, очищая ее."""
    if not amount_str or not isinstance(amount_str, str):
        return None
    try:
        # Убираем неразрывные пробелы, заменяем запятую на точку
        cleaned_str = amount_str.replace('\xa0', '').replace(',', '.')
        return Decimal(cleaned_str)
    except InvalidOperation:
        print(f"  [Предупреждение] Не удалось распознать сумму: '{amount_str}'")
        return None

# --- ОСНОВНАЯ ЛОГИКА ИМПОРТА ---

def import_data():
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        print("Шаг 1: Загрузка существующих справочников из базы данных...")
        
        accounts = {acc.name.lower(): acc.id for acc in session.query(models.Accounts).all()}
        categories = {cat.name.lower(): cat.id for cat in session.query(models.OperationCategories).all()}
        counterparties = {c.name.lower(): c.id for c in session.query(models.Counterparties).all()}
        
        print("Шаг 2: Чтение CSV файла и импорт данных...")
        
        with open(CSV_FILE_PATH, mode='r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for index, row in enumerate(reader, start=2):
                date = parse_date(row.get('Дата'))
                amount = parse_amount(row.get('Сумма'))
                
                if not date or amount is None:
                    print(f"Строка {index}: пропущена (нет даты или суммы).")
                    continue

                # 1. Обработка "Кошелька" (Счета)
                account_name = row.get('Кошелек', '').strip()
                
                # VVV НАЧАЛО ИЗМЕНЕНИЙ VVV
                # Добавляем правило для замены
                if account_name == "Карта Роман":
                    account_name = "Карта ВТБ Роман"
                # Примечание: сюда можно будет добавить и другие правила, если понадобится,
                # например: elif account_name == "Нал": account_name = "Наличные"
                # ^^^ КОНЕЦ ИЗМЕНЕНИЙ ^^^
                
                account_id = None
                if account_name:
                    if account_name.lower() not in accounts:
                        print(f"  -> Создание нового счета: '{account_name}'")
                        new_account = models.Accounts(name=account_name)
                        session.add(new_account)
                        session.flush()
                        accounts[account_name.lower()] = new_account.id
                    account_id = accounts[account_name.lower()]

                # 2. Обработка "Статьи" (Категории операций)
                category_name = row.get('Статья', '').strip()
                category_id = None
                if category_name:
                    if category_name.lower() not in categories:
                        print(f"  -> Создание новой категории: '{category_name}'")
                        op_type = 'income' if amount > 0 else 'expense'
                        new_category = models.OperationCategories(name=category_name, type=op_type)
                        session.add(new_category)
                        session.flush()
                        categories[category_name.lower()] = new_category.id
                    category_id = categories[category_name.lower()]
                
                # 3. Обработка "Контрагента"
                counterparty_name = row.get('Контрагент', '').strip()
                counterparty_id = None
                if counterparty_name and counterparty_name.lower() not in ['nan', '1']:
                    if counterparty_name.lower() not in counterparties:
                        print(f"  -> Создание нового контрагента: '{counterparty_name}'")
                        new_counterparty = models.Counterparties(name=counterparty_name, type="Общий")
                        session.add(new_counterparty)
                        session.flush()
                        counterparties[counterparty_name.lower()] = new_counterparty.id
                    counterparty_id = counterparties[counterparty_name.lower()]

                # Создаем запись CashFlow
                cash_flow_entry = models.CashFlow(
                    date=date,
                    amount=amount,
                    account_id=account_id,
                    operation_categories_id=category_id,
                    counterparty_id=counterparty_id,
                    description=row.get('Назначение платежа', '').strip(),
                    currency_id=1
                )
                session.add(cash_flow_entry)

                if index % 100 == 0:
                    print(f"Обработано {index} строк...")

            print("Шаг 3: Сохранение данных в базу...")
            session.commit()
            print(f"\n✅ Импорт успешно завершен! Обработано {index - 1} строк.")

    except FileNotFoundError:
        print(f"Ошибка: Файл '{CSV_FILE_PATH}' не найден. Убедись, что он лежит в той же папке, что и скрипт.")
    except Exception as e:
        print(f"Произошла критическая ошибка: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    import_data()