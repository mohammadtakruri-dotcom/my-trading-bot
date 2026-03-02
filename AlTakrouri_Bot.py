import os, time, threading, requests, ccxt, mysql.connector
from datetime import datetime, timezone
from flask import Flask

app = Flask(__name__)

# ================== ENV (لا تضع أسرار داخل الكود) ==================
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "database": os.getenv("DB_NAME"),
    "connect_timeout": 10,
}

TG_TOKEN = os.getenv("TG_TOKEN")
TG_ID = os.getenv("TG_ID")

MODE = os.getenv("MODE", "paper").lower()          # paper | live
BUY_USDT = float(os.getenv("BUY_USDT", "15"))      # قيمة الشراء بالـ USDT
MIN_USDT_FREE = float(os.getenv("MIN_USDT_FREE", "15"))
LOOP_SECONDS = int(os.getenv("LOOP_SECONDS", "60"))

# فلترة أساسية (اختياري)
PCT_MIN = float(os.getenv("PCT_MIN", "5"))         # نسبة صعود 24h للتصفية
MIN_USDT_VALUE = float(os.getenv("MIN_USDT_VALUE", "10"))  # أقل قيمة عملة للمزامنة

exchange = ccxt.binance({
    "apiKey": os.getenv("BINANCE_API_KEY"),
    "secret": os.getenv("BINANCE_SECRET_KEY"),
    "enableRateLimit": True,
    "options": {"defaultType": "spot"},
})

# ================== أدوات ==================
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def send_telegram(msg: str):
    if not TG_TOKEN or not TG_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_ID, "text": msg}, timeout=8)
    except:
        pass

def db_conn():
    return mysql.connector.connect(**DB_CONFIG)

def init_db():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INT AUTO_INCREMENT PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL,
        status VARCHAR(10) NOT NULL DEFAULT 'OPEN',   -- OPEN/CLOSED
        buy_price DOUBLE,
        buy_qty DOUBLE,
        buy_usdt DOUBLE,
        buy_order_id VARCHAR(64),
        buy_time VARCHAR(40),
        sell_price DOUBLE,
        sell_qty DOUBLE,
        sell_order_id VARCHAR(64),
        sell_time VARCHAR(40)
    )
    """)
    conn.commit()
    conn.close()

def get_open_symbols():
    conn = db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT symbol FROM trades WHERE status='OPEN'")
    rows = cur.fetchall()
    conn.close()
    return set(r["symbol"] for r in rows)

def insert_open_trade(symbol, buy_price, buy_qty, buy_usdt, buy_order_id=None):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO trades(symbol,status,buy_price,buy_qty,buy_usdt,buy_order_id,buy_time)
        VALUES(%s,'OPEN',%s,%s,%s,%s,%s)
    """, (symbol, buy_price, buy_qty, buy_usdt, buy_order_id, now_iso()))
    conn.commit()
    conn.close()

