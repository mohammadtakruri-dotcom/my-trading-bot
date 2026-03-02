import os, time, math, random, requests
import ccxt
from db import init_db, set_status, open_symbols, insert_open_trade, close_trade

# ====== إعدادات أساسية ======
MODE = os.getenv("MODE", "paper").lower()   # paper / live
BUY_USDT = float(os.getenv("BUY_USDT", "15"))
MIN_HOLD_USD = float(os.getenv("MIN_HOLD_USD", "10"))  # مزامنة العملات أكبر من هذا
TP_PCT = float(os.getenv("TP_PCT", "0.10"))            # 10% هدف
SL_PCT = float(os.getenv("SL_PCT", "0.05"))            # 5% وقف
SLEEP_SEC = int(os.getenv("SLEEP_SEC", "60"))

TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_ID = os.getenv("TG_ID", "")

# أمان: لا تسمح بالـ live إذا لم تكن المفاتيح موجودة
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")

def send_telegram(msg: str):
    if not TG_TOKEN or not TG_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_ID, "text": msg}, timeout=5)
    except:
        pass

def make_exchange():
    ex = ccxt.binance({
        "apiKey": BINANCE_API_KEY,
        "secret": BINANCE_SECRET_KEY,
        "enableRateLimit": True,
        "options": {"defaultType": "spot"}  # فقط Spot
    })
    return ex

def safe_float(x, default=0.0):
    try:
        return float(x)
    except:
        return default

# ====== مؤشرات بسيطة (RSI) ======
def rsi_from_closes(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i-1]
        if diff >= 0:
            gains += diff
        else:
            losses += -diff
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs))

def fetch_rsi(exchange, symbol):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe="5m", limit=60)
    closes = [c[4] for c in ohlcv]
    return rsi_from_closes(closes, 14)

# ====== منطق اختيار عملة (بسيط وغير عدواني) ======
def pick_symbol(exchange):
    tickers = exchange.fetch_tickers()
    candidates = []
    for sym, t in tickers.items():
        if not sym.endswith("/USDT"):
            continue
        if sym.startswith("USDC/") or sym.startswith("BUSD/"):
            continue
        pct = safe_float(t.get("percentage"))
        last = safe_float(t.get("last"))
        if last <= 0:
            continue

        # فلتر بسيط: حركة يومية بين 3% و 15% (فرص بدون جنون)
        if 3.0 <= pct <= 15.0:
            candidates.append(sym)

    random.shuffle(candidates)
    return candidates[:20]  # اختبر أول 20

def qty_from_usdt(price, usdt):
    if price <= 0:
        return 0.0
    return usdt / price

# ====== مزامنة “الذاكرة” من المحفظة ======
def sync_from_wallet(exchange):
    """إذا كان عندك عملات في المحفظة ولم تكن مسجلة كصفقات OPEN، سجّلها."""
    try:
        bal = exchange.fetch_balance()
        totals = bal.get("total", {})
        opens = open_symbols()
        for asset, amount in totals.items():
            amt = safe_float(amount)
            if amt <= 0:
                continue
            if asset in ("USDT", "BNB"):
                continue
            sym = f"{asset}/USDT"
            if sym in opens:
                continue

            try:
                ticker = exchange.fetch_ticker(sym)
                last = safe_float(ticker.get("last"))
                usd_val = last * amt
                if usd_val >= MIN_HOLD_USD:
                    # نضيفها كصفقة مفتوحة (بسعر تقريبي الحالي)
                    insert_open_trade(sym, last, amt, usd_val, buy_order_id="SYNC")
                    send_telegram(f"🧠 Sync: اكتشفت عملة في المحفظة وسجلتها OPEN: {sym} قيمة≈{usd_val:.2f} USDT")
            except:
                continue
    except:
        pass

# ====== مراقبة TP/SL على الصفقات OPEN ======
def monitor_positions(exchange):
    from db import list_trades
    open_trades = list_trades(status="OPEN", limit=500)
    for t in open_trades:
        sym = t["symbol"]
        buy_price = safe_float(t.get("buy_price"))
        qty = safe_float(t.get("buy_qty"))
        if qty <= 0 or buy_price <= 0:
            continue

        try:
            last = safe_float(exchange.fetch_ticker(sym).get("last"))
        except:
            continue
        if last <= 0:
            continue

        tp = buy_price * (1 + TP_PCT)
        sl = buy_price * (1 - SL_PCT)

        if last >= tp or last <= sl:
            # بيع (paper أو live)
            if MODE == "live":
                # Safety: لا تداول حقيقي إذا المفاتيح ناقصة
                if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
                    set_status(last_error="Live mode ولكن مفاتيح Binance غير موجودة", notes="أوقف البيع لحماية الحساب")
                    continue
                try:
                    order = exchange.create_market_sell_order(sym, qty)
                    oid = str(order.get("id"))
                except Exception as e:
                    set_status(last_error=f"Sell error: {e}")
                    continue
            else:
                oid = "PAPER_SELL"

            close_trade(sym, last, qty, sell_order_id=oid)
            side = "TP ✅" if last >= tp else "SL 🛑"
            send_telegram(f"📤 {side} بيع: {sym} بسعر {last:.6f} qty={qty}")
    return

def main_loop():
    init_db()
    send_telegram("🚀 Bot started (SQLite) | MODE=" + MODE)
    exchange = make_exchange()

    while True:
        try:
            # تحديث حالة عامة
            try:
                bal = exchange.fetch_balance()
                usdt_free = safe_float(bal.get("free", {}).get("USDT", 0))
            except:
                usdt_free = 0.0

            set_status(mode=MODE, usdt_free=usdt_free, last_error="", notes="running")

            # مزامنة من المحفظة (مهم لتفادي “نسيان” العملات)
            sync_from_wallet(exchange)

            # مراقبة TP/SL
            monitor_positions(exchange)

            # شراء (فقط إذا لا يوجد صفقات كثيرة مفتوحة)
            opens = open_symbols()
            if len(opens) >= 5:
                time.sleep(SLEEP_SEC)
                continue

            if usdt_free >= BUY_USDT:
                # اختر عملة + تأكد RSI منخفض (دخول محافظ)
                for sym in pick_symbol(exchange):
                    if sym in opens:
                        continue

                    try:
                        rsi = fetch_rsi(exchange, sym)
                        ticker = exchange.fetch_ticker(sym)
                        last = safe_float(ticker.get("last"))
                        if last <= 0:
                            continue
                    except:
                        continue

                    # شرط دخول بسيط: RSI <= 35 (يعني “هبوط نسبي”)
                    if rsi is None or rsi > 35:
                        continue

                    qty = qty_from_usdt(last, BUY_USDT)
                    if qty <= 0:
                        continue

                    if MODE == "live":
                        if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
                            set_status(last_error="Live mode ولكن مفاتيح Binance غير موجودة", notes="أوقف الشراء لحماية الحساب")
                            break
                        try:
                            order = exchange.create_market_buy_order(sym, qty)
                            oid = str(order.get("id"))
                        except Exception as e:
                            set_status(last_error=f"Buy error: {e}")
                            continue
                    else:
                        oid = "PAPER_BUY"

                    insert_open_trade(sym, last, qty, BUY_USDT, buy_order_id=oid)
                    send_telegram(f"✅ شراء ({MODE}): {sym} @ {last:.6f} qty={qty:.6f} RSI={rsi:.1f}")
                    break

        except Exception as e:
            set_status(last_error=str(e), notes="loop exception")
        time.sleep(SLEEP_SEC)

if __name__ == "__main__":
    main_loop()
