# app/bot.py
import os
from dotenv import load_dotenv
load_dotenv()
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from decimal import Decimal
from sqlalchemy.orm import joinedload, selectinload 
from sqlalchemy import select
from typing import Callable, Dict, Any, Awaitable
from aiogram.dispatcher.middlewares.base import BaseMiddleware

from . import crud, schemas, models
from .database import AsyncSessionLocal



# --- НАСТРОЙКИ ---
# Замените на ваш токен или лучше загрузите из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

admin_keyboard = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📦 Заказы поставщиков")],
    [KeyboardButton(text="📈 Аналитика"), KeyboardButton(text="💰 Финансы")],
], resize_keyboard=True, input_field_placeholder="Выберите действие:")

# Клавиатура для Технического специалиста
tech_keyboard = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="⚙️ Инспекция")],
], resize_keyboard=True, input_field_placeholder="Выберите действие:")

# Клавиатура для Продавца
sales_keyboard = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📦 Заказы поставщиков"), KeyboardButton(text="📈 Аналитика")],
    [KeyboardButton(text="💰 Финансы"), KeyboardButton(text="⚙️ Инспекция")]
], resize_keyboard=True, input_field_placeholder="Выберите действие:")

@dp.message(Command('whoami'))
async def who_am_i(message: Message):
    """Проверяет, может ли бот найти пользователя по его ID в своей БД."""
    user_id_to_check = message.from_user.id

    async with AsyncSessionLocal() as session:
        stmt = select(models.Users).options(selectinload(models.Users.role)).filter(models.Users.telegram_id == user_id_to_check)
        result = await session.execute(stmt)
        user = result.scalars().first()

    if user:
        await message.answer(f"✅ Я нашел вас в базе!\nUsername: {user.username}\nРоль: {user.role.role_name if user.role else 'Нет роли'}")
    else:
        await message.answer(f"❌ Не могу найти пользователя с Telegram ID {user_id_to_check} в базе данных, к которой я подключен.")

# --- ЛОГИКА ОПЛАТЫ (МАШИНА СОСТОЯНИЙ) ---
class Payment(StatesGroup):
    waiting_for_amount = State()
    waiting_for_account = State()

class DbUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: types.Update,
        data: Dict[str, Any]
    ) -> Any:

        from_user = None
        if event.message:
            from_user = event.message.from_user
        elif event.callback_query:
            from_user = event.callback_query.from_user

        # --- НАЧАЛО БЛОКА ДИАГНОСТИКИ ---
        print("\n--- DEBUG MIDDLEWARE ---")
        if from_user:
            print(f"Получено событие от Telegram ID: {from_user.id}") # <-- НОВАЯ СТРОКА
        else:
            print("Не удалось извлечь ID пользователя из события.")
        # --- КОНЕЦ БЛОКА ДИАГНОСТИКИ ---

        db_user = None
        if from_user:
            async with AsyncSessionLocal() as session:
                stmt = select(models.Users).options(
                    joinedload(models.Users.role)
                    .joinedload(models.Roles.role_permissions)
                    .joinedload(models.RolePermissions.permission)
                ).filter(models.Users.telegram_id == from_user.id)
                result = await session.execute(stmt)
                db_user = result.unique().scalars().first()

        if db_user:
            print(f"Найден пользователь в БД: {db_user.username}")
        else:
            print("Пользователь в БД НЕ НАЙДЕН.")
        print("--- END DEBUG ---\n")

        data['db_user'] = db_user
        return await handler(event, data)
    
# Регистрируем Middleware
dp.update.middleware.register(DbUserMiddleware())

def user_has_permission(user: models.Users, permission_code: str) -> bool:
    if not user or not user.role or not hasattr(user.role, 'role_permissions'):
        return False
    user_permissions = {rp.permission.code for rp in user.role.role_permissions if rp.permission}
    return permission_code in user_permissions