def close_trade(symbol, sell_price, sell_qty, sell_order_id=None):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE trades
        SET status='CLOSED', sell_price=%s, sell_qty=%s, sell_order_id=%s, sell_time=%s
        WHERE symbol=%s AND status='OPEN'
        ORDER BY id DESC
        LIMIT 1
    """, (sell_price, sell_qty, sell_order_id, now_iso(), symbol))
    conn.commit()
    conn.close()

def get_last_price(symbol):
    t = exchange.fetch_ticker(symbol)
    return float(t["last"])

# شراء Market بقيمة USDT صحيحة على Binance: quoteOrderQty
def market_buy_by_usdt(symbol, usdt_amount):
    if MODE == "paper":
        price = get_last_price(symbol)
        qty = usdt_amount / price
        return {"id": None, "price": price, "qty": qty}

    order = exchange.create_market_buy_order(symbol, None, params={"quoteOrderQty": usdt_amount})
    # ccxt أحيانًا لا يعيد avg مباشرة
    price = float(order.get("average") or get_last_price(symbol))
    filled = float(order.get("filled") or 0.0)
    return {"id": str(order.get("id")), "price": price, "qty": filled if filled > 0 else usdt_amount / price}

def market_sell_qty(symbol, qty):
    if MODE == "paper":
        price = get_last_price(symbol)
        return {"id": None, "price": price, "qty": qty}

    order = exchange.create_market_sell_order(symbol, qty)
    price = float(order.get("average") or get_last_price(symbol))
    filled = float(order.get("filled") or qty)
    return {"id": str(order.get("id")), "price": price, "qty": filled}

# ================== المزامنة (Memory الحديدية) ==================
def monitor_and_sync():
    while True:
        try:
            open_syms = get_open_symbols()
            bal = exchange.fetch_balance()

            # اكتشاف عملات موجودة بالمحفظة وليست OPEN بالـ DB
            for asset, total in (bal.get("total") or {}).items():
                if not total or total <= 0:
                    continue
                if asset in ("USDT", "BNB"):
                    continue

                sym = f"{asset}/USDT"
                # تجاهل لو الرمز غير متاح
                if sym not in exchange.markets:
                    continue

                price = get_last_price(sym)
                usdt_value = price * float(total)
                if usdt_value >= MIN_USDT_VALUE and sym not in open_syms:
                    # سجلها كصفقة مفتوحة "مكتشفة"
                    insert_open_trade(sym, buy_price=price, buy_qty=float(total), buy_usdt=usdt_value, buy_order_id="SYNC")
                    send_telegram(f"🧠 Sync: تم اكتشاف صفقة/عملة غير مسجلة وإضافتها للذاكرة: {sym} قيمة≈{usdt_value:.2f}$")

        except Exception as e:
            print("SYNC ERROR:", e)

        time.sleep(60)

# ================== محرك التداول ==================
def trading_engine():
    send_telegram(f"🚀 الروبوت يعمل | MODE={MODE}")

    while True:
        try:
            open_syms = get_open_symbols()

            bal = exchange.fetch_balance()
            usdt_free = float((bal.get("USDT") or {}).get("free") or 0.0)

            if usdt_free >= MIN_USDT_FREE:
                tickers = exchange.fetch_tickers()

                # اختيار رمز مناسب: USDT + نسبة صعود + ليس لدينا صفقة مفتوحة عليه
                candidates = []
                for sym, t in tickers.items():
                    if "/USDT" not in sym:
                        continue
                    if sym in open_syms:
                        continue
                    pct = t.get("percentage")
                    last = t.get("last")
                    if pct is None or last is None:
                        continue
                    if float(pct) >= PCT_MIN:
                        candidates.append((sym, float(pct), float(last)))

                # أعلى مرشح
                candidates.sort(key=lambda x: x[1], reverse=True)

                if candidates:
                    sym, pct, last = candidates[0]

                    buy = market_buy_by_usdt(sym, BUY_USDT)
                    insert_open_trade(sym, buy_price=buy["price"], buy_qty=buy["qty"], buy_usdt=BUY_USDT, buy_order_id=buy["id"])
                    send_telegram(f"✅ شراء: {sym} | pct={pct:.2f}% | price≈{buy['price']:.6f} | qty≈{buy['qty']:.8f}")

            # مثال بيع بسيط (هدف 10% / ستوب 5%) على آخر صفقة لكل رمز
            # (نقدر نطورها لاحقًا بشكل أقوى)
            # هنا نكتفي بتتبع الصفقات المفتوحة من DB:
            conn = db_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM trades WHERE status='OPEN'")
            opens = cur.fetchall()
            conn.close()

            for tr in opens:
                sym = tr["symbol"]
                buy_price = float(tr["buy_price"] or 0)
                buy_qty = float(tr["buy_qty"] or 0)
                if buy_price <= 0 or buy_qty <= 0:
                    continue

                cur_price = get_last_price(sym)
                change = (cur_price - buy_price) / buy_price * 100.0

                if change >= 10.0 or change <= -5.0:
                    sell = market_sell_qty(sym, buy_qty)
                    close_trade(sym, sell_price=sell["price"], sell_qty=sell["qty"], sell_order_id=sell["id"])
                    send_telegram(f"📤 بيع: {sym} | change={change:.2f}% | sell≈{sell['price']:.6f}")

        except Exception as e:
            print("ENGINE ERROR:", e)

        time.sleep(LOOP_SECONDS)

# ================== تشغيل آمن داخل Web (مع تحذير تعدد workers) ==================
_started = False

@app.before_request
def start_once():
    global _started
    if _started:
        return
    _started = True
    init_db()
    threading.Thread(target=trading_engine, daemon=True).start()
    threading.Thread(target=monitor_and_sync, daemon=True).start()

@app.route("/")
def home():
    return "<h1>Takruri Trading Bot ✅ (Memory + Sync Running)</h1>"

@app.route("/health")
def health():
    return {"status": "ok", "mode": MODE, "time": now_iso()}

if __name__ == "__main__":
    init_db()
    threading.Thread(target=trading_engine, daemon=True).start()
    threading.Thread(target=monitor_and_sync, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
