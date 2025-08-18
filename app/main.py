# app/main.py 

from . import security

from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from datetime import timedelta, date, datetime, time
from typing import List, Optional
from pydantic import BaseModel
from decimal import Decimal
import secrets

from fastapi.responses import JSONResponse
from fastapi import Depends, FastAPI, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import select, update 
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .database import AsyncSessionLocal
from .models import format_enum_value_for_display
from aiogram import types
from .bot import bot, dp, TELEGRAM_BOT_TOKEN

# Удалить этот импорт, так как используется AsyncSession
# from sqlalchemy.orm import Session 
from pydantic import ValidationError
from . import crud, schemas, security, models
from .database import get_db
from fastapi.middleware.cors import CORSMiddleware
# Следующие импорты больше не нужны, если FastAPI не отдает статику
# from fastapi.staticfiles import StaticFiles
# from starlette.responses import HTMLResponse


app = FastAPI(title="resale shop API")

origins = [
    "http://localhost:5173",
    "http://localhost:5174" # Адрес вашего React-приложения
    # Можно добавить и другие адреса, если понадобится
]

async def close_overdue_shifts():
    """Находит все незавершенные смены и закрывает их в 23:59."""
    print("Планировщик: Запущена проверка незакрытых смен...")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Находим все смены, где shift_end еще не установлен
            stmt = select(models.EmployeeShifts).where(models.EmployeeShifts.shift_end == None)
            result = await session.execute(stmt)
            open_shifts = result.scalars().all()

            shifts_to_close = []
            for shift in open_shifts:
                # Определяем конец дня для каждой смены
                end_of_day = datetime.combine(shift.shift_start.date(), time(23, 59, 59))
                
                # Если текущее время уже прошло конец дня начала смены, закрываем ее
                if datetime.now() > end_of_day:
                    shift.shift_end = end_of_day
                    shifts_to_close.append(shift)
                    print(f"Планировщик: Смена ID {shift.id} будет закрыта временем {end_of_day}")

            if shifts_to_close:
                await session.commit()
                print(f"Планировщик: Успешно закрыто {len(shifts_to_close)} смен.")
            else:
                print("Планировщик: Незакрытых смен для завершения не найдено.")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Логируем детальную информацию об ошибке в ваш терминал
    print("="*50)
    print("!!! ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ПОЙМАЛ ОШИБКУ ВАЛИДАЦИИ 422 !!!")
    print(f"URL запроса: {request.url}")
    
    # exc.errors() - это самое важное, здесь Pydantic подробно описывает,
    # какое поле и почему не прошло валидацию.
    print(f"Детали ошибки: {exc.errors()}")
    print("="*50)
    
    # Возвращаем стандартный JSON-ответ клиенту
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )

# --- Эндпоинты для Инспекции ---



