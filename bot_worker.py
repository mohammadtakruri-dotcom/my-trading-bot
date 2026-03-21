import ccxt
import time
import requests
import os
from dotenv import load_dotenv

# تحميل .env
load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

TG_TOKEN = os.getenv("TG_TOKEN")
TG_ID = os.getenv("TG_ID")

SYMBOLS = os.getenv("SYMBOLS").split(",")

BUY_USDT = float(os.getenv("BUY_USDT", 20))
TP = float(os.getenv("TP", 0.5))
SL = float(os.getenv("SL", -1.2))


def tg(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_ID, "text": msg}
        )
    except:
        pass


exchange = ccxt.binance({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "enableRateLimit": True,
    "options": {"defaultType": "spot"}
})

positions = {}

def get_ohlc(symbol):
    ohlc = exchange.fetch_ohlcv(symbol, timeframe="1m", limit=50)
    return [x[4] for x in ohlc]

def ema(data, period):
    k = 2 / (period + 1)
    ema_val = data[0]
    for price in data:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val

def rsi(data):
    gains, losses = 0, 0
    for i in range(1, len(data)):
        diff = data[i] - data[i-1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100
    rs = gains / losses
    return 100 - (100 / (1 + rs))


print("🚀 BOT STARTED")
tg("🤖 البوت بدأ العمل")

while True:
    try:
        for sym in SYMBOLS:
            price = exchange.fetch_ticker(sym)["last"]

            closes = get_ohlc(sym)
            e9 = ema(closes[-20:], 9)
            e21 = ema(closes[-20:], 21)
            r = rsi(closes)

            # ===== BUY =====
            if sym not in positions:
                if e9 > e21 and r > 30:
                    qty = BUY_USDT / price
                    exchange.create_market_buy_order(sym, qty)

                    positions[sym] = price
                    msg = f"🟢 BUY {sym}\nPrice: {price}"
                    print(msg)
                    tg(msg)

            # ===== SELL =====
            else:
                entry = positions[sym]
                change = ((price - entry) / entry) * 100

                if change >= TP or change <= SL:
                    balance = exchange.fetch_balance()
                    base = sym.split("/")[0]
                    qty = balance["free"][base]

                    if qty > 0:
                        exchange.create_market_sell_order(sym, qty)

                        msg = f"🔴 SELL {sym}\nPrice: {price}\nP/L: {change:.2f}%"
                        print(msg)
                        tg(msg)

                        del positions[sym]

        time.sleep(5)

    except Exception as e:
        print("ERROR:", e)
        time.sleep(5)
