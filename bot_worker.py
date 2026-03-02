import os
import time
from datetime import datetime
import requests
from binance.client import Client
from binance.enums import SIDE_SELL, ORDER_TYPE_MARKET
from binance.helpers import round_step_size

# =======================
# ENV
# =======================
MODE = os.getenv("MODE", "paper")
SYMBOLS = os.getenv("SYMBOLS", "BTCUSDT,ETHFIUSDT").split(",")
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "3"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0"))
MIN_USDT_POSITION = float(os.getenv("MIN_USDT_POSITION", "5"))
SLEEP_SEC = int(os.getenv("SLEEP_SEC", "20"))

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

TG_TOKEN = os.getenv("TG_TOKEN")
TG_ID = os.getenv("TG_ID")

client = Client(API_KEY, API_SECRET)

# =======================
# Telegram
# =======================
def send_telegram(msg):
    if not TG_TOKEN or not TG_ID:
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TG_ID, "text": msg})

# =======================
def get_price(symbol):
    return float(client.get_symbol_ticker(symbol=symbol)["price"])

def get_balance(asset):
    bal = client.get_asset_balance(asset=asset)
    return float(bal["free"]) if bal else 0

def base_asset(symbol):
    return symbol.replace("USDT","")

def get_step(symbol):
    info = client.get_symbol_info(symbol)
    lot = next(f for f in info["filters"] if f["filterType"] == "LOT_SIZE")
    return float(lot["stepSize"])

def sell_market(symbol, qty):
    if MODE != "live":
        send_telegram(f"🟡 PAPER SELL {symbol} qty={qty}")
        return
    client.create_order(
        symbol=symbol,
        side=SIDE_SELL,
        type=ORDER_TYPE_MARKET,
        quantity=qty
    )
    send_telegram(f"🔴 SOLD {symbol} qty={qty}")

# =======================
ENTRY = {}

print("🚀 BOT STARTED")
send_telegram("🤖 Bot Started")

while True:
    try:
        for symbol in SYMBOLS:
            symbol = symbol.strip().upper()
            price = get_price(symbol)
            asset = base_asset(symbol)
            qty = get_balance(asset)

            if qty <= 0:
                continue

            value = qty * price
            if value < MIN_USDT_POSITION:
                continue

            if symbol not in ENTRY:
                ENTRY[symbol] = price
                send_telegram(f"📌 Tracking {symbol} at {price}")

            entry = ENTRY[symbol]
            pnl = ((price - entry) / entry) * 100

            print(f"{symbol} price={price} pnl={pnl:.2f}%")

            if pnl >= TAKE_PROFIT_PCT:
                step = get_step(symbol)
                qty = round_step_size(qty, step)
                sell_market(symbol, qty)
                ENTRY.pop(symbol, None)

            if STOP_LOSS_PCT > 0 and pnl <= -STOP_LOSS_PCT:
                step = get_step(symbol)
                qty = round_step_size(qty, step)
                sell_market(symbol, qty)
                ENTRY.pop(symbol, None)

        time.sleep(SLEEP_SEC)

    except Exception as e:
        print("Error:", e)
        send_telegram(f"❌ Error: {e}")
        time.sleep(10)