@app.get("/api/v1/model-numbers/search", response_model=List[schemas.ModelNumber], tags=["Inspections"], dependencies=[Depends(security.require_permission("perform_inspections"))])
async def search_for_model_numbers(
    q: str, # Параметр запроса, например /search?q=ABC
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    """Ищет номера моделей для автодополнения."""
    return await crud.search_model_numbers(db=db, query=q)


@app.get("/api/v1/phones/for-inspection", response_model=List[schemas.Phone], tags=["Inspections"])
async def read_phones_for_inspection(db: AsyncSession = Depends(get_db)):
    phones = await crud.get_phones_for_inspection(db=db)
    return [_format_phone_response(p) for p in phones]



@app.get("/api/v1/checklist-items", response_model=List[schemas.ChecklistItem], tags=["Inspections"], dependencies=[Depends(security.require_permission("perform_inspections"))])
async def read_checklist_items(
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    """Получает список всех пунктов чек-листа."""
    checklist_items = await crud.get_checklist_items(db=db)

    return await crud.get_checklist_items(db=db)

@app.post("/api/v1/phones/{phone_id}/initial-inspections", response_model=schemas.Phone, tags=["Inspections"], dependencies=[Depends(security.require_permission("perform_inspections"))])
async def create_initial_inspection_endpoint(
    phone_id: int,
    inspection_data: schemas.InspectionSubmission,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    updated_phone = await crud.create_initial_inspection(db=db, phone_id=phone_id, inspection_data=inspection_data, user_id=current_user.id)
    return _format_phone_response(updated_phone)


@app.put("/api/v1/inspections/{inspection_id}/battery-test", response_model=schemas.Phone, tags=["Inspections"], dependencies=[Depends(security.require_permission("perform_inspections"))])
async def add_battery_test_endpoint(
    inspection_id: int,
    battery_data: schemas.BatteryTestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    """Добавляет результаты теста аккумулятора к существующей инспекции."""
    updated_phone = await crud.add_battery_test_results(
        db=db, 
        inspection_id=inspection_id, 
        battery_data=battery_data, 
        user_id=current_user.id
    )

    # Используем __dict__ для получения всех атрибутов
    phone_dict = updated_phone.__dict__.copy()

    # Преобразуем Enum в строку
    if updated_phone.technical_status:
        phone_dict["technical_status"] = updated_phone.technical_status.value
    if updated_phone.commercial_status:
        phone_dict["commercial_status"] = updated_phone.commercial_status.value

    if updated_phone.model:
        model_name_base = updated_phone.model.model_name.name if updated_phone.model.model_name else ""
        storage_display = models.format_storage_for_display(updated_phone.model.storage.storage) if updated_phone.model.storage else ""
        color_name = updated_phone.model.color.color_name if updated_phone.model.color else ""
        full_display_name = " ".join(part for part in [model_name_base, storage_display, color_name] if part)
        
        phone_dict['model'] = schemas.ModelDetail(
            id=updated_phone.model.id,
            name=full_display_name,
            base_name=model_name_base,
            model_name_id=updated_phone.model.model_name_id,
            storage_id=updated_phone.model.storage_id,
            color_id=updated_phone.model.color_id
        )
        
    return schemas.Phone.model_validate(phone_dict, from_attributes=True)

@app.get("/api/v1/phones/ready-for-packaging", response_model=List[schemas.Phone], tags=["Inspections"])
async def read_phones_for_packaging(db: AsyncSession = Depends(get_db)):
    phones = await crud.get_phones_ready_for_packaging(db=db)
    return [_format_phone_response(p) for p in phones]

@app.post("/api/v1/phones/package", response_model=List[schemas.Phone], tags=["Inspections"])
async def package_phones_endpoint(
    phone_ids: List[int],
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    updated_phones = await crud.package_phones(db=db, phone_ids=phone_ids, user_id=current_user.id)
    return [_format_phone_response(p) for p in updated_phones]


# Эндпоинт для получения списка телефонов, ожидающих тест аккумулятора
@app.get("/api/v1/phones/for-battery-test", response_model=List[schemas.InspectionInfo], tags=["Inspections"])
async def read_phones_for_battery_test(db: AsyncSession = Depends(get_db)):
    inspections = await crud.get_phones_for_battery_test(db=db)
    
    response_list = []
    for inspection in inspections:
        if inspection.phone:
            formatted_phone = _format_phone_response(inspection.phone)
            inspection_info = schemas.InspectionInfo(
                id=inspection.id,
                phone=formatted_phone
            )
            response_list.append(inspection_info)
            
    return response_list

# --- Новые эндпоинты для получения списка моделей и аксессуаров по названию ---
@app.get("/api/v1/models_for_orders", response_model=List[schemas.ModelName], tags=["Models"])
async def read_models_for_orders(
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user),
):
    """Получает список моделей (для выпадающих списков в заказах)."""
    models_data = await crud.get_models_by_name(db=db)
    # Форматируем, чтобы вернуть только id и name, а не всю модель
    return [schemas.ModelName(id=m.id, name=m.model_name.name if m.model_name else None) for m in models_data]

@app.get("/api/v1/accessories_for_orders", response_model=List[schemas.Accessory], tags=["Accessories"])
async def read_accessories_for_orders(
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user),
):
    """Получает список аксессуаров (для выпадающих списков в заказах)."""
    accessories_data = await crud.get_accessories_by_name(db=db)
    return [schemas.Accessory.model_validate(a) for a in accessories_data]




app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _format_phone_response(phone: models.Phones) -> schemas.Phone:
    """Форматирует объект телефона из БД в Pydantic-схему для ответа API."""

    # --- ФИНАЛЬНОЕ ИСПРАВЛЕНИЕ ---
    # Проверяем, что связанные объекты существуют, прежде чем их использовать
    model_detail_schema = None
    if phone.model:
        model_name_base = phone.model.model_name.name if phone.model.model_name else ""
        storage_display = models.format_storage_for_display(phone.model.storage.storage) if phone.model.storage else ""
        color_name = phone.model.color.color_name if phone.model.color else ""
        full_display_name = " ".join(part for part in [model_name_base, storage_display, color_name] if part)

        model_detail_schema = schemas.ModelDetail(
            id=phone.model.id,
            name=full_display_name,
            base_name=model_name_base,
            model_name_id=phone.model.model_name_id,
            storage_id=phone.model.storage_id,
            color_id=phone.model.color_id,
            image_url=phone.model.image_url
        )

    model_number_schema = schemas.ModelNumber.from_orm(phone.model_number) if phone.model_number else None
    location = getattr(phone, 'storage_location', None)
    defect_reason = getattr(phone, 'defect_reason', None)

    return schemas.Phone(
        id=phone.id,
        serial_number=phone.serial_number,
        technical_status=phone.technical_status.value if phone.technical_status else None,
        commercial_status=phone.commercial_status.value if phone.commercial_status else None,
        model_id=phone.model_id,
        model_number_id=phone.model_number_id,
        supplier_order_id=phone.supplier_order_id,
        added_date=phone.added_date,
        model=model_detail_schema,
        model_number=model_number_schema,
        supplier_order=phone.supplier_order,
        storage_location=location,
        defect_reason=defect_reason
    )


async def _format_sale_response(sale: models.Sales, db: AsyncSession) -> schemas.SaleResponse:
    """Вспомогательная функция для форматирования ответа о продаже."""
    # Собираем ID телефонов и аксессуаров из деталей продажи
    phone_ids = [
        detail.warehouse.product_id for detail in sale.sale_details 
        if detail.warehouse and detail.warehouse.product_type_id == 1
    ]
    accessory_ids = [
        detail.warehouse.product_id for detail in sale.sale_details 
        if detail.warehouse and detail.warehouse.product_type_id == 2
    ]

    # Загружаем все нужные телефоны и аксессуары одним запросом для каждого типа
    phones_map = {}
    if phone_ids:
        phones_res = await db.execute(
            select(models.Phones).options(
                selectinload(models.Phones.model).options(
                    selectinload(models.Models.model_name),
                    selectinload(models.Models.storage),
                    selectinload(models.Models.color)
                ),
                selectinload(models.Phones.model_number)
            ).filter(models.Phones.id.in_(phone_ids))
        )
        phones_map = {p.id: p for p in phones_res.scalars().all()}

    accessories_map = {}
    if accessory_ids:
        accessories_res = await db.execute(select(models.Accessories).filter(models.Accessories.id.in_(accessory_ids)))
        accessories_map = {a.id: a for a in accessories_res.scalars().all()}

    # Собираем финальный ответ
    response_details = []
    for detail in sale.sale_details:
        product_name = "Неизвестный товар"
        serial_number, model_number = None, None

        if not detail.warehouse: continue

        if detail.warehouse.product_type_id == 1: # Телефон
            product_obj = phones_map.get(detail.warehouse.product_id)
            if product_obj:
                serial_number = product_obj.serial_number
                model_number = product_obj.model_number.name if product_obj.model_number else None
                if product_obj.model:
                    model_name_base = product_obj.model.model_name.name if product_obj.model.model_name else ""
                    storage_display = models.format_storage_for_display(product_obj.model.storage.storage) if product_obj.model.storage else ""
                    color_name = product_obj.model.color.color_name if product_obj.model.color else ""
                    product_name = " ".join(part for part in [model_name_base, storage_display, color_name] if part)

        elif detail.warehouse.product_type_id == 2: # Аксессуар
            product_obj = accessories_map.get(detail.warehouse.product_id)
            if product_obj:
                product_name = product_obj.name

        response_details.append(
            schemas.SaleDetailResponse(
                id=detail.id, product_name=product_name, serial_number=serial_number,
                model_number=model_number, quantity=detail.quantity, unit_price=detail.unit_price
            )
        )

    return schemas.SaleResponse(
        id=sale.id, sale_date=sale.sale_date, customer_id=sale.customer_id,
        total_amount=sale.total_amount, details=response_details
    )

# --- Эндпоинты для Движения Денег ---

@app.get("/api/v1/cashflow/categories", response_model=List[schemas.OperationCategory], tags=["Cash Flow"],
         dependencies=[Depends(security.require_permission("manage_cashflow"))])
async def read_operation_categories(db: AsyncSession = Depends(get_db), current_user: schemas.User = Depends(security.get_current_active_user)):
    return await crud.get_operation_categories(db=db)

@app.get("/api/v1/cashflow/counterparties", response_model=List[schemas.Counterparty], tags=["Cash Flow"],
         dependencies=[Depends(security.require_permission("manage_cashflow"))])
async def read_counterparties(db: AsyncSession = Depends(get_db), current_user: schemas.User = Depends(security.get_current_active_user)):
    return await crud.get_counterparties(db=db)

@app.get("/api/v1/cashflow/accounts", response_model=List[schemas.Account], tags=["Cash Flow"],
         dependencies=[Depends(security.require_any_permission("manage_cashflow", "perform_sales"))])
async def read_accounts(db: AsyncSession = Depends(get_db), current_user: schemas.User = Depends(security.get_current_active_user)):
    return await crud.get_accounts(db=db)

@app.get("/api/v1/sales/my-sales", response_model=List[schemas.SaleResponse], tags=["Sales"])
async def read_my_sales(
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
):
    """Возвращает список продаж, сделанных текущим пользователем за период (оптимизированная версия)."""
    # 1. Получаем все продажи одним запросом
    sales = await crud.get_sales_by_user_id(
        db=db, user_id=current_user.id, start_date=start_date, end_date=end_date
    )
    if not sales:
        return []

    # 2. Собираем ВСЕ уникальные ID товаров из ВСЕХ продаж
    all_phone_ids = set()
    all_accessory_ids = set()
    for sale in sales:
        for detail in sale.sale_details:
            if detail.warehouse:
                if detail.warehouse.product_type_id == 1:
                    all_phone_ids.add(detail.warehouse.product_id)
                elif detail.warehouse.product_type_id == 2:
                    all_accessory_ids.add(detail.warehouse.product_id)

    # 3. Загружаем все нужные телефоны и аксессуары ОДНИМ запросом для каждого типа
    phones_map = {}
    if all_phone_ids:
        phones_res = await db.execute(
            select(models.Phones).options(
                selectinload(models.Phones.model).options(
                    selectinload(models.Models.model_name),
                    selectinload(models.Models.storage),
                    selectinload(models.Models.color)
                ),
                selectinload(models.Phones.model_number)
            ).filter(models.Phones.id.in_(all_phone_ids))
        )
        phones_map = {p.id: p for p in phones_res.scalars().all()}
    
    accessories_map = {}
    if all_accessory_ids:
        accessories_res = await db.execute(select(models.Accessories).filter(models.Accessories.id.in_(all_accessory_ids)))
        accessories_map = {a.id: a for a in accessories_res.scalars().all()}

    # 4. Теперь собираем финальный ответ, используя уже загруженные данные (без новых запросов к БД)
    final_response = []
    for sale in sales:
        response_details = []
        for detail in sale.sale_details:
            product_name = "Неизвестный товар"
            serial_number, model_number = None, None
            
            if not detail.warehouse: continue

            if detail.warehouse.product_type_id == 1: # Телефон
                product_obj = phones_map.get(detail.warehouse.product_id)
                if product_obj:
                    serial_number = product_obj.serial_number
                    model_number = product_obj.model_number.name if product_obj.model_number else None
                    if product_obj.model:
                        model_name_base = product_obj.model.model_name.name if product_obj.model.model_name else ""
                        storage_display = models.format_storage_for_display(product_obj.model.storage.storage) if product_obj.model.storage else ""
                        color_name = product_obj.model.color.color_name if product_obj.model.color else ""
                        product_name = " ".join(part for part in [model_name_base, storage_display, color_name] if part)
            
            elif detail.warehouse.product_type_id == 2: # Аксессуар
                product_obj = accessories_map.get(detail.warehouse.product_id)
                if product_obj:
                    product_name = product_obj.name

            response_details.append(
                schemas.SaleDetailResponse(
                    id=detail.id, product_name=product_name, serial_number=serial_number,
                    model_number=model_number, quantity=detail.quantity, unit_price=detail.unit_price
                )
            )
        
        final_response.append(schemas.SaleResponse(
            id=sale.id, sale_date=sale.sale_date, customer_id=sale.customer_id,
            total_amount=sale.total_amount, details=response_details
        ))

    return final_response



@app.post("/api/v1/cashflow", 
          response_model=schemas.CashFlow, 
          tags=["Cash Flow"],
          dependencies=[Depends(security.require_permission("manage_cashflow"))])
async def create_new_cash_flow(
    cash_flow_data: schemas.CashFlowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    return await crud.create_cash_flow(db=db, cash_flow=cash_flow_data, user_id=current_user.id)

@app.get("/api/v1/cashflow", 
         response_model=List[schemas.CashFlow], 
         tags=["Cash Flow"],
         dependencies=[Depends(security.require_permission("manage_cashflow"))])
async def read_cash_flows(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    return await crud.get_cash_flows(db=db, skip=skip, limit=limit)

@app.post("/api/v1/cashflow/accounts", response_model=schemas.Account, tags=["Cash Flow"],
          dependencies=[Depends(security.require_permission("manage_cashflow"))])
async def create_new_account(
    account_data: schemas.AccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    return await crud.create_account(db=db, account=account_data)

@app.post("/api/v1/cashflow/counterparties", response_model=schemas.Counterparty, tags=["Cash Flow"],
          dependencies=[Depends(security.require_permission("manage_cashflow"))])
async def create_new_counterparty(
    counterparty_data: schemas.CounterpartyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    return await crud.create_counterparty(db=db, counterparty=counterparty_data)

@app.get("/api/v1/cashflow/total-balance", response_model=schemas.TotalBalance, tags=["Cash Flow"],
        dependencies=[Depends(security.require_permission("manage_cashflow"))])
async def read_total_balance(
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    """Возвращает общий баланс компании (сумму на всех счетах)."""
    total = await crud.get_total_balance(db=db)
    return schemas.TotalBalance(total_balance=total)

# --- Эндпоинты для Вкладов ---

@app.post("/api/v1/deposits", response_model=schemas.Deposit, tags=["Deposits"],
          dependencies=[Depends(security.require_permission("manage_cashflow"))])
async def add_new_deposit(
    deposit_data: schemas.DepositCreate,
    db: AsyncSession = Depends(get_db)
):
    """Добавляет новый вклад (обязательство)."""
    return await crud.create_deposit(db=db, deposit_data=deposit_data)

@app.get("/api/v1/deposits/details", response_model=List[schemas.DepositDetails], tags=["Deposits"],
         dependencies=[Depends(security.require_permission("manage_cashflow"))])
async def read_deposits_details(
    target_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db)
):
    """Получает детали по всем вкладам на указанную дату (или на сегодня)."""
    if target_date is None:
        target_date = date.today()
    return await crud.get_all_deposits_details(db=db, target_date=target_date)

@app.post("/api/v1/deposits/pay", response_model=schemas.DepositPayment, tags=["Deposits"],
          dependencies=[Depends(security.require_permission("manage_cashflow"))])
async def pay_for_deposit(
    payment_data: schemas.DepositPaymentCreate,
    db: AsyncSession = Depends(get_db)
):
    """Проводит оплату по вкладу."""
    return await crud.create_deposit_payment(db=db, payment_data=payment_data)


@app.get("/api/v1/accounts/balances", 
         response_model=List[schemas.AccountWithBalance], 
         tags=["Cash Flow"],
         dependencies=[Depends(security.require_any_permission("manage_cashflow", "perform_sales"))])
async def read_accounts_with_balances(db: AsyncSession = Depends(get_db)):
    """Получает список всех счетов с их текущими балансами."""
    return await crud.get_accounts_with_balances(db=db)

@app.get("/api/v1/roles", response_model=List[schemas.RoleInfo], tags=["Users"], dependencies=[Depends(security.require_permission("manage_users"))])
async def read_roles(db: AsyncSession = Depends(get_db)):
    """Получает список всех ролей для формы регистрации."""
    return await crud.get_roles(db=db)

@app.post("/api/v1/users/register-employee", response_model=schemas.User, tags=["Users"], dependencies=[Depends(security.require_permission("manage_users"))])
async def register_new_employee(
    employee_data: schemas.EmployeeCreate,
    db: AsyncSession = Depends(get_db)
):
    """Регистрирует нового сотрудника. Доступно только пользователям с правом 'manage_users'."""
    new_user = await crud.create_user(db=db, user_data=employee_data)
    
    # Чтобы ответ соответствовал схеме schemas.User, нужно подгрузить роль с правами
    await db.refresh(new_user, attribute_names=['role'])
    
    user_data_response = {
        "id": new_user.id, "username": new_user.username, "email": new_user.email,
        "name": new_user.name, "last_name": new_user.last_name, "active": new_user.active,
        "role": None
    }
    if new_user.role:
        # Загружаем роль со всеми правами, чтобы вернуть полный объект
        role_with_permissions_result = await db.execute(
            select(models.Roles).options(
                selectinload(models.Roles.role_permissions).selectinload(models.RolePermissions.permission)
            ).filter(models.Roles.id == new_user.role.id)
        )
        role_with_permissions = role_with_permissions_result.scalars().one()
        permissions_list = [rp.permission for rp in role_with_permissions.role_permissions if rp.permission]
        user_data_response["role"] = {"role_name": new_user.role.role_name, "permissions": permissions_list}

    return schemas.User.model_validate(user_data_response)

@app.get("/api/v1/users", response_model=List[schemas.User], tags=["Users"], dependencies=[Depends(security.require_permission("manage_users"))])
async def read_users(db: AsyncSession = Depends(get_db)):
    """Получает список всех сотрудников."""
    users = await crud.get_users(db=db)
    # Форматируем ответ, чтобы он соответствовал схеме, включая роль
    response_list = []
    for user in users:
        user_data = {
            "id": user.id, "username": user.username, "email": user.email,
            "name": user.name, "last_name": user.last_name, "active": user.active,
            "role": None
        }
        if user.role:
            # Для простого списка права не нужны, отдаем только название роли
            user_data["role"] = {"role_name": user.role.role_name, "permissions": []}
        response_list.append(schemas.User.model_validate(user_data))
    return response_list

@app.delete("/api/v1/users/{user_id}", response_model=schemas.User, tags=["Users"], dependencies=[Depends(security.require_permission("manage_users"))])
async def remove_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Удаляет сотрудника по ID."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Вы не можете удалить свою собственную учетную запись.")
    
    deleted_user = await crud.delete_user(db=db, user_id=user_id)
    # Форматируем ответ для удаленного пользователя
    user_data = {
        "id": deleted_user.id, "username": deleted_user.username, "email": deleted_user.email,
        "name": deleted_user.name, "last_name": deleted_user.last_name, "active": deleted_user.active,
        "role": None
    }
    if deleted_user.role:
         user_data["role"] = {"role_name": deleted_user.role.role_name, "permissions": []}
    return schemas.User.model_validate(user_data)

@app.post("/api/v1/auth/token", response_model=schemas.Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: AsyncSession = Depends(get_db)
):
    user = await crud.get_user_by_username(db, username=form_data.username)
    if not user or not security.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/v1/users/me/", response_model=schemas.User)
async def read_users_me(current_user: models.Users = Depends(security.get_current_active_user)):
    user_data = {
        "id": current_user.id, "username": current_user.username, "email": current_user.email,
        "name": current_user.name, "last_name": current_user.last_name, "active": current_user.active,
        "role": None
    }
    if current_user.role:
        permissions_list = [rp.permission for rp in current_user.role.role_permissions if rp.permission]
        user_data["role"] = {"role_name": current_user.role.role_name, "permissions": permissions_list}
    return user_data

@app.get("/api/v1/users/me/telegram-link-token", response_model=schemas.Token, tags=["Users"])
async def get_telegram_link_token(
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Генерирует одноразовый токен для привязки Telegram аккаунта."""
    token = secrets.token_hex(16)
    # В реальном приложении токен нужно сохранять в базу или кэш с временем жизни
    # Для простоты, мы будем использовать ID пользователя
    link_code = f"{current_user.id}-{token}"
    return {"access_token": link_code, "token_type": "link"}


@app.get("/api/v1/all_models_full_info", response_model=List[schemas.ModelDetail], tags=["Models"])
async def read_all_models_full_info(
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user),
):
    """
    Получает список всех моделей с полной информацией (название, память, цвет) для выбора в заказах.
    """
    models_data = await crud.get_all_models_full_info(db=db)
    
    formatted_models = []
    for m in models_data:
        # Проверяем наличие model_name объекта, его id и name
        if not m.model_name or m.model_name.id is None or not m.model_name.name:
            continue
        
        # ADD NEW: Получаем данные и форматируем полное название ВРУЧНУЮ
        model_id = m.id # ID самой модели
        model_name_base_id = m.model_name.id # ID базового имени
        model_name_base_name = m.model_name.name # Базовое имя
        
        storage_id = m.storage.id if m.storage and m.storage.id is not None else None
        storage_value = m.storage.storage if m.storage and m.storage.storage is not None else None
        
        color_id = m.color.id if m.color and m.color.id is not None else None
        color_name = m.color.color_name if m.color and m.color.color_name else None

        # Форматирование storage (используя функцию из models.py)
        formatted_storage_display = models.format_storage_for_display(storage_value)
        
        # Формируем полное отображаемое название (ОНО СТАНЕТ name В ModelDetail)
        full_model_display_name_parts = [model_name_base_name]
        if formatted_storage_display:
            full_model_display_name_parts.append(formatted_storage_display)
        if color_name:
            full_model_display_name_parts.append(color_name)
        
        full_model_display_name = " ".join(full_model_display_name_parts).strip()

        # <--- ИСПРАВЛЕНО: ЯВНО СОЗДАЕМ ModelDetail, передавая name и все вложенные объекты ---
        formatted_models.append(schemas.ModelDetail(
        id=model_id,
        name=full_model_display_name,
        base_name=model_name_base_name,
        model_name_id=model_name_base_id,
        storage_id=storage_id,
        color_id=color_id
    ))
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
    return formatted_models

# --- НОВЫЙ ЭНДПОИНТ: Получение уникальных базовых названий моделей ---
@app.get("/api/v1/unique_model_names", response_model=List[schemas.ModelName], tags=["Models"])
async def read_unique_model_names(
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user),
):
    """Получает список уникальных базовых названий моделей для выпадающего списка 'Базовая модель'."""
    unique_names = await crud.get_unique_model_names(db=db)
    # Возвращаем ModelName объекты, которые уже содержат id и name базовой модели
    return [schemas.ModelName.model_validate(n) for n in unique_names]


# --- Новые эндпоинты для получения всех опций памяти ---
@app.get("/api/v1/storage_options", response_model=List[schemas.Storage], tags=["Options"])
async def read_storage_options(
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user),
):
    """Получает список всех доступных опций памяти."""
    storage_data = await crud.get_all_storage_options(db=db)
    return [schemas.Storage.model_validate(s) for s in storage_data]

# --- Новые эндпоинты для получения всех опций цвета ---
@app.get("/api/v1/color_options", response_model=List[schemas.Color], tags=["Options"])
async def read_color_options(
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user),
):
    """Получает список всех доступных опций цвета."""
    color_data = await crud.get_all_color_options(db=db)
    return [schemas.Color.model_validate(c) for c in color_data]


# --- Новый эндпоинт для получения ВСЕХ аксессуаров ---
@app.get("/api/v1/all_accessories_info", response_model=List[schemas.Accessory], tags=["Accessories"])
async def read_all_accessories_info(
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user),
):
    """Получает список всех аксессуаров для выбора в заказах."""
    accessories_data = await crud.get_all_accessories_info(db=db)
    return [schemas.Accessory.model_validate(a) for a in accessories_data]

@app.get("/api/v1/accessories/in-stock", response_model=List[schemas.AccessoryInStock], tags=["Accessories"], dependencies=[Depends(security.require_permission("manage_inventory"))])
async def read_accessories_in_stock(db: AsyncSession = Depends(get_db)):
    """Получает список аксессуаров, которые есть на складе."""
    results = await crud.get_accessories_in_stock(db=db)

    response_list = []
    for acc, quantity in results:
        latest_price = None
        if acc.retail_price_accessories:
            latest_price_entry = sorted(acc.retail_price_accessories, key=lambda p: p.date, reverse=True)[0]
            latest_price = latest_price_entry.price

        acc_in_stock = schemas.AccessoryInStock(
            id=acc.id,
            name=acc.name,
            barcode=acc.barcode,
            category_accessory=acc.category_accessory,
            purchase_price=acc.purchase_price,
            current_price=latest_price,
            quantity=quantity
        )
        response_list.append(acc_in_stock)
    return response_list


# --- Эндпоинт для получения списка телефонов ---

# MODIFY: Обновляем read_phones, чтобы он тоже явно формировал ModelDetail
@app.get("/api/v1/phones", response_model=List[schemas.Phone], tags=["Phones"])
async def read_phones(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user),
):
    """
    Получает список всех телефонов.
    Доступно только для авторизованных пользователей.
    """
    phones = await crud.get_phones(db=db, skip=skip, limit=limit)
    
    formatted_phones_for_response = []
    for phone in phones:
        phone_dict = phone.__dict__.copy() 
        
        if phone.technical_status:
            phone_dict["technical_status"] = models.format_enum_value_for_display(phone.technical_status.value)
        else:
            phone_dict["technical_status"] = None

        if phone.commercial_status:
            phone_dict["commercial_status"] = models.format_enum_value_for_display(phone.commercial_status.value)
        else:
            phone_dict["commercial_status"] = None

        if phone.model: # Убедимся, что phone.model существует
            model_obj = phone.model
            
            model_id = model_obj.id
            model_name_base_id = model_obj.model_name.id if model_obj.model_name else None
            model_name_base_name = model_obj.model_name.name if model_obj.model_name and model_obj.model_name.name else "Без названия"
            
            storage_id = model_obj.storage.id if model_obj.storage and model_obj.storage.id is not None else None
            storage_value = model_obj.storage.storage if model_obj.storage and model_obj.storage.storage is not None else None
            
            color_id = model_obj.color.id if model_obj.color and model_obj.color.id is not None else None
            color_name = model_obj.color.color_name if model_obj.color and model_obj.color.color_name else None

            formatted_storage_display = models.format_storage_for_display(storage_value)
            
            full_model_display_name_parts = [model_name_base_name]
            if formatted_storage_display:
                full_model_display_name_parts.append(formatted_storage_display)
            if color_name:
                full_model_display_name_parts.append(color_name)
            
            full_model_display_name = " ".join(full_model_display_name_parts).strip()

            phone_dict['model'] = schemas.ModelDetail(
                id=model_id, 
                name=full_model_display_name, 
                base_name=model_name_base_name, # <--- ИСПРАВЛЕНО: Присваиваем базовое название
                model_name_id=model_name_base_id, 
                storage_id=storage_id, 
                color_id=color_id
            )
        else:
            phone_dict['model'] = None 

        if 'added_date' not in phone_dict and hasattr(phone, 'added_date'):
             phone_dict['added_date'] = phone.added_date

        formatted_phones_for_response.append(schemas.Phone.model_validate(phone_dict))
    
    return formatted_phones_for_response



@app.get(
    "/api/v1/phones/history/{serial_number}",
    response_model=schemas.PhoneHistoryResponse,
    tags=["Phones"],
    dependencies=[Depends(security.require_any_permission("manage_inventory", "perform_sales"))]
)
async def get_phone_history(
    serial_number: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Получает историю телефона. Доступно только менеджерам и продавцам."""

    phone = await crud.get_phone_history_by_serial(db=db, serial_number=serial_number)

    if not phone:
        raise HTTPException(status_code=404, detail="Телефон не найден")

    # --- НАЧАЛО БЛОКА ИЗМЕНЕНИЙ ---

    # 1. Загружаем и форматируем информацию о ремонтах и подменных устройствах
    repairs_list = []
    for repair in phone.repairs:
        active_loaner_info = None
        # Ищем активную (невозвращенную) запись о выдаче для этого ремонта
        active_loaner_log = next((log for log in repair.loaner_logs if not log.date_returned), None)

        if active_loaner_log and active_loaner_log.loaner_phone:
            loaner = active_loaner_log.loaner_phone
            
            # --- НАЧАЛО НОВОЙ ЛОГИКИ СБОРКИ СТРОКИ ---
            model_name_base = ""
            storage_display = ""
            color_name = ""
            
            if loaner.model:
                model_name_base = loaner.model.model_name.name if loaner.model.model_name else ""
                storage_display = models.format_storage_for_display(loaner.model.storage.storage) if loaner.model.storage else ""
                color_name = loaner.model.color.color_name if loaner.model.color else ""
            
            full_name = " ".join(part for part in [model_name_base, storage_display, color_name] if part)
            
            loaner_details_str = f"ID: {loaner.id}, {full_name} (S/N: {loaner.serial_number or 'б/н'})"
            # --- КОНЕЦ НОВОЙ ЛОГИКИ ---

            active_loaner_info = schemas.ActiveLoanerLog(
                id=active_loaner_log.id,
                date_issued=active_loaner_log.date_issued,
                loaner_phone_details=loaner_details_str
            )

        # Явно указываем все поля, чтобы избежать конфликта
        repairs_list.append(schemas.Repair(
            id=repair.id,
            phone_id=repair.phone_id,
            user_id=repair.user_id,
            repair_type=repair.repair_type.value, # Форматируем Enum в строку
            estimated_cost=repair.estimated_cost,
            final_cost=repair.final_cost,
            payment_status=repair.payment_status.value if repair.payment_status else None, # Форматируем Enum в строку
            date_accepted=repair.date_accepted,
            customer_name=repair.customer_name,
            customer_phone=repair.customer_phone,
            problem_description=repair.problem_description,
            device_condition=repair.device_condition,
            included_items=repair.included_items,
            notes=repair.notes,
            date_returned=repair.date_returned,
            work_performed=repair.work_performed,
            active_loaner=active_loaner_info # Добавляем вычисленное значение
        ))



    # --- КОНЕЦ БЛОКА ИЗМЕНЕНИЙ ---

    is_manager = security.user_has_permission(current_user, "manage_inventory")
    is_salesperson = security.user_has_permission(current_user, "perform_sales")

    logs_to_display = phone.movement_logs
    purchase_info = None
    inspections_list = []

    if phone.supplier_order:
        purchase_info = schemas.PhoneHistoryPurchase(
            supplier_order_id=phone.supplier_order.id,
            order_date=phone.supplier_order.order_date,
            purchase_price=phone.purchase_price,
            supplier_name=phone.supplier_order.supplier.name if phone.supplier_order.supplier else "Неизвестно"
        )

    for insp in phone.device_inspections:
        # ... (остальная часть функции остается без изменений)
        inspection_details = schemas.PhoneHistoryInspection(
            inspection_date=insp.inspection_date,
            inspected_by=insp.user.name if insp.user else "Неизвестно",
            results=[ schemas.PhoneHistoryInspectionResult(item_name=res.checklist_item.name, result=res.result, notes=res.notes) for res in insp.inspection_results ],
            battery_tests=[ schemas.PhoneHistoryBatteryTest(start_time=bt.start_time, end_time=bt.end_time, start_battery_level=bt.start_battery_level, end_battery_level=bt.end_battery_level, battery_drain=bt.battery_drain) for bt in insp.battery_tests ]
        )
        inspections_list.append(inspection_details)

    warehouse_info = None
    sale_info = None
    warehouse_entry_result = await db.execute(select(models.Warehouse).options(selectinload(models.Warehouse.shop), selectinload(models.Warehouse.user)).filter_by(product_id=phone.id, product_type_id=1))
    warehouse_entry = warehouse_entry_result.scalars().first()
    if warehouse_entry:
        warehouse_info = schemas.PhoneHistoryWarehouse(added_date=warehouse_entry.added_date, shop_name=warehouse_entry.shop.name if warehouse_entry.shop else "Неизвестно", accepted_by=warehouse_entry.user.name if warehouse_entry.user else "Неизвестно")
        sale_detail_result = await db.execute(select(models.SaleDetails).options(selectinload(models.SaleDetails.sale).selectinload(models.Sales.customer)).filter_by(warehouse_id=warehouse_entry.id))
        sale_detail = sale_detail_result.scalars().first()
        if sale_detail and sale_detail.sale:
            sale = sale_detail.sale
            sale_info = schemas.PhoneHistorySale(sale_id=sale.id, sale_date=sale.sale_date, unit_price=sale_detail.unit_price, customer_name=sale.customer.name if sale.customer else None, customer_number=sale.customer.number if sale.customer else None)

    if is_salesperson and not is_manager:
        salesperson_visible_events = { models.PhoneEventType.ПРИНЯТ_НА_СКЛАД, models.PhoneEventType.ПРОДАН, models.PhoneEventType.ВОЗВРАТ_ОТ_КЛИЕНТА, models.PhoneEventType.ОТПРАВЛЕН_В_РЕМОНТ, models.PhoneEventType.ПОЛУЧЕН_ИЗ_РЕМОНТА, models.PhoneEventType.ОБМЕНЕН, models.PhoneEventType.ПЕРЕМЕЩЕНИЕ, }
        logs_to_display = [ log for log in phone.movement_logs if log.event_type in salesperson_visible_events ]
        purchase_info = None
        inspections_list = []

    model_detail = None
    if phone.model:
        model_name_base = phone.model.model_name.name if phone.model.model_name else ""
        storage_display = models.format_storage_for_display(phone.model.storage.storage) if phone.model.storage else ""
        color_name = phone.model.color.color_name if phone.model.color else ""
        full_display_name = " ".join(part for part in [model_name_base, storage_display, color_name] if part)
        model_detail = schemas.ModelDetail(id=phone.model.id, name=full_display_name, base_name=model_name_base, model_name_id=phone.model.model_name_id, storage_id=phone.model.storage_id, color_id=phone.model.color_id, image_url=phone.model.image_url)

    return schemas.PhoneHistoryResponse(
        id=phone.id, serial_number=phone.serial_number,
        technical_status=phone.technical_status.value if phone.technical_status else None,
        commercial_status=phone.commercial_status.value if phone.commercial_status else None,
        added_date=phone.added_date, model=model_detail, model_number=phone.model_number,
        movement_logs=[ schemas.PhoneMovementLog(id=log.id, timestamp=log.timestamp, event_type=log.event_type.value.replace('_', ' ').capitalize(), details=log.details, user=log.user) for log in logs_to_display ],
        purchase_info=purchase_info, inspections=inspections_list,
        warehouse_info=warehouse_info, sale_info=sale_info,
        repairs=repairs_list # <--- ДОБАВЛЕНО: Передаем отформатированный список ремонтов
    )

# --- Эндпоинты для Поставщиков ---

@app.post("/api/v1/suppliers", response_model=schemas.Supplier, tags=["Suppliers"])
async def create_new_supplier(
    supplier: schemas.SupplierCreate,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user),
):
    """
    Создает нового поставщика в базе данных.
    """
    return await crud.create_supplier(db=db, supplier=supplier)


@app.get("/api/v1/suppliers", response_model=List[schemas.Supplier], tags=["Suppliers"])
async def read_suppliers(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user),
):
    """
    Получает список всех поставщиков.
    """
    suppliers = await crud.get_suppliers(db=db, skip=skip, limit=limit)
    return suppliers

@app.delete("/api/v1/suppliers/{supplier_id}", response_model=schemas.Supplier, tags=["Suppliers"])
async def remove_supplier(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user),
):
    """
    Удаляет поставщика по ID.
    """
    db_supplier = await crud.delete_supplier(db=db, supplier_id=supplier_id)
    if db_supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return db_supplier

@app.put("/api/v1/suppliers/{supplier_id}", response_model=schemas.Supplier, tags=["Suppliers"])
async def edit_supplier(
    supplier_id: int,
    supplier: schemas.SupplierCreate,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user),
):
    """
    Редактирует данные поставщика по ID.
    """
    updated_supplier = await crud.update_supplier(db=db, supplier_id=supplier_id, supplier=supplier)
    if updated_supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return updated_supplier

# --- Эндпоинты для Заказов у Поставщиков ---

# app/main.py

# app/main.py

@app.post("/api/v1/supplier-orders", response_model=schemas.SupplierOrder, tags=["Supplier Orders"], dependencies=[Depends(security.require_permission("manage_inventory"))])
async def create_new_supplier_order(
    order: schemas.SupplierOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user),
):
    """
    Создает новый заказ у поставщика и возвращает его в полностью отформатированном виде.
    """
    # 1. Создаем объект заказа в базе данных
    db_order = models.SupplierOrders(
        supplier_id=order.supplier_id,
        order_date=datetime.now(),
        status=models.StatusDelivery.ЗАКАЗ,
        payment_status=models.OrderPaymentStatus.НЕ_ОПЛАЧЕН, # <-- Убедитесь, что это установлено
        supplier_order_details=[
            models.SupplierOrderDetails(**detail.model_dump())
            for detail in order.details
        ]
    )
    db.add(db_order)
    await db.commit()
    await db.refresh(db_order)

    new_order_id = db_order.id

    result = await db.execute(
        select(models.SupplierOrders).options(
            joinedload(models.SupplierOrders.supplier_order_details).options(
                joinedload(models.SupplierOrderDetails.model).options(
                    selectinload(models.Models.model_name),
                    selectinload(models.Models.storage),
                    selectinload(models.Models.color)
                ),
                joinedload(models.SupplierOrderDetails.accessory)
            )
        ).filter(models.SupplierOrders.id == new_order_id)
    )
    full_new_order = result.unique().scalars().one_or_none()

    if not full_new_order:
        raise HTTPException(status_code=404, detail="Только что созданный заказ не найден")

    formatted_status_delivery = models.format_enum_value_for_display(full_new_order.status.value) if full_new_order.status else None
    formatted_payment_status = models.format_enum_value_for_display(full_new_order.payment_status.value) if full_new_order.payment_status else None

    formatted_details = []
    for detail in full_new_order.supplier_order_details:
        detail_dict = {
            "id": detail.id, "supplier_order_id": detail.supplier_order_id,
            "model_id": detail.model_id, "accessory_id": detail.accessory_id,
            "quantity": detail.quantity, "price": detail.price,
            "model_name": None, "accessory_name": None
        }
        if detail.model:
            model_name = detail.model.model_name.name if detail.model.model_name else "Модель"
            storage_info = models.format_storage_for_display(detail.model.storage.storage) if detail.model.storage and detail.model.storage.storage is not None else ""
            color_info = detail.model.color.color_name if detail.model.color and detail.model.color.color_name else ""
            full_name_parts = [part for part in [model_name, storage_info, color_info] if part]
            detail_dict['model_name'] = " ".join(full_name_parts)
        if detail.accessory:
            detail_dict['accessory_name'] = detail.accessory.name
        validated_detail = schemas.SupplierOrderDetail.model_validate(detail_dict)
        formatted_details.append(validated_detail)

    return schemas.SupplierOrder(
        id=full_new_order.id,
        supplier_id=full_new_order.supplier_id,
        order_date=full_new_order.order_date,
        status=formatted_status_delivery,
        payment_status=formatted_payment_status, # <-- ВКЛЮЧАЕМ НОВЫЙ СТАТУС ОПЛАТЫ
        details=formatted_details
    )


@app.get("/api/v1/supplier-orders", response_model=List[schemas.SupplierOrder], tags=["Supplier Orders"], dependencies=[Depends(security.require_any_permission("manage_inventory", "receive_supplier_orders"))])
async def read_supplier_orders(
    skip: int = 0,
    limit: int = 100000,
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user),
):
    # Эта проверка теперь контролирует всю финансовую информацию
    can_view_financial_info = security.user_has_permission(current_user, "view_purchase_prices")
    
    is_limited_role = not security.user_has_permission(current_user, "manage_inventory")
    
    orders = await crud.get_supplier_orders(db=db, skip=skip, limit=limit, apply_role_limit=is_limited_role)

    formatted_orders = []
    for order in orders:
        formatted_status_delivery = order.status.value.replace('_', ' ').capitalize() if order.status else None
        
        # Скрываем статус оплаты, если нет прав
        formatted_payment_status = "—" # По умолчанию ставим прочерк
        if can_view_financial_info and order.payment_status:
            formatted_payment_status = order.payment_status.value.replace('_', ' ').capitalize()

        formatted_details = []
        for detail in order.supplier_order_details:
            detail_dict = {
                "id": detail.id, "supplier_order_id": detail.supplier_order_id,
                "model_id": detail.model_id, "accessory_id": detail.accessory_id,
                "quantity": detail.quantity, "price": detail.price,
                "model_name": None, "accessory_name": None
            }
            
            # Цена уже скрывается этой логикой
            if not can_view_financial_info:
                detail_dict['price'] = 0.0

            if detail.model:
                model_name = detail.model.model_name.name if detail.model.model_name else "Неизвестно"
                storage_info = models.format_storage_for_display(detail.model.storage.storage) if detail.model.storage and detail.model.storage.storage is not None else "Неизвестно"
                color_info = detail.model.color.color_name if detail.model.color else "Неизвестно"
                detail_dict['model_name'] = f"{model_name} {storage_info} {color_info}".strip()

            if detail.accessory:
                detail_dict['accessory_name'] = detail.accessory.name
                
            formatted_details.append(schemas.SupplierOrderDetail.model_validate(detail_dict)) 

        formatted_orders.append(
            schemas.SupplierOrder(
                id=order.id,
                supplier_id=order.supplier_id,
                order_date=order.order_date,
                status=formatted_status_delivery,
                payment_status=formatted_payment_status,
                details=formatted_details
            )
        )
    return formatted_orders


@app.put("/api/v1/supplier-orders/{order_id}/receive", response_model=schemas.SupplierOrder, tags=["Supplier Orders"], dependencies=[Depends(security.require_any_permission("manage_inventory", "receive_supplier_orders"))])
async def receive_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user),
):
    """
    Отметить заказ как "Получен" и добавить все телефоны из него на склад.
    """
    updated_order = await crud.receive_supplier_order(db=db, order_id=order_id, user_id=current_user.id)    

    result = await db.execute(
        select(models.SupplierOrders).options(
            joinedload(models.SupplierOrders.supplier_order_details).options(
                selectinload(models.SupplierOrderDetails.model).options(
                    selectinload(models.Models.model_name),
                    selectinload(models.Models.storage),
                    selectinload(models.Models.color)
                ),
                joinedload(models.SupplierOrderDetails.accessory)
            )
        ).filter(models.SupplierOrders.id == updated_order.id)
    )
    full_updated_order = result.unique().scalars().one()

    formatted_status = models.format_enum_value_for_display(full_updated_order.status.value) if full_updated_order.status else None

    # --- ДОБАВЛЕНА ЭТА СТРОКА ---
    formatted_payment_status = models.format_enum_value_for_display(full_updated_order.payment_status.value) if full_updated_order.payment_status else None

    formatted_details = []
    for detail in full_updated_order.supplier_order_details:
        detail_dict = {
            "id": detail.id, "supplier_order_id": detail.supplier_order_id,
            "model_id": detail.model_id, "accessory_id": detail.accessory_id,
            "quantity": detail.quantity, "price": detail.price,
            "model_name": None, "accessory_name": None
        }
        if detail.model:
            model_name = detail.model.model_name.name if detail.model.model_name else "Модель"
            storage_info = models.format_storage_for_display(detail.model.storage.storage) if detail.model.storage and detail.model.storage.storage is not None else ""
            color_info = detail.model.color.color_name if detail.model.color and detail.model.color.color_name else ""
            full_name_parts = [part for part in [model_name, storage_info, color_info] if part]
            detail_dict['model_name'] = " ".join(full_name_parts)
        if detail.accessory:
            detail_dict['accessory_name'] = detail.accessory.name

        validated_detail = schemas.SupplierOrderDetail.model_validate(detail_dict)
        formatted_details.append(validated_detail)

    return schemas.SupplierOrder(
        id=full_updated_order.id,
        supplier_id=full_updated_order.supplier_id,
        order_date=full_updated_order.order_date,
        status=formatted_status,
        # --- И ДОБАВЛЕНА ЭТА СТРОКА ---
        payment_status=formatted_payment_status,
        details=formatted_details
    )


