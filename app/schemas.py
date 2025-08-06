# app/schemas.py

from datetime import date, datetime
from pydantic import BaseModel, computed_field
from typing import Optional, List, Dict, Any 
from .models import TechStatus, CommerceStatus, StatusDelivery, EnumShop, EnumPayment, StatusPay, ProductTypeEnum
from decimal import Decimal

# ADD NEW: Вспомогательная функция _format_storage_for_display (скопирована из models.py)
# def _format_storage_for_display(storage_value_raw: Optional[Union[int, str]]) -> Optional[str]:
#     """
#     Форматирует значение памяти (целое число или строку) в строку с правильной единицей измерения (GB/TB).
#     Это копия из models.py, чтобы избежать циклической зависимости.
#     """
#     if storage_value_raw is None:
#         return None
    
#     numeric_value: Optional[int] = None
#     if isinstance(storage_value_raw, int):
#         numeric_value = storage_value_raw
#     elif isinstance(storage_value_raw, str):
#         try:
#             clean_value = ''.join(filter(str.isdigit, storage_value_raw))
#             if clean_value:
#                 numeric_value = int(clean_value)
#         except ValueError:
#             pass # numeric_value останется None

#     if numeric_value is None:
#         return None 

#     if numeric_value >= 1024 and (numeric_value % 1024 == 0):
#         return f"{numeric_value // 1024}TB"
#     else:
#         return f"{numeric_value}GB"
    

# --- Схемы для токена ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class PermissionSchema(BaseModel):
    code: str
    description: Optional[str] = None
    
    class Config:
        from_attributes = True

class RoleSchema(BaseModel):
    role_name: str
    permissions: List[PermissionSchema] = [] # Просто ожидаем список прав

    class Config:
        from_attributes = True

    class Config:
        from_attributes = True


# --- Схемы для пользователя ---
class UserBase(BaseModel):
    username: str
    email: Optional[str] = None
    name: Optional[str] = None
    last_name: Optional[str] = None

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    active: bool
    role: Optional[RoleSchema] = None # <--- ИЗМЕНИ ЭТУ СТРОКУ

    class Config:
        from_attributes = True


# --- Схемы для Телефонов ---
class Color(BaseModel):
    id: int # ADD NEW: Добавлен id
    color_name: Optional[str] = None
    class Config:
        from_attributes = True

class Storage(BaseModel):
    id: int # Оставляем int, так как это ID.
    storage: Optional[str] = None # <--- ИЗМЕНЕНО: тип изменен на Optional[str] для вывода
    class Config:
        from_attributes = True

class ModelName(BaseModel):
    id: Optional[int] = None # <-- Обязательно Optional[int]
    name: Optional[str] = None # <-- Обязательно Optional[str]
    class Config:
        from_attributes = True

# Это схема, которая отправляется на фронтенд для выбора модели в списке.
class ModelDetail(BaseModel):
    # ID самой модели
    id: int 
    name: str 
    base_name: Optional[str] = None 
    model_name_id: Optional[int] = None # ADD NEW: ID базовой модели
    storage_id: Optional[int] = None # ADD NEW: ID памяти
    color_id: Optional[int] = None # ADD NEW: ID цвета
    image_url: Optional[str] = None
    
    class Config:
        from_attributes = True # KEEP: Хотя мы будем явно создавать, это может помочь



class Accessory(BaseModel): # <--- УБЕДИТЕСЬ, ЧТО ЭТОТ КЛАСС ПРИСУТСТВУЕТ
    id: int
    name: Optional[str] = None
    # category_accessory_id: Optional[int] = None # Можно добавить, если нужно в API ответе
    class Config:
        from_attributes = True        

class ModelNumber(BaseModel):
    id: int
    name: Optional[str] = None
    class Config:
        from_attributes = True

# --- Схемы для Телефонов ---
class Phone(BaseModel):
    id: int
    serial_number: Optional[str] = None
    technical_status: Optional[str]
    commercial_status: Optional[str]
    model: Optional[ModelDetail] = None
    added_date: Optional[date] = None
    model_number: Optional[ModelNumber] = None
    storage_location: Optional[str] = None
    defect_reason: Optional[str] = None


class PhoneCreate(BaseModel):
    serial_number: Optional[str] = None
    model_id: int
    technical_status: Optional[TechStatus] = None
    commercial_status: Optional[CommerceStatus] = None

class PhoneInStock(BaseModel):
    id: int
    serial_number: Optional[str] = None
    full_model_name: str
    price: Optional[float] = None
    image_url: Optional[str] = None

    class Config:
        from_attributes = True

class GroupedPhoneInStock(BaseModel):
    model_id: int
    full_model_name: str
    price: Optional[float] = None
    image_url: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True



