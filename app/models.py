from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import List, Optional, Union
from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, 
    Interval, Numeric, String, Text, TIMESTAMP, Enum
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Enum definitions
class TechStatus(PyEnum):
    ОЖИДАЕТ_ПРОВЕРКУ = "ОЖИДАЕТ_ПРОВЕРКУ"
    НА_ТЕСТЕ_АККУМУЛЯТОРА = "НА_ТЕСТЕ_АККУМУЛЯТОРА" 
    НА_УПАКОВКЕ = "НА_УПАКОВКЕ" 
    УПАКОВАН = "УПАКОВАН"
    БРАК = "БРАК"
    НА_ПРОВЕРКЕ = "НА_ПРОВЕРКЕ" # <--- ИЗМЕНЕНО


class CommerceStatus(PyEnum):
    НЕ_ГОТОВ_К_ПРОДАЖЕ = "НЕ_ГОТОВ_К_ПРОДАЖЕ"
    НА_СКЛАДЕ = "НА_СКЛАДЕ"
    ПРОДАН = "ПРОДАН"
    ВОЗВРАТ = "ВОЗВРАТ"
    В_РЕМОНТЕ = "В_РЕМОНТЕ"
    ОТПРАВЛЕН_ПОСТАВЩИКУ = "ОТПРАВЛЕН_ПОСТАВЩИКУ"
    СПИСАН_ПОСТАВЩИКОМ = "СПИСАН_ПОСТАВЩИКОМ" 
    ПОДМЕННЫЙ_ФОНД = "ПОДМЕННЫЙ_ФОНД" 
    ВЫДАН_КАК_ПОДМЕННЫЙ = "ВЫДАН_КАК_ПОДМЕННЫЙ"
    ОТПРАВЛЕН_КЛИЕНТУ = "ОТПРАВЛЕН_КЛИЕНТУ"


class StatusDelivery(PyEnum):
    ЗАКАЗ = "ЗАКАЗ"
    В_ПУТИ = "В ПУТИ"
    ПОЛУЧЕН = "ПОЛУЧЕН"


class EnumShop(PyEnum):
    СКЛАД = "СКЛАД"
    ВИТРИНА = "ВИТРИНА"
    ПОДМЕННЫЙ_ФОНД = "ПОДМЕННЫЙ_ФОНД"


class EnumPayment(PyEnum):
    НАЛИЧНЫЕ = "НАЛИЧНЫЕ"
    КАРТА = "КАРТА"
    КРЕДИТ_РАССРОЧКА = "КРЕДИТ/РАССРОЧКА"
    ПЕРЕВОД = "ПЕРЕВОД"
    КРИПТОВАЛЮТА = "КРИПТОВАЛЮТА"


class StatusPay(PyEnum):
    ОЖИДАНИЕ_ОПЛАТЫ = "ОЖИДАНИЕ ОПЛАТЫ"
    ЧАСТИЧНО_ОПЛАЧЕН = "ЧАСТИЧНО_ОПЛАЧЕН"
    ОПЛАЧЕН = "ОПЛАЧЕН"
    ОТМЕНА = "ОТМЕНА"


class ProductTypeEnum(PyEnum):
    PHONE = "PHONE" # Тоже сделал заглавными, для согласованности
    ACCESSORY = "ACCESSORY" # Тоже сделал заглавными, для согласованности

class OrderPaymentStatus(PyEnum):
    НЕ_ОПЛАЧЕН = "НЕ_ОПЛАЧЕН"
    ЧАСТИЧНО_ОПЛАЧЕН = "ЧАСТИЧНО_ОПЛАЧЕН"
    ОПЛАЧЕН = "ОПЛАЧЕН"

