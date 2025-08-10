# app/crud.py

from sqlalchemy.orm import Session
from sqlalchemy.future import select
from . import models
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload, aliased
from sqlalchemy import func, select, case, or_
from . import models, schemas
from datetime import date
from fastapi import HTTPException
from decimal import Decimal, InvalidOperation
from sqlalchemy import select, or_
from datetime import date, timedelta, datetime, time
from sqlalchemy import func
from typing import List, Optional
from sqlalchemy import update
from . import security
from sqlalchemy import extract


BATTERY_THRESHOLDS = {
    # Вы можете добавлять сюда любые модели по аналогии
    "iPhone 12": 12.0,
    "iPhone 13": 12.0,
    "iPhone 14": 11.5,
    "iPhone 14 Pro": 9.0,
    "iPhone 15": 8.5,
}
# Пороговое значение по умолчанию для моделей, которых нет в списке
DEFAULT_BATTERY_THRESHOLD = 12.0

def _extract_specific_defect_reason(details: str) -> str:
    """Извлекает из полного лога только строки с конкретной причиной брака."""
    if not details:
        return "Причина не указана."

    # Если в логе есть результаты проверки из чек-листа
    if "--- Результаты проверки ---" in details:
        try:
            # Отделяем часть с чек-листом
            checklist_str = details.split("--- Результаты проверки ---")[1]
            
            # Находим все строки, в которых есть слово "БРАК"
            failed_items = [
                # Убираем лишние символы и само слово "БРАК"
                line.strip().replace(": БРАК", "").split('(')[0].strip()
                for line in checklist_str.strip().split('\n')
                if "БРАК" in line
            ]
            
            if failed_items:
                # Если найдены, возвращаем их списком
                return "Брак: " + ", ".join(failed_items)
            else:
                # Если слово "БРАК" не найдено (маловероятно), возвращаем общий статус
                return "Брак по результатам инспекции"
        except Exception:
             # В случае любой ошибки при обработке строки, возвращаем исходный текст
            return details
    else:
        # Для других типов логов (возврат, обмен, тест АКБ) возвращаем как есть
        return details
    
async def get_unique_model_color_combos(db: AsyncSession):
    """Получает уникальные комбинации 'модель + цвет' с их текущим URL изображения."""
    query = (
        select(
            models.ModelName.id.label("model_name_id"),
            models.ModelName.name.label("model_name"),
            models.Colors.id.label("color_id"),
            models.Colors.color_name.label("color_name"),
            models.Models.image_url
        )
        .join(models.Models, models.ModelName.id == models.Models.model_name_id)
        .join(models.Colors, models.Models.color_id == models.Colors.id)
        .group_by(
            models.ModelName.id,
            models.ModelName.name,
            models.Colors.id,
            models.Colors.color_name,
            models.Models.image_url
        )
        .distinct()
    )
    result = await db.execute(query)
    return result.mappings().all()

async def update_image_for_model_color_combo(db: AsyncSession, data: schemas.ModelImageUpdate):
    """Находит все модели с указанным именем и цветом и обновляет их image_url."""
    stmt = (
        update(models.Models)
        .where(
            models.Models.model_name_id == data.model_name_id,
            models.Models.color_id == data.color_id
        )
        .values(image_url=data.image_url)
    )
    await db.execute(stmt)
    await db.commit()
    return {"message": "Update successful"}

# --- Функции для Инспекции ---

async def get_phones_for_inspection(db: AsyncSession):
    """Получает все телефоны со статусом 'ОЖИДАЕТ_ПРОВЕРКУ'."""
    query = (
        select(models.Phones)
        .options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color),
            selectinload(models.Phones.model_number),
            selectinload(models.Phones.supplier_order)
        )
        .filter(models.Phones.technical_status == models.TechStatus.ОЖИДАЕТ_ПРОВЕРКУ)
    )
    result = await db.execute(query)
    return result.scalars().all()

async def get_checklist_items(db: AsyncSession):
    """Получает все пункты из чек-листа."""
    result = await db.execute(select(models.ChecklistItems))
    return result.scalars().all()


async def create_initial_inspection(db: AsyncSession, phone_id: int, inspection_data: schemas.InspectionSubmission, user_id: int):
    
    if inspection_data.serial_number:
        existing_phone_result = await db.execute(
            select(models.Phones).filter(
                models.Phones.serial_number == inspection_data.serial_number,
                models.Phones.id != phone_id
            )
        )
        existing_phone = existing_phone_result.scalars().first()
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Серийный номер '{inspection_data.serial_number}' уже присвоен другому устройству (ID: {existing_phone.id})."
            )

    # Загружаем телефон со связанной моделью, чтобы получить его название
    phone_result = await db.execute(
        select(models.Phones)
        .options(selectinload(models.Phones.model).selectinload(models.Models.model_name))
        .filter(models.Phones.id == phone_id)
    )
    phone = phone_result.scalars().one_or_none()
    if not phone:
        raise HTTPException(status_code=404, detail="Телефон не найден")

    phone.serial_number = inspection_data.serial_number

    if inspection_data.model_number:
        # ... (код для model_number остается без изменений)
        result = await db.execute(select(models.ModelNumber).filter(models.ModelNumber.name == inspection_data.model_number))
        model_number_obj = result.scalars().first()
        if not model_number_obj:
            model_number_obj = models.ModelNumber(name=inspection_data.model_number)
            db.add(model_number_obj)
            await db.flush()
        phone.model_number_id = model_number_obj.id

    new_inspection = models.DeviceInspection(
        phone_id=phone_id,
        inspection_date=datetime.now(),
        user_id=user_id
    )
    db.add(new_inspection)
    await db.flush()

    # ... (код для сбора checklist_summary_str остается без изменений)
    checklist_item_ids = [res.checklist_item_id for res in inspection_data.results]
    checklist_items_result = await db.execute(
        select(models.ChecklistItems).filter(models.ChecklistItems.id.in_(checklist_item_ids))
    )
    checklist_items_map = {item.id: item.name for item in checklist_items_result.scalars().all()}
    checklist_summary_lines = []
    for res in inspection_data.results:
        item_name = checklist_items_map.get(res.checklist_item_id, "Неизвестный пункт")
        status = "Пройдено" if res.result else "БРАК"
        notes = f" ({res.notes})" if res.notes else ""
        checklist_summary_lines.append(f"{item_name}: {status}{notes}")
    checklist_summary_str = "\n".join(checklist_summary_lines)
    
    has_failed_checks = any(not item.result for item in inspection_data.results)
    
    if has_failed_checks:
        phone.technical_status = models.TechStatus.БРАК
        log_event = models.PhoneEventType.ОБНАРУЖЕН_БРАК
        log_details = (
            f"Обнаружен брак при первичной инспекции. S/N: {inspection_data.serial_number}.\n"
            f"--- Результаты проверки ---\n{checklist_summary_str}"
        )
    else:
        # VVV НАЧАЛО НОВОЙ ЛОГИКИ VVV
        
        # Список моделей, которые пропускают тест АКБ
        SKIP_BATTERY_TEST_MODELS = {"iPhone 15", "iPhone 16"}
        
        phone_model_name = ""
        if phone.model and phone.model.model_name:
            phone_model_name = phone.model.model_name.name

        # Проверяем, содержит ли название модели что-то из нашего списка
        if any(skip_model in phone_model_name for skip_model in SKIP_BATTERY_TEST_MODELS):
            phone.technical_status = models.TechStatus.НА_УПАКОВКЕ
            log_details = (
                f"Первичная инспекция пройдена. Тест АКБ пропущен для данной модели. S/N присвоен: {inspection_data.serial_number}.\n"
                f"--- Результаты проверки ---\n{checklist_summary_str}"
            )
        else:
            # Если нет - отправляем на тест, как и раньше
            phone.technical_status = models.TechStatus.НА_ТЕСТЕ_АККУМУЛЯТОРА
            log_details = (
                f"Первичная инспекция пройдена. S/N присвоен: {inspection_data.serial_number}.\n"
                f"--- Результаты проверки ---\n{checklist_summary_str}"
            )
            
        log_event = models.PhoneEventType.ИНСПЕКЦИЯ_ПРОЙДЕНА
        # VVV КОНЕЦ НОВОЙ ЛОГИКИ VVV
        
    log_entry = models.PhoneMovementLog(
        phone_id=phone.id,
        user_id=user_id,
        event_type=log_event,
        details=log_details
    )
    db.add(log_entry)

    results_to_add = [
        models.InspectionResults(
            device_inspection_id=new_inspection.id,
            checklist_item_id=item.checklist_item_id,
            result=item.result,
            notes=item.notes
        ) for item in inspection_data.results
    ]
    db.add_all(results_to_add)
    await db.commit()

    final_phone_result = await db.execute(
        select(models.Phones).options(
            selectinload(models.Phones.model).options(
                selectinload(models.Models.model_name),
                selectinload(models.Models.storage),
                selectinload(models.Models.color)
            ),
            # VVV ADD THIS LINE VVV
            selectinload(models.Phones.model_number),
            selectinload(models.Phones.supplier_order)
        ).filter(models.Phones.id == phone_id)
    )
    return final_phone_result.scalars().one()


async def add_battery_test_results(db: AsyncSession, inspection_id: int, battery_data: schemas.BatteryTestCreate, user_id: int):
    """Добавляет результаты теста аккумулятора и принимает решение о браке."""
    inspection_result = await db.execute(
        select(models.DeviceInspection)
        # VVV ДОБАВЛЕНА ЗАГРУЗКА ДАННЫХ О МОДЕЛИ VVV
        .options(
            selectinload(models.DeviceInspection.phone)
            .selectinload(models.Phones.model)
            .selectinload(models.Models.model_name)
        )
        .filter(models.DeviceInspection.id == inspection_id)
    )
    inspection = inspection_result.scalars().one_or_none()

    if not inspection or not inspection.phone:
        raise HTTPException(status_code=404, detail="Инспекция или связанный телефон не найдены")

    phone_id_to_return = inspection.phone.id

    duration = None
    drain_rate = None
    if battery_data.start_time and battery_data.end_time and battery_data.start_battery_level is not None and battery_data.end_battery_level is not None:
        if battery_data.end_time > battery_data.start_time:
            duration = battery_data.end_time - battery_data.start_time
            try:
                battery_dropped = Decimal(battery_data.start_battery_level) - Decimal(battery_data.end_battery_level)
                duration_hours = Decimal(duration.total_seconds()) / Decimal(3600)
                if duration_hours > 0 and battery_dropped >= 0:
                    drain_rate = battery_dropped / duration_hours
            except (InvalidOperation, TypeError):
                drain_rate = None

    new_battery_test = models.BatteryTest(
        device_inspection_id=inspection_id,
        start_time=battery_data.start_time,
        start_battery_level=battery_data.start_battery_level,
        end_time=battery_data.end_time,
        end_battery_level=battery_data.end_battery_level,
        test_duration=duration,
        battery_drain=drain_rate
    )
    db.add(new_battery_test)

    # VVV НАЧАЛО НОВОЙ ЛОГИКИ ПРОВЕРКИ VVV
    phone = inspection.phone
    model_name = ""
    if phone.model and phone.model.model_name:
        # Ищем модель в словаре по частичному совпадению (например, "iPhone 14 Pro" сработает для "iPhone 14")
        for key in BATTERY_THRESHOLDS:
            if key in phone.model.model_name.name:
                model_name = key
                break

    threshold = BATTERY_THRESHOLDS.get(model_name, DEFAULT_BATTERY_THRESHOLD)

    log_event = models.PhoneEventType.ИНСПЕКЦИЯ_ПРОЙДЕНА # По умолчанию
    log_details = ""

    if drain_rate is not None and drain_rate > Decimal(threshold):
        # Тест НЕ пройден
        phone.technical_status = models.TechStatus.БРАК
        log_event = models.PhoneEventType.ОБНАРУЖЕН_БРАК
        log_details = f"Тест АКБ не пройден. Расход: {drain_rate:.2f}%/час (Порог: {threshold}%/час). Отправлен в брак."
    else:
        # Тест пройден
        phone.technical_status = models.TechStatus.НА_УПАКОВКЕ
        log_details = f"Тест АКБ пройден. Расход: {f'{drain_rate:.2f}' if drain_rate else 'N/A'} %/час (Порог: {threshold}%/час). Статус изменен на 'На упаковке'."

    log_entry = models.PhoneMovementLog(
        phone_id=phone.id, user_id=user_id,
        event_type=log_event, details=log_details
    )
    db.add(log_entry)
    # ^^^ КОНЕЦ НОВОЙ ЛОГИКИ ПРОВЕРКИ ^^^

    await db.commit()

    # Запрос на возврат данных остается прежним
    final_phone_result = await db.execute(
        select(models.Phones).options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color),
            selectinload(models.Phones.model_number),
            selectinload(models.Phones.supplier_order)
        ).filter(models.Phones.id == phone_id_to_return)
    )
    return final_phone_result.scalars().one()