# --- Схемы для Поставщиков ---
class SupplierBase(BaseModel):
    name: Optional[str] = None
    contact_info: str

class SupplierCreate(SupplierBase):
    pass

class Supplier(SupplierBase):
    id: int
    class Config:
        from_attributes = True


# --- Схемы для Заказов у Поставщиков ---
# ИСПРАВЛЕНО: SupplierOrderDetailCreate теперь находится выше, чем SupplierOrderDetail
class SupplierOrderDetailCreate(BaseModel): 
    model_id: Optional[int] = None
    accessory_id: Optional[int] = None
    quantity: int
    price: float

class SupplierOrderDetail(SupplierOrderDetailCreate):
    id: int
    supplier_order_id: int
    
    # Новые поля для названий (они будут заполняться на бэкенде)
    model_name: Optional[str] = None # Полное название модели (iPhone 13 256GB Midnight)
    accessory_name: Optional[str] = None # Название аксессуара

    class Config:
        from_attributes = True # Позволит Pydantic маппить из ORM объектов

# ИСПРАВЛЕНО: SupplierOrderCreate теперь находится выше, чем SupplierOrder
class SupplierOrderCreate(BaseModel):
    supplier_id: int
    details: List[SupplierOrderDetailCreate] # Ссылается на уже определенный SupplierOrderDetailCreate

class SupplierPaymentCreate(BaseModel):
    supplier_order_id: int
    amount: Decimal
    account_id: int # Счет, с которого произведена оплата
    payment_date: Optional[datetime] = None # Дата оплаты, по умолчанию datetime.now()
    notes: Optional[str] = None

# ИСПРАВЛЕНО: SupplierOrder теперь находится после SupplierOrderCreate
class SupplierOrder(BaseModel):
    id: int
    supplier_id: int
    order_date: Optional[datetime] = None
    status: Optional[str] = None
    payment_status: Optional[str] = None
    details: List[SupplierOrderDetail] = [] # Ссылается на уже определенный SupplierOrderDetail
    class Config:
        from_attributes = True
        
# --- Схемы для Инспекции ---

class BatteryTestCreate(BaseModel):
    start_time: Optional[datetime] = None
    start_battery_level: Optional[int] = None
    end_time: Optional[datetime] = None
    end_battery_level: Optional[int] = None

class InspectionResultItem(BaseModel):
    checklist_item_id: int
    result: bool 
    notes: Optional[str] = None

class InspectionSubmission(BaseModel):
    serial_number: str
    results: List[InspectionResultItem]
    battery_test: Optional[BatteryTestCreate] = None
    model_number: Optional[str] = None


class ChecklistItem(BaseModel):
    id: int
    name: str
    notes: Optional[str] = None
    class Config:
        from_attributes = True
        
class InspectionInfo(BaseModel):
    id: int # ID самой инспекции
    phone: Phone # Вложенные данные о телефоне

    class Config:
        from_attributes = True



class Shop(BaseModel):
    id: int
    name: Optional[str] = None
    
    class Config:
        from_attributes = True

class WarehouseAcceptanceRequest(BaseModel):
    phone_ids: List[int]
    shop_id: int

class CategoryAccessory(BaseModel):
    id: int
    name: Optional[str] = None
    class Config:
        from_attributes = True

class RetailPriceAccessory(BaseModel):
    price: Optional[Decimal] = None
    date: Optional[datetime] = None
    class Config:
        from_attributes = True

class AccessoryDetail(Accessory): # Наследуемся от простой схемы Accessory
    barcode: Optional[str] = None
    category_accessory: Optional[CategoryAccessory] = None
    current_price: Optional[Decimal] = None # Добавим поле для актуальной цены
    purchase_price: Optional[Decimal] = None
    
class AccessoryInStock(AccessoryDetail):
    quantity: int
    
class AccessoryCreate(BaseModel):
    name: str
    barcode: Optional[str] = None
    category_accessory_id: int

class TrafficSource(BaseModel):
    id: int
    name: str
    class Config:
        from_attributes = True

class TrafficSourceCreate(BaseModel):
    name: str


class CustomerCreate(BaseModel):
    name: str
    number: Optional[str] = None
    source_id: Optional[int] = None
    referrer_id: Optional[int] = None

class Customer(BaseModel):
    id: int
    name: Optional[str] = None
    number: Optional[str] = None
    source: Optional[TrafficSource] = None # <-- Изменено
    # Добавим информацию о том, кто привел клиента, для отображения
    referrer_name: Optional[str] = None
    class Config:
        from_attributes = True

# Универсальная схема для товара на продажу
class ProductForSale(BaseModel):
    warehouse_id: int
    product_id: int
    product_type: str # "Телефон" или "Аксессуар"
    name: str
    price: Optional[Decimal] = None
    serial_number: Optional[str] = None # Только для телефонов
    quantity: int

    # Cхема для одной позиции в чеке при создании