class PhoneEventType(PyEnum):
    ПОСТУПЛЕНИЕ_ОТ_ПОСТАВЩИКА = "ПОСТУПЛЕНИЕ_ОТ_ПОСТАВЩИКА"
    ИНСПЕКЦИЯ_ПРОЙДЕНА = "ИНСПЕКЦИЯ_ПРОЙДЕНА"
    ОБНАРУЖЕН_БРАК = "ОБНАРУЖЕН_БРАК"
    ПРИНЯТ_НА_СКЛАД = "ПРИНЯТ_НА_СКЛАД"
    ПРОДАН = "ПРОДАН"
    ВОЗВРАТ_ОТ_КЛИЕНТА = "ВОЗВРАТ_ОТ_КЛИЕНТА"
    ОТПРАВЛЕН_ПОСТАВЩИКУ = "ОТПРАВЛЕН_ПОСТАВЩИКУ"
    ПОЛУЧЕН_ОТ_ПОСТАВЩИКА = "ПОЛУЧЕН_ОТ_ПОСТАВЩИКА"
    ОТПРАВЛЕН_В_РЕМОНТ = "ОТПРАВЛЕН_В_РЕМОНТ"
    ПОЛУЧЕН_ИЗ_РЕМОНТА = "ПОЛУЧЕН_ИЗ_РЕМОНТА"
    ОБМЕНЕН = "ОБМЕНЕН"    
    ПЕРЕМЕЩЕНИЕ = "ПЕРЕМЕЩЕНИЕ"
    ВЫДАН_КАК_ПОДМЕННЫЙ = "ВЫДАН_КАК_ПОДМЕННЫЙ" 
    ПРИНЯТ_ИЗ_ПОДМЕНЫ = "ПРИНЯТ_ИЗ_ПОДМЕНЫ"

class RepairType(PyEnum):
    ГАРАНТИЙНЫЙ = "ГАРАНТИЙНЫЙ"
    ПЛАТНЫЙ = "ПЛАТНЫЙ"


# Model definitions
class Supplier(Base):
    __tablename__ = "supplier"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    contact_info: Mapped[str] = mapped_column(Text, nullable=False)
    
    supplier_orders: Mapped[List["SupplierOrders"]] = relationship("SupplierOrders", back_populates="supplier")


class SupplierOrders(Base):
    __tablename__ = "supplier_orders"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("supplier.id"))
    order_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[Optional[StatusDelivery]] = mapped_column(Enum(StatusDelivery, native_enum=False)) # <-- ИЗМЕНЕНИЕ
    
    payment_status: Mapped[Optional[OrderPaymentStatus]] = mapped_column(Enum(OrderPaymentStatus, native_enum=False), default=OrderPaymentStatus.НЕ_ОПЛАЧЕН)

    supplier: Mapped[Optional["Supplier"]] = relationship("Supplier", back_populates="supplier_orders")
    phones: Mapped[List["Phones"]] = relationship("Phones", back_populates="supplier_order")
    supplier_order_details: Mapped[List["SupplierOrderDetails"]] = relationship("SupplierOrderDetails", back_populates="supplier_order")


class SupplierOrderDetails(Base):
    __tablename__ = "supplier_order_details"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("models.id"))
    accessory_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("accessories.id"))
    quantity: Mapped[Optional[int]] = mapped_column(Integer)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    supplier_order_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("supplier_orders.id"))
    
    model: Mapped[Optional["Models"]] = relationship("Models", back_populates="supplier_order_details")
    accessory: Mapped[Optional["Accessories"]] = relationship("Accessories", back_populates="supplier_order_details")
    supplier_order: Mapped[Optional["SupplierOrders"]] = relationship("SupplierOrders", back_populates="supplier_order_details")


class ModelName(Base):
    __tablename__ = "model_name"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    models: Mapped[List["Models"]] = relationship("Models", back_populates="model_name")
    accessories_models: Mapped[List["AccessoriesModel"]] = relationship("AccessoriesModel", back_populates="model_name")


class Storage(Base):
    __tablename__ = "storage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    storage: Mapped[Optional[int]] = mapped_column(Integer)
    models: Mapped[List["Models"]] = relationship("Models", back_populates="storage")


class Colors(Base):
    __tablename__ = "colors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    color_name: Mapped[Optional[str]] = mapped_column(String(255))
    models: Mapped[List["Models"]] = relationship("Models", back_populates="color")


class ModelNumber(Base):
    __tablename__ = "model_number"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    phones: Mapped[List["Phones"]] = relationship("Phones", back_populates="model_number")