async def get_phones_for_battery_test(db: AsyncSession):
    """ Ищет ПОСЛЕДНИЕ инспекции для каждого телефона, который находится на тесте аккумулятора. """
    query = (
        select(models.DeviceInspection)
        .join(models.DeviceInspection.phone)
        .options(
            selectinload(models.DeviceInspection.phone).selectinload(models.Phones.model).options(
                selectinload(models.Models.model_name),
                selectinload(models.Models.storage),
                selectinload(models.Models.color)
            ),
            selectinload(models.DeviceInspection.phone).selectinload(models.Phones.model_number),
            selectinload(models.DeviceInspection.phone).selectinload(models.Phones.supplier_order)
        )
        .filter(models.Phones.technical_status == models.TechStatus.НА_ТЕСТЕ_АККУМУЛЯТОРА)
        .order_by(models.DeviceInspection.phone_id, models.DeviceInspection.inspection_date.desc())
    )
    result = await db.execute(query)
    all_inspections = result.unique().scalars().all()

    # Отбираем только самые последние инспекции для каждого телефона
    latest_inspections_dict = {}
    for insp in all_inspections:
        if insp.phone_id not in latest_inspections_dict:
            latest_inspections_dict[insp.phone_id] = insp

    return list(latest_inspections_dict.values())

async def search_model_numbers(db: AsyncSession, query: str):
    """Ищет номера моделей по частичному совпадению."""
    search_query = select(models.ModelNumber).filter(models.ModelNumber.name.ilike(f"%{query}%")).limit(10)
    result = await db.execute(search_query)
    return result.scalars().all()

async def get_unique_model_names(db: AsyncSession, skip: int = 0, limit: int = 1000):
    """Получает список уникальных базовых названий моделей (из таблицы model_name)."""
    query = select(models.ModelName).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


async def get_models_by_name(db: AsyncSession, skip: int = 0, limit: int = 1000):
    """Получает список моделей с их названиями."""
    result = await db.execute(
        select(models.Models)
        .options(selectinload(models.Models.model_name))
        .offset(skip).limit(limit)
    )
    return result.scalars().all()

async def get_accessories_by_name(db: AsyncSession, skip: int = 0, limit: int = 1000):
    """Получает список аксессуаров с их названиями."""
    result = await db.execute(
        select(models.Accessories)
        .offset(skip).limit(limit)
    )
    return result.scalars().all()


async def get_user_by_username(db: AsyncSession, username: str):
    """Асинхронно получает пользователя из БД по его имени, сразу загружая роль и права."""
    query = (
        select(models.Users)
        .options(
            joinedload(models.Users.role)
            .joinedload(models.Roles.role_permissions)
            .joinedload(models.RolePermissions.permission)
        )
        .filter(models.Users.username == username)
    )
    result = await db.execute(query)
    return result.unique().scalars().first()

async def get_phone_by_id_fully_loaded(db: AsyncSession, phone_id: int):
    """Безопасно загружает один телефон со всеми связанными данными для ответов API."""
    query = (
        select(models.Phones)
        .options(
            selectinload(models.Phones.model).options(
                selectinload(models.Models.model_name),
                selectinload(models.Models.storage),
                selectinload(models.Models.color)
            ),
            selectinload(models.Phones.model_number),
            selectinload(models.Phones.supplier_order)
        )
        .filter(models.Phones.id == phone_id)
    )
    result = await db.execute(query)
    phone = result.scalars().one_or_none()
    if not phone:
        raise HTTPException(status_code=404, detail="Телефон не найден")
    return phone

async def get_phones(db: Session, skip: int = 0, limit: int = 1000):
    """Получает список телефонов с вложенными данными о модели."""
    query = (
        select(models.Phones)
        .options(
            selectinload(models.Phones.model)
            .selectinload(models.Models.model_name),
            selectinload(models.Phones.model)
            .selectinload(models.Models.storage),
            selectinload(models.Phones.model)
            .selectinload(models.Models.color),
        )
        .order_by(models.Phones.id.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()

# --- Функции для Поставщиков ---

async def get_suppliers(db: Session, skip: int = 0, limit: int = 100):
    """Получает список всех поставщиков."""
    result = await db.execute(select(models.Supplier).offset(skip).limit(limit))
    return result.scalars().all()

async def create_supplier(db: Session, supplier: schemas.SupplierCreate):
    """Создает нового поставщика в базе данных."""
    db_supplier = models.Supplier(**supplier.model_dump())
    db.add(db_supplier)
    await db.commit()
    await db.refresh(db_supplier)
    return db_supplier

async def delete_supplier(db: Session, supplier_id: int):
    """Удаляет поставщика по его ID."""
    result = await db.execute(select(models.Supplier).where(models.Supplier.id == supplier_id))
    db_supplier = result.scalars().first()
    if db_supplier:
        await db.delete(db_supplier)
        await db.commit()
        return db_supplier
    return None

async def update_supplier(db: Session, supplier_id: int, supplier: schemas.SupplierCreate):
    """Обновляет данные поставщика по его ID."""
    result = await db.execute(select(models.Supplier).where(models.Supplier.id == supplier_id))
    db_supplier = result.scalars().first()
    if db_supplier:
        db_supplier.name = supplier.name
        db_supplier.contact_info = supplier.contact_info
        await db.commit()
        await db.refresh(db_supplier)
        return db_supplier
    return None

# --- Функции для Заказов у Поставщиков ---

async def create_supplier_order(db: AsyncSession, order: schemas.SupplierOrderCreate):
    """Создает новый заказ у поставщика вместе со всеми позициями."""
    order_details_objects = [
        models.SupplierOrderDetails(**detail.model_dump())
        for detail in order.details
    ]

    db_order = models.SupplierOrders(
        supplier_id=order.supplier_id,
        order_date=datetime.now(),
        status=models.StatusDelivery.ЗАКАЗ,
        payment_status=models.OrderPaymentStatus.НЕ_ОПЛАЧЕН,
        supplier_order_details=order_details_objects
    )

    db.add(db_order)
    await db.commit()
    await db.refresh(db_order)
    return db_order

async def pay_supplier_order(db: AsyncSession, payment_data: schemas.SupplierPaymentCreate, user_id: int):
    """Регистрирует оплату за заказ поставщику и создает запись в движении денег."""
    order_result = await db.execute(
        select(models.SupplierOrders).options(
            joinedload(models.SupplierOrders.supplier)
        ).filter(models.SupplierOrders.id == payment_data.supplier_order_id)
    )
    order = order_result.scalars().one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Заказ поставщика не найден")

    operation_category_result = await db.execute(
        select(models.OperationCategories).filter(models.OperationCategories.name == "Закупка товара")
    )
    op_category = operation_category_result.scalars().first()
    if not op_category:
        raise HTTPException(status_code=500, detail="Категория операции 'Закупка товара' не найдена в БД.")

    counterparty_id_for_cash_flow = None
    if order.supplier and order.supplier.name:
        counterparty_res = await db.execute(select(models.Counterparties).filter(models.Counterparties.name == order.supplier.name))
        counterparty_obj = counterparty_res.scalars().first()
        if counterparty_obj:
            counterparty_id_for_cash_flow = counterparty_obj.id
        else:
            new_counterparty = models.Counterparties(name=order.supplier.name, type="Поставщик")
            db.add(new_counterparty)
            await db.flush()
            counterparty_id_for_cash_flow = new_counterparty.id

    cash_flow_entry = models.CashFlow(
        date=payment_data.payment_date or datetime.now(),
        operation_categories_id=op_category.id,
        account_id=payment_data.account_id,
        amount=-payment_data.amount,
        description=f"Оплата по заказу поставщику №{payment_data.supplier_order_id}",
        currency_id=1,
        counterparty_id=counterparty_id_for_cash_flow
    )
    db.add(cash_flow_entry)

    order.payment_status = models.OrderPaymentStatus.ОПЛАЧЕН
    order_id_to_return = order.id
    
    await db.commit()
    return order_id_to_return

async def get_all_storage_options(db: AsyncSession, skip: int = 0, limit: int = 100):
    """Получает все опции памяти."""
    result = await db.execute(select(models.Storage).offset(skip).limit(limit))
    return result.scalars().all()

async def get_all_color_options(db: AsyncSession, skip: int = 0, limit: int = 100):
    """Получает все опции цвета."""
    result = await db.execute(select(models.Colors).offset(skip).limit(limit))
    return result.scalars().all()


async def get_all_models_full_info(db: AsyncSession, skip: int = 0, limit: int = 1000):
    """Получает все модели с полной информацией."""
    query = (
        select(models.Models)
        .options(
            selectinload(models.Models.model_name),
            selectinload(models.Models.storage),
            selectinload(models.Models.color)
        )
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()

async def get_all_accessories_info(db: AsyncSession, skip: int = 0, limit: int = 100):
    """Получает список всех аксессуаров."""
    result = await db.execute(select(models.Accessories).offset(skip).limit(limit))
    return result.scalars().all()

async def get_accessories_in_stock(db: AsyncSession):
    """Получает список аксессуаров, которые есть на складе."""
    query = (
        select(models.Accessories, models.Warehouse.quantity)
        .join(models.Warehouse, (models.Accessories.id == models.Warehouse.product_id) & (models.Warehouse.product_type_id == 2))
        .filter(models.Warehouse.quantity > 0)
        .options(
            selectinload(models.Accessories.category_accessory),
            selectinload(models.Accessories.retail_price_accessories)
        )
    )
    result = await db.execute(query)
    return result.all()



async def get_supplier_orders(db: AsyncSession, skip: int = 0, limit: int = 100000, apply_role_limit: bool = False):
    """Получает список заказов у поставщиков с деталями и опциональным лимитом для роли."""
    orders_query = select(models.SupplierOrders).options(
        joinedload(models.SupplierOrders.supplier_order_details).options(
            joinedload(models.SupplierOrderDetails.model).options(
                selectinload(models.Models.model_name),
                selectinload(models.Models.storage),
                selectinload(models.Models.color)
            ),
            joinedload(models.SupplierOrderDetails.accessory)
        )
    ).order_by(models.SupplierOrders.id.desc()) # Сортируем, чтобы новые были сверху

    # Если нужно применить лимит для роли (например, для техника)
    if apply_role_limit:
        orders_query = orders_query.limit(10) # Показываем только последние 10
    else:
        # Для остальных ролей - стандартная пагинация
        orders_query = orders_query.offset(skip).limit(limit)

    result = await db.execute(orders_query)
    return result.scalars().unique().all()

async def receive_supplier_order(db: AsyncSession, order_id: int, user_id: int):
    """Обрабатывает получение заказа, добавляет товары и создает первую запись в логе."""
    result = await db.execute(
        select(models.SupplierOrders).options(
            selectinload(models.SupplierOrders.supplier_order_details).options(
                joinedload(models.SupplierOrderDetails.accessory),
                joinedload(models.SupplierOrderDetails.model)
            ),
            selectinload(models.SupplierOrders.supplier)
        ).filter(models.SupplierOrders.id == order_id)
    )
    order = result.scalars().unique().one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    if order.status == models.StatusDelivery.ПОЛУЧЕН:
        raise HTTPException(status_code=400, detail="Заказ уже был получен")

    order.status = models.StatusDelivery.ПОЛУЧЕН

    new_phones = []
    warehouse_entries = []
    log_entries = []

    for detail in order.supplier_order_details:
        if detail.model_id:
            for _ in range(detail.quantity):
                new_phone = models.Phones(
                    model_id=detail.model_id,
                    supplier_order_id=order.id,
                    purchase_price=detail.price,
                    technical_status=models.TechStatus.ОЖИДАЕТ_ПРОВЕРКУ,
                    commercial_status=models.CommerceStatus.НЕ_ГОТОВ_К_ПРОДАЖЕ,
                    added_date=datetime.now()
                )
                new_phones.append(new_phone)
        elif detail.accessory_id:
            if detail.accessory:
                detail.accessory.purchase_price = detail.price
            warehouse_entry = models.Warehouse(
                product_type_id=2, 
                product_id=detail.accessory_id,
                quantity=detail.quantity,
                shop_id=1, 
                storage_location=models.EnumShop.СКЛАД,
                added_date=datetime.now()
            )
            warehouse_entries.append(warehouse_entry)

    if new_phones:
        db.add_all(new_phones)
    if warehouse_entries:
        db.add_all(warehouse_entries)
        
    await db.flush()

    for phone in new_phones:
        supplier_name = order.supplier.name if order.supplier else "Неизвестно"
        log_entry = models.PhoneMovementLog(
            phone_id=phone.id,
            user_id=user_id,
            event_type=models.PhoneEventType.ПОСТУПЛЕНИЕ_ОТ_ПОСТАВЩИКА,
            details=f"Заказ №{order.id}. Поставщик: {supplier_name}. Цена: {phone.purchase_price} руб."
        )
        log_entries.append(log_entry)

    if log_entries:
        db.add_all(log_entries)

    await db.commit()
    await db.refresh(order)
    return order


async def get_shops(db: AsyncSession):
    """Получает список всех магазинов."""
    result = await db.execute(select(models.Shops))
    return result.scalars().all()

async def get_phones_ready_for_stock(db: AsyncSession):
    """Получает все телефоны со статусом 'УПАКОВАН', отсортированные по времени упаковки."""
    # Создаем подзапрос для поиска последнего лога об упаковке для каждого телефона
    latest_log_subquery = (
        select(
            models.PhoneMovementLog.phone_id,
            func.max(models.PhoneMovementLog.timestamp).label("max_timestamp")
        )
        .filter(models.PhoneMovementLog.details == "Телефон упакован и готов к приемке на склад.")
        .group_by(models.PhoneMovementLog.phone_id)
        .subquery()
    )

    query = (
        select(models.Phones)
        # Используем LEFT JOIN, чтобы не терять телефоны без логов
        .outerjoin(latest_log_subquery, models.Phones.id == latest_log_subquery.c.phone_id)
        .options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color)
        )
        .filter(models.Phones.technical_status == models.TechStatus.УПАКОВАН)
        .filter(models.Phones.commercial_status == models.CommerceStatus.НЕ_ГОТОВ_К_ПРОДАЖЕ)
        # Сортируем по времени из подзапроса, помещая телефоны без логов в конец
        .order_by(latest_log_subquery.c.max_timestamp.desc().nulls_last(), models.Phones.id.desc())
    )
    result = await db.execute(query)
    return result.scalars().unique().all()

async def accept_phones_to_warehouse(db: AsyncSession, data: schemas.WarehouseAcceptanceRequest, user_id: int):
    """Перемещает телефоны на склад и обновляет их статус."""
    phones_to_update_result = await db.execute(
        select(models.Phones).filter(models.Phones.id.in_(data.phone_ids))
    )
    phones_to_update = phones_to_update_result.scalars().all()
    
    shop = await db.get(models.Shops, data.shop_id)
    shop_name = shop.name if shop else "Неизвестный магазин"
    
    warehouse_entries = []
    log_entries = []
    for phone in phones_to_update:
        phone.commercial_status = models.CommerceStatus.НА_СКЛАДЕ
        
        warehouse_entry = models.Warehouse(
            product_type_id=1, 
            product_id=phone.id,
            quantity=1,
            shop_id=data.shop_id,
            storage_location=models.EnumShop.СКЛАД,
            added_date=datetime.now(),
            user_id=user_id
        )
        warehouse_entries.append(warehouse_entry)
        log_entries.append(models.PhoneMovementLog(
            phone_id=phone.id,
            user_id=user_id,
            event_type=models.PhoneEventType.ПРИНЯТ_НА_СКЛАД,
            details=f"Принят на склад магазина '{shop_name}' (размещение: {warehouse_entry.storage_location.value})."
        ))

    db.add_all(warehouse_entries)
    db.add_all(log_entries)
    await db.commit()
    
    # Запрашиваем телефоны заново, чтобы вернуть актуальные данные со всеми связями
    final_phones_result = await db.execute(
        select(models.Phones).options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color)
        ).filter(models.Phones.id.in_(data.phone_ids))
    )
    return final_phones_result.scalars().all()


