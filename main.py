from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import random
import asyncio
from typing import Dict, List, Optional

app = FastAPI()

# Хранение данных о курсах
crypto_data: Dict[str, Dict[str, List[float]]] = {
    "btc": {"prices": [], "timestamps": []},
    "eth": {"prices": [], "timestamps": []},
    "xrp": {"prices": [], "timestamps": []},
    "ltc": {"prices": [], "timestamps": []},
}

# Баланс пользователя
user_balance = {
    "main": 1000.0,  # Основной баланс
    "btc": 0.0,  # Баланс BTC
    "eth": 0.0,  # Баланс ETH
    "xrp": 0.0,  # Баланс XRP
    "ltc": 0.0,  # Баланс LTC
}

# История операций
trade_history: Dict[str, List[Dict]] = {
    "btc": [],
    "eth": [],
    "xrp": [],
    "ltc": [],
}


# Модель для данных запроса
class TradeRequest(BaseModel):
    action: str  # "buy" или "sell"
    amount: float  # Количество монет


# Генерация случайных данных для курса
def generate_crypto_data(crypto_id: str):
    last_price = crypto_data[crypto_id]["prices"][-1] if crypto_data[crypto_id]["prices"] else random.uniform(50, 200)
    new_price = last_price + random.uniform(-2, 2)

    crypto_data[crypto_id]["prices"].append(new_price)
    crypto_data[crypto_id]["timestamps"].append(len(crypto_data[crypto_id]["timestamps"]))

    # Ограничиваем данные до последних 60 секунд
    if len(crypto_data[crypto_id]["prices"]) > 60:
        crypto_data[crypto_id]["prices"] = crypto_data[crypto_id]["prices"][-60:]
        crypto_data[crypto_id]["timestamps"] = crypto_data[crypto_id]["timestamps"][-60:]

    return new_price


# Фоновая задача для генерации данных
async def generate_data_task():
    while True:
        for crypto_id in crypto_data.keys():
            generate_crypto_data(crypto_id)
        await asyncio.sleep(1)  # Обновление каждую секунду


# Запуск фоновой задачи при старте сервера
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(generate_data_task())


# WebSocket для обновления графика в реальном времени
@app.websocket("/ws/{crypto_id}")
async def websocket_endpoint(websocket: WebSocket, crypto_id: str):
    await websocket.accept()
    try:
        while True:
            if crypto_id not in crypto_data:
                await websocket.send_json({"error": "Crypto not found"})
                break

            await websocket.send_json({
                "crypto_id": crypto_id,
                "price": crypto_data[crypto_id]["prices"][-1],
                "timestamps": crypto_data[crypto_id]["timestamps"],
                "prices": crypto_data[crypto_id]["prices"],
                "balance": user_balance[crypto_id],  # Отправляем баланс монеты
                "main_balance": user_balance["main"],  # Отправляем основной баланс
                "history": trade_history[crypto_id],  # Отправляем историю операций
            })
            await asyncio.sleep(1)  # Отправка данных каждую секунду
    except WebSocketDisconnect:
        print("Client disconnected")


# API для покупки/продажи монет
@app.post("/trade/{crypto_id}")
async def trade(crypto_id: str, request: TradeRequest):
    if crypto_id not in crypto_data:
        raise HTTPException(status_code=404, detail="Crypto not found")

    if request.action not in ["buy", "sell"]:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'buy' or 'sell'.")

    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0.")

    price = crypto_data[crypto_id]["prices"][-1]
    cost = price * request.amount

    # Сохраняем старый баланс
    old_main_balance = user_balance["main"]
    old_coin_balance = user_balance[crypto_id]

    if request.action == "buy":
        if user_balance["main"] < cost:
            raise HTTPException(status_code=400, detail="Not enough funds")
        user_balance["main"] -= cost
        user_balance[crypto_id] += request.amount
    elif request.action == "sell":
        if user_balance[crypto_id] < request.amount:
            raise HTTPException(status_code=400, detail="Not enough coins")
        user_balance["main"] += cost
        user_balance[crypto_id] -= request.amount

    # Добавляем операцию в историю
    trade_history[crypto_id].insert(0, {
        "action": request.action,
        "price": price,
        "amount": request.amount,
        "old_main_balance": old_main_balance,
        "new_main_balance": user_balance["main"],
        "old_coin_balance": old_coin_balance,
        "new_coin_balance": user_balance[crypto_id],
    })

    # Ограничиваем историю до последних 10 операций
    if len(trade_history[crypto_id]) > 10:
        trade_history[crypto_id] = trade_history[crypto_id][:10]

    return {
        "crypto_id": crypto_id,
        "action": request.action,
        "amount": request.amount,
        "price": price,
        "main_balance": user_balance["main"],
        "coin_balance": user_balance[crypto_id],
        "history": trade_history[crypto_id],
    }


# Статические файлы (HTML, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")


# Веб-страница
@app.get("/")
async def get():
    with open("static/index.html") as f:
        return HTMLResponse(content=f.read())