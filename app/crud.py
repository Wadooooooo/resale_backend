# app/crud.py

from sqlalchemy.orm import Session
from sqlalchemy.future import select
from . import models
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy import func, select, case
from . import models, schemas
from datetime import date
from fastapi import HTTPException
from decimal import Decimal, InvalidOperation
from sqlalchemy import select, or_
from datetime import date, timedelta, datetime, time
from sqlalchemy import func
from typing import List
from . import security


# --- Функции для Инспекции ---

async def get_phones_for_inspection(db: AsyncSession):
    """Получает все телефоны со статусом 'ОЖИДАЕТ_ПРОВЕРКУ'."""
    query = (
        select(models.Phones)
        .options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color),
            selectinload(models.Phones.model_number)
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
            # Если да - сразу ставим статус "Упакован"
            phone.technical_status = models.TechStatus.УПАКОВАН
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
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color)
        ).filter(models.Phones.id == phone_id)
    )
    return final_phone_result.scalars().one()


async def add_battery_test_results(db: AsyncSession, inspection_id: int, battery_data: schemas.BatteryTestCreate, user_id: int):
    """Добавляет результаты теста аккумулятора к существующей проверке."""
    inspection_result = await db.execute(
        select(models.DeviceInspection).options(selectinload(models.DeviceInspection.phone))
        .filter(models.DeviceInspection.id == inspection_id)
    )
    inspection = inspection_result.scalars().one_or_none()

    if not inspection or not inspection.phone:
        raise HTTPException(status_code=404, detail="Инспекция или связанный телефон не найдены")

    # --- НАЧАЛО ИСПРАВЛЕНИЯ ---
    # Получаем ID телефона ДО коммита и сохраняем его в переменную
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

    inspection.phone.technical_status = models.TechStatus.УПАКОВАН

    log_entry = models.PhoneMovementLog(
        phone_id=inspection.phone.id,
        user_id=user_id,
        event_type=models.PhoneEventType.ИНСПЕКЦИЯ_ПРОЙДЕНА,
        details=f"Тест АКБ пройден. Расход: {f'{drain_rate:.2f}' if drain_rate else 'N/A'} %/час. Статус изменен на 'Упакован'."
    )
    db.add(log_entry)
    
    await db.commit()

    # Теперь мы запрашиваем телефон по уже сохраненному ID
    final_phone_result = await db.execute(
        select(models.Phones).options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color),
            selectinload(models.Phones.model_number)
        ).filter(models.Phones.id == phone_id_to_return) # <--- ИСПОЛЬЗУЕМ СОХРАНЕННЫЙ ID
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
            selectinload(models.DeviceInspection.phone).selectinload(models.Phones.model_number)
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
    """Получает все телефоны со статусом 'УПАКОВАН'."""
    query = (
        select(models.Phones)
        .options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color)
        )
        .filter(models.Phones.technical_status == models.TechStatus.УПАКОВАН)
        .filter(models.Phones.commercial_status == models.CommerceStatus.НЕ_ГОТОВ_К_ПРОДАЖЕ)
    )
    result = await db.execute(query)
    return result.scalars().all()

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


async def get_customers(db: AsyncSession):
    """Получает список всех клиентов."""
    result = await db.execute(select(models.Customers))
    return result.scalars().all()