class Models(Base):
    __tablename__ = "models"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("model_name.id"))
    storage_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("storage.id"))
    color_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("colors.id"))
    image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    model_name: Mapped[Optional["ModelName"]] = relationship("ModelName", back_populates="models")
    storage: Mapped[Optional["Storage"]] = relationship("Storage", back_populates="models")
    color: Mapped[Optional["Colors"]] = relationship("Colors", back_populates="models")
    phones: Mapped[List["Phones"]] = relationship("Phones", back_populates="model")
    supplier_order_details: Mapped[List["SupplierOrderDetails"]] = relationship("SupplierOrderDetails", back_populates="model")
    retail_prices_phones: Mapped[List["RetailPricesPhones"]] = relationship("RetailPricesPhones", back_populates="model")


class Phones(Base):
    __tablename__ = "phones"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(255))
    model_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("models.id"))
    supplier_order_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("supplier_orders.id"))
    model_number_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("model_number.id"))
    purchase_price: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    technical_status: Mapped[Optional[TechStatus]] = mapped_column(Enum(TechStatus, native_enum=False)) # <-- ИЗМЕНЕНИЕ
    commercial_status: Mapped[Optional[CommerceStatus]] = mapped_column(Enum(CommerceStatus, native_enum=False)) # <-- ИЗМЕНЕНИЕ
    added_date: Mapped[Optional[date]] = mapped_column(Date)
    
    model: Mapped[Optional["Models"]] = relationship("Models", back_populates="phones")
    supplier_order: Mapped[Optional["SupplierOrders"]] = relationship("SupplierOrders", back_populates="phones")
    model_number: Mapped[Optional["ModelNumber"]] = relationship("ModelNumber", back_populates="phones")
    device_inspections: Mapped[List["DeviceInspection"]] = relationship("DeviceInspection", back_populates="phone")
    movement_logs: Mapped[List["PhoneMovementLog"]] = relationship("PhoneMovementLog", back_populates="phone")
    repairs: Mapped[List["Repairs"]] = relationship("Repairs", back_populates="phone")


class Roles(Base):
    __tablename__ = "roles"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_name: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    users: Mapped[List["Users"]] = relationship("Users", back_populates="role")
    role_permissions: Mapped[List["RolePermissions"]] = relationship("RolePermissions", back_populates="role")


class Users(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    role_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("roles.id"))
    active: Mapped[Optional[bool]] = mapped_column(Boolean)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    last_name: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Relationships
    role: Mapped[Optional["Roles"]] = relationship("Roles", back_populates="users")
    device_inspections: Mapped[List["DeviceInspection"]] = relationship("DeviceInspection", back_populates="user")
    sales: Mapped[List["Sales"]] = relationship("Sales", back_populates="user")


class Permissions(Base):
    __tablename__ = "permissions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    role_permissions: Mapped[List["RolePermissions"]] = relationship("RolePermissions", back_populates="permission")


class RolePermissions(Base):
    __tablename__ = "role_permissions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("roles.id"))
    permission_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("permissions.id"))
    
    # Relationships
    role: Mapped[Optional["Roles"]] = relationship("Roles", back_populates="role_permissions")
    permission: Mapped[Optional["Permissions"]] = relationship("Permissions", back_populates="role_permissions")


class ChecklistItems(Base):
    __tablename__ = "checklist_items"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    inspection_results: Mapped[List["InspectionResults"]] = relationship("InspectionResults", back_populates="checklist_item")


class DeviceInspection(Base):
    __tablename__ = "device_inspection"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("phones.id"))
    inspection_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    
    # Relationships
    phone: Mapped[Optional["Phones"]] = relationship("Phones", back_populates="device_inspections")
    user: Mapped[Optional["Users"]] = relationship("Users", back_populates="device_inspections")
    inspection_results: Mapped[List["InspectionResults"]] = relationship("InspectionResults", back_populates="device_inspection")
    battery_tests: Mapped[List["BatteryTest"]] = relationship("BatteryTest", back_populates="device_inspection")