async def get_all_accessories(db: AsyncSession):
    """Получает все аксессуары с категориями и историей цен."""
    result = await db.execute(
        select(models.Accessories)
        .options(
            selectinload(models.Accessories.category_accessory),
            selectinload(models.Accessories.retail_price_accessories)
        )
    )
    return result.scalars().unique().all()

async def get_traffic_sources(db: AsyncSession):
    """Получает список всех источников трафика."""
    result = await db.execute(select(models.TrafficSource))
    return result.scalars().all()

async def create_customer(db: AsyncSession, customer: schemas.CustomerCreate):
    """Создает нового покупателя в базе данных."""
    db_customer = models.Customers(**customer.model_dump())
    db.add(db_customer)
    await db.commit()
    await db.refresh(db_customer)
    return db_customer

async def get_customers(db: AsyncSession):
    """Получает список всех клиентов со связанными данными."""
    result = await db.execute(
        select(models.Customers).options(
            selectinload(models.Customers.source),
            selectinload(models.Customers.referrer) # Загружаем того, кто привел
        )
    )
    return result.scalars().all()

async def get_products_for_sale(db: AsyncSession):
    """Получает единый список всех товаров со склада."""
    warehouse_items_result = await db.execute(
        select(models.Warehouse).filter(
            models.Warehouse.quantity > 0,
            # VVV ДОБАВЬТЕ ЭТО УСЛОВИЕ VVV
            models.Warehouse.storage_location != models.EnumShop.ПОДМЕННЫЙ_ФОНД
        )
    )
    warehouse_items = warehouse_items_result.scalars().all()

    phone_ids = [item.product_id for item in warehouse_items if item.product_type_id == 1]
    accessory_ids = [item.product_id for item in warehouse_items if item.product_type_id == 2]

    phones = {}
    if phone_ids:
        phones_result = await db.execute(
            select(models.Phones).options(
                selectinload(models.Phones.model).selectinload(models.Models.model_name),
                selectinload(models.Phones.model).selectinload(models.Models.storage),
                selectinload(models.Phones.model).selectinload(models.Models.color),
                selectinload(models.Phones.model).selectinload(models.Models.retail_prices_phones)
            ).filter(
                models.Phones.id.in_(phone_ids)
            )
        )
        phones = {p.id: p for p in phones_result.scalars().all()}

    accessories = {}
    if accessory_ids:
        accessories_result = await db.execute(
            select(models.Accessories).options(
                selectinload(models.Accessories.category_accessory),
                selectinload(models.Accessories.retail_price_accessories)
            ).filter(models.Accessories.id.in_(accessory_ids))
        )
        accessories = {a.id: a for a in accessories_result.scalars().all()}

    final_warehouse_items = []
    for item in warehouse_items:
        product = None
        if item.product_type_id == 1:
            phone = phones.get(item.product_id)
            if phone and phone.commercial_status == models.CommerceStatus.НА_СКЛАДЕ:
                product = phone
        
        elif item.product_type_id == 2:
            product = accessories.get(item.product_id)

        if product:
            item.product = product
            final_warehouse_items.append(item)
            
    return final_warehouse_items

async def create_sale(db: AsyncSession, sale_data: schemas.SaleCreate, user_id: int):
    """Создает новую продажу, обновляет остатки, учитывает сдачу и рассчитывает прибыль."""
    
    subtotal = sum(item.unit_price * item.quantity for item in sale_data.details)
    discount_amount = sale_data.discount or Decimal('0')
    total_amount = subtotal - discount_amount

    if not sale_data.account_id:
        raise HTTPException(status_code=400, detail="Не указан счет для проведения операции.")

    new_sale = models.Sales(
        sale_date=datetime.now(),
        customer_id=sale_data.customer_id,
        payment_method=models.EnumPayment(sale_data.payment_method),
        total_amount=total_amount,
        discount=discount_amount,
        # VVV СОХРАНЯЕМ НОВЫЕ ДАННЫЕ VVV
        cash_received=sale_data.cash_received,
        change_given=sale_data.change_given,
        payment_status=models.StatusPay.ОПЛАЧЕН,
        user_id=user_id,
        notes=sale_data.notes,
        account_id=sale_data.account_id
    )
    db.add(new_sale)
    await db.flush()

    # Основная транзакция поступления от продажи
    amount_for_cash_flow = total_amount
    description_for_cash_flow = f"Поступление от продажи №{new_sale.id}"

    # Если оплата наличными и клиент не забрал сдачу
    if sale_data.payment_method == 'НАЛИЧНЫЕ' and sale_data.cash_received and not sale_data.change_given:
        # Фактическое поступление в кассу - это вся сумма, которую дал клиент
        amount_for_cash_flow = sale_data.cash_received
        # Добавляем в описание информацию об оставленной сдаче
        change_left = sale_data.cash_received - total_amount
        if change_left > 0:
            description_for_cash_flow += f". Клиент оставил сдачу: {change_left} руб."
    # --- КОНЕЦ ИЗМЕНЕНИЙ ---

    # Основная транзакция поступления от продажи
    cash_flow_entry = models.CashFlow(
        date=datetime.now(),
        operation_categories_id=2, # Поступление от продажи/услуг
        account_id=sale_data.account_id,
        amount=amount_for_cash_flow, # Используем новую, фактическую сумму
        description=description_for_cash_flow, # Используем новое описание
        currency_id=1
    )
    db.add(cash_flow_entry)

    # VVV НОВАЯ ЛОГИКА: Создаем транзакцию для сдачи, если она есть VVV
    if sale_data.change_given and sale_data.change_given > 0:
        change_cash_flow_entry = models.CashFlow(
            date=datetime.now(),
            operation_categories_id=7, # Предполагаем, что ID 7 = "Прочие расходы" или "Выдача сдачи"
            account_id=sale_data.account_id, # Сдача выдается с того же счета (кассы)
            amount=-abs(sale_data.change_given), # Расход
            description=f"Сдача по продаже №{new_sale.id}",
            currency_id=1
        )
        db.add(change_cash_flow_entry)
        
    for detail in sale_data.details:
        warehouse_item = await db.get(models.Warehouse, detail.warehouse_id)
        if not warehouse_item or warehouse_item.quantity < detail.quantity:
            await db.rollback()
            raise HTTPException(status_code=400, detail=f"Товара на складе (ID: {detail.warehouse_id}) недостаточно.")

        warehouse_item.quantity -= detail.quantity
        item_profit = None

        if warehouse_item.product_type_id == 1: # Телефон
            phone = await db.get(models.Phones, warehouse_item.product_id)
            if phone:
                phone.commercial_status = models.CommerceStatus.ПРОДАН
                customer_name = "Розничный покупатель"
                if new_sale.customer_id:
                    customer = await db.get(models.Customers, new_sale.customer_id)
                    if customer: customer_name = customer.name
                log_entry = models.PhoneMovementLog(
                    phone_id=phone.id, user_id=user_id,
                    event_type=models.PhoneEventType.ПРОДАН,
                    details=f"Продажа №{new_sale.id} клиенту '{customer_name}'. Цена: {detail.unit_price} руб."
                )
                db.add(log_entry)
                purchase_price = phone.purchase_price or 0
                item_profit = (detail.unit_price * detail.quantity) - (purchase_price * detail.quantity) - Decimal(800)

        elif warehouse_item.product_type_id == 2: # Аксессуар
            accessory = await db.get(models.Accessories, warehouse_item.product_id)
            if accessory:
                purchase_price = accessory.purchase_price or 0
                item_profit = (detail.unit_price * detail.quantity) - (purchase_price * detail.quantity)

        sale_detail_entry = models.SaleDetails(
            sale_id=new_sale.id, warehouse_id=detail.warehouse_id, quantity=detail.quantity,
            unit_price=detail.unit_price, profit=item_profit
        )
        db.add(sale_detail_entry)
    
    await db.commit()
    await db.refresh(new_sale, attribute_names=['sale_details'])
    return new_sale

async def add_price_for_model(db: AsyncSession, model_id: int, price_data: schemas.PriceCreate):
    """Добавляет новую розничную цену для модели телефона."""
    new_price = models.RetailPricesPhones(
        model_id=model_id,
        price=price_data.price,
        date=datetime.now()
    )
    db.add(new_price)
    await db.commit()
    await db.refresh(new_price)
    return new_price

async def add_price_for_accessory(db: AsyncSession, accessory_id: int, price_data: schemas.PriceCreate):
    """Добавляет новую розничную цену для аксессуара."""
    new_price = models.RetailPriceAccessories(
        accessory_id=accessory_id,
        price=price_data.price,
        date=datetime.now()
    )
    db.add(new_price)
    await db.commit()
    await db.refresh(new_price)
    return new_price