async def get_products_for_sale(db: AsyncSession):
    """Получает единый список всех товаров со склада."""
    warehouse_items_result = await db.execute(
        select(models.Warehouse).filter(models.Warehouse.quantity > 0)
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
    """Создает новую продажу, обновляет остатки, учитывает скидку и рассчитывает прибыль."""

    # --- НАЧАЛО ИЗМЕНЕНИЙ ---
    # 1. Считаем сумму до скидки (субтотал)
    subtotal = sum(item.unit_price * item.quantity for item in sale_data.details)
    
    # 2. Вычисляем итоговую сумму с учетом скидки
    discount_amount = sale_data.discount or Decimal('0')
    total_amount = subtotal - discount_amount
    # --- КОНЕЦ ИЗМЕНЕНИЙ ---

    if not sale_data.account_id:
        raise HTTPException(status_code=400, detail="Не указан счет для проведения операции.")

    new_sale = models.Sales(
        sale_date=datetime.now(),
        customer_id=sale_data.customer_id,
        payment_method=models.EnumPayment(sale_data.payment_method),
        total_amount=total_amount, # <-- Используем новую итоговую сумму
        discount=discount_amount, # <-- Сохраняем скидку
        payment_status=models.StatusPay.ОПЛАЧЕН,
        user_id=user_id,
        notes=sale_data.notes,
        account_id=sale_data.account_id
    )
    db.add(new_sale)
    await db.flush()

    for detail in sale_data.details:
        # ... (весь остальной код внутри цикла for остается без изменений)
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
                    if customer:
                        customer_name = customer.name
                
                log_entry = models.PhoneMovementLog(
                    phone_id=phone.id,
                    user_id=user_id,
                    event_type=models.PhoneEventType.ПРОДАН,
                    details=f"Продажа №{new_sale.id} клиенту '{customer_name}'. Цена: {detail.unit_price} руб."
                )
                db.add(log_entry)
                
                purchase_price = phone.purchase_price or 0
                prep_and_seller_costs = 800
                profit_per_unit = detail.unit_price - purchase_price - prep_and_seller_costs
                item_profit = profit_per_unit * detail.quantity

        elif warehouse_item.product_type_id == 2: # Аксессуар
            accessory = await db.get(models.Accessories, warehouse_item.product_id)
            if accessory:
                purchase_price = accessory.purchase_price or 0
                item_profit = (detail.unit_price * detail.quantity) - (purchase_price * detail.quantity)

        sale_detail_entry = models.SaleDetails(
            sale_id=new_sale.id,
            warehouse_id=detail.warehouse_id,
            quantity=detail.quantity,
            unit_price=detail.unit_price,
            profit=item_profit
        )
        db.add(sale_detail_entry)

    cash_flow_entry = models.CashFlow(
        date=datetime.now(),
        operation_categories_id=2,
        account_id=sale_data.account_id,
        amount=total_amount, # <-- В движение денег идет итоговая сумма
        description=f"Поступление от продажи №{new_sale.id}",
        currency_id=1
    )
    db.add(cash_flow_entry)
    
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
            selectinload(models.Phones.model_number)
        )
        .filter(func.lower(models.Phones.serial_number) == func.lower(serial_number))
    )
    phone_result = await db.execute(phone_query)
    phone = phone_result.scalars().first()

    if not phone:
        raise HTTPException(status_code=404, detail="Телефон с таким серийным номером не найден")

    sale_info = None
    warehouse_info = None

    warehouse_entry_result = await db.execute(
            select(models.Warehouse)
            .options(
                selectinload(models.Warehouse.shop),
                selectinload(models.Warehouse.user))
            .filter_by(product_id=phone.id, product_type_id=1)
    )
    warehouse_entry = warehouse_entry_result.scalars().first()

    if warehouse_entry:
        warehouse_info = {
            "added_date": warehouse_entry.added_date,
            "shop_name": warehouse_entry.shop.name if warehouse_entry.shop else "Неизвестный магазин"
        }

        sale_detail_result = await db.execute(
            select(models.SaleDetails)
            .options(selectinload(models.SaleDetails.sale).selectinload(models.Sales.customer))
            .filter_by(warehouse_id=warehouse_entry.id)
        )
        sale_detail = sale_detail_result.scalars().first()
        if sale_detail and sale_detail.sale:
            sale = sale_detail.sale
            sale_info = {
                "sale_id": sale.id,
                "sale_date": sale.sale_date,
                "unit_price": sale_detail.unit_price,
                "customer_name": sale.customer.name if sale.customer else None,
                "customer_number": sale.customer.number if sale.customer else None,
            }

    return phone

async def get_defective_phones(db: AsyncSession):
    """Получает телефоны со статусом 'БРАК', которые еще не отправлены поставщику."""
    query = (
        select(models.Phones)
        .options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color),
            selectinload(models.Phones.model_number)  # <--- ДОБАВЬТЕ ЭТУ СТРОКУ
        )
        .filter(models.Phones.technical_status == models.TechStatus.БРАК)
        .filter(models.Phones.commercial_status != models.CommerceStatus.ОТПРАВЛЕН_ПОСТАВЩИКУ)
    )
    result = await db.execute(query)
    return result.scalars().all()