class InspectionResults(Base):
    __tablename__ = "inspection_results"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_inspection_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("device_inspection.id"))
    checklist_item_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("checklist_items.id"))
    result: Mapped[Optional[bool]] = mapped_column(Boolean)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    device_inspection: Mapped[Optional["DeviceInspection"]] = relationship("DeviceInspection", back_populates="inspection_results")
    checklist_item: Mapped[Optional["ChecklistItems"]] = relationship("ChecklistItems", back_populates="inspection_results")


class BatteryTest(Base):
    __tablename__ = "battery_test"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_inspection_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("device_inspection.id"))
    start_time: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    start_battery_level: Mapped[Optional[int]] = mapped_column(Integer)
    end_time: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    end_battery_level: Mapped[Optional[int]] = mapped_column(Integer)
    test_duration: Mapped[Optional[str]] = mapped_column(Interval)
    battery_drain: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    
    # Relationships
    device_inspection: Mapped[Optional["DeviceInspection"]] = relationship("DeviceInspection", back_populates="battery_tests")


class CategoryAccessories(Base):
    __tablename__ = "category_accessories"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Relationships
    accessories: Mapped[List["Accessories"]] = relationship("Accessories", back_populates="category_accessory")


class Accessories(Base):
    __tablename__ = "accessories"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_accessory_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("category_accessories.id"))
    name: Mapped[Optional[str]] = mapped_column(String(255))
    barcode: Mapped[Optional[str]] = mapped_column(String(255))
    purchase_price: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    
    # Relationships
    category_accessory: Mapped[Optional["CategoryAccessories"]] = relationship("CategoryAccessories", back_populates="accessories")
    supplier_order_details: Mapped[List["SupplierOrderDetails"]] = relationship("SupplierOrderDetails", back_populates="accessory")
    retail_price_accessories: Mapped[List["RetailPriceAccessories"]] = relationship("RetailPriceAccessories", back_populates="accessory")
    accessories_models: Mapped[List["AccessoriesModel"]] = relationship("AccessoriesModel", back_populates="accessory")
    waiting_rooms: Mapped[List["WaitingRoom"]] = relationship("WaitingRoom", back_populates="accessory")


class RetailPricesPhones(Base):
    __tablename__ = "retail_prices_phones"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("models.id"))
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    date: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    
    # Relationships
    model: Mapped[Optional["Models"]] = relationship("Models", back_populates="retail_prices_phones")


class RetailPriceAccessories(Base):
    __tablename__ = "retail_price_accessories"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accessory_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("accessories.id"))
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    date: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    
    # Relationships
    accessory: Mapped[Optional["Accessories"]] = relationship("Accessories", back_populates="retail_price_accessories")


class AccessoriesModel(Base):
    __tablename__ = "accessories_model"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accessory_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("accessories.id"))
    model_name_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("model_name.id"))
    
    # Relationships
    accessory: Mapped[Optional["Accessories"]] = relationship("Accessories", back_populates="accessories_models")
    model_name: Mapped[Optional["ModelName"]] = relationship("ModelName", back_populates="accessories_models")


class ProductType(Base):
    __tablename__ = "product_type"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))  # "phone", "accessory", etc.
    #table_name: Mapped[Optional[str]] = mapped_column(String(255))  # "phones", "accessories", etc.
    
    # Relationships
    warehouses: Mapped[List["Warehouse"]] = relationship("Warehouse", back_populates="product_type")


class Shops(Base):
    __tablename__ = "shops"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    address: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    warehouses: Mapped[List["Warehouse"]] = relationship("Warehouse", back_populates="shop")