async def get_unique_model_storage_combos(db: AsyncSession):
    """
    Возвращает уникальные комбинации 'модель + память' с их текущей ценой
    ТОЛЬКО для тех моделей, которые есть на складе или в заказах.
    """
    stmt_warehouse = (
        select(models.Phones.model_id)
        .join(models.Warehouse, models.Phones.id == models.Warehouse.product_id)
        .where(models.Warehouse.product_type_id == 1)
    )
    warehouse_models_result = await db.execute(stmt_warehouse)
    warehouse_model_ids = {row[0] for row in warehouse_models_result.all() if row[0] is not None}

    stmt_orders = (
        select(models.SupplierOrderDetails.model_id)
        .where(models.SupplierOrderDetails.model_id.is_not(None))
    )
    order_details_models_result = await db.execute(stmt_orders)
    order_model_ids = {row[0] for row in order_details_models_result.all() if row[0] is not None}

    relevant_model_ids = warehouse_model_ids.union(order_model_ids)

    if not relevant_model_ids:
        return []

    all_models_result = await db.execute(
        select(models.Models).options(
            selectinload(models.Models.model_name),
            selectinload(models.Models.storage),
            selectinload(models.Models.retail_prices_phones)
        ).filter(models.Models.id.in_(list(relevant_model_ids)))
    )
    all_models = all_models_result.scalars().unique().all()

    combos = {}
    for model in all_models:
        if model.model_name and model.storage:
            key = (model.model_name_id, model.storage_id)
            if key not in combos:
                latest_price = None
                if model.retail_prices_phones:
                    latest_price_entry = sorted(model.retail_prices_phones, key=lambda p: p.date, reverse=True)[0]
                    latest_price = latest_price_entry.price
                
                combos[key] = {
                    "display_name": f"{model.model_name.name} {models.format_storage_for_display(model.storage.storage)}",
                    "model_name_id": model.model_name_id,
                    "storage_id": model.storage_id,
                    "current_price": latest_price
                }
    return list(combos.values())

async def add_price_for_model_storage_combo(db: AsyncSession, data: schemas.PriceSetForCombo):
    """Находит все цветовые вариации для комбинации 'модель+память' и устанавливает им цену."""
    
    models_to_update_result = await db.execute(
        select(models.Models).filter_by(
            model_name_id=data.model_name_id,
            storage_id=data.storage_id
        )
    )
    models_to_update = models_to_update_result.scalars().all()

    if not models_to_update:
        raise HTTPException(status_code=404, detail="Модели для такой комбинации не найдены")

    new_prices = [
        models.RetailPricesPhones(
            model_id=model.id,
            price=data.price,
            date=datetime.now()
        )
        for model in models_to_update
    ]

    db.add_all(new_prices)
    await db.commit()

    for price_entry in new_prices:
        await db.refresh(price_entry)


    return new_prices




# --- Функции для Движения Денег ---

async def get_operation_categories(db: AsyncSession):
    """Получает список всех категорий операций."""
    result = await db.execute(select(models.OperationCategories))
    return result.scalars().all()

async def get_counterparties(db: AsyncSession):
    """Получает список всех контрагентов."""
    result = await db.execute(select(models.Counterparties))
    return result.scalars().all()

async def get_accounts(db: AsyncSession):
    """Получает список всех счетов."""
    result = await db.execute(select(models.Accounts))
    return result.scalars().all()

async def create_cash_flow(db: AsyncSession, cash_flow: schemas.CashFlowCreate, user_id: int):
    """Создает новую запись о движении денежных средств."""
    db_cash_flow = models.CashFlow(
        **cash_flow.model_dump(),
        date=datetime.now(),
        currency_id=1
    )
    db.add(db_cash_flow)
    await db.commit()
    await db.refresh(db_cash_flow)
    return db_cash_flow

async def get_cash_flows(db: AsyncSession, skip: int = 0, limit: int = 100):
    """Получает список всех денежных операций."""
    result = await db.execute(
        select(models.CashFlow)
        .order_by(models.CashFlow.date.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()

async def create_account(db: AsyncSession, account: schemas.AccountCreate):
    """Создает новый счет."""
    db_account = models.Accounts(**account.model_dump())
    db.add(db_account)
    await db.commit()
    await db.refresh(db_account)
    return db_account

async def create_counterparty(db: AsyncSession, counterparty: schemas.CounterpartyCreate):
    """Создает нового контрагента."""
    db_counterparty = models.Counterparties(**counterparty.model_dump())
    db.add(db_counterparty)
    await db.commit()
    await db.refresh(db_counterparty)
    return db_counterparty

async def get_total_balance(db: AsyncSession) -> Decimal:
    """Подсчитывает и возвращает общий баланс по всем счетам."""
    stmt = select(func.coalesce(func.sum(models.CashFlow.amount), 0))
    result = await db.execute(stmt)
    total = result.scalar_one()
    return total

async def get_inventory_valuation(db: AsyncSession) -> Decimal:
    """Подсчитывает стоимость всех телефонов на складе по их закупочной цене."""
    stmt = select(func.sum(models.Phones.purchase_price)).where(
        models.Phones.commercial_status == models.CommerceStatus.НА_СКЛАДЕ
    )
    result = await db.execute(stmt)
    total_valuation = result.scalar_one_or_none()

    return total_valuation or Decimal('0')

async def get_profit_report(db: AsyncSession, start_date: date, end_date: date) -> dict:
    end_date_inclusive = end_date + timedelta(days=1)

    revenue_result = await db.execute(
        select(func.sum(models.Sales.total_amount))
        .filter(models.Sales.sale_date >= start_date)
        .filter(models.Sales.sale_date < end_date_inclusive)
    )
    total_revenue = revenue_result.scalar_one_or_none() or Decimal('0')

    gross_profit_result = await db.execute(
        select(func.sum(models.SaleDetails.profit))
        .join(models.Sales)
        .filter(models.Sales.sale_date >= start_date)
        .filter(models.Sales.sale_date < end_date_inclusive)
    )
    gross_profit = gross_profit_result.scalar_one_or_none() or Decimal('0')
    total_cogs = total_revenue - gross_profit

    expenses_result = await db.execute(
        select(func.sum(models.CashFlow.amount))
        .join(models.OperationCategories)
        .filter(models.CashFlow.date >= start_date)
        .filter(models.CashFlow.date < end_date_inclusive)
        .filter(models.OperationCategories.type == 'expense')
    )
    total_expenses = expenses_result.scalar_one_or_none() or Decimal('0')

    operating_profit = gross_profit + total_expenses
    
    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_revenue": total_revenue,
        "total_cogs": total_cogs,
        "gross_profit": gross_profit,
        "total_expenses": total_expenses,
        "operating_profit": operating_profit
    }

async def create_accessory(db: AsyncSession, accessory: schemas.AccessoryCreate):
    """Создает новый аксессуар в базе данных."""
    db_accessory = models.Accessories(**accessory.model_dump())
    db.add(db_accessory)
    await db.commit()
    await db.refresh(db_accessory)
    return db_accessory

async def get_accessory_categories(db: AsyncSession):
    """Получает список всех категорий аксессуаров."""
    result = await db.execute(select(models.CategoryAccessories))
    return result.scalars().all()

async def link_accessory_to_model(db: AsyncSession, link_data: schemas.AccessoryModelCreate):
    """Создает связь между аксессуаром и базовой моделью телефона."""
    existing_link = await db.execute(
        select(models.AccessoriesModel).filter_by(
            accessory_id=link_data.accessory_id,
            model_name_id=link_data.model_name_id
        )
    )
    if existing_link.scalars().first():
        raise HTTPException(status_code=400, detail="Такая связь уже существует")

    db_link = models.AccessoriesModel(**link_data.model_dump())
    db.add(db_link)
    await db.commit()
    await db.refresh(db_link, attribute_names=['accessory', 'model_name'])
    return db_link

async def get_accessory_model_links(db: AsyncSession):
    """Получает все существующие связи 'аксессуар-модель'."""
    result = await db.execute(
        select(models.AccessoriesModel).options(
            joinedload(models.AccessoriesModel.accessory),
            joinedload(models.AccessoriesModel.model_name)
        )
    )
    return result.scalars().all()

async def unlink_accessory_from_model(db: AsyncSession, link_id: int):
    """Удаляет связь по ее ID."""
    link = await db.get(models.AccessoriesModel, link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Связь не найдена")
    await db.delete(link)
    await db.commit()
    return {"ok": True}

async def get_accessories_for_model(db: AsyncSession, model_name_id: int):
    """
    Получает список аксессуаров, совместимых с указанной базовой моделью,
    И которые ЕСТЬ НА СКЛАДЕ.
    """
    query = (
        select(models.Accessories)
        .join(models.AccessoriesModel)
        .join(models.Warehouse, (models.Warehouse.product_id == models.Accessories.id) & (models.Warehouse.product_type_id == 2))
        .filter(models.AccessoriesModel.model_name_id == model_name_id)
        .filter(models.Warehouse.quantity > 0)
        .options(
            selectinload(models.Accessories.retail_price_accessories),
            selectinload(models.Accessories.category_accessory)
        )
    )
    result = await db.execute(query)
    return result.scalars().unique().all()

async def get_phone_history_by_serial(db: AsyncSession, serial_number: str):
    """Собирает полную историю телефона по его серийному номеру."""
    phone_query = (
        select(models.Phones)
        .options(
            selectinload(models.Phones.model).options(
                selectinload(models.Models.model_name),
                selectinload(models.Models.storage),
                selectinload(models.Models.color)
            ),
            selectinload(models.Phones.supplier_order).selectinload(models.SupplierOrders.supplier),
            selectinload(models.Phones.device_inspections).options(
                selectinload(models.DeviceInspection.user),
                selectinload(models.DeviceInspection.inspection_results).selectinload(models.InspectionResults.checklist_item),
                selectinload(models.DeviceInspection.battery_tests)
            ),
            selectinload(models.Phones.movement_logs).options(
                selectinload(models.PhoneMovementLog.user)
            ),
            selectinload(models.Phones.model_number),
            # --- НАЧАЛО ИСПРАВЛЕНИЯ ---
            selectinload(models.Phones.repairs).options(
                selectinload(models.Repairs.loaner_logs).options(
                    selectinload(models.LoanerLog.loaner_phone).options(
                        selectinload(models.Phones.model).options(  
                            selectinload(models.Models.model_name),
                            selectinload(models.Models.storage),  
                            selectinload(models.Models.color)    
                        )
                    )
                )
            )
        )
        .filter(func.lower(models.Phones.serial_number) == func.lower(serial_number))
    )
    phone_result = await db.execute(phone_query)
    phone = phone_result.scalars().unique().one_or_none() # Используем unique() для корректной сборки

    if not phone:
        raise HTTPException(status_code=404, detail="Телефон с таким серийным номером не найден")
    
    return phone

async def get_defective_phones(db: AsyncSession):
    """Получает телефоны со статусом 'БРАК' с последней записью в логе как причиной."""
    query = (
        select(models.Phones)
        .options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color),
            selectinload(models.Phones.model_number),
            selectinload(models.Phones.supplier_order),
            selectinload(models.Phones.repairs).options(
                selectinload(models.Repairs.loaner_logs).options(
                    selectinload(models.LoanerLog.loaner_phone).options(
                        selectinload(models.Phones.model).selectinload(models.Models.model_name)
                    )
                )
            ),
            selectinload(models.Phones.movement_logs) # Загружаем логи
        )
        .filter(models.Phones.technical_status == models.TechStatus.БРАК)
        .filter(models.Phones.commercial_status != models.CommerceStatus.ОТПРАВЛЕН_ПОСТАВЩИКУ)
        .filter(models.Phones.commercial_status != models.CommerceStatus.СПИСАН_ПОСТАВЩИКОМ)
        
    )
    result = await db.execute(query)
    phones = result.scalars().unique().all() # Используем unique() для корректной сборки

    for phone in phones:
        defect_log = None
        # Сортируем логи, чтобы проверить самые свежие первыми
        sorted_logs = sorted(phone.movement_logs, key=lambda log: log.timestamp, reverse=True)
        
        # Ищем последнюю запись, которая является причиной брака
        for phone in phones:
            defect_log = None
            sorted_logs = sorted(phone.movement_logs, key=lambda log: log.timestamp, reverse=True)

            for log in sorted_logs:
                if log.event_type in [
                    models.PhoneEventType.ОБНАРУЖЕН_БРАК,
                    models.PhoneEventType.ВОЗВРАТ_ОТ_КЛИЕНТА,
                    models.PhoneEventType.ОБМЕНЕН
                ]:
                    defect_log = log
                    break

            if defect_log and defect_log.details:
                # VVV ИЗМЕНЕНИЕ ЗДЕСЬ VVV
                phone.defect_reason = _extract_specific_defect_reason(defect_log.details)
            elif defect_log:
                phone.defect_reason = defect_log.event_type.value
            else:
                phone.defect_reason = "Изначальная причина не найдена"
    return phones

