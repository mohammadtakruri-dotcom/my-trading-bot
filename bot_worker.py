import ccxt
import time

# ========= CONFIG =========
API_KEY = "PUT_YOUR_KEY"
API_SECRET = "PUT_YOUR_SECRET"

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT"]

BUY_USDT = 20
TP = 0.5   # 0.5%
SL = -1.2  # -1.2%

# ==========================

exchange = ccxt.binance({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "enableRateLimit": True,
    "options": {"defaultType": "spot"}
})

positions = {}

# ========= INDICATORS =========
def get_ohlc(symbol):
    ohlc = exchange.fetch_ohlcv(symbol, timeframe="1m", limit=50)
    closes = [x[4] for x in ohlc]
    return closes

def ema(data, period):
    k = 2 / (period + 1)
    ema_val = data[0]
    for price in data:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val

def rsi(data, period=14):
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

# ========= LOOP =========
print("🚀 BOT STARTED")

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

                    order = exchange.create_market_buy_order(sym, qty)

                    positions[sym] = price
                    print(f"🟢 BUY {sym} @ {price}")

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
                        print(f"🔴 SELL {sym} @ {price} | {change:.2f}%")
                        del positions[sym]

        time.sleep(5)

    except Exception as e:
        print("ERROR:", e)
        time.sleep(5)