class Warehouse(Base):
    __tablename__ = "warehouse"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_type_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("product_type.id"))
    product_id: Mapped[Optional[int]] = mapped_column(Integer)  # ID товара в соответствующей таблице
    quantity: Mapped[Optional[int]] = mapped_column(Integer)
    shop_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("shops.id"))
    storage_location: Mapped[Optional[EnumShop]] = mapped_column(Enum(EnumShop, native_enum=False))
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    added_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Relationships
    product_type: Mapped[Optional["ProductType"]] = relationship("ProductType", back_populates="warehouses")
    shop: Mapped[Optional["Shops"]] = relationship("Shops", back_populates="warehouses")
    sale_details: Mapped[List["SaleDetails"]] = relationship("SaleDetails", back_populates="warehouse")
    user: Mapped[Optional["Users"]] = relationship("Users")
    
    # Hybrid properties для получения товара
    def get_product(self, session):
        """Получает товар из соответствующей таблицы на основе product_type_id и product_id"""
        if self.product_type_id == 1:  # Телефоны
            return session.query(Phones).filter(Phones.id == self.product_id).first()
        elif self.product_type_id == 2:  # Аксессуары
            return session.query(Accessories).filter(Accessories.id == self.product_id).first()
        return None
    
    def set_product(self, product):
        """Устанавливает товар и автоматически определяет product_type_id"""
        if isinstance(product, Phones):
            self.product_type_id = 1  # ID для телефонов
            self.product_id = product.id
        elif isinstance(product, Accessories):
            self.product_type_id = 2  # ID для аксессуаров
            self.product_id = product.id


class Currency(Base):
    __tablename__ = "currency"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    sales: Mapped[List["Sales"]] = relationship("Sales", back_populates="currency")
    cash_flows: Mapped[List["CashFlow"]] = relationship("CashFlow", back_populates="currency")


class Accounts(Base):
    __tablename__ = "accounts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Relationships
    sale_payments: Mapped[List["SalePayments"]] = relationship("SalePayments", back_populates="account") 
    cash_flows: Mapped[List["CashFlow"]] = relationship("CashFlow", back_populates="account")


class Customers(Base):
    __tablename__ = "customers"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    number: Mapped[Optional[str]] = mapped_column(String(255))
    source_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("traffic_sources.id"), nullable=True)
    referrer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("customers.id"), nullable=True)

    # Relationships
    sales: Mapped[List["Sales"]] = relationship("Sales", back_populates="customer")
    source: Mapped[Optional["TrafficSource"]] = relationship("TrafficSource", back_populates="customers")
    # Связь "сам на себя" для реферальной программы
    referrer: Mapped[Optional["Customers"]] = relationship("Customers", remote_side=[id], backref="referrals")

class Sales(Base):
    __tablename__ = "sales"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sale_date: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    customer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("customers.id"), nullable=True)
    delivery_method: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    discount: Mapped[Optional[Decimal]] = mapped_column(Numeric, default=0)
    payment_status: Mapped[Optional[StatusPay]] = mapped_column(Enum(StatusPay, native_enum=False))
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    cash_received: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True) # Оставляем для сдачи
    change_given: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True) # Оставляем для сдачи
    currency_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("currency.id"))
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    customer: Mapped["Customers"] = relationship("Customers", back_populates="sales")
    user: Mapped[Optional["Users"]] = relationship("Users", back_populates="sales")
    sale_details: Mapped[List["SaleDetails"]] = relationship("SaleDetails", back_populates="sale")
    payments: Mapped[List["SalePayments"]] = relationship("SalePayments", back_populates="sale") 
    currency: Mapped[Optional["Currency"]] = relationship("Currency", back_populates="sales")


class SalePayments(Base):
    __tablename__ = "sale_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sale_id: Mapped[int] = mapped_column(Integer, ForeignKey("sales.id"))
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    payment_method: Mapped[EnumPayment] = mapped_column(Enum(EnumPayment, name="enumpayment", create_type=False))
    payment_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Relationships
    sale: Mapped["Sales"] = relationship("Sales", back_populates="payments")
    account: Mapped["Accounts"] = relationship("Accounts", back_populates="sale_payments") 




class SaleDetails(Base):
    __tablename__ = "sale_details"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sale_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sales.id"))
    warehouse_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("warehouse.id"))
    quantity: Mapped[Optional[int]] = mapped_column(Integer)
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    profit: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    
    # Relationships
    sale: Mapped[Optional["Sales"]] = relationship("Sales", back_populates="sale_details")
    warehouse: Mapped[Optional["Warehouse"]] = relationship("Warehouse", back_populates="sale_details")


class Counterparties(Base):
    __tablename__ = "counterparties"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    type: Mapped[Optional[str]] = mapped_column(String(255))
    contact_details: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    cash_flows: Mapped[List["CashFlow"]] = relationship("CashFlow", back_populates="counterparty")