async def get_phones_sent_to_supplier(db: AsyncSession):
    """Получает телефоны, отправленные поставщику."""
    query = (
        select(models.Phones)
        .options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color),
            selectinload(models.Phones.model_number),
            selectinload(models.Phones.supplier_order),
            selectinload(models.Phones.movement_logs)
        )
        .filter(models.Phones.commercial_status == models.CommerceStatus.ОТПРАВЛЕН_ПОСТАВЩИКУ)
    )
    result = await db.execute(query)
    phones = result.scalars().unique().all()

    for phone in phones:
        defect_log = None
        # Сортируем логи, чтобы проверить самые свежие первыми
        sorted_logs = sorted(phone.movement_logs, key=lambda log: log.timestamp, reverse=True)
        
        # Ищем последнюю запись, которая является причиной брака
        for phone in phones:
            defect_log = None
            sorted_logs = sorted(phone.movement_logs, key=lambda log: log.timestamp, reverse=True)

            for log in sorted_logs:
                if log.event_type in [
                    models.PhoneEventType.ОБНАРУЖЕН_БРАК,
                    models.PhoneEventType.ВОЗВРАТ_ОТ_КЛИЕНТА,
                    models.PhoneEventType.ОБМЕНЕН
                ]:
                    defect_log = log
                    break

            if defect_log and defect_log.details:
                # VVV ИЗМЕНЕНИЕ ЗДЕСЬ VVV
                phone.defect_reason = _extract_specific_defect_reason(defect_log.details)
            elif defect_log:
                phone.defect_reason = defect_log.event_type.value
            else:
                phone.defect_reason = "Изначальная причина не найдена"

    return phones

async def send_phones_to_supplier(db: AsyncSession, phone_ids: List[int], user_id: int):
    """Меняет коммерческий статус телефонов и создает лог."""
    result = await db.execute(select(models.Phones).filter(models.Phones.id.in_(phone_ids)))
    phones_to_update = result.scalars().all()

    for phone in phones_to_update:
        phone.commercial_status = models.CommerceStatus.ОТПРАВЛЕН_ПОСТАВЩИКУ
        log_entry = models.PhoneMovementLog(
            phone_id=phone.id,
            user_id=user_id,
            event_type=models.PhoneEventType.ОТПРАВЛЕН_ПОСТАВЩИКУ,
            details="Отправлен поставщику для возврата/ремонта брака."
        )
        db.add(log_entry)

    await db.commit()

    final_phones_result = await db.execute(
        select(models.Phones).options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color)
        ).filter(models.Phones.id.in_(phone_ids))
    )
    return final_phones_result.scalars().all()

async def process_return_from_supplier(db: AsyncSession, phone_id: int, user_id: int):
    """Обрабатывает возврат от поставщика, сбрасывая статус на перепроверку."""
    phone = await db.get(models.Phones, phone_id)
    if not phone:
        raise HTTPException(status_code=404, detail="Телефон не найден")

    phone.technical_status = models.TechStatus.ОЖИДАЕТ_ПРОВЕРКУ
    phone.commercial_status = models.CommerceStatus.НЕ_ГОТОВ_К_ПРОДАЖЕ
    
    log_entry = models.PhoneMovementLog(
        phone_id=phone.id,
        user_id=user_id,
        event_type=models.PhoneEventType.ПОЛУЧЕН_ОТ_ПОСТАВЩИКА,
        details="Получен от поставщика после возврата. Направлен на повторную инспекцию."
    )
    db.add(log_entry)
    
    await db.commit()

    final_phone_result = await db.execute(
        select(models.Phones).options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color)
        ).filter(models.Phones.id == phone_id)
    )
    return final_phone_result.scalars().one()


async def process_customer_refund(db: AsyncSession, phone_id: int, refund_data: schemas.RefundRequest, user_id: int):
    """Обрабатывает возврат телефона от клиента."""
    phone = await db.get(models.Phones, phone_id)
    if not phone:
        raise HTTPException(status_code=404, detail="Телефон не найден")
    if phone.commercial_status != models.CommerceStatus.ПРОДАН:
        raise HTTPException(status_code=400, detail="Этот телефон не был продан")

    warehouse_entry_result = await db.execute(
        select(models.Warehouse).filter_by(product_id=phone.id, product_type_id=1)
    )
    warehouse_entry = warehouse_entry_result.scalars().first()
    if not warehouse_entry:
        raise HTTPException(status_code=404, detail="Запись о складе для этого телефона не найдена")

    sale_detail_result = await db.execute(
        select(models.SaleDetails).filter_by(warehouse_id=warehouse_entry.id)
    )
    sale_detail = sale_detail_result.scalars().first()
    if not sale_detail:
        raise HTTPException(status_code=404, detail="Запись о продаже для этого телефона не найдена")

    phone.technical_status = models.TechStatus.БРАК
    phone.commercial_status = models.CommerceStatus.ВОЗВРАТ

    warehouse_entry.quantity += 1
    
    log_entry = models.PhoneMovementLog(
        phone_id=phone.id,
        user_id=user_id,
        event_type=models.PhoneEventType.ВОЗВРАТ_ОТ_КЛИЕНТА,
        details=f"Возврат по продаже №{sale_detail.sale_id}. Сумма: {sale_detail.unit_price} руб. Причина: {refund_data.notes or 'не указана'}."
    )
    db.add(log_entry)
    
    refund_amount = sale_detail.unit_price
    cash_flow_entry = models.CashFlow(
        date=datetime.now(),
        operation_categories_id=6,
        account_id=refund_data.account_id,
        amount=-refund_amount,
        description=f"Возврат средств за телефон S/N: {phone.serial_number}. Продажа ID: {sale_detail.sale_id}. {refund_data.notes or ''}".strip(),
        currency_id=1
    )
    db.add(cash_flow_entry)

    sale_detail.profit = 0

    await db.commit()
    await db.refresh(phone)
    return phone


async def start_repair(db: AsyncSession, phone_id: int, repair_data: schemas.RepairCreate, user_id: int):
    """Начинает ремонт и НЕ ВОЗВРАЩАЕТ ОБЪЕКТ."""
    phone = await db.get(models.Phones, phone_id)
    if not phone or phone.commercial_status != models.CommerceStatus.ПРОДАН:
        raise HTTPException(status_code=400, detail="Телефон не найден или не имеет статус 'ПРОДАН'")
    
    phone.commercial_status = models.CommerceStatus.В_РЕМОНТЕ
    
    new_repair_record = models.Repairs(**repair_data.model_dump(), phone_id=phone_id, user_id=user_id)
    db.add(new_repair_record)
    
    log_details = f"Принят от клиента на {repair_data.repair_type.lower()} ремонт. Проблема: {repair_data.problem_description}"
    if repair_data.repair_type == 'ПЛАТНЫЙ' and repair_data.estimated_cost:
        log_details += f" Предв. стоимость: {repair_data.estimated_cost} руб."

    log_entry = models.PhoneMovementLog(
        phone_id=phone.id, user_id=user_id,
        event_type=models.PhoneEventType.ОТПРАВЛЕН_В_РЕМОНТ, details=log_details
    )
    db.add(log_entry)
    
    await db.commit()


async def finish_repair(db: AsyncSession, repair_id: int, finish_data: schemas.RepairFinish, user_id: int) -> int:
    """Завершает ремонт и ВОЗВРАЩАЕТ ТОЛЬКО ID ТЕЛЕФОНА."""
    repair_record = await db.get(models.Repairs, repair_id, options=[selectinload(models.Repairs.phone)])
    if not repair_record or not repair_record.phone:
        raise HTTPException(status_code=404, detail="Запись о ремонте или связанный телефон не найдены")
    
    phone_id_to_return = repair_record.phone.id
    
    repair_record.date_returned = datetime.now()
    repair_record.work_performed = finish_data.work_performed
    repair_record.final_cost = finish_data.final_cost
    repair_record.service_cost = finish_data.service_cost

    log_details = f"Ремонт завершен. Работы: {finish_data.work_performed}."

    if repair_record.repair_type == models.RepairType.ПЛАТНЫЙ:
        repair_record.payment_status = models.StatusPay.ОЖИДАНИЕ_ОПЛАТЫ
        log_details += f" Итоговая стоимость: {finish_data.final_cost or 0} руб. Ожидается оплата."
    else: # Для гарантийного ремонта
        repair_record.phone.commercial_status = models.CommerceStatus.ПРОДАН
    
    if finish_data.service_cost and finish_data.service_cost > 0 and finish_data.expense_account_id:
            cash_flow_entry = models.CashFlow(
                date=datetime.now(),
                operation_categories_id=5, # ПРЕДПОЛАГАЕМ, ЧТО ID 5 = "Ремонтные работы (Расход)"
                account_id=finish_data.expense_account_id,
                amount=-abs(finish_data.service_cost), # Расход всегда отрицательный
                description=f"Оплата мастеру за ремонт №{repair_id} (S/N: {repair_record.phone.serial_number})",
                currency_id=1
            )
            db.add(cash_flow_entry)
            log_details += f" Себестоимость: {finish_data.service_cost} руб."
    
    log_entry = models.PhoneMovementLog(
        phone_id=repair_record.phone.id, user_id=user_id,
        event_type=models.PhoneEventType.ПОЛУЧЕН_ИЗ_РЕМОНТА, details=log_details
    )
    db.add(log_entry)
    
    await db.commit()
    return phone_id_to_return


async def record_repair_payment(db: AsyncSession, repair_id: int, payment_data: schemas.RepairPayment, user_id: int) -> int:
    """Регистрирует оплату за платный ремонт и ВОЗВРАЩАЕТ ТОЛЬКО ID ТЕЛЕФОНА."""
    repair = await db.get(models.Repairs, repair_id, options=[selectinload(models.Repairs.phone)])
    if not repair or not repair.phone:
        raise HTTPException(status_code=404, detail="Запись о ремонте или связанный телефон не найдены")
    if repair.repair_type != models.RepairType.ПЛАТНЫЙ:
        raise HTTPException(status_code=400, detail="Этот ремонт не является платным")
    if repair.payment_status == models.StatusPay.ОПЛАЧЕН:
        raise HTTPException(status_code=400, detail="Этот ремонт уже оплачен")

    # Сохраняем ID телефона перед коммитом
    phone_id_to_return = repair.phone.id

    # Создаем запись в движении денег
    cash_flow_entry = models.CashFlow(
        date=datetime.now(),
        operation_categories_id=2, # Поступление от продажи/услуг
        account_id=payment_data.account_id,
        amount=payment_data.amount,
        description=f"Оплата за платный ремонт №{repair.id} (S/N: {repair.phone.serial_number})",
        currency_id=1
    )
    db.add(cash_flow_entry)

    # Обновляем статус ремонта и телефона
    repair.payment_status = models.StatusPay.ОПЛАЧЕН
    repair.phone.commercial_status = models.CommerceStatus.ПРОДАН
    
    # Создаем лог
    log_entry = models.PhoneMovementLog(
        phone_id=repair.phone.id,
        user_id=user_id,
        event_type=models.PhoneEventType.ПОЛУЧЕН_ИЗ_РЕМОНТА,
        details=f"Ремонт №{repair.id} оплачен на сумму {payment_data.amount} руб. Телефон выдан клиенту."
    )
    db.add(log_entry)
    
    await db.commit()
    
    # Возвращаем только ID
    return phone_id_to_return

async def get_phone_by_id_fully_loaded(db: AsyncSession, phone_id: int):
    """Загружает один телефон со всеми связанными данными для ответов API."""
    query = (
        select(models.Phones)
        .options(
            selectinload(models.Phones.model).options(
                selectinload(models.Models.model_name),
                selectinload(models.Models.storage),
                selectinload(models.Models.color)
            ),
            selectinload(models.Phones.model_number)
        )
        .filter(models.Phones.id == phone_id)
    )
    result = await db.execute(query)
    phone = result.scalars().one_or_none()
    if not phone:
        raise HTTPException(status_code=404, detail="Телефон не найден")
    return phone