# Cхема для одной позиции в чеке при создании
class SaleDetailCreate(BaseModel):
    warehouse_id: int
    quantity: int
    unit_price: Decimal

# Схема для создания новой продажи (данные с фронтенда)
class SaleCreate(BaseModel):
    customer_id: Optional[int] = None
    payment_method: str
    notes: Optional[str] = None
    details: List[SaleDetailCreate]
    account_id: Optional[int] = None
    discount: Optional[Decimal] = None
    cash_received: Optional[Decimal] = None
    change_given: Optional[Decimal] = None

# --- Схемы для ответа от сервера ---

class SaleDetailResponse(BaseModel):
    id: int
    product_name: str
    serial_number: Optional[str] = None   # <--- ДОБАВИТЬ
    model_number: Optional[str] = None    # <--- ДОБАВИТЬ
    quantity: int
    unit_price: Decimal
    
    class Config:
        from_attributes = True

class SaleResponse(BaseModel):
    id: int
    sale_date: datetime
    customer_id: Optional[int] = None
    total_amount: Decimal
    details: List[SaleDetailResponse] = []

    class Config:
        from_attributes = True

class PriceCreate(BaseModel):
    price: Decimal

class RetailPriceResponse(BaseModel):
    id: int
    price: Decimal
    date: datetime
    
    class Config:
        from_attributes = True

# Схема для комбинации "модель + память"
class ModelStorageCombo(BaseModel):
    display_name: str
    model_name_id: int
    storage_id: int
    current_price: Optional[Decimal] = None 


class ModelColorCombo(BaseModel):
    model_name_id: int
    model_name: str
    color_id: int
    color_name: str
    image_url: Optional[str] = None

class ModelImageUpdate(BaseModel):
    model_name_id: int
    color_id: int
    image_url: Optional[str] = None


# Схема для установки цены на комбинацию
class PriceSetForCombo(BaseModel):
    price: Decimal
    model_name_id: int
    storage_id: int

class OperationCategory(BaseModel):
    id: int
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    class Config:
        from_attributes = True

class Counterparty(BaseModel):
    id: int
    name: Optional[str] = None
    type: Optional[str] = None
    class Config:
        from_attributes = True

class Account(BaseModel):
    id: int
    name: Optional[str] = None
    class Config:
        from_attributes = True

class CashFlowBase(BaseModel):
    operation_categories_id: int
    counterparty_id: Optional[int] = None
    account_id: int
    amount: Decimal
    description: Optional[str] = None

class CashFlowCreate(CashFlowBase):
    pass

class CashFlow(CashFlowBase):
    id: int
    date: datetime
    class Config:
        from_attributes = True

class AccountCreate(BaseModel):
    name: str

class CounterpartyCreate(BaseModel):
    name: str
    type: Optional[str] = None

class TotalBalance(BaseModel):
    total_balance: Decimal

class InventoryValuation(BaseModel):
    total_valuation: Decimal

class ProfitReport(BaseModel):
    start_date: date
    end_date: date
    total_revenue: Decimal
    total_cogs: Decimal # Cost of Goods Sold - Себестоимость
    gross_profit: Decimal
    total_expenses: Decimal
    operating_profit: Decimal


class AccessoryModelLink(BaseModel):
    id: int
    accessory_id: int
    model_name_id: int
    # Добавим названия для удобства отображения
    accessory_name: str
    model_name: str

    class Config:
        from_attributes = True

class AccessoryModelCreate(BaseModel):
    accessory_id: int
    model_name_id: int
    
# --- Схемы для истории телефона ---

class PhoneHistoryPurchase(BaseModel):
    supplier_order_id: int
    order_date: Optional[datetime] = None
    purchase_price: Optional[Decimal] = None
    supplier_name: Optional[str] = None

class PhoneHistoryInspectionResult(BaseModel):
    item_name: str
    result: bool
    notes: Optional[str] = None