@app.get("/api/v1/shops", response_model=List[schemas.Shop], tags=["Warehouse"], dependencies=[Depends(security.require_any_permission("manage_inventory", "perform_sales"))])
async def read_shops(db: AsyncSession = Depends(get_db), current_user: schemas.User = Depends(security.get_current_active_user)):
    return await crud.get_shops(db=db)

@app.get("/api/v1/phones/ready-for-stock", response_model=List[schemas.Phone], tags=["Warehouse"], dependencies=[Depends(security.require_any_permission("manage_inventory", "perform_sales"))])
async def read_phones_ready_for_stock(
    db: AsyncSession = Depends(get_db), 
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    phones = await crud.get_phones_ready_for_stock(db=db)
    
    # --- НАЧАЛО БЛОКА ФОРМАТИРОВАНИЯ ---
    formatted_phones = []
    for phone in phones:
        phone_dict = {
            "id": phone.id,
            "serial_number": phone.serial_number,
            "technical_status": phone.technical_status.value if phone.technical_status else None,
            "commercial_status": phone.commercial_status.value if phone.commercial_status else None,
            "added_date": phone.added_date,
            "model": None
        }

        if phone.model:
            model_name_base = phone.model.model_name.name if phone.model.model_name else ""
            storage_display = models.format_storage_for_display(phone.model.storage.storage) if phone.model.storage else ""
            color_name = phone.model.color.color_name if phone.model.color else ""

            full_name_parts = [part for part in [model_name_base, storage_display, color_name] if part]
            full_display_name = " ".join(full_name_parts)

            phone_dict['model'] = schemas.ModelDetail(
                id=phone.model.id,
                name=full_display_name,
                base_name=model_name_base,
                model_name_id=phone.model.model_name_id,
                storage_id=phone.model.storage_id,
                color_id=phone.model.color_id
            )
        
        formatted_phones.append(schemas.Phone.model_validate(phone_dict))
    
    return formatted_phones

@app.post("/api/v1/warehouse/accept-phones", response_model=List[schemas.Phone], tags=["Warehouse"], dependencies=[Depends(security.require_any_permission("manage_inventory", "perform_sales"))])
async def accept_phones_to_warehouse_endpoint(
    data: schemas.WarehouseAcceptanceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    updated_phones = await crud.accept_phones_to_warehouse(db=db, data=data, user_id=current_user.id)

    # --- НАЧАЛО БЛОКА ФОРМАТИРОВАНИЯ ---
    formatted_phones = []
    for phone in updated_phones:
        phone_dict = {
            "id": phone.id,
            "serial_number": phone.serial_number,
            "technical_status": phone.technical_status.value if phone.technical_status else None,
            "commercial_status": phone.commercial_status.value if phone.commercial_status else None,
            "added_date": phone.added_date,
            "model": None
        }

        if phone.model:
            model_name_base = phone.model.model_name.name if phone.model.model_name else ""
            storage_display = models.format_storage_for_display(phone.model.storage.storage) if phone.model.storage else ""
            color_name = phone.model.color.color_name if phone.model.color else ""

            full_name_parts = [part for part in [model_name_base, storage_display, color_name] if part]
            full_display_name = " ".join(full_name_parts)

            phone_dict['model'] = schemas.ModelDetail(
                id=phone.model.id,
                name=full_display_name,
                base_name=model_name_base,
                model_name_id=phone.model.model_name_id,
                storage_id=phone.model.storage_id,
                color_id=phone.model.color_id
            )
        
        formatted_phones.append(schemas.Phone.model_validate(phone_dict))
    
    return formatted_phones

@app.get("/api/v1/accessory-categories", response_model=List[schemas.CategoryAccessory], tags=["Accessories"], dependencies=[Depends(security.require_permission("manage_inventory"))])
async def read_accessory_categories(db: AsyncSession = Depends(get_db), current_user: schemas.User = Depends(security.get_current_active_user)):
    """Получает список всех категорий аксессуаров."""
    return await crud.get_accessory_categories(db=db)

@app.post("/api/v1/accessories", response_model=schemas.Accessory, tags=["Accessories"], dependencies=[Depends(security.require_permission("manage_inventory"))])
async def create_new_accessory(
    accessory: schemas.AccessoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    """Создает новый аксессуар."""
    return await crud.create_accessory(db=db, accessory=accessory)


@app.get("/api/v1/accessories", response_model=List[schemas.AccessoryDetail], tags=["Accessories"])
async def read_all_accessories(
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    """Получает полный список аксессуаров с категориями и актуальными ценами."""
    accessories_data = await crud.get_all_accessories(db=db)
    
    response_list = []
    for acc in accessories_data:
        # --- START OF FIX ---
        latest_price = None
        if acc.retail_price_accessories:
            latest_price_entry = sorted(acc.retail_price_accessories, key=lambda p: p.date, reverse=True)[0]
            latest_price = latest_price_entry.price

        # Create the response object using all fields from the schema
        acc_detail = schemas.AccessoryDetail(
            id=acc.id,
            name=acc.name,
            barcode=acc.barcode,
            category_accessory=acc.category_accessory,
            current_price=latest_price # This field is now correctly populated
        )
        response_list.append(acc_detail)
        # --- END OF FIX ---
        
    return response_list

@app.post("/api/v1/customers", response_model=schemas.Customer, tags=["Sales"])
async def create_new_customer(
    customer_data: schemas.CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Создает нового покупателя."""
    return await crud.create_customer(db=db, customer=customer_data)

@app.get("/api/v1/traffic-sources", response_model=List[schemas.TrafficSource], tags=["Sales"])
async def read_traffic_sources(db: AsyncSession = Depends(get_db)):
    return await crud.get_traffic_sources(db=db)

@app.post("/api/v1/traffic-sources", response_model=schemas.TrafficSource, tags=["Sales"],
          dependencies=[Depends(security.require_permission("manage_users"))])
async def create_new_traffic_source(
    source_data: schemas.TrafficSourceCreate,
    db: AsyncSession = Depends(get_db)
):
    return await crud.create_traffic_source(db=db, source=source_data)

@app.delete("/api/v1/traffic-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Sales"],
            dependencies=[Depends(security.require_permission("manage_users"))])
async def update_existing_traffic_source(
    source_id: int,
    source_data: schemas.TrafficSourceCreate,
    db: AsyncSession = Depends(get_db)
):
    return await crud.update_traffic_source(db=db, source_id=source_id, source_data=source_data)

@app.delete("/api/v1/traffic-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Sales"])
async def delete_existing_traffic_source(
    source_id: int,
    db: AsyncSession = Depends(get_db)
):
    await crud.delete_traffic_source(db=db, source_id=source_id)
    return

@app.get("/api/v1/customers", response_model=List[schemas.Customer], tags=["Sales"])
async def read_customers(db: AsyncSession = Depends(get_db)):
    customers = await crud.get_customers(db=db)
    # Форматируем ответ, чтобы включить имя того, кто привел клиента
    return [
        schemas.Customer(
            id=c.id,
            name=c.name,
            number=c.number,
            source=c.source,
            referrer_name=c.referrer.name if c.referrer else None
        ) for c in customers
    ]

@app.get("/api/v1/products-for-sale", response_model=List[schemas.ProductForSale], tags=["Sales"],
         dependencies=[Depends(security.require_permission("perform_sales"))])
async def read_products_for_sale(db: AsyncSession = Depends(get_db), current_user: schemas.User = Depends(security.get_current_active_user)):
    warehouse_items = await crud.get_products_for_sale(db=db)
    

    products_for_sale = []
    for item in warehouse_items:
        
        # В предыдущем исправлении мы добавили атрибут 'product' в crud.py
        if not hasattr(item, 'product') or not item.product:
            
            continue

        product_obj = item.product
        name = ""
        price = None
        serial_number = None
        product_type = "Неизвестно"

        if isinstance(product_obj, models.Phones):
            product_type = "Телефон"
            serial_number = product_obj.serial_number
            if product_obj.model:
                model_name_base = product_obj.model.model_name.name if product_obj.model.model_name else ""
                storage_display = models.format_storage_for_display(product_obj.model.storage.storage) if product_obj.model.storage else ""
                color_name = product_obj.model.color.color_name if product_obj.model.color else ""
                full_name_parts = [part for part in [model_name_base, storage_display, color_name] if part]
                name = " ".join(full_name_parts)
                if product_obj.model.retail_prices_phones:
                    latest_price_entry = sorted(product_obj.model.retail_prices_phones, key=lambda p: p.date, reverse=True)[0]
                    price = latest_price_entry.price
        
        elif isinstance(product_obj, models.Accessories):
            product_type = "Аксессуар"
            name = product_obj.name
            if product_obj.retail_price_accessories:
                latest_price_entry = sorted(product_obj.retail_price_accessories, key=lambda p: p.date, reverse=True)[0]
                price = latest_price_entry.price
        
        

        products_for_sale.append(
            schemas.ProductForSale(
                warehouse_id=item.id,
                product_id=product_obj.id,
                product_type=product_type,
                name=name,
                price=price,
                serial_number=serial_number,
                quantity=item.quantity
            )
        )
    
    
    return products_for_sale

@app.post("/api/v1/sales", response_model=schemas.SaleResponse, tags=["Sales"],
          dependencies=[Depends(security.require_permission("perform_sales"))])
async def create_new_sale(
    sale_data: schemas.SaleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    """Создает новую продажу и возвращает полную информацию для чека."""
    
    # 1. Вызываем CRUD-функцию, которая создает все записи в базе данных
    created_sale = await crud.create_sale(db=db, sale_data=sale_data, user_id=current_user.id)

    # 2. Запрашиваем созданную продажу со связями, чтобы получить ID товаров
    fresh_sale_result = await db.execute(
        select(models.Sales)
        .options(
            selectinload(models.Sales.sale_details).selectinload(models.SaleDetails.warehouse)
        )
        .filter(models.Sales.id == created_sale.id)
    )
    fresh_sale = fresh_sale_result.scalars().one_or_none()

    if not fresh_sale:
        raise HTTPException(status_code=404, detail="Не удалось найти созданную продажу.")

    # 3. Собираем ID телефонов и аксессуаров из деталей продажи
    phone_ids = []
    accessory_ids = []
    for detail in fresh_sale.sale_details:
        if detail.warehouse.product_type_id == 1:
            phone_ids.append(detail.warehouse.product_id)
        elif detail.warehouse.product_type_id == 2:
            accessory_ids.append(detail.warehouse.product_id)

    # 4. Загружаем все нужные телефоны и аксессуары ОДНИМ запросом для каждого типа
    phones_map = {}
    if phone_ids:
        phones_res = await db.execute(
            select(models.Phones).options(
                selectinload(models.Phones.model).options(
                    selectinload(models.Models.model_name),
                    selectinload(models.Models.storage),
                    selectinload(models.Models.color)
                ),
                selectinload(models.Phones.model_number)
            ).filter(models.Phones.id.in_(phone_ids))
        )
        phones_map = {p.id: p for p in phones_res.scalars().all()}
    
    accessories_map = {}
    if accessory_ids:
        accessories_res = await db.execute(select(models.Accessories).filter(models.Accessories.id.in_(accessory_ids)))
        accessories_map = {a.id: a for a in accessories_res.scalars().all()}

    # 5. Теперь собираем финальный ответ, используя загруженные данные
    response_details = []
    for detail in fresh_sale.sale_details:
        product_name = "Неизвестный товар"
        serial_number, model_number = None, None
        
        warehouse = detail.warehouse
        if warehouse.product_type_id == 1: # Телефон
            product_obj = phones_map.get(warehouse.product_id)
            if product_obj:
                serial_number = product_obj.serial_number
                model_number = product_obj.model_number.name if product_obj.model_number else None
                if product_obj.model:
                    model_name_base = product_obj.model.model_name.name if product_obj.model.model_name else ""
                    storage_display = models.format_storage_for_display(product_obj.model.storage.storage) if product_obj.model.storage else ""
                    color_name = product_obj.model.color.color_name if product_obj.model.color else ""
                    product_name = " ".join(part for part in [model_name_base, storage_display, color_name] if part)
        
        elif warehouse.product_type_id == 2: # Аксессуар
            product_obj = accessories_map.get(warehouse.product_id)
            if product_obj:
                product_name = product_obj.name

        response_details.append(
            schemas.SaleDetailResponse(
                id=detail.id,
                product_name=product_name,
                serial_number=serial_number,
                model_number=model_number,
                quantity=detail.quantity,
                unit_price=detail.unit_price
            )
        )

    return schemas.SaleResponse(
        id=fresh_sale.id,
        sale_date=fresh_sale.sale_date,
        customer_id=fresh_sale.customer_id,
        total_amount=fresh_sale.total_amount,
        discount=fresh_sale.discount,
        details=response_details
    )

@app.get("/api/v1/sales/pending", response_model=List[schemas.SaleResponse], tags=["Sales"],
         dependencies=[Depends(security.require_permission("perform_sales"))])
async def get_pending_sales_endpoint(db: AsyncSession = Depends(get_db)):
    """Получает список продаж, ожидающих оплаты."""
    sales = await crud.get_pending_sales(db=db)
    # Используем готовую функцию для форматирования ответа
    return [await _format_sale_response(sale, db) for sale in sales]

@app.post("/api/v1/sales/{sale_id}/finalize-payment", response_model=schemas.SaleResponse, tags=["Sales"],
          dependencies=[Depends(security.require_permission("perform_sales"))])
async def finalize_payment_endpoint(
    sale_id: int,
    request: schemas.FinalizePaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Завершает продажу с отложенным платежом."""
    

    # 1. crud-функция готовит все изменения, но НЕ КОММИТИТ их, 
    #    а возвращает объект sale со всеми предзагруженными данными.
    sale_to_finalize = await crud.finalize_sale(
        db, sale_id, request.account_id, current_user.id
    )
    
    # 2. Форматируем ответ, пока сессия открыта. 
    #    На этом шаге SQLAlchemy может безопасно дозагружать любые данные, если потребуется.
    response = await _format_sale_response(sale_to_finalize, db)

    # 3. И только теперь, когда вся работа сделана, коммитим транзакцию.
    await db.commit()
    
    # 4. Возвращаем готовый ответ.
    return response


@app.post("/api/v1/accessories/{accessory_id}/prices", response_model=schemas.RetailPriceResponse, tags=["Pricing"]
          ,dependencies=[Depends(security.require_permission("manage_pricing"))])
async def create_price_for_accessory(
    accessory_id: int,
    price_data: schemas.PriceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    return await crud.add_price_for_accessory(db=db, accessory_id=accessory_id, price_data=price_data)


@app.get("/api/v1/model-storage-combos", response_model=List[schemas.ModelStorageCombo], tags=["Pricing"],
         dependencies=[Depends(security.require_permission("manage_pricing"))])
async def read_model_storage_combos(
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    """Возвращает уникальные комбинации 'модель + память' для установки цен."""
    return await crud.get_unique_model_storage_combos(db=db)

@app.post("/api/v1/prices/phone-combo", response_model=List[schemas.RetailPriceResponse], tags=["Pricing"],
          dependencies=[Depends(security.require_permission("manage_pricing"))])
async def create_price_for_combo(
    price_data: schemas.PriceSetForCombo,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    """Устанавливает цену для всех цветовых вариаций одной модели."""
    return await crud.add_price_for_model_storage_combo(db=db, data=price_data)

@app.post("/api/v1/supplier-orders/{order_id}/pay", 
          response_model=schemas.SupplierOrder, 
          tags=["Supplier Orders"],
          dependencies=[Depends(security.require_permission("manage_inventory"))])
async def pay_for_supplier_order_endpoint(
    order_id: int,
    payment_data: schemas.SupplierPaymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user),
):
    """
    Регистрирует оплату за заказ поставщику и создает запись в движении денег.
    Возвращает обновленный объект заказа.
    """
    if payment_data.supplier_order_id != order_id:
        raise HTTPException(status_code=400, detail="ID заказа в теле запроса не соответствует ID в пути.")

    # 1. Получаем ТОЛЬКО ID обновленного заказа
    updated_order_id = await crud.pay_supplier_order(db=db, payment_data=payment_data, user_id=current_user.id)

    # 2. Теперь в рамках ОДНОЙ сессии загружаем этот заказ со ВСЕМИ нужными связями
    result = await db.execute(
        select(models.SupplierOrders).options(
            # Используем joinedload/selectinload для "энергичной" загрузки
            selectinload(models.SupplierOrders.supplier_order_details).options(
                joinedload(models.SupplierOrderDetails.model).options(
                    selectinload(models.Models.model_name),
                    selectinload(models.Models.storage),
                    selectinload(models.Models.color)
                ),
                joinedload(models.SupplierOrderDetails.accessory)
            )
        ).filter(models.SupplierOrders.id == updated_order_id)
    )
    # .unique() нужен, чтобы избежать дубликатов из-за join'ов
    full_order_for_response = result.unique().scalars().one_or_none()

    if not full_order_for_response:
        raise HTTPException(status_code=404, detail="Не удалось найти заказ после обновления.")

    # 3. Форматируем уже полностью загруженные данные для ответа
    formatted_status_delivery = models.format_enum_value_for_display(full_order_for_response.status.value) if full_order_for_response.status else None
    formatted_payment_status = models.format_enum_value_for_display(full_order_for_response.payment_status.value) if full_order_for_response.payment_status else None
    
    formatted_details = []
    for detail in full_order_for_response.supplier_order_details:
        detail_dict = {
            "id": detail.id, "supplier_order_id": detail.supplier_order_id,
            "model_id": detail.model_id, "accessory_id": detail.accessory_id,
            "quantity": detail.quantity, "price": detail.price,
            "model_name": None, "accessory_name": None
        }

        if detail.model:
            model_name = detail.model.model_name.name if detail.model.model_name else ""
            storage_info = models.format_storage_for_display(detail.model.storage.storage) if detail.model.storage else ""
            color_info = detail.model.color.color_name if detail.model.color else ""
            detail_dict['model_name'] = f"{model_name} {storage_info} {color_info}".strip()
        
        if detail.accessory:
            detail_dict['accessory_name'] = detail.accessory.name

        formatted_details.append(schemas.SupplierOrderDetail.model_validate(detail_dict))

    return schemas.SupplierOrder(
        id=full_order_for_response.id,
        supplier_id=full_order_for_response.supplier_id,
        order_date=full_order_for_response.order_date,
        status=formatted_status_delivery,
        payment_status=formatted_payment_status,
        details=formatted_details
    )


@app.get("/api/v1/models/color-combos", response_model=List[schemas.ModelColorCombo], tags=["Models"], dependencies=[Depends(security.require_permission("manage_inventory"))])
async def read_unique_model_color_combos(db: AsyncSession = Depends(get_db)):
    """Получает сгруппированный список 'модель+цвет' для управления фото."""
    return await crud.get_unique_model_color_combos(db=db)

@app.put("/api/v1/models/image-by-color", tags=["Models"], dependencies=[Depends(security.require_permission("manage_inventory"))])
async def update_image_for_combo(
    update_data: schemas.ModelImageUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Обновляет URL изображения для всех моделей с одинаковым названием и цветом."""
    return await crud.update_image_for_model_color_combo(db=db, data=update_data)


@app.get("/api/v1/warehouse/valuation", response_model=schemas.InventoryValuation, tags=["Warehouse"], dependencies=[Depends(security.require_permission("manage_inventory"))])
async def read_inventory_valuation(
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    """Возвращает общую стоимость телефонов на складе по закупочной цене."""
    total = await crud.get_inventory_valuation(db=db)
    return schemas.InventoryValuation(total_valuation=total)

@app.get("/api/v1/reports/profit", 
         response_model=schemas.ProfitReport,
         tags=["Reports"],
         dependencies=[Depends(security.require_permission("view_reports"))])
async def read_profit_report(
    start_date: date,
    end_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    """Возвращает отчет по прибыли за указанный период."""
    report_data = await crud.get_profit_report(db=db, start_date=start_date, end_date=end_date)
    return schemas.ProfitReport(**report_data)


# --- Эндпоинты для совместимости Аксессуаров ---

@app.post("/api/v1/accessory-model-links", response_model=schemas.AccessoryModelLink, tags=["Accessory Compatibility"], dependencies=[Depends(security.require_permission("manage_inventory"))])
async def create_accessory_model_link(link_data: schemas.AccessoryModelCreate, db: AsyncSession = Depends(get_db)):
    new_link = await crud.link_accessory_to_model(db=db, link_data=link_data)
    # Вручную соберем ответ, чтобы включить имена
    return schemas.AccessoryModelLink(
        id=new_link.id,
        accessory_id=new_link.accessory_id,
        model_name_id=new_link.model_name_id,
        accessory_name=new_link.accessory.name,
        model_name=new_link.model_name.name
    )

@app.get("/api/v1/accessory-model-links", response_model=List[schemas.AccessoryModelLink], tags=["Accessory Compatibility"], dependencies=[Depends(security.require_permission("manage_inventory"))])
async def read_accessory_model_links(db: AsyncSession = Depends(get_db)):
    links = await crud.get_accessory_model_links(db=db)
    # Преобразуем ответ, чтобы включить имена
    return [
        schemas.AccessoryModelLink(
            id=link.id,
            accessory_id=link.accessory_id,
            model_name_id=link.model_name_id,
            accessory_name=link.accessory.name if link.accessory else "N/A",
            model_name=link.model_name.name if link.model_name else "N/A"
        ) for link in links
    ]

@app.delete("/api/v1/accessory-model-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Accessory Compatibility"], dependencies=[Depends(security.require_permission("manage_inventory"))])
async def delete_accessory_model_link(link_id: int, db: AsyncSession = Depends(get_db)):
    await crud.unlink_accessory_from_model(db=db, link_id=link_id)
    return

@app.get("/api/v1/models/{model_name_id}/compatible-accessories", response_model=List[schemas.AccessoryDetail], tags=["Sales"])
async def read_compatible_accessories(model_name_id: int, db: AsyncSession = Depends(get_db)):
    accessories = await crud.get_accessories_for_model(db=db, model_name_id=model_name_id)
    # Преобразуем в схему AccessoryDetail, которая включает актуальную цену
    response_list = []
    for acc in accessories:
        latest_price = None
        if acc.retail_price_accessories:
            latest_price_entry = sorted(acc.retail_price_accessories, key=lambda p: p.date, reverse=True)[0]
            latest_price = latest_price_entry.price

        acc_detail = schemas.AccessoryDetail(
            id=acc.id,
            name=acc.name,
            barcode=acc.barcode,
            category_accessory=acc.category_accessory,
            current_price=latest_price
        )
        response_list.append(acc_detail)
    return response_list

# --- Эндпоинты для управления браком и возвратами ---

@app.get("/api/v1/phones/defective", response_model=List[schemas.Phone], tags=["Returns"], dependencies=[Depends(security.require_any_permission("manage_inventory", "perform_inspections"))])
async def read_defective_phones(db: AsyncSession = Depends(get_db)):
    phones = await crud.get_defective_phones(db=db)
    return [_format_phone_response(p) for p in phones]
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

@app.get("/api/v1/phones/sent-to-supplier", response_model=List[schemas.Phone], tags=["Returns"], dependencies=[Depends(security.require_any_permission("manage_inventory", "perform_inspections"))])
async def read_phones_sent_to_supplier(db: AsyncSession = Depends(get_db)):
    phones = await crud.get_phones_sent_to_supplier(db=db)
    return [_format_phone_response(p) for p in phones]

@app.post("/api/v1/phones/send-to-supplier", response_model=List[schemas.Phone], tags=["Returns"], dependencies=[Depends(security.require_any_permission("manage_inventory", "perform_inspections"))])
async def mark_phones_as_sent_to_supplier(
    phone_ids: List[int], 
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)):
    updated_phones = await crud.send_phones_to_supplier(db=db, phone_ids=phone_ids, user_id=current_user.id)

    # --- НАЧАЛО ИЗМЕНЕНИЙ: Добавляем форматирование ---
    # Этот код форматирует ответ так же, как мы делали в других эндпоинтах,
    # чтобы избежать ошибок валидации.
    formatted_phones = []
    for phone in updated_phones:
        phone_dict = phone.__dict__
        if phone.model:
            model_name_base = phone.model.model_name.name if phone.model.model_name else ""
            storage_display = models.format_storage_for_display(phone.model.storage.storage) if phone.model.storage else ""
            color_name = phone.model.color.color_name if phone.model.color else ""
            full_display_name = " ".join(part for part in [model_name_base, storage_display, color_name] if part)
            phone_dict['model'] = schemas.ModelDetail(
                id=phone.model.id,
                name=full_display_name,
                base_name=model_name_base,
                model_name_id=phone.model.model_name_id,
                storage_id=phone.model.storage_id,
                color_id=phone.model.color_id
            )

        # Преобразуем Enum в строку для Pydantic
        if 'technical_status' in phone_dict and hasattr(phone_dict['technical_status'], 'value'):
            phone_dict['technical_status'] = phone_dict['technical_status'].value
        if 'commercial_status' in phone_dict and hasattr(phone_dict['commercial_status'], 'value'):
            phone_dict['commercial_status'] = phone_dict['commercial_status'].value

        formatted_phones.append(schemas.Phone.model_validate(phone_dict))

    return formatted_phones

@app.post("/api/v1/phones/{phone_id}/return-from-supplier", response_model=schemas.Phone, tags=["Returns"], dependencies=[Depends(security.require_any_permission("manage_inventory", "perform_inspections"))])
async def process_phone_return_from_supplier(phone_id: int, db: AsyncSession = Depends(get_db), current_user: models.Users = Depends(security.get_current_active_user)):
    updated_phone = await crud.process_return_from_supplier(db=db, phone_id=phone_id, user_id=current_user.id)

    # --- НАЧАЛО ИЗМЕНЕНИЙ: Добавляем форматирование ответа ---
    phone_dict = updated_phone.__dict__
    if updated_phone.model:
        model_name_base = updated_phone.model.model_name.name if updated_phone.model.model_name else ""
        storage_display = models.format_storage_for_display(updated_phone.model.storage.storage) if updated_phone.model.storage else ""
        color_name = updated_phone.model.color.color_name if updated_phone.model.color else ""
        full_display_name = " ".join(part for part in [model_name_base, storage_display, color_name] if part)
        phone_dict['model'] = schemas.ModelDetail(
            id=updated_phone.model.id,
            name=full_display_name,
            base_name=model_name_base,
            model_name_id=updated_phone.model.model_name_id,
            storage_id=updated_phone.model.storage_id,
            color_id=updated_phone.model.color_id
        )

    # Преобразуем Enum в строку для Pydantic
    if 'technical_status' in phone_dict and hasattr(phone_dict['technical_status'], 'value'):
        phone_dict['technical_status'] = phone_dict['technical_status'].value
    if 'commercial_status' in phone_dict and hasattr(phone_dict['commercial_status'], 'value'):
        phone_dict['commercial_status'] = phone_dict['commercial_status'].value

    return schemas.Phone.model_validate(phone_dict)

@app.post("/api/v1/phones/{phone_id}/refund", response_model=schemas.Phone, tags=["Returns"])
async def create_refund(
    phone_id: int,
    refund_data: schemas.RefundRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)  
):
    """Оформляет возврат телефона от клиента."""
    # Используем форматирование ответа, чтобы избежать ошибок
    updated_phone = await crud.process_customer_refund(db=db, phone_id=phone_id, refund_data=refund_data, user_id=current_user.id)

    phone_dict = updated_phone.__dict__
    # ... (здесь можно добавить полное форматирование модели, как в других функциях)

    return schemas.Phone.model_validate(phone_dict, from_attributes=True)

@app.post("/api/v1/phones/{phone_id}/start-repair", response_model=schemas.Phone, tags=["Returns"])
async def start_phone_repair(
    phone_id: int,
    repair_data: schemas.RepairCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Начинает процесс гарантийного или платного ремонта."""
    await crud.start_repair(
        db=db, 
        phone_id=phone_id,
        repair_data=repair_data,
        user_id=current_user.id
    )
    # После коммита безопасно загружаем полные данные
    fresh_phone_data = await crud.get_phone_by_id_fully_loaded(db, phone_id)
    return _format_phone_response(fresh_phone_data)


@app.post("/api/v1/repairs/{repair_id}/finish", response_model=schemas.Phone, tags=["Returns"])
async def finish_phone_repair(
    repair_id: int, 
    finish_data: schemas.RepairFinish,
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Завершает процесс ремонта."""
    phone_id = await crud.finish_repair(
        db=db, 
        repair_id=repair_id, 
        finish_data=finish_data,
        user_id=current_user.id
    )
    # После коммита безопасно загружаем полные данные
    fresh_phone_data = await crud.get_phone_by_id_fully_loaded(db, phone_id)
    return _format_phone_response(fresh_phone_data)

# ДОБАВЬТЕ ЭТОТ НОВЫЙ ЭНДПОИНТ
@app.post("/api/v1/repairs/{repair_id}/pay", response_model=schemas.Phone, tags=["Returns"], dependencies=[Depends(security.require_permission("perform_sales"))])
async def pay_for_repair(
    repair_id: int,
    payment_data: schemas.RepairPayment,
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Регистрирует оплату за платный ремонт."""
    # 1. Получаем ID телефона из CRUD-функции
    phone_id = await crud.record_repair_payment(
        db=db, repair_id=repair_id, payment_data=payment_data, user_id=current_user.id
    )
    
    # 2. Безопасно загружаем полные данные о телефоне для ответа
    fresh_phone_data = await crud.get_phone_by_id_fully_loaded(db, phone_id)
    
    # 3. Форматируем и возвращаем ответ
    return _format_phone_response(fresh_phone_data)


@app.post("/api/v1/phones/{phone_id}/replace-from-supplier", response_model=schemas.Phone, tags=["Returns"], dependencies=[Depends(security.require_any_permission("manage_inventory", "perform_inspections"))])
async def replace_phone_from_supplier(
    phone_id: int,
    replacement_data: schemas.SupplierReplacementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Обрабатывает замену бракованного телефона на новый от поставщика."""
    
    # 1. crud-функция теперь делает всю работу и возвращает только ID нового телефона
    new_phone_id = await crud.process_supplier_replacement(
        db=db,
        original_phone_id=phone_id,
        new_phone_data=replacement_data,
        user_id=current_user.id
    )

    # 2. Теперь, получив ID, мы используем специальную функцию,
    #    чтобы "чисто" загрузить этот телефон со всеми связями.
    fresh_new_phone = await crud.get_phone_by_id_fully_loaded(db, new_phone_id)

    # 3. Форматируем свежие и полные данные в ответ
    return _format_phone_response(fresh_new_phone)


@app.get("/api/v1/models/{model_id}/alternatives", response_model=List[schemas.ModelDetail], tags=["Models"])
async def read_model_alternatives(model_id: int, db: AsyncSession = Depends(get_db)):
    """Получает список моделей-альтернатив (другие цвета той же модели)."""
    
    alternative_models = await crud.get_replacement_model_options(db=db, model_id=model_id)
    
    # Форматируем ответ
    response_list = []
    for model in alternative_models:
        if model.model_name and model.storage and model.color:
            name = f"{model.model_name.name} {models.format_storage_for_display(model.storage.storage)} {model.color.color_name}"
            response_list.append(schemas.ModelDetail(
                id=model.id,
                name=name,
                base_name=model.model_name.name,
                model_name_id=model.model_name_id,
                storage_id=model.storage_id,
                color_id=model.color_id
            ))
    return response_list


@app.get("/api/v1/phones/{phone_id}/replacements", response_model=List[schemas.PhoneForExchange], tags=["Returns"])
async def get_replacement_phones(phone_id: int, db: AsyncSession = Depends(get_db)):
    """Получает список телефонов для обмена (та же модель, на складе)."""
    phone = await db.get(models.Phones, phone_id)
    if not phone:
        raise HTTPException(status_code=404, detail="Телефон не найден")

    replacement_phones = await crud.get_replacement_options(db=db, original_phone_model_id=phone.model_id)

    # --- НАЧАЛО ИЗМЕНЕНИЙ: Формируем полный ответ ---
    response_list = []
    for p in replacement_phones:
        full_name = "Модель не определена"
        if p.model:
            model_name_base = p.model.model_name.name if p.model.model_name else ""
            storage_display = models.format_storage_for_display(p.model.storage.storage) if p.model.storage else ""
            color_name = p.model.color.color_name if p.model.color else ""
            full_name = " ".join(part for part in [model_name_base, storage_display, color_name] if part)

        response_list.append(
            schemas.PhoneForExchange(
                id=p.id,
                serial_number=p.serial_number,
                full_model_name=full_name
            )
        )
    return response_list



@app.post("/api/v1/phones/{phone_id}/exchange", response_model=schemas.Phone, tags=["Returns"])
async def create_exchange(
    phone_id: int,
    exchange_data: schemas.ExchangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user) # Added for consistency
):
    """Выполняет обмен телефона."""
    updated_phone = await crud.process_phone_exchange(
        db=db,
        original_phone_id=phone_id,
        replacement_phone_id=exchange_data.replacement_phone_id,
        user_id=current_user.id
    )

    # --- ADD THIS FORMATTING BLOCK ---
    phone_dict = updated_phone.__dict__
    if updated_phone.model:
        model_name_base = updated_phone.model.model_name.name if updated_phone.model.model_name else ""
        storage_display = models.format_storage_for_display(updated_phone.model.storage.storage) if updated_phone.model.storage else ""
        color_name = updated_phone.model.color.color_name if updated_phone.model.color else ""
        full_display_name = " ".join(part for part in [model_name_base, storage_display, color_name] if part)
        phone_dict['model'] = schemas.ModelDetail(
            id=updated_phone.model.id,
            name=full_display_name,
            base_name=model_name_base,
            model_name_id=updated_phone.model.model_name_id,
            storage_id=updated_phone.model.storage_id,
            color_id=updated_phone.model.color_id
        )
    
    if 'technical_status' in phone_dict and hasattr(phone_dict['technical_status'], 'value'):
        phone_dict['technical_status'] = phone_dict['technical_status'].value
    if 'commercial_status' in phone_dict and hasattr(phone_dict['commercial_status'], 'value'):
        phone_dict['commercial_status'] = phone_dict['commercial_status'].value
    
    return schemas.Phone.model_validate(phone_dict, from_attributes=True)

@app.get("/api/v1/phones/in-stock", response_model=List[schemas.GroupedPhoneInStock], tags=["Phones"])
async def read_phones_in_stock(db: AsyncSession = Depends(get_db)):
    """Получает сгруппированный список телефонов на складе."""
    grouped_phones_data = await crud.get_grouped_phones_in_stock(db=db)
    
    response_list = []
    for item in grouped_phones_data:
        phone_model = item["model"]
        quantity = item["quantity"]

        model_name_base = phone_model.model_name.name if phone_model.model_name else ""
        storage_display = models.format_storage_for_display(phone_model.storage.storage) if phone_model.storage else ""
        color_name = phone_model.color.color_name if phone_model.color else ""
        full_name = " ".join(part for part in [model_name_base, storage_display, color_name] if part)

        latest_price = None
        if phone_model.retail_prices_phones:
            latest_price_entry = sorted(phone_model.retail_prices_phones, key=lambda p: p.date, reverse=True)[0]
            latest_price = latest_price_entry.price

        response_list.append(
            schemas.GroupedPhoneInStock(
                model_id=phone_model.id,
                full_model_name=full_name,
                price=latest_price,
                image_url=phone_model.image_url,
                quantity=quantity
            )
        )
    return sorted(response_list, key=lambda x: x.full_model_name)

@app.get("/api/v1/phones/stock-details", response_model=List[schemas.Phone], tags=["Warehouse"], dependencies=[Depends(security.require_any_permission("manage_inventory", "perform_sales"))])
async def read_all_phones_in_stock_detailed(db: AsyncSession = Depends(get_db)):
    """Получает детальный список всех телефонов на складе с их местоположением."""
    phones = await crud.get_all_phones_in_stock_detailed(db=db)
    # Форматируем ответ с помощью общей функции
    return [_format_phone_response(p) for p in phones]

@app.get("/api/v1/phones/available-for-loaner", response_model=list[schemas.LoanerPhoneInfo], tags=["Repairs"])
async def get_available_loaner_phones(db: AsyncSession = Depends(get_db)):
    """Получает список телефонов, которые можно выдать как подменные."""
    phones = await crud.get_available_for_loaner(db=db)
    response = []
    for p in phones:
        # Формируем полное имя модели для отображения в списке
        model_name = p.model.model_name.name if p.model and p.model.model_name else ""
        storage = models.format_storage_for_display(p.model.storage.storage) if p.model and p.model.storage else ""
        color = p.model.color.color_name if p.model and p.model.color else ""
        full_name = f"{model_name} {storage} {color}".strip()
        response.append({"id": p.id, "name": full_name, "serial_number": p.serial_number})
    return response


@app.get("/api/v1/phones/{phone_id}", response_model=schemas.Phone, tags=["Phones"])
async def read_phone_by_id(
    phone_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(security.get_current_active_user)
):
    """
    Получает информацию о конкретном телефоне по его ID.
    """
    phone = await db.get(models.Phones, phone_id, options=[
        selectinload(models.Phones.model).selectinload(models.Models.model_name),
        selectinload(models.Phones.model).selectinload(models.Models.storage),
        selectinload(models.Phones.model).selectinload(models.Models.color),
        selectinload(models.Phones.model_number)
    ])
    if not phone:
        raise HTTPException(status_code=404, detail="Телефон не найден")

    # Форматируем ответ, как в других эндпоинтах
    phone_dict = {
        "id": phone.id,
        "serial_number": phone.serial_number,
        "technical_status": phone.technical_status.value if phone.technical_status else None,
        "commercial_status": phone.commercial_status.value if phone.commercial_status else None,
        "added_date": phone.added_date,
        "model": None,
        "model_number": phone.model_number
    }

    if phone.model:
        model_name_base = phone.model.model_name.name if phone.model.model_name else ""
        storage_display = models.format_storage_for_display(phone.model.storage.storage) if phone.model.storage else ""
        color_name = phone.model.color.color_name if phone.model.color else ""

        full_name_parts = [part for part in [model_name_base, storage_display, color_name] if part]
        full_display_name = " ".join(full_name_parts)

        phone_dict['model'] = schemas.ModelDetail(
            id=phone.model.id,
            name=full_display_name,
            base_name=model_name_base,
            model_name_id=phone.model.model_name_id,
            storage_id=phone.model.storage_id,
            color_id=phone.model.color_id
        )

    return schemas.Phone.model_validate(phone_dict)


class SalesSummary(BaseModel):
    sales_count: int
    total_revenue: Decimal
    cash_in_register: Decimal

@app.get("/api/v1/dashboard/sales-summary", response_model=SalesSummary, tags=["Dashboard"], dependencies=[Depends(security.require_permission("perform_sales"))])
async def get_dashboard_sales_summary(
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Возвращает сводку по продажам для текущего пользователя за день."""
    return await crud.get_sales_summary_for_user(db=db, user_id=current_user.id)

@app.get("/api/v1/dashboard/ready-for-sale", response_model=List[schemas.Phone], tags=["Dashboard"])
async def get_dashboard_ready_for_sale(
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Получает последние 5 телефонов, готовые к продаже."""
    query = (
        select(models.Phones)
        .options(
            selectinload(models.Phones.model).options(
                selectinload(models.Models.model_name),
                selectinload(models.Models.storage),
                selectinload(models.Models.color)
            ),
            selectinload(models.Phones.model_number),
            selectinload(models.Phones.supplier_order)  # <--- ДОБАВЛЕНА ЭТА СТРОКА
        )
        .filter(models.Phones.commercial_status == models.CommerceStatus.НА_СКЛАДЕ)
        .order_by(models.Phones.id.desc())
        .limit(5)
    )
    result = await db.execute(query)
    phones = result.scalars().all()
    return [_format_phone_response(p) for p in phones]

class ShiftResponse(BaseModel):
    id: int
    shift_start: datetime
    shift_end: Optional[datetime] = None

@app.get("/api/v1/shifts/active", response_model=Optional[ShiftResponse], tags=["Shifts"])
async def get_user_active_shift(
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Проверяет, есть ли у текущего пользователя активная смена."""
    active_shift = await crud.get_active_shift(db, user_id=current_user.id)
    return active_shift

@app.post("/api/v1/shifts/start", response_model=ShiftResponse, tags=["Shifts"])
async def start_user_shift(
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Начинает новую смену для текущего пользователя."""
    return await crud.start_shift(db, user_id=current_user.id)

@app.put("/api/v1/shifts/end", response_model=ShiftResponse, tags=["Shifts"])
async def end_user_shift(
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Завершает активную смену для текущего пользователя."""
    return await crud.end_shift(db, user_id=current_user.id)


# --- Эндпоинты для Заметок ---

@app.get("/api/v1/notes", response_model=List[schemas.Note], tags=["Notes"], dependencies=[Depends(security.require_permission("perform_sales"))])
async def read_notes(show_all: bool = False, db: AsyncSession = Depends(get_db)):
    """Получает список заметок. ?show_all=true для показа всех, включая выполненные."""
    return await crud.get_notes(db=db, show_all=show_all)

@app.post("/api/v1/notes", response_model=schemas.Note, tags=["Notes"], dependencies=[Depends(security.require_permission("perform_sales"))])
async def create_new_note(
    note: schemas.NoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Создает новую заметку."""
    return await crud.create_note(db=db, note=note, user_id=current_user.id)

@app.put("/api/v1/notes/{note_id}", response_model=schemas.Note, tags=["Notes"], dependencies=[Depends(security.require_permission("perform_sales"))])
async def update_note(
    note_id: int,
    note_update: schemas.NoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Обновляет статус заметки (выполнена/не выполнена)."""
    return await crud.update_note_status(
        db=db, note_id=note_id, completed=note_update.is_completed, user_id=current_user.id
    )

@app.put("/api/v1/warehouse/move-phone/{phone_id}", response_model=schemas.Phone, tags=["Warehouse"], dependencies=[Depends(security.require_any_permission("manage_inventory", "perform_sales"))])
async def move_phone(
    phone_id: int,
    request: schemas.MovePhoneRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.Users = Depends(security.get_current_active_user)
):
    """Перемещает телефон на новое место (СКЛАД или ВИТРИНА)."""
    try:
        new_location_enum = models.EnumShop[request.new_location]
    except KeyError:
        raise HTTPException(status_code=400, detail="Неверное местоположение. Используйте 'СКЛАД' или 'ВИТРИНА'.")
    
    updated_phone = await crud.move_phone_location(
        db=db, phone_id=phone_id, new_location=new_location_enum, user_id=current_user.id
    )
    return _format_phone_response(updated_phone)



@app.post("/api/v1/repairs/{repair_id}/issue-loaner", tags=["Repairs"])
async def issue_loaner_phone_endpoint(
    repair_id: int, 
    request: schemas.IssueLoanerRequest,
    db: AsyncSession = Depends(get_db), 
    current_user: models.Users = Depends(security.get_current_active_user)
):
    await crud.issue_loaner(db, repair_id=repair_id, loaner_phone_id=request.loaner_phone_id, user_id=current_user.id)
    return {"status": "success", "message": "Loaner phone issued."}

@app.post("/api/v1/loaner-logs/{log_id}/return-loaner", tags=["Repairs"])
async def return_loaner_phone_endpoint(
    log_id: int, 
    db: AsyncSession = Depends(get_db), 
    current_user: models.Users = Depends(security.get_current_active_user)
):
    await crud.return_loaner(db, loaner_log_id=log_id, user_id=current_user.id)
    return {"status": "success", "message": "Loaner phone returned."}


@app.get("/api/v1/reports/payroll", 
         response_model=List[schemas.PayrollReportItem],
         tags=["Reports"],
         dependencies=[Depends(security.require_permission("view_reports"))])
async def get_payroll_report_endpoint(
    start_date: date,
    end_date: date,
    db: AsyncSession = Depends(get_db)
):
    """Формирует и возвращает зарплатный отчет за период."""
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="Дата начала не может быть позже даты окончания.")
        
    return await crud.get_payroll_report(db=db, start_date=start_date, end_date=end_date)

@app.post("/api/v1/reports/payroll/pay", 
          tags=["Reports"],
          dependencies=[Depends(security.require_permission("manage_cashflow"))])
async def pay_salary_endpoint(
    payment_data: schemas.PayrollPaymentCreate,
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Проводит выплату зарплаты сотруднику."""
    if payment_data.amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма выплаты должна быть положительной.")
    
    await crud.create_payroll_payment(db=db, user_id=user_id, payment_data=payment_data)
    return {"status": "success", "message": "Выплата успешно проведена."}

@app.get("/api/v1/reports/financial-snapshots",
         response_model=List[schemas.FinancialSnapshotSchema],
         tags=["Reports"],
         dependencies=[Depends(security.require_permission("view_reports"))])
async def read_financial_snapshots(db: AsyncSession = Depends(get_db)):
    """Получает историю всех финансовых срезов."""
    return await crud.get_financial_snapshots(db=db)

@app.post("/api/v1/reports/financial-snapshots",
          response_model=schemas.FinancialSnapshotSchema,
          tags=["Reports"],
          dependencies=[Depends(security.require_permission("view_reports"))])
async def create_new_financial_snapshot(db: AsyncSession = Depends(get_db)):
    """Создает новый финансовый срез на текущую дату."""
    return await crud.create_financial_snapshot(db=db)

WEBHOOK_URL = f"https://604aa28a8f19.ngrok-free.app/api/v1/telegram/webhook/{TELEGRAM_BOT_TOKEN}"

@app.post("/api/v1/telegram/webhook/{token}")
async def telegram_webhook(token: str, update: dict):
    """Принимает обновления от Telegram."""
    if token != TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

    telegram_update = types.Update(**update)
    await dp.feed_update(bot=bot, update=telegram_update)
    return {"ok": True}

# Создаем экземпляр планировщика
scheduler = AsyncIOScheduler(timezone="Asia/Yekaterinburg") # Укажите ваш часовой пояс

# Добавляем нашу задачу в планировщик
scheduler.add_job(close_overdue_shifts, 'cron', hour=23, minute=59)

@app.on_event("startup")
async def startup_event():
    """Запускает планировщик и устанавливает вебхук при старте приложения."""
    # Устанавливаем вебхук
    webhook_info = await bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await bot.set_webhook(url=WEBHOOK_URL)
        print(">>> Вебхук для Telegram бота УСТАНОВЛЕН.")
    else:
        # ДОБАВЛЕН ЭТОТ БЛОК ДЛЯ ИНФОРМАТИВНОСТИ
        print(">>> Вебхук для Telegram бота УЖЕ БЫЛ УСТАНОВЛЕН.")
    
    scheduler.start()
    print("Планировщик задач запущен.")

@app.on_event("shutdown")
async def shutdown_event():
    """Останавливает планировщик и удаляет вебхук при выключении приложения."""
    await bot.delete_webhook()
    print("Вебхук для Telegram бота удален.")

    scheduler.shutdown()
    print("Планировщик задач остановлен.")