class OperationCategories(Base):
    __tablename__ = "operation_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    type: Mapped[Optional[str]] = mapped_column(String(10)) # <--- ДОБАВЬТЕ ЭТУ СТРОКУ

    # Relationships
    cash_flows: Mapped[List["CashFlow"]] = relationship("CashFlow", back_populates="operation_category")

class CashFlow(Base):
    __tablename__ = "cash_flow"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    operation_categories_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operation_categories.id"))
    counterparty_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("counterparties.id"), nullable=True)
    account_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("accounts.id"))
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    currency_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("currency.id"))
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    operation_category: Mapped[Optional["OperationCategories"]] = relationship("OperationCategories", back_populates="cash_flows")
    counterparty: Mapped[Optional["Counterparties"]] = relationship("Counterparties", back_populates="cash_flows")
    account: Mapped[Optional["Accounts"]] = relationship("Accounts", back_populates="cash_flows")
    currency: Mapped[Optional["Currency"]] = relationship("Currency", back_populates="cash_flows")


class WaitingRoom(Base):
    __tablename__ = "waiting_room"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accessory_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("accessories.id"))
    quantity: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Relationships
    accessory: Mapped[Optional["Accessories"]] = relationship("Accessories", back_populates="waiting_rooms")

class Repairs(Base):
    __tablename__ = "repairs" # Таблица будет переименована

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_id: Mapped[int] = mapped_column(Integer, ForeignKey("phones.id"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))

    # Новые поля для типа и стоимости ремонта
    repair_type: Mapped[RepairType] = mapped_column(Enum(RepairType, native_enum=False))
    estimated_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    final_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    service_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    payment_status: Mapped[Optional[StatusPay]] = mapped_column(Enum(StatusPay, native_enum=False), nullable=True)

    # Старые поля
    date_accepted: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    customer_name: Mapped[str] = mapped_column(String(255))
    customer_phone: Mapped[str] = mapped_column(String(50))
    problem_description: Mapped[str] = mapped_column(Text)
    device_condition: Mapped[str] = mapped_column(Text)
    included_items: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    date_returned: Mapped[Optional[datetime]] = mapped_column(DateTime)
    work_performed: Mapped[Optional[str]] = mapped_column(Text)

    phone: Mapped["Phones"] = relationship("Phones")
    user: Mapped["Users"] = relationship("Users")
    loaner_logs: Mapped[list["LoanerLog"]] = relationship("LoanerLog", back_populates="repair")

class Notes(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))

    # Связи
    created_by: Mapped["Users"] = relationship("Users", foreign_keys=[created_by_user_id])
    completed_by: Mapped[Optional["Users"]] = relationship("Users", foreign_keys=[completed_by_user_id])

