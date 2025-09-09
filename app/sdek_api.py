# app/sdek_api.py
import httpx
import os
from fastapi import HTTPException
import json

SDEK_API_URL = "https://api.edu.cdek.ru/v2" # Тестовый контур
CLIENT_ID = os.getenv("SDEK_CLIENT_ID")
CLIENT_SECRET = os.getenv("SDEK_CLIENT_SECRET")

async def get_sdek_token():
    """Получает токен авторизации СДЭК."""
    auth_url = f"{SDEK_API_URL}/oauth/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(auth_url, data=payload)
            response.raise_for_status()
            return response.json()["access_token"]
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=500, detail=f"SDEK Auth Error: {e.response.text}")

async def calculate_sdek_delivery_cost(calculation_data: dict, token: str):
    """Рассчитывает стоимость доставки СДЭК."""
    calculator_url = f"{SDEK_API_URL}/calculator/tariff"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Формируем тело запроса для калькулятора
    calculator_payload = {
        "tariff_code": 483, # Ваш тариф "Посылка склад-склад"
        "from_location": {
            "address": calculation_data['from_location_address']
        },
        "to_location": {
            "code": 270
        },
        "packages": [{
            "weight": calculation_data['weight'],
            "length": calculation_data['length'],
            "width": calculation_data['width'],
            "height": calculation_data['height']
        }]
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(calculator_url, headers=headers, json=calculator_payload, timeout=20.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=400, detail=f"SDEK Calculator Error: {e.response.text}")


async def create_sdek_delivery_order(order_data: dict, token: str):
    """Создает заказ на доставку в СДЭК."""
    order_url = f"{SDEK_API_URL}/orders"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # --- НАЧАЛО ИЗМЕНЕНИЙ: Формируем содержимое посылки по вашим требованиям ---
    package_items = [{
        "name": "Телефон",          # Название товара
        "ware_key": "1",            # Артикул
        "payment": {"value": 2000}, # Оценочная стоимость
        "cost": 2000,               # Реальная стоимость
        "weight": order_data['weight'], # Вес этого товара равен общему весу посылки
        "amount": 1                 # Количество всегда 1
    }]
    # --- КОНЕЦ ИЗМЕНЕНИЙ ---

    sdek_payload = {
        "type": 1,
        "tariff_code": 483, # Тариф "Посылка склад-склад"
        "comment": f"Заказ от поставщика № {order_data['supplier_order_id']}",
        
        # Указываем код ПВЗ, куда нужно доставить
        "delivery_point": "ORN10", 

        "sender": {
            "name": order_data['sender_name'],
            "phones": [{"number": order_data['sender_phone']}]
        },
        "recipient": {
            "name": "Садыков Роман", # Теперь здесь ваше имя
            "phones": [{"number": "+79228758950"}] # и ваш телефон
        },
        "from_location": {
            "address": order_data['from_location_address']
        },
        # Блок to_location полностью удален, так как есть delivery_point
        "packages": [{
            "number": f"SUP-ORDER-{order_data['supplier_order_id']}",
            "weight": order_data['weight'],
            "length": order_data['length'],
            "width": order_data['width'],
            "height": order_data['height'],
            "items": package_items
        }]
    }

    print("\n" + "="*50)
    print("--- ОТПРАВКА В СДЭК ---")
    print(json.dumps(sdek_payload, indent=2, ensure_ascii=False))
    print("="*50 + "\n")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(order_url, headers=headers, json=sdek_payload, timeout=20.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print("\n" + "!"*50)
            print("--- ОШИБКА ОТ СДЭК ---")
            print(f"Статус код: {e.response.status_code}")
            print(f"Ответ: {e.response.text}")
            print("!"*50 + "\n")
            raise HTTPException(status_code=400, detail=f"Ошибка от API СДЭК: {e.response.text}")