async def get_replacement_options(db: AsyncSession, original_phone_model_id: int):
    """
    Находит на складе телефоны для обмена.
    Теперь ищет ту же модель и память, но позволяет выбрать другой цвет.
    """
    # 1. Сначала получаем детали оригинальной модели (название и память)
    original_model = await db.get(models.Models, original_phone_model_id)
    if not original_model:
        return []

    # 2. Находим ID всех моделей с таким же названием и памятью (но любым цветом)
    matching_models_result = await db.execute(
        select(models.Models.id).filter(
            models.Models.model_name_id == original_model.model_name_id,
            models.Models.storage_id == original_model.storage_id
        )
    )
    matching_model_ids = matching_models_result.scalars().all()
    if not matching_model_ids:
        return []

    # 3. Теперь ищем на складе доступные телефоны, у которых model_id - один из найденных
    latest_warehouse_sq = (
        select(
            models.Warehouse.product_id,
            models.Warehouse.storage_location,
            func.row_number().over(
                partition_by=models.Warehouse.product_id,
                order_by=models.Warehouse.id.desc()
            ).label("row_num"),
        )
        .where(models.Warehouse.product_type_id == 1)
        .subquery()
    )

    query = (
        select(models.Phones)
        .join(latest_warehouse_sq, models.Phones.id == latest_warehouse_sq.c.product_id)
        .where(latest_warehouse_sq.c.row_num == 1)
        .filter(models.Phones.model_id.in_(matching_model_ids)) # <--- Используем новый список ID
        .filter(models.Phones.commercial_status == models.CommerceStatus.НА_СКЛАДЕ)
        .filter(
            or_(
                latest_warehouse_sq.c.storage_location == models.EnumShop.СКЛАД,
                latest_warehouse_sq.c.storage_location == models.EnumShop.ВИТРИНА
            )
        )
        .options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color)
        )
    )
    result = await db.execute(query)
    return result.scalars().all()

async def process_phone_exchange(db: AsyncSession, original_phone_id: int, replacement_phone_id: int, user_id: int):
    """Обрабатывает обмен и создает логи для обоих телефонов."""
    # Загружаем телефоны сразу с их моделями для проверки
    original_phone = await db.get(models.Phones, original_phone_id, options=[selectinload(models.Phones.model)])
    replacement_phone = await db.get(models.Phones, replacement_phone_id, options=[selectinload(models.Phones.model)])

    # Проверки на существование и статусы
    if not original_phone or original_phone.commercial_status != models.CommerceStatus.ПРОДАН:
        raise HTTPException(status_code=400, detail="Исходный телефон не найден или не был продан.")
    if not replacement_phone or replacement_phone.commercial_status != models.CommerceStatus.НА_СКЛАДЕ:
        raise HTTPException(status_code=400, detail="Телефон для замены не найден на складе.")
    
    # --- НОВАЯ ГИБКАЯ ПРОВЕРКА МОДЕЛЕЙ ---
    if (not original_phone.model or not replacement_phone.model or
            original_phone.model.model_name_id != replacement_phone.model.model_name_id or
            original_phone.model.storage_id != replacement_phone.model.storage_id):
        raise HTTPException(status_code=400, detail="Обмен возможен только на ту же модель и объем памяти.")
    # --- КОНЕЦ НОВОЙ ПРОВЕРКИ ---

    # ... (остальная часть функции остается без изменений)
    
    orig_wh_res = await db.execute(
        select(models.Warehouse)
        .filter_by(product_id=original_phone.id, product_type_id=1)
        .order_by(models.Warehouse.id.desc())
        )
    original_warehouse_entry = orig_wh_res.scalars().first()
        
    repl_wh_res = await db.execute(
        select(models.Warehouse)
        .filter_by(product_id=replacement_phone.id, product_type_id=1)
        .order_by(models.Warehouse.id.desc())
        )
    replacement_warehouse_entry = repl_wh_res.scalars().first()

    if not original_warehouse_entry or not replacement_warehouse_entry:
        raise HTTPException(status_code=404, detail="Не найдена складская запись для одного из телефонов.")

    sale_detail_res = await db.execute(
        select(models.SaleDetails).filter_by(warehouse_id=original_warehouse_entry.id)
        )
    sale_detail = sale_detail_res.scalars().one()
    
    log_original = models.PhoneMovementLog(
        phone_id=original_phone.id,
        user_id=user_id,
        event_type=models.PhoneEventType.ОБМЕНЕН,
        details=f"Обменян (возвращен клиентом) в рамках продажи №{sale_detail.sale_id}. Заменен на S/N: {replacement_phone.serial_number}."
    )
    db.add(log_original)

    log_replacement = models.PhoneMovementLog(
        phone_id=replacement_phone.id,
        user_id=user_id,
        event_type=models.PhoneEventType.ОБМЕНЕН,
        details=f"Обменян (выдан клиенту) в рамках продажи №{sale_detail.sale_id}. Заменил S/N: {original_phone.serial_number}."
    )
    db.add(log_replacement)
    
    original_phone.commercial_status = models.CommerceStatus.ВОЗВРАТ
    original_phone.technical_status = models.TechStatus.БРАК
    original_warehouse_entry.quantity += 1

    replacement_phone.commercial_status = models.CommerceStatus.ПРОДАН
    replacement_warehouse_entry.quantity -= 1

    sale_detail.warehouse_id = replacement_warehouse_entry.id

    new_profit = sale_detail.unit_price - (replacement_phone.purchase_price or 0) - 800
    sale_detail.profit = new_profit

    await db.commit()

    return await get_phone_by_id_fully_loaded(db, original_phone_id)


async def process_supplier_replacement(
    db: AsyncSession, 
    original_phone_id: int, 
    new_phone_data: schemas.SupplierReplacementCreate, 
    user_id: int
) -> int:  # <-- Указываем, что возвращаем число (ID)
    """Обрабатывает замену устройства и возвращает ID нового телефона."""
    
    original_phone = await db.get(models.Phones, original_phone_id)
    if not original_phone:
        raise HTTPException(status_code=404, detail="Оригинальный телефон для замены не найден.")
    if original_phone.commercial_status != models.CommerceStatus.ОТПРАВЛЕН_ПОСТАВЩИКУ:
        raise HTTPException(status_code=400, detail="Телефон не был отправлен поставщику.")

    original_phone.commercial_status = models.CommerceStatus.СПИСАН_ПОСТАВЩИКОМ
    
    new_phone = models.Phones(
        serial_number=new_phone_data.new_serial_number,
        model_id=new_phone_data.new_model_id,
        supplier_order_id=original_phone.supplier_order_id,
        purchase_price=original_phone.purchase_price,
        technical_status=models.TechStatus.ОЖИДАЕТ_ПРОВЕРКУ,
        commercial_status=models.CommerceStatus.НЕ_ГОТОВ_К_ПРОДАЖЕ,
        added_date=datetime.now()
    )
    db.add(new_phone)
    
    log_original = models.PhoneMovementLog(
        phone_id=original_phone.id,
        user_id=user_id,
        event_type=models.PhoneEventType.ОБМЕНЕН,
        details=f"Заменен поставщиком на новый телефон с S/N: {new_phone_data.new_serial_number}."
    )
    db.add(log_original)
    
    await db.flush() # Получаем ID для new_phone

    log_new = models.PhoneMovementLog(
        phone_id=new_phone.id,
        user_id=user_id,
        event_type=models.PhoneEventType.ПОСТУПЛЕНИЕ_ОТ_ПОСТАВЩИКА,
        details=f"Поступил от поставщика в качестве замены для старого телефона с S/N: {original_phone.serial_number}."
    )
    db.add(log_new)
    
    # Сохраняем ID перед коммитом
    new_phone_id = new_phone.id
    
    # Коммит теперь находится здесь, завершая операцию в CRUD
    await db.commit()
    
    return new_phone_id # <-- Возвращаем только ID

async def get_replacement_model_options(db: AsyncSession, model_id: int):
    """Находит все модели с тем же названием и памятью, но разными цветами."""
    
    # Находим оригинальную модель
    original_model = await db.get(models.Models, model_id)
    if not original_model:
        return []

    # Находим все модели с тем же model_name_id и storage_id
    query = (
        select(models.Models)
        .options(
            selectinload(models.Models.model_name),
            selectinload(models.Models.storage),
            selectinload(models.Models.color)
        )
        .filter(
            models.Models.model_name_id == original_model.model_name_id,
            models.Models.storage_id == original_model.storage_id
        )
    )
    result = await db.execute(query)
    return result.scalars().all()

async def get_roles(db: AsyncSession):
    """Получает список всех ролей."""
    result = await db.execute(select(models.Roles))
    return result.scalars().all()

async def create_user(db: AsyncSession, user_data: schemas.EmployeeCreate):
    """Создает нового пользователя (сотрудника)."""
    existing_user_result = await db.execute(
        select(models.Users).filter(models.Users.username == user_data.username)
    )
    if existing_user_result.scalars().first():
        raise HTTPException(status_code=400, detail="Пользователь с таким именем уже существует")

    hashed_password = security.get_password_hash(user_data.password)
    db_user = models.Users(
        username=user_data.username,
        password_hash=hashed_password,
        email=user_data.email,
        name=user_data.name,
        last_name=user_data.last_name,
        role_id=user_data.role_id,
        active=user_data.active
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def get_users(db: AsyncSession):
    """Получает список всех пользователей с их ролями."""
    result = await db.execute(
        select(models.Users).options(selectinload(models.Users.role))
    )
    return result.scalars().all()

async def delete_user(db: AsyncSession, user_id: int):
    """Удаляет пользователя по ID."""
    user_to_delete = await db.get(models.Users, user_id)
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    await db.delete(user_to_delete)
    await db.commit()
    return user_to_delete

async def get_sales_summary_for_user(db: AsyncSession, user_id: int):
    """Собирает сводку по продажам для пользователя за текущий день."""
    today_start = datetime.combine(date.today(), time.min)
    today_end = datetime.combine(date.today(), time.max)

    # Запрос на получение данных
    query = (
        select(
            func.count(models.Sales.id),
            func.sum(models.Sales.total_amount),
            func.sum(
                case(
                    (models.Sales.payment_method == models.EnumPayment.НАЛИЧНЫЕ, models.Sales.total_amount),
                    else_=0
                )
            )
        )
        .filter(models.Sales.user_id == user_id)
        .filter(models.Sales.sale_date >= today_start)
        .filter(models.Sales.sale_date <= today_end)
    )
    result = await db.execute(query)
    sales_count, total_revenue, cash_revenue = result.one()

    return {
        "sales_count": sales_count or 0,
        "total_revenue": total_revenue or 0,
        "cash_in_register": cash_revenue or 0
    }

async def get_recent_phones_in_stock(db: AsyncSession):
    """Получает 5 последних телефонов, добавленных на склад."""
    query = (
        select(models.Phones)
        # --- НАЧАЛО ИСПРАВЛЕНИЯ ---
        .options(
            selectinload(models.Phones.model).options(
                selectinload(models.Models.model_name),
                selectinload(models.Models.storage),
                selectinload(models.Models.color)
            ),
            selectinload(models.Phones.model_number)
        )
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
        .filter(models.Phones.commercial_status == models.CommerceStatus.НА_СКЛАДЕ)
        .order_by(models.Phones.id.desc())
        .limit(5)
    )
    result = await db.execute(query)
    return result.scalars().all()

async def get_grouped_phones_in_stock(db: AsyncSession):
    """
    Получает сгруппированный список моделей телефонов на складе,
    считая их количество.
    """
    # Шаг 1: Группируем телефоны по model_id и считаем количество
    group_query = (
        select(
            models.Phones.model_id,
            func.count(models.Phones.id).label("quantity")
        )
        # VVV ДОБАВЬТЕ ЭТОТ JOIN VVV
        .join(models.Warehouse, (models.Phones.id == models.Warehouse.product_id) & (models.Warehouse.product_type_id == 1))
        .where(
            models.Phones.commercial_status == models.CommerceStatus.НА_СКЛАДЕ,
            # VVV И ЭТОТ ФИЛЬТР VVV
            models.Warehouse.storage_location != models.EnumShop.ПОДМЕННЫЙ_ФОНД,
            models.Phones.model_id.is_not(None)
        )
        .group_by(models.Phones.model_id)
    )
    grouped_result = await db.execute(group_query)
    grouped_phones = grouped_result.all()

    if not grouped_phones:
        return []

    # Шаг 2: Извлекаем все model_id для следующего запроса
    model_ids = [item.model_id for item in grouped_phones]
    
    # Шаг 3: Получаем полную информацию для этих моделей
    models_query = (
        select(models.Models)
        .options(
            selectinload(models.Models.model_name),
            selectinload(models.Models.storage),
            selectinload(models.Models.color),
            selectinload(models.Models.retail_prices_phones)
        )
        .where(models.Models.id.in_(model_ids))
    )
    models_result = await db.execute(models_query)
    models_map = {m.id: m for m in models_result.scalars().all()}
    
    # Шаг 4: Собираем финальный результат
    final_result = []
    for model_id, quantity in grouped_phones:
        model_obj = models_map.get(model_id)
        if model_obj:
            final_result.append({"model": model_obj, "quantity": quantity})

    return final_result

async def get_phones_ready_for_packaging(db: AsyncSession):
    """Получает все телефоны со статусом 'НА_УПАКОВКЕ'."""
    query = (
        select(models.Phones)
        .options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color),
            selectinload(models.Phones.model_number),
            selectinload(models.Phones.supplier_order) # <--- ДОБАВЬТЕ ЭТУ СТРОКУ
        )
        .filter(models.Phones.technical_status == models.TechStatus.НА_УПАКОВКЕ)
    )
    result = await db.execute(query)
    return result.scalars().all()