async def get_phones_sent_to_supplier(db: AsyncSession):
    """Получает телефоны, отправленные поставщику."""
    query = (
        select(models.Phones)
        .options(
            selectinload(models.Phones.model).selectinload(models.Models.model_name),
            selectinload(models.Phones.model).selectinload(models.Models.storage),
            selectinload(models.Phones.model).selectinload(models.Models.color),
            selectinload(models.Phones.model_number)  # <--- И ЭТУ СТРОКУ
        )
        .filter(models.Phones.commercial_status == models.CommerceStatus.ОТПРАВЛЕН_ПОСТАВЩИКУ)
    )
    result = await db.execute(query)
    return result.scalars().all()

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


async def start_warranty_repair(db: AsyncSession, phone_id: int, repair_data: schemas.WarrantyRepairCreate, user_id: int):
    """Начинает ремонт, создает лог, запись о ремонте и возвращает готовую Pydantic-схему."""
    phone = await db.get(models.Phones, phone_id)
    if not phone or phone.commercial_status != models.CommerceStatus.ПРОДАН:
        raise HTTPException(status_code=400, detail="Телефон не найден или не имеет статус 'ПРОДАН'")
    
    phone.commercial_status = models.CommerceStatus.ГАРАНТИЙНЫЙ_РЕМОНТ
    
    new_repair_record = models.WarrantyRepair(
        phone_id=phone_id,
        user_id=user_id,
        **repair_data.model_dump()
    )
    db.add(new_repair_record)
    
    log_entry = models.PhoneMovementLog(
        phone_id=phone.id,
        user_id=user_id,
        event_type=models.PhoneEventType.ОТПРАВЛЕН_В_РЕМОНТ,
        details=f"Принят от клиента на гарантийный ремонт. Проблема: {repair_data.problem_description}"
    )
    db.add(log_entry)
    
    await db.commit()

    # Запрашиваем телефон заново со всеми связями для ответа
    final_phone_result = await db.execute(
        select(models.Phones).options(
            selectinload(models.Phones.model).options(
                selectinload(models.Models.model_name),
                selectinload(models.Models.storage),
                selectinload(models.Models.color)
            ),
            selectinload(models.Phones.model_number)
        ).filter(models.Phones.id == phone_id)
    )
    updated_phone = final_phone_result.scalars().one()

    # Форматируем ответ прямо здесь
    model_detail = None
    if updated_phone.model:
        model_name_base = updated_phone.model.model_name.name if updated_phone.model.model_name else ""
        storage_display = models.format_storage_for_display(updated_phone.model.storage.storage) if updated_phone.model.storage else ""
        color_name = updated_phone.model.color.color_name if updated_phone.model.color else ""
        full_display_name = " ".join(part for part in [model_name_base, storage_display, color_name] if part)
        model_detail = schemas.ModelDetail(
            id=updated_phone.model.id,
            name=full_display_name,
            base_name=model_name_base,
            model_name_id=updated_phone.model.model_name_id,
            storage_id=updated_phone.model.storage_id,
            color_id=updated_phone.model.color_id
        )

    return schemas.Phone(
        id=updated_phone.id,
        serial_number=updated_phone.serial_number,
        technical_status=updated_phone.technical_status.value if updated_phone.technical_status else None,
        commercial_status=updated_phone.commercial_status.value if updated_phone.commercial_status else None,
        added_date=updated_phone.added_date,
        model=model_detail,
        model_number=updated_phone.model_number
    )

async def finish_warranty_repair(db: AsyncSession, phone_id: int, finish_data: schemas.WarrantyRepairFinish, user_id: int):
    """Завершает ремонт, обновляет запись и создает лог."""
    phone = await db.get(models.Phones, phone_id)
    if not phone or phone.commercial_status != models.CommerceStatus.ГАРАНТИЙНЫЙ_РЕМОНТ:
        raise HTTPException(status_code=400, detail="Телефон не находится в гарантийном ремонте")

    # Находим последнюю активную запись о ремонте для этого телефона
    repair_record_result = await db.execute(
        select(models.WarrantyRepair)
        .filter_by(phone_id=phone_id, date_returned=None)
        .order_by(models.WarrantyRepair.date_accepted.desc())
    )
    repair_record = repair_record_result.scalars().first()

    if repair_record:
        repair_record.date_returned = datetime.now()
        repair_record.work_performed = finish_data.work_performed

    phone.commercial_status = models.CommerceStatus.ПРОДАН
    
    log_entry = models.PhoneMovementLog(
        phone_id=phone.id,
        user_id=user_id,
        event_type=models.PhoneEventType.ПОЛУЧЕН_ИЗ_РЕМОНТА,
        details=f"Ремонт завершен. Проведенные работы: {finish_data.work_performed}"
    )
    db.add(log_entry)
    
    await db.commit()

    # Запрашиваем телефон заново со всеми связями для ответа
    final_phone_result = await db.execute(
        select(models.Phones).options(
            selectinload(models.Phones.model).options(
                selectinload(models.Models.model_name),
                selectinload(models.Models.storage),
                selectinload(models.Models.color)
            ),
            selectinload(models.Phones.model_number)
        ).filter(models.Phones.id == phone_id)
    )
    return final_phone_result.scalars().one()