@dp.message(Command('cancel'))
async def cancel_handler(message: Message, state: FSMContext):
    """Отменяет любое текущее действие."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активных действий для отмены.")
        return

    await state.clear()
    await message.answer("Действие отменено.")

# --- ОБРАБОТЧИКИ КОМАНД ---
@dp.message(CommandStart())
async def send_welcome(message: Message, db_user: models.Users):
    """
    Отправляет приветствие и показывает клавиатуру в зависимости от роли.
    """
    if not db_user:
        await message.answer(
            "Привет! Я бот магазина resale.\n"
            "Чтобы привязать ваш аккаунт, попросите руководителя сделать это для вас."
        )
        return

    # Проверяем права и выбираем нужную клавиатуру
    if user_has_permission(db_user, 'manage_inventory'): # Право есть у Админа/Менеджера
        await message.answer(f"Добро пожаловать, {db_user.name}! Выберите действие:", reply_markup=admin_keyboard)
    elif user_has_permission(db_user, 'perform_inspections'): # Право есть у Техника
        await message.answer(f"Добро пожаловать, {db_user.name}! Выберите действие:", reply_markup=tech_keyboard)
    elif user_has_permission(db_user, 'perform_sales'):
        await message.answer(f"Добро пожаловать, {db_user.name}! Выберите действие:", reply_markup=sales_keyboard)
    else:
        await message.answer(f"Добро пожаловать, {db_user.name}! У вас нет доступных действий.")



@dp.message(Command('link'))
async def link_user_account(message: Message, command: CommandObject, db_user: models.Users):
    """
    Привязывает Telegram аккаунт к пользователю в системе.
    Использование: ответьте на пересланное сообщение от пользователя командой /link <логин_пользователя>
    """
    # 1. Проверяем, есть ли у отправителя права администратора
    if not db_user or not user_has_permission(db_user, 'manage_users'):
        await message.reply("⛔ У вас недостаточно прав для выполнения этой команды.")
        return

    # 2. Проверяем, что это ответ на пересланное сообщение
    if not message.reply_to_message or not message.reply_to_message.forward_from:
        await message.reply("Ошибка: Эту команду нужно использовать как ответ на пересланное сообщение от пользователя.")
        return

    # 3. Проверяем, что указан логин для привязки
    app_username = command.args
    if not app_username:
        await message.reply("Пожалуйста, укажите логин пользователя из веб-приложения. Пример: /link ivanov_ivan")
        return

    # 4. Извлекаем данные и обновляем запись в БД
    telegram_id_to_link = message.reply_to_message.forward_from.id
    telegram_name = message.reply_to_message.forward_from.full_name

    async with AsyncSessionLocal() as session:
        # Находим пользователя в БД по логину из веб-приложения
        user_to_link = await crud.get_user_by_username(session, app_username)

        if not user_to_link:
            await message.reply(f"Пользователь с логином '{app_username}' не найден в базе данных.")
            return

        # Присваиваем ему Telegram ID и сохраняем
        user_to_link.telegram_id = telegram_id_to_link
        await session.commit()

        await message.reply(f"✅ Аккаунт Telegram пользователя '{telegram_name}' успешно привязан к сотруднику '{app_username}'.")



@dp.message(F.text == "📦 Заказы поставщиков")
async def list_pending_orders_handler(message: Message, db_user: models.Users):
    """Показывает заказы, ожидающие оплаты (реагирует на кнопку)."""

    # Проверяем, что у пользователя есть право просматривать заказы
    if not user_has_permission(db_user, 'receive_supplier_orders'):
        await message.answer("⛔ У вас недостаточно прав для просмотра заказов.")
        return
    
    """Показывает заказы, ожидающие оплаты."""
    async with AsyncSessionLocal() as session:
        orders = await crud.get_supplier_orders(session)
        pending_orders = [
            o for o in orders 
            if o.status.value == 'ПОЛУЧЕН' and o.delivery_payment_status.value != 'ОПЛАЧЕН'
        ]

        if not pending_orders:
            await message.answer("Заказов, ожидающих оплаты, нет.")
            return

        for order in pending_orders:
            total_cost = sum(d.price * d.quantity for d in order.supplier_order_details)
            supplier_name = order.supplier.name if order.supplier else "Неизвестный поставщик"

            text = (
                f"📦 **Заказ ID: {order.id}**\n"
                f"Поставщик: {supplier_name}\n"
                f"Сумма: **{total_cost:.2f} руб.**"
            )

            # Создаем кнопку "Оплатить" для каждого заказа
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Оплатить доставку", callback_data=f"pay_{order.id}")]
            ])
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# --- ОБРАБОТЧИКИ КНОПОК И ВВОДА ДАННЫХ ---
@dp.callback_query(lambda c: c.data and c.data.startswith('pay_'))
async def process_payment_start(callback_query: types.CallbackQuery, state: FSMContext):
    """Начинает процесс оплаты после нажатия кнопки."""
    order_id = int(callback_query.data.split('_')[1])
    await state.update_data(order_id=order_id)
    await state.set_state(Payment.waiting_for_amount)
    await bot.send_message(callback_query.from_user.id, f"Введите сумму оплаты доставки для заказа ID: {order_id}")
    await callback_query.answer()

@dp.message(Payment.waiting_for_amount)
async def process_amount_entered(message: Message, state: FSMContext):
    """Обрабатывает введенную сумму и запрашивает счет."""
    try:
        amount = Decimal(message.text)
        await state.update_data(amount=amount)

        # Получаем список счетов для выбора
        async with AsyncSessionLocal() as session:
            accounts = await crud.get_accounts(session)

        if not accounts:
            await message.answer("В системе нет счетов для оплаты. Сначала добавьте их в приложении.")
            await state.clear()
            return

        # Создаем клавиатуру со счетами
        buttons = [[InlineKeyboardButton(text=acc.name, callback_data=f"account_{acc.id}")] for acc in accounts]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        await state.set_state(Payment.waiting_for_account)
        await message.answer("С какого счета произвести оплату?", reply_markup=keyboard)

    except (ValueError, TypeError):
        await message.reply("Пожалуйста, введите корректное числовое значение для суммы.")

@dp.callback_query(Payment.waiting_for_account)
async def process_account_selected(callback_query: types.CallbackQuery, state: FSMContext):
    """Завершает операцию после выбора счета."""
    account_id = int(callback_query.data.split('_')[1])
    user_data = await state.get_data()
    order_id = user_data['order_id']

    try:
        async with AsyncSessionLocal() as session:
            # --- НАЧАЛО ИЗМЕНЕНИЙ ---

            # 1. Находим сам заказ в базе данных
            order_to_update_stmt = select(models.SupplierOrders).where(models.SupplierOrders.id == order_id)
            order_result = await session.execute(order_to_update_stmt)
            order_to_update = order_result.scalars().first()

            if not order_to_update:
                await bot.send_message(callback_query.from_user.id, f"❌ Ошибка: Заказ ID {order_id} не найден.")
                await state.clear()
                await callback_query.answer()
                return

            # 2. Находим контрагента и категорию (этот код у вас уже есть)
            sdek_stmt = select(models.Counterparties).where(models.Counterparties.name == 'СДЭК')
            sdek_result = await session.execute(sdek_stmt)
            sdek_counterparty = sdek_result.scalars().first()

            if not sdek_counterparty:
                await bot.send_message(callback_query.from_user.id, "❌ Ошибка: Контрагент 'СДЭК' не найден в базе данных.")
                await state.clear()
                await callback_query.answer()
                return

            # 2. Находим категорию "Транспортные услуги"
            stmt = select(models.OperationCategories).where(models.OperationCategories.name == 'Транспортные услуги')
            result = await session.execute(stmt)
            transport_category = result.scalars().first()

            if not transport_category:
                await bot.send_message(callback_query.from_user.id, "❌ Ошибка: Категория 'Транспортные услуги' не найдена в базе.")
                await state.clear()
                await callback_query.answer()
                return

            # 3. Создаем финансовую операцию (этот код у вас уже есть)
            cash_flow_data = schemas.CashFlowCreate(
                operation_categories_id=transport_category.id,
                account_id=account_id,
                counterparty_id=sdek_counterparty.id,
                amount=-abs(user_data['amount']),
                description=f"Оплата доставки (СДЭК) по заказу ID {order_id}"
            )
            await crud.create_cash_flow(db=session, cash_flow=cash_flow_data, user_id=1) # Предполагая user_id=1 для системных операций

            # 4. Обновляем статус доставки у заказа и сохраняем
            order_to_update.delivery_payment_status = models.OrderPaymentStatus.ОПЛАЧЕН
            await session.commit()

            await bot.send_message(
                callback_query.from_user.id,
                f"✅ Оплата доставки (СДЭК) по заказу ID {user_data['order_id']} на сумму {user_data['amount']} руб. успешно проведена!"
            )
    except Exception as e:
        await bot.send_message(
            callback_query.from_user.id,
            f"❌ Произошла ошибка при оплате: {e}"
        )
    finally:
        await state.clear()
        await callback_query.answer()