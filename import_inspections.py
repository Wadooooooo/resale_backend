import csv
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import models

# --- НАСТРОЙКИ ---
DATABASE_URL = "postgresql://user:password@127.0.0.1:5432/resale29051332"
CSV_FILE_PATH = "Re_Sale Проверка телефонов - Проверка Телефонов.csv"
DEFAULT_USER_ID = 1 # ID пользователя, от имени которого будут созданы проверки

# VVV НАЧАЛО ИЗМЕНЕНИЙ: Обновленная и полная карта сопоставления VVV
# Карта сопоставления колонок из CSV с названиями в справочнике checklist_items в БД
CSV_TO_DB_CHECKLIST_MAP = {
    'Корпус': 'Корпус (внешний вид)',
    'Face ID': 'Face ID',
    'TrueTon': 'True Tone',
    'Кнопки': 'Физические кнопки',
    'Дисплей': 'Дисплей (тачскрин, дефекты)',
    'Камера основная': 'Основная камера (фото/видео)',
    'Микрофон Камера основная': 'Микрофон (основная камера)',
    'Камера фронтальная': 'Фронтальная камера (фото/видео)',
    'Микрофон Камера фронтальная': 'Микрофон (фронтальная камера)',
    'Сим-карта': 'Связь (Wi-Fi, Bluetooth, SIM)',
    'Состояние Аккумулятора': 'Аккумулятор (состояние)',
    # Колонка 'Фонарик' из CSV игнорируется, так как нет аналога в новом чек-листе
}
# ^^^ КОНЕЦ ИЗМЕНЕНИЙ ^^^

def import_data():
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        print("Шаг 1: Загрузка справочников и телефонов из БД...")
        checklist_items_db = {item.name: item.id for item in session.query(models.ChecklistItems).all()}
        phones_map = {p.serial_number: p for p in session.query(models.Phones).filter(models.Phones.serial_number.isnot(None)).all()}

        print(f"Найдено {len(phones_map)} телефонов с S/N и {len(checklist_items_db)} пунктов в чек-листе.")
        print("Шаг 2: Чтение CSV и импорт проверок...")

        with open(CSV_FILE_PATH, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for index, row in enumerate(reader, start=2):
                serial_number = row.get('Serial Number', '').strip()
                date_str = row.get('Дата проверки', '').strip()

                if not serial_number or not date_str:
                    continue

                phone = phones_map.get(serial_number)
                if not phone:
                    print(f"Строка {index}: [Пропуск] Телефон с S/N '{serial_number}' не найден в базе данных.")
                    continue
                
                print(f" -- Обработка S/N: {serial_number} (ID телефона: {phone.id}) --")
                
                try:
                    inspection_date = datetime.strptime(date_str, '%d.%m.%Y')
                except ValueError:
                    print(f"    [Пропуск] Некорректная дата проверки: {date_str}")
                    continue

                new_inspection = models.DeviceInspection(
                    phone_id=phone.id,
                    inspection_date=inspection_date,
                    user_id=DEFAULT_USER_ID
                )
                session.add(new_inspection)
                session.flush()

                found_db_items = set()
                is_failed = False

                for csv_col, db_name in CSV_TO_DB_CHECKLIST_MAP.items():
                    if db_name in checklist_items_db:
                        # Значение по умолчанию '1', если ячейка пустая, но колонка есть
                        result_val = str(row.get(csv_col, '1')).strip()
                        # Считаем пройденным, если значение '1', '1.0', или 'TRUE' (без учета регистра)
                        result = result_val.upper() in ['1', '1.0', 'TRUE']
                        
                        if not result:
                            is_failed = True

                        inspection_result = models.InspectionResults(
                            device_inspection_id=new_inspection.id,
                            checklist_item_id=checklist_items_db[db_name],
                            result=result,
                            notes="Импортировано из CSV"
                        )
                        session.add(inspection_result)
                        found_db_items.add(db_name)

                missing_items = set(checklist_items_db.keys()) - found_db_items
                for item_name in missing_items:
                    inspection_result = models.InspectionResults(
                        device_inspection_id=new_inspection.id,
                        checklist_item_id=checklist_items_db[item_name],
                        result=True, # По умолчанию пройдено
                        notes="Пункт отсутствовал в старом чек-листе"
                    )
                    session.add(inspection_result)
                
                if is_failed:
                    phone.technical_status = models.TechStatus.БРАК
                else:
                    phone.technical_status = models.TechStatus.УПАКОВАН
                
                print(f"    -> Статус телефона обновлен на: {phone.technical_status.value}")

        print("Шаг 3: Сохранение всех данных в базу...")
        session.commit()
        print(f"\n✅ Импорт проверок успешно завершен!")

    except FileNotFoundError:
        print(f"Ошибка: Файл '{CSV_FILE_PATH}' не найден.")
    except Exception as e:
        print(f"Произошла критическая ошибка: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    import_data()