async def package_phones(db: AsyncSession, phone_ids: List[int], user_id: int):
    """Меняет статус телефонов на 'УПАКОВАН' и создает лог."""
    # VVV НАЧНИТЕ ИЗМЕНЕНИЯ ЗДЕСЬ VVV
    result = await db.execute(
        select(models.Phones)
        .options(
            selectinload(models.Phones.model).options(
                selectinload(models.Models.model_name),
                selectinload(models.Models.storage),
                selectinload(models.Models.color)
            ),
            selectinload(models.Phones.model_number),
            selectinload(models.Phones.supplier_order) 
        )
        .filter(models.Phones.id.in_(phone_ids))
    )
    # ^^^ ЗАКОНЧИТЕ ИЗМЕНЕНИЯ ЗДЕСЬ ^^^
    phones_to_update = result.scalars().all()

    for phone in phones_to_update:
        phone.technical_status = models.TechStatus.УПАКОВАН
        log_entry = models.PhoneMovementLog(
            phone_id=phone.id,
            user_id=user_id,
            event_type=models.PhoneEventType.ИНСПЕКЦИЯ_ПРОЙДЕНА,
            details="Телефон упакован и готов к приемке на склад."
        )
        db.add(log_entry)

    await db.commit()
    for phone in phones_to_update:
        await db.refresh(phone, attribute_names=['model', 'model_number'])

    return phones_to_update

async def create_traffic_source(db: AsyncSession, source: schemas.TrafficSourceCreate):
    """Создает новый источник трафика."""
    # Проверка на дубликат
    existing_source = await db.execute(select(models.TrafficSource).filter_by(name=source.name))
    if existing_source.scalars().first():
        raise HTTPException(status_code=400, detail="Источник с таким названием уже существует.")
    
    db_source = models.TrafficSource(**source.model_dump())
    db.add(db_source)
    await db.commit()
    await db.refresh(db_source)
    return db_source

async def update_traffic_source(db: AsyncSession, source_id: int, source_data: schemas.TrafficSourceCreate):
    """Обновляет название источника трафика."""
    db_source = await db.get(models.TrafficSource, source_id)
    if not db_source:
        raise HTTPException(status_code=404, detail="Источник не найден.")
    
    db_source.name = source_data.name
    await db.commit()
    await db.refresh(db_source)
    return db_source

async def delete_traffic_source(db: AsyncSession, source_id: int):
    """Удаляет источник трафика."""
    db_source = await db.get(models.TrafficSource, source_id)
    if not db_source:
        raise HTTPException(status_code=404, detail="Источник не найден.")
    
    await db.delete(db_source)
    await db.commit()
    return db_source

async def get_sales_by_user_id(db: AsyncSession, user_id: int, start_date: Optional[date] = None, end_date: Optional[date] = None):
    """
    Получает все продажи для указанного ID пользователя за определенный период.
    Оптимизировано для избежания проблемы N+1.
    """
    query = (
        select(models.Sales)
        .options(
            selectinload(models.Sales.customer),
            selectinload(models.Sales.sale_details).selectinload(models.SaleDetails.warehouse)
        )
        .filter(models.Sales.user_id == user_id)
        .order_by(models.Sales.sale_date.desc())
    )

    if start_date:
        query = query.filter(models.Sales.sale_date >= start_date)
    if end_date:
        # Включаем end_date в диапазон
        end_date_inclusive = datetime.combine(end_date, time.max)
        query = query.filter(models.Sales.sale_date <= end_date_inclusive)

    result = await db.execute(query)
    return result.scalars().all()


# --- Функции для Заметок ---

async def get_notes(db: AsyncSession, show_all: bool = False):
    """Получает список заметок. По умолчанию только невыполненные."""
    query = (
        select(models.Notes)
        .options(
            selectinload(models.Notes.created_by),
            selectinload(models.Notes.completed_by)
        )
        .order_by(models.Notes.created_at.desc())
    )
    if not show_all:
        query = query.filter(models.Notes.is_completed == False)
        
    result = await db.execute(query)
    return result.scalars().all()

async def create_note(db: AsyncSession, note: schemas.NoteCreate, user_id: int):
    """Создает новую заметку."""
    db_note = models.Notes(**note.model_dump(), created_by_user_id=user_id)
    db.add(db_note)
    await db.commit()
    await db.refresh(db_note, attribute_names=['created_by'])
    return db_note

async def update_note_status(db: AsyncSession, note_id: int, completed: bool, user_id: int):
    """Обновляет статус выполнения заметки."""
    note = await db.get(models.Notes, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    
    note.is_completed = completed
    if completed:
        note.completed_at = datetime.now()
        note.completed_by_user_id = user_id
    else:
        # Если "раз-отмечаем", сбрасываем данные о выполнении
        note.completed_at = None
        note.completed_by_user_id = None
        
    await db.commit()
    await db.refresh(note, attribute_names=['created_by', 'completed_by'])
    return note


async def get_all_phones_in_stock_detailed(db: AsyncSession):
    """Получает детальный список всех телефонов со статусом 'НА_СКЛАДЕ' с их самым последним местоположением."""

    # 1. Создаем подзапрос, который нумерует записи о складе для каждого телефона,
    #    начиная с самой новой (row_num = 1).
    latest_warehouse_sq = (
        select(
            models.Warehouse,
            func.row_number()
            .over(
                partition_by=models.Warehouse.product_id,
                order_by=models.Warehouse.id.desc()
            )
            .label("row_num"),
        )
        .where(models.Warehouse.product_type_id == 1)
        .subquery()
    )

    # Создаем псевдоним для удобного обращения к полям подзапроса
    LatestWarehouse = aliased(models.Warehouse, latest_warehouse_sq)

    # 2. Основной запрос теперь присоединяется к подзапросу и берет только строки, где row_num = 1.
    query = (
        select(models.Phones, LatestWarehouse.storage_location)
        .join(
            latest_warehouse_sq,
            models.Phones.id == latest_warehouse_sq.c.product_id,
        )
        .where(latest_warehouse_sq.c.row_num == 1) # <--- Ключевое условие
        .options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color),
            selectinload(models.Phones.model_number),
            selectinload(models.Phones.supplier_order)
        )
        .filter(
            or_(
                models.Phones.commercial_status == models.CommerceStatus.НА_СКЛАДЕ,
                models.Phones.commercial_status == models.CommerceStatus.ПОДМЕННЫЙ_ФОНД
            )
        )
        .order_by(models.Phones.id.desc())
    )

    result = await db.execute(query)

    phones_with_location = []
    # Метод .unique() здесь больше не нужен, так как запрос сам по себе корректен
    for phone, location in result.all():
        phone.storage_location = location.value if location else None
        phones_with_location.append(phone)

    return phones_with_location

async def move_phone_location(db: AsyncSession, phone_id: int, new_location: models.EnumShop, user_id: int):
    """Перемещает телефон и обновляет его коммерческий статус в зависимости от местоположения."""
    phone = await db.get(models.Phones, phone_id)
    
    warehouse_entry_result = await db.execute(
        select(models.Warehouse)
        .filter_by(product_id=phone_id, product_type_id=1)
        .order_by(models.Warehouse.id.desc())
    )
    warehouse_entry = warehouse_entry_result.scalars().first()

    if not phone or not warehouse_entry:
        raise HTTPException(status_code=404, detail="Телефон или его запись на складе не найдены.")

    old_location = warehouse_entry.storage_location.value if warehouse_entry.storage_location else "неизвестно"
    warehouse_entry.storage_location = new_location
    
    if new_location == models.EnumShop.ПОДМЕННЫЙ_ФОНД:
        phone.commercial_status = models.CommerceStatus.ПОДМЕННЫЙ_ФОНД
    elif new_location in [models.EnumShop.СКЛАД, models.EnumShop.ВИТРИНА]:
        phone.commercial_status = models.CommerceStatus.НА_СКЛАДЕ

    log_entry = models.PhoneMovementLog(
        phone_id=phone_id, user_id=user_id,
        event_type=models.PhoneEventType.ПЕРЕМЕЩЕНИЕ,
        details=f"Перемещен с '{old_location}' на '{new_location.value}'."
    )
    db.add(log_entry)
    await db.commit()
    
    # Загружаем и возвращаем обновленные данные
    updated_phone = await get_phone_by_id_fully_loaded_with_location(db, phone_id)
    return updated_phone