async def get_replacement_options(db: AsyncSession, model_id: int):
    """Находит на складе телефоны той же модели для обмена."""
    query = (
        select(models.Phones)
        .filter(models.Phones.model_id == model_id)
        .filter(models.Phones.commercial_status == models.CommerceStatus.НА_СКЛАДЕ)
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
    original_phone = await db.get(models.Phones, original_phone_id)
    replacement_phone = await db.get(models.Phones, replacement_phone_id)

    if not original_phone or original_phone.commercial_status != models.CommerceStatus.ПРОДАН:
        raise HTTPException(status_code=400, detail="Исходный телефон не найден или не был продан.")
    if not replacement_phone or replacement_phone.commercial_status != models.CommerceStatus.НА_СКЛАДЕ:
        raise HTTPException(status_code=400, detail="Телефон для замены не найден на складе.")
    if original_phone.model_id != replacement_phone.model_id:
        raise HTTPException(status_code=400, detail="Телефоны должны быть одной модели.")

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

    final_phone_result = await db.execute(
            select(models.Phones).options(
                selectinload(models.Phones.model).selectinload(models.Models.model_name),
                selectinload(models.Phones.model).selectinload(models.Models.storage),
                selectinload(models.Phones.model).selectinload(models.Models.color)
            ).filter(models.Phones.id == original_phone_id)
        )
    return final_phone_result.scalars().one()


async def process_supplier_replacement(
    db: AsyncSession, 
    original_phone_id: int, 
    new_phone_data: schemas.SupplierReplacementCreate, 
    user_id: int
):
    """Обрабатывает замену устройства от поставщика."""
    
    # 1. Находим старый телефон
    original_phone = await db.get(models.Phones, original_phone_id)
    if not original_phone:
        raise HTTPException(status_code=404, detail="Оригинальный телефон для замены не найден.")
    if original_phone.commercial_status != models.CommerceStatus.ОТПРАВЛЕН_ПОСТАВЩИКУ:
        raise HTTPException(status_code=400, detail="Телефон не был отправлен поставщику.")

    # 2. Меняем статус старого телефона на "Списан"
    original_phone.commercial_status = models.CommerceStatus.СПИСАН_ПОСТАВЩИКОМ
    
    # 3. Создаем новый телефон
    new_phone = models.Phones(
        serial_number=new_phone_data.new_serial_number,
        model_id=new_phone_data.new_model_id,
        supplier_order_id=original_phone.supplier_order_id, # Копируем данные от старого
        purchase_price=original_phone.purchase_price,       # Копируем данные от старого
        technical_status=models.TechStatus.ОЖИДАЕТ_ПРОВЕРКУ,
        commercial_status=models.CommerceStatus.НЕ_ГОТОВ_К_ПРОДАЖЕ,
        added_date=datetime.now()
    )
    db.add(new_phone)
    await db.flush() # Получаем ID для нового телефона

    # 4. Создаем логи для обоих телефонов
    log_original = models.PhoneMovementLog(
        phone_id=original_phone.id,
        user_id=user_id,
        event_type=models.PhoneEventType.ОБМЕНЕН, # Используем статус "Обменян"
        details=f"Заменен поставщиком на новый телефон с S/N: {new_phone.serial_number}."
    )
    
    log_new = models.PhoneMovementLog(
        phone_id=new_phone.id,
        user_id=user_id,
        event_type=models.PhoneEventType.ПОСТУПЛЕНИЕ_ОТ_ПОСТАВЩИКА,
        details=f"Поступил от поставщика в качестве замены для старого телефона с S/N: {original_phone.serial_number}."
    )
    
    db.add_all([log_original, log_new])
    
    await db.commit()
    await db.refresh(new_phone)
    
    return new_phone

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