class PhoneHistoryBatteryTest(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    start_battery_level: Optional[int] = None
    end_battery_level: Optional[int] = None
    battery_drain: Optional[Decimal] = None

class PhoneHistoryInspection(BaseModel):
    inspection_date: Optional[datetime] = None
    inspected_by: Optional[str] = None
    results: List[PhoneHistoryInspectionResult] = []
    battery_tests: List[PhoneHistoryBatteryTest] = []

class PhoneHistorySale(BaseModel):
    sale_id: int
    sale_date: Optional[datetime] = None
    unit_price: Optional[Decimal] = None
    customer_name: Optional[str] = None
    customer_number: Optional[str] = None

class PhoneHistoryWarehouse(BaseModel):
    added_date: Optional[datetime] = None 
    shop_name: Optional[str] = None
    accepted_by: Optional[str] = None

# Простая схема для отображения пользователя в логе
class UserInLog(BaseModel):
    username: str
    name: Optional[str] = None
    last_name: Optional[str] = None

    class Config:
        from_attributes = True

# Схема для одной записи в логе
class PhoneMovementLog(BaseModel):
    id: int
    timestamp: datetime
    event_type: str 
    details: Optional[str] = None
    user: Optional[UserInLog] = None

    class Config: # <-- Оставляем только один
        from_attributes = True

class RepairCreate(BaseModel):
    repair_type: str # "ГАРАНТИЙНЫЙ" или "ПЛАТНЫЙ"
    estimated_cost: Optional[Decimal] = None
    customer_name: str
    customer_phone: str
    problem_description: str
    device_condition: str
    included_items: Optional[str] = None
    notes: Optional[str] = None

class RepairFinish(BaseModel):
    work_performed: str
    final_cost: Optional[Decimal] = None
    service_cost: Optional[Decimal] = None     
    expense_account_id: Optional[int] = None

class RepairPayment(BaseModel):
    account_id: int
    amount: Decimal


class ActiveLoanerLog(BaseModel):
    id: int
    date_issued: datetime
    loaner_phone_details: str # e.g., "iPhone 15 Pro (SN: ...)"
    
    class Config:
        from_attributes = True

class Repair(RepairCreate):
    id: int
    phone_id: int
    user_id: int
    date_accepted: datetime
    date_returned: Optional[datetime] = None
    work_performed: Optional[str] = None
    final_cost: Optional[Decimal] = None
    payment_status: Optional[str] = None
    active_loaner: Optional[ActiveLoanerLog] = None

    class Config:
        from_attributes = True

class PhoneHistoryResponse(Phone): # Наследуем от основной схемы телефона
    purchase_info: Optional[PhoneHistoryPurchase] = None
    inspections: List[PhoneHistoryInspection] = []
    warehouse_info: Optional[PhoneHistoryWarehouse] = None
    sale_info: Optional[PhoneHistorySale] = None
    movement_logs: List[PhoneMovementLog] = []
    repairs: List[Repair] = []

class RefundRequest(BaseModel):
    account_id: int # ID счета, с которого возвращаются деньги
    notes: Optional[str] = None
    
class ExchangeRequest(BaseModel):
    replacement_phone_id: int

class PhoneForExchange(BaseModel):
    id: int
    serial_number: Optional[str] = None
    full_model_name: str
    # Можно добавить и другие поля, если они нужны для выбора
    
class SupplierReplacementCreate(BaseModel):
    new_serial_number: str
    new_model_id: int






class RoleInfo(BaseModel):
    id: int
    role_name: str

    class Config:
        from_attributes = True

class EmployeeCreate(UserBase):
    password: str
    role_id: int
    active: bool = True


class NoteUser(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True

class Note(BaseModel):
    id: int
    content: str
    is_completed: bool
    created_at: datetime
    created_by: NoteUser
    completed_at: Optional[datetime] = None
    completed_by: Optional[NoteUser] = None

    class Config:
        from_attributes = True

class NoteCreate(BaseModel):
    content: str

class NoteUpdate(BaseModel):
    is_completed: bool

class MovePhoneRequest(BaseModel):
    new_location: str

class LoanerPhoneInfo(BaseModel):
    id: int
    name: str
    serial_number: Optional[str] = None

class IssueLoanerRequest(BaseModel):
    loaner_phone_id: int

class ActiveLoanerLog(BaseModel):
    id: int
    date_issued: datetime
    loaner_phone_details: str # e.g., "iPhone 15 Pro (SN: ...)"
    
    class Config:
        from_attributes = True


# --- Схемы для отчета по Зарплатам ---

class PayrollDetailItem(BaseModel):
    count: int
    rate: Decimal
    total: Decimal

class PayrollBreakdown(BaseModel):
    inspections: Optional[PayrollDetailItem] = None
    battery_tests: Optional[PayrollDetailItem] = None
    packaging: Optional[PayrollDetailItem] = None
    shifts: Optional[PayrollDetailItem] = None
    phone_sales_bonus: Optional[PayrollDetailItem] = None

class PayrollReportItem(BaseModel):
    user_id: int
    username: str
    name: str
    role: str
    breakdown: PayrollBreakdown
    total_earned: Decimal
    total_paid: Decimal
    balance: Decimal

class PayrollPaymentCreate(BaseModel):
    amount: Decimal
    account_id: int
    notes: Optional[str] = None

class FinancialSnapshotSchema(BaseModel):
    id: int
    snapshot_date: datetime
    cash_balance: Decimal
    inventory_value: Decimal
    goods_in_transit_value: Decimal
    total_assets: Decimal
    details: Optional[Dict[str, Any]] = None 

    class Config:
        from_attributes = True