# Вспомогательные функции для работы с полиморфными связями
class WarehouseService:
    """Сервис для работы с полиморфными связями в Warehouse"""
    
    PRODUCT_TYPE_MAPPING = {
        1: {'model': 'Phones', 'name': 'PHONE'}, # Обновил имена на заглавные
        2: {'model': 'Accessories', 'name': 'ACCESSORY'}
    }
    
    @staticmethod
    def get_product_by_warehouse(session, warehouse: Warehouse) -> Union[Phones, Accessories, None]:
        """Получает товар из соответствующей таблицы"""
        if not warehouse.product_type_id or not warehouse.product_id:
            return None
            
        if warehouse.product_type_id == 1:  # Телефоны
            return session.query(Phones).filter(Phones.id == warehouse.product_id).first()
        elif warehouse.product_type_id == 2:  # Аксессуары
            return session.query(Accessories).filter(Accessories.id == warehouse.product_id).first()
        return None
    
    @staticmethod
    def create_warehouse_record(session, product: Union[Phones, Accessories], 
                              quantity: int, shop_id: int, 
                              storage_location: EnumShop) -> Warehouse:
        """Создает запись в складе для указанного товара"""
        warehouse = Warehouse(
            quantity=quantity,
            shop_id=shop_id,
            storage_location=storage_location,
            added_date=date.today()
        )
        
        if isinstance(product, Phones):
            warehouse.product_type_id = 1
            warehouse.product_id = product.id
        elif isinstance(product, Accessories):
            warehouse.product_type_id = 2
            warehouse.product_id = product.id
        else:
            raise ValueError(f"Неподдерживаемый тип товара: {type(product)}")
            
        return warehouse
    
    @staticmethod
    def get_warehouse_items_by_type(session, product_type_id: int):
        """Получает все товары на складе определенного типа"""
        return session.query(Warehouse).filter(
            Warehouse.product_type_id == product_type_id
        ).all()
    
    @staticmethod
    def get_product_details_with_warehouse(session, warehouse: Warehouse) -> dict:
        """Получает детальную информацию о товаре со складскими данными"""
        product = WarehouseService.get_product_by_warehouse(session, warehouse)
        if not product:
            return {}
            
        result = {
            'warehouse_id': warehouse.id,
            'quantity': warehouse.quantity,
            'storage_location': warehouse.storage_location.value if warehouse.storage_location else None,
            'added_date': warehouse.added_date,
            'product_type': WarehouseService.PRODUCT_TYPE_MAPPING.get(warehouse.product_type_id, {}).get('name'),
            'product': {}
        }
        
        if isinstance(product, Phones):
            result['product'] = {
                'id': product.id,
                'serial_number': product.serial_number,
                'technical_status': product.technical_status.value if product.technical_status else None,
                'commercial_status': product.commercial_status.value if product.commercial_status else None,
                'model': None,
                'model_number': None
            }
            
            # Получаем связанные данные
            if product.model:
                model_info = {}
                if product.model.model_name:
                    model_info['name'] = product.model.model_name.name
                if product.model.storage:
                    model_info['storage'] = product.model.storage.storage
                if product.model.color:
                    model_info['color'] = product.model.color.color_name
                result['product']['model'] = model_info
                
            if product.model_number:
                result['product']['model_number'] = product.model_number.name
                
        elif isinstance(product, Accessories):
            result['product'] = {
                'id': product.id,
                'name': product.name,
                'barcode': product.barcode,
                'category': product.category_accessory.name if product.category_accessory else None
            }
            
        return result

# --- ФУНКЦИИ ФОРМАТИРОВАНИЯ ДЛЯ ОТОБРАЖЕНИЯ ---
# Вы можете разместить это в отдельном файле, например, app/utils/formatters.py
# и импортировать сюда.
def format_enum_value_for_display(value: str) -> str:
    """
    Форматирует строковое значение Enum для отображения,
    делая первую букву заглавной, а остальные строчными,
    и заменяя подчеркивания на пробелы.
    
    Примеры:
    "УПАКОВАН" -> "Упакован"
    "НА УПАКОВКЕ" -> "На упаковке"
    "НЕ ГОТОВ К ПРОДАЖЕ" -> "Не готов к продаже"
    "КРЕДИТ/РАССРОЧКА" -> "Кредит/Рассрочка"
    """
    if not value:
        return ""
    
    # Обработка специальных случаев
    if value == "КРЕДИТ/РАССРОЧКА":
        return "Кредит/Рассрочка"
    
    # Заменяем подчеркивания на пробелы и приводим к нижнему регистру
    formatted_value = value.replace('_', ' ').lower()
    
    # Делаем каждое слово с заглавной буквы, затем меняем на первую букву заглавную
    # Или просто делаем первую букву всего предложения заглавной, остальное маленькими
    
    # Для "НА УПАКОВКЕ" -> "На упаковке"
    # Для "НЕ ГОТОВ К ПРОДАЖЕ" -> "Не готов к продаже"
    # Это более сложная логика, так как просто .capitalize() не сработает для нескольких слов
    
    # Вариант 1: Каждое слово с заглавной (title case)
    # return formatted_value.title() # "На Упаковке", "Не Готов К Продаже" - может не всегда подходить
    
    # Вариант 2: Первая буква всего выражения заглавная, остальное маленькие
    # return formatted_value.capitalize() # "На упаковке", но "не готов к продаже" (первое слово)
    
    # Более надежный вариант: разбиваем на слова, делаем первое слово с заглавной, остальные маленькие.
    # Или просто делаем первую букву всей строки заглавной
    
    # Если вы хотите, чтобы только первое слово начиналось с заглавной, а остальные были строчными
    words = formatted_value.split(' ')
    if words:
        words[0] = words[0].capitalize()
    return ' '.join(words)