async def get_available_for_loaner(db: AsyncSession):
    """Получает список телефонов, которые доступны для выдачи в подменный фонд."""
    query = (
        select(models.Phones)
        .options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color)
        )
        .filter(models.Phones.commercial_status == models.CommerceStatus.ПОДМЕННЫЙ_ФОНД)
        .order_by(models.Phones.id.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()

async def issue_loaner(db: AsyncSession, repair_id: int, loaner_phone_id: int, user_id: int):
    """Выдает подменный телефон и меняет его статус."""
    loaner_phone = await db.get(models.Phones, loaner_phone_id)
    
    if not loaner_phone or loaner_phone.commercial_status != models.CommerceStatus.ПОДМЕННЫЙ_ФОНД:
        raise HTTPException(status_code=400, detail="Этот телефон недоступен для выдачи.")

    loaner_phone.commercial_status = models.CommerceStatus.ВЫДАН_КАК_ПОДМЕННЫЙ

    new_log = models.LoanerLog(repair_id=repair_id, loaner_phone_id=loaner_phone_id, user_id=user_id)
    db.add(new_log)

    history_log = models.PhoneMovementLog(
        phone_id=loaner_phone_id, user_id=user_id,
        event_type=models.PhoneEventType.ВЫДАН_КАК_ПОДМЕННЫЙ,
        details=f"Выдан как подменный телефон по ремонту №{repair_id}"
    )
    db.add(history_log)
    await db.commit()
    return new_log

async def return_loaner(db: AsyncSession, loaner_log_id: int, user_id: int):
    """Принимает подменный телефон обратно на склад."""
    log_entry = await db.get(models.LoanerLog, loaner_log_id, options=[selectinload(models.LoanerLog.loaner_phone)])
    if not log_entry or not log_entry.loaner_phone:
        raise HTTPException(status_code=404, detail="Запись о выдаче не найдена.")

    # Обновляем запись о выдаче
    log_entry.date_returned = datetime.now()

    # Возвращаем телефон на склад для повторной проверки
    phone = log_entry.loaner_phone
    phone.commercial_status = models.CommerceStatus.НЕ_ГОТОВ_К_ПРОДАЖЕ
    phone.technical_status = models.TechStatus.ОЖИДАЕТ_ПРОВЕРКУ

    # Создаем запись в истории
    history_log = models.PhoneMovementLog(
        phone_id=phone.id,
        user_id=user_id,
        event_type=models.PhoneEventType.ПРИНЯТ_ИЗ_ПОДМЕНЫ, # Используем новое короткое название
        details=f"Возвращен из подменного фонда после ремонта №{log_entry.repair_id}. Отправлен на инспекцию."
    )
    db.add(history_log)
    await db.commit()
    return log_entry

async def get_phone_by_id_fully_loaded(db: AsyncSession, phone_id: int):
    """Безопасно загружает один телефон со всеми связанными данными для ответов API."""
    query = (
        select(models.Phones)
        .options(
            selectinload(models.Phones.model).options(
                selectinload(models.Models.model_name),
                selectinload(models.Models.storage),
                selectinload(models.Models.color)
            ),
            selectinload(models.Phones.model_number),
            selectinload(models.Phones.supplier_order)
        )
        .filter(models.Phones.id == phone_id)
    )
    result = await db.execute(query)
    phone = result.scalars().one_or_none()
    if not phone:
        raise HTTPException(status_code=404, detail="Телефон не найден")
    return phone

async def get_phone_by_id_fully_loaded_with_location(db: AsyncSession, phone_id: int):
    """Загружает один телефон со всеми связанными данными и последним местоположением."""
    query = (
        select(models.Phones, models.Warehouse.storage_location)
        .join(models.Warehouse, (models.Phones.id == models.Warehouse.product_id) & (models.Warehouse.product_type_id == 1))
        .options(
            selectinload(models.Phones.model).options(
                selectinload(models.Models.model_name),
                selectinload(models.Models.storage),
                selectinload(models.Models.color)
            ),
            selectinload(models.Phones.model_number),
            selectinload(models.Phones.supplier_order)  # <--- ДОБАВЛЕНА ЭТА СТРОКА
        )
        .filter(models.Phones.id == phone_id)
        .order_by(models.Warehouse.id.desc())
    )
    result = await db.execute(query)
    phone_with_location = result.first()

    if not phone_with_location:
        raise HTTPException(status_code=404, detail="Телефон не найден.")
    
    phone, location = phone_with_location
    phone.storage_location = location.value if location else None
    return phone

async def get_payroll_report(db: AsyncSession, start_date: date, end_date: date):
    """Собирает и рассчитывает данные для зарплатного отчета, включая выплаты."""
    
    users_result = await db.execute(
        select(models.Users).options(selectinload(models.Users.role))
        .join(models.Users.role)
        .filter(models.Roles.role_name.in_(['Продавец', 'Тех. специалист', 'Администратор']))
    )
    users = users_result.scalars().all()

    report = []
    end_date_inclusive = end_date + timedelta(days=1)

    for user in users:
        # --- РАСЧЕТ НАЧИСЛЕНИЙ (EARNED) ---
        earned_salary = Decimal(0)
        breakdown = {}
        
        # Расчет для техника
        inspections_count = (await db.execute(select(func.count(models.DeviceInspection.id)).filter(models.DeviceInspection.user_id == user.id, models.DeviceInspection.inspection_date >= start_date, models.DeviceInspection.inspection_date < end_date_inclusive))).scalar_one()
        battery_tests_count = (await db.execute(select(func.count(models.BatteryTest.id)).join(models.DeviceInspection).filter(models.DeviceInspection.user_id == user.id, models.DeviceInspection.inspection_date >= start_date, models.DeviceInspection.inspection_date < end_date_inclusive))).scalar_one()
        packaging_count = (await db.execute(select(func.count(models.PhoneMovementLog.id)).filter(models.PhoneMovementLog.user_id == user.id, models.PhoneMovementLog.details == "Телефон упакован и готов к приемке на склад.", models.PhoneMovementLog.timestamp >= start_date, models.PhoneMovementLog.timestamp < end_date_inclusive))).scalar_one()

        if inspections_count > 0 or battery_tests_count > 0 or packaging_count > 0:
            inspection_total = inspections_count * Decimal(150)
            battery_total = battery_tests_count * Decimal(50)
            packaging_total = packaging_count * Decimal(100)
            breakdown["inspections"] = {"count": inspections_count, "rate": Decimal(150), "total": inspection_total}
            breakdown["battery_tests"] = {"count": battery_tests_count, "rate": Decimal(50), "total": battery_total}
            breakdown["packaging"] = {"count": packaging_count, "rate": Decimal(100), "total": packaging_total}
            earned_salary += inspection_total + battery_total + packaging_total

        # Расчет для продавца
        shifts_count = (await db.execute(select(func.count(func.distinct(func.date(models.EmployeeShifts.shift_start)))).filter(models.EmployeeShifts.user_id == user.id, models.EmployeeShifts.shift_start >= start_date, models.EmployeeShifts.shift_start < end_date_inclusive))).scalar_one()
        phones_sold_count = (await db.execute(select(func.sum(models.SaleDetails.quantity)).join(models.Sales).join(models.Warehouse).filter(models.Sales.user_id == user.id, models.Warehouse.product_type_id == 1, models.Sales.sale_date >= start_date, models.Sales.sale_date < end_date_inclusive))).scalar_one() or 0
        
        if shifts_count > 0 or phones_sold_count > 0:
            shift_total = shifts_count * Decimal(2000)
            bonus_total = phones_sold_count * Decimal(500)
            breakdown["shifts"] = {"count": shifts_count, "rate": Decimal(2000), "total": shift_total}
            breakdown["phone_sales_bonus"] = {"count": phones_sold_count, "rate": Decimal(500), "total": bonus_total}
            earned_salary += shift_total + bonus_total

        # --- РАСЧЕТ ВЫПЛАТ (PAID) ---
        paid_amount_res = await db.execute(
            select(func.sum(models.Payroll.amount))
            .filter(models.Payroll.user_id == user.id)
            .filter(models.Payroll.payment_date >= start_date, models.Payroll.payment_date < end_date_inclusive)
        )
        paid_amount = paid_amount_res.scalar_one() or Decimal(0)

        # Собираем итоговый отчет, только если были начисления или выплаты
        if earned_salary > 0 or paid_amount > 0:
            report.append({
                "user_id": user.id,
                "username": user.username,
                "name": f"{user.name or ''} {user.last_name or ''}".strip(),
                "role": user.role.role_name,
                "breakdown": breakdown,
                "total_earned": earned_salary,
                "total_paid": paid_amount,
                "balance": earned_salary - paid_amount
            })
            
    return report

async def get_active_shift(db: AsyncSession, user_id: int) -> Optional[models.EmployeeShifts]:
    """Находит активную (незавершенную) смену для пользователя."""
    result = await db.execute(
        select(models.EmployeeShifts)
        .filter_by(user_id=user_id, shift_end=None)
        .order_by(models.EmployeeShifts.shift_start.desc())
    )
    return result.scalars().first()

async def start_shift(db: AsyncSession, user_id: int) -> models.EmployeeShifts:
    """Начинает новую смену для пользователя."""
    active_shift = await get_active_shift(db, user_id)
    if active_shift:
        raise HTTPException(status_code=400, detail="У вас уже есть активная смена. Сначала завершите ее.")
    
    new_shift = models.EmployeeShifts(user_id=user_id)
    db.add(new_shift)
    await db.commit()
    await db.refresh(new_shift)
    return new_shift

async def end_shift(db: AsyncSession, user_id: int) -> models.EmployeeShifts:
    """Завершает активную смену пользователя."""
    active_shift = await get_active_shift(db, user_id)
    if not active_shift:
        raise HTTPException(status_code=404, detail="Нет активной смены для завершения.")
        
    active_shift.shift_end = datetime.now()
    await db.commit()
    await db.refresh(active_shift)
    return active_shift

async def create_payroll_payment(db: AsyncSession, user_id: int, payment_data: schemas.PayrollPaymentCreate):
    """Создает запись о выплате ЗП и соответствующую транзакцию в движении денег."""
    
    # --- НАЧАЛО ИЗМЕНЕНИЙ ---
    # 1. По ID находим сотрудника, чтобы получить его имя/логин
    user = await db.get(models.Users, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"Сотрудник с ID {user_id} не найден.")
    
    # Выбираем, что отображать: полное имя или логин, если имя не заполнено
    user_display_name = f"{user.name or ''} {user.last_name or ''}".strip() or user.username
    # --- КОНЕЦ ИЗМЕНЕНИЙ ---

    # 2. Создаем запись о выплате (без изменений)
    new_payroll_entry = models.Payroll(
        user_id=user_id,
        amount=payment_data.amount,
        account_id=payment_data.account_id,
        notes=payment_data.notes
    )
    db.add(new_payroll_entry)

    # 3. Создаем расход в движении денег с новым описанием
    cash_flow_entry = models.CashFlow(
        date=datetime.now(),
        operation_categories_id=4, 
        account_id=payment_data.account_id,
        amount=-abs(payment_data.amount),
        # VVV ИЗМЕНЕНА СТРОКА ОПИСАНИЯ VVV
        description=f"Выплата ЗП сотруднику: {user_display_name}. {payment_data.notes or ''}".strip(),
        currency_id=1
    )
    db.add(cash_flow_entry)
    
    await db.commit()
    await db.refresh(new_payroll_entry)
    return new_payroll_entry

async def get_financial_snapshots(db: AsyncSession):
    """Получает все финансовые срезы, отсортированные по дате."""
    result = await db.execute(
        select(models.FinancialSnapshot).order_by(models.FinancialSnapshot.snapshot_date.desc())
    )
    return result.scalars().all()

async def create_financial_snapshot(db: AsyncSession):
    """Создает снимок финансового состояния компании, включая детализацию."""
    
    # 1. Считаем баланс наличных ПО СЧЕТАМ
    cash_by_account_res = await db.execute(
        select(
            models.Accounts.name,
            func.coalesce(func.sum(models.CashFlow.amount), 0).label("balance")
        )
        .join(models.CashFlow, models.Accounts.id == models.CashFlow.account_id, isouter=True)
        .group_by(models.Accounts.id)
    )
    cash_by_account_details = [
        {"account_name": row.name, "balance": float(row.balance)} 
        for row in cash_by_account_res.all()
    ]
    cash_balance = sum(item['balance'] for item in cash_by_account_details)


    # 2. Считаем стоимость склада и собираем детали (этот блок без изменений)
    inventory_phones_res = await db.execute(
        select(models.Phones.id, models.Phones.serial_number, models.Phones.purchase_price)
        .where(models.Phones.commercial_status.not_in([
            models.CommerceStatus.ПРОДАН,
            models.CommerceStatus.СПИСАН_ПОСТАВЩИКОМ,
            models.CommerceStatus.В_РЕМОНТЕ
        ]))
    )
    inventory_phones = inventory_phones_res.all()
    inventory_value = sum(p.purchase_price or 0 for p in inventory_phones)
    inventory_details = [{"id": p.id, "sn": p.serial_number, "price": float(p.purchase_price or 0)} for p in inventory_phones]

    # 3. Считаем стоимость товаров в пути и собираем детали (этот блок без изменений)
    goods_in_transit_res = await db.execute(
        select(models.SupplierOrders.id, models.SupplierOrderDetails.price, models.SupplierOrderDetails.quantity)
        .join(models.SupplierOrderDetails)
        .where(
            models.SupplierOrders.payment_status == models.OrderPaymentStatus.ОПЛАЧЕН,
            models.SupplierOrders.status != models.StatusDelivery.ПОЛУЧЕН
        )
    )
    goods_in_transit = goods_in_transit_res.all()
    goods_in_transit_value = sum(g.price * g.quantity for g in goods_in_transit)
    
    transit_details_grouped = {}
    for g in goods_in_transit:
        if g.id not in transit_details_grouped:
            transit_details_grouped[g.id] = 0
        transit_details_grouped[g.id] += float(g.price * g.quantity)
    transit_details = [{"order_id": order_id, "value": value} for order_id, value in transit_details_grouped.items()]

    # 4. Считаем общую стоимость активов
    total_assets = Decimal(cash_balance) + inventory_value + goods_in_transit_value

    # 5. Создаем и сохраняем срез с НОВОЙ детализацией
    new_snapshot = models.FinancialSnapshot(
        snapshot_date=datetime.now(),
        cash_balance=cash_balance,
        inventory_value=inventory_value,
        goods_in_transit_value=goods_in_transit_value,
        total_assets=total_assets,
        details={
            "inventory": inventory_details,
            "goods_in_transit": transit_details,
            "cash_by_account": cash_by_account_details  # <-- Добавляем новую информацию
        }
    )
    db.add(new_snapshot)
    await db.commit()
    await db.refresh(new_snapshot)
    
    return new_snapshot


async def get_accounts_with_balances(db: AsyncSession):
    """Получает список всех счетов с их текущими балансами."""
    query = (
        select(
            models.Accounts.id,
            models.Accounts.name,
            func.coalesce(func.sum(models.CashFlow.amount), 0).label("balance")
        )
        .outerjoin(models.CashFlow, models.Accounts.id == models.CashFlow.account_id)
        .group_by(models.Accounts.id, models.Accounts.name)
        .order_by(models.Accounts.id)
    )
    result = await db.execute(query)
    return result.mappings().all()