def format_storage_for_display(storage_value_raw: Optional[Union[int, str]]) -> Optional[str]: # <--- ИЗМЕНЕНО: Добавлено Union[int, str]
    """
    Форматирует значение памяти (целое число или строку) в строку с правильной единицей измерения (GB/TB).
    Пытается извлечь число из строки, если это строка.
    Пример: 1024 -> "1TB", 128 -> "128GB", "128GB" -> "128GB", "1TB" -> "1TB"
    """
    if storage_value_raw is None:
        return None
    
    # Попытка преобразовать входное значение в число
    numeric_value: Optional[int] = None
    if isinstance(storage_value_raw, int):
        numeric_value = storage_value_raw
    elif isinstance(storage_value_raw, str):
        # Попытаемся извлечь число из строки, удалив нечисловые символы в конце
        try:
            # Удаляем 'GB', 'TB' и другие символы, оставляя только число
            clean_value = ''.join(filter(str.isdigit, storage_value_raw))
            if clean_value:
                numeric_value = int(clean_value)
            else:
                return storage_value_raw # Если не удалось извлечь число, возвращаем как есть
        except ValueError:
            return storage_value_raw # Если не удалось преобразовать в int, возвращаем как есть
    
    if numeric_value is None: # Если после всех попыток число не получено
        return None 

    # Теперь применяем логику GB/TB к числовому значению
    if numeric_value >= 1024 and (numeric_value % 1024 == 0): # Добавлено (numeric_value % 1024 == 0) для точных TB
        return f"{numeric_value // 1024}TB" # Используем целочисленное деление
    else:
        return f"{numeric_value}GB"
class PhoneMovementLog(Base):
    __tablename__ = "phone_movement_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_id: Mapped[int] = mapped_column(Integer, ForeignKey("phones.id"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    event_type: Mapped[PhoneEventType] = mapped_column(Enum(PhoneEventType, native_enum=False))
    details: Mapped[Optional[str]] = mapped_column(Text)

    # Связи
    phone: Mapped["Phones"] = relationship("Phones", back_populates="movement_logs")
    user: Mapped["Users"] = relationship("Users")
    
class TrafficSource(Base):
    __tablename__ = "traffic_sources"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    
    # Связь с покупателями, которые пришли из этого источника
    customers: Mapped[List["Customers"]] = relationship(
        "Customers", 
        foreign_keys="[Customers.source_id]", # <-- ДОБАВЬТЕ ЭТУ СТРОКУ
        back_populates="source"
    )

class LoanerLog(Base):
    __tablename__ = "loaner_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repair_id: Mapped[int] = mapped_column(Integer, ForeignKey("repairs.id"))
    loaner_phone_id: Mapped[int] = mapped_column(Integer, ForeignKey("phones.id"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    
    date_issued: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    date_returned: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Связи для удобного доступа
    repair: Mapped["Repairs"] = relationship("Repairs")
    loaner_phone: Mapped["Phones"] = relationship("Phones")
    user: Mapped["Users"] = relationship("Users")

class EmployeeShifts(Base):
    __tablename__ = "employee_shifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    shift_start: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    shift_end: Mapped[Optional[datetime]] = mapped_column(DateTime)

    user: Mapped["Users"] = relationship("Users")

class Payroll(Base):
    __tablename__ = "payroll"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    payment_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    amount: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped["Users"] = relationship("Users")
    account: Mapped["Accounts"] = relationship("Accounts")

class FinancialSnapshot(Base):
    __tablename__ = "financial_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    cash_balance: Mapped[Decimal] = mapped_column(Numeric, default=0)
    inventory_value: Mapped[Decimal] = mapped_column(Numeric, default=0)
    goods_in_transit_value: Mapped[Decimal] = mapped_column(Numeric, default=0)
    total_assets: Mapped[Decimal] = mapped_column(Numeric, default=0)
    
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True) # Для хранения деталей расчета
