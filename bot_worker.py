# bot_worker.py
import os, time, requests
import ccxt
from db import conn, init_db, now_iso

MODE = os.getenv("MODE", "paper").lower()          # paper | live
BUY_USDT = float(os.getenv("BUY_USDT", "15"))
MIN_USDT_FREE = float(os.getenv("MIN_USDT_FREE", "15"))
LOOP_SECONDS = int(os.getenv("LOOP_SECONDS", "60"))
PCT_MIN = float(os.getenv("PCT_MIN", "5"))
MIN_USDT_VALUE = float(os.getenv("MIN_USDT_VALUE", "10"))

TG_TOKEN = os.getenv("TG_TOKEN")
TG_ID = os.getenv("TG_ID")

exchange = ccxt.binance({
    "apiKey": os.getenv("BINANCE_API_KEY"),
    "secret": os.getenv("BINANCE_SECRET_KEY"),
    "enableRateLimit": True,
    "options": {"defaultType": "spot"},
})

def send_telegram(msg: str):
    if not TG_TOKEN or not TG_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_ID, "text": msg}, timeout=8)
    except:
        pass

def set_status(usdt_free=None, last_error=None, notes=None):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        UPDATE bot_status
        SET mode=%s, last_run=%s,
            usdt_free=COALESCE(%s, usdt_free),
            last_error=COALESCE(%s, last_error),
            notes=COALESCE(%s, notes)
        WHERE id=1
    """, (MODE, now_iso(), usdt_free, last_error, notes))
    c.commit()
    c.close()

def get_open_symbols():
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT symbol FROM trades WHERE status='OPEN'")
    rows = cur.fetchall()
    c.close()
    return set(r["symbol"] for r in rows)

def insert_open_trade(symbol, buy_price, buy_qty, buy_usdt, buy_order_id=None):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO trades(symbol,status,buy_price,buy_qty,buy_usdt,buy_order_id,buy_time)
        VALUES(%s,'OPEN',%s,%s,%s,%s,%s)
    """, (symbol, buy_price, buy_qty, buy_usdt, buy_order_id, now_iso()))
    c.commit()
    c.close()

def close_trade(symbol, sell_price, sell_qty, sell_order_id=None):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        UPDATE trades
        SET status='CLOSED', sell_price=%s, sell_qty=%s, sell_order_id=%s, sell_time=%s
        WHERE symbol=%s AND status='OPEN'
        ORDER BY id DESC
        LIMIT 1
    """, (sell_price, sell_qty, sell_order_id, now_iso(), symbol))
    c.commit()
    c.close()

def last_price(symbol):
    t = exchange.fetch_ticker(symbol)
    return float(t["last"])

def market_buy_by_usdt(symbol, usdt_amount):
    if MODE == "paper":
        p = last_price(symbol)
        qty = usdt_amount / p
        return {"id": None, "price": p, "qty": qty}

    # شراء صحيح بقيمة USDT
    order = exchange.create_market_buy_order(symbol, None, params={"quoteOrderQty": usdt_amount})
    p = float(order.get("average") or last_price(symbol))
    filled = float(order.get("filled") or 0.0)
    return {"id": str(order.get("id")), "price": p, "qty": filled if filled > 0 else usdt_amount / p}

def market_sell_qty(symbol, qty):
    if MODE == "paper":
        p = last_price(symbol)
        return {"id": None, "price": p, "qty": qty}

    order = exchange.create_market_sell_order(symbol, qty)
    p = float(order.get("average") or last_price(symbol))
    filled = float(order.get("filled") or qty)
    return {"id": str(order.get("id")), "price": p, "qty": filled}

def sync_wallet_to_db():
    open_syms = get_open_symbols()
    bal = exchange.fetch_balance()
    totals = bal.get("total") or {}

    for asset, total in totals.items():
        if not total or float(total) <= 0:
            continue
        if asset in ("USDT", "BNB"):
            continue

        sym = f"{asset}/USDT"
        if sym not in exchange.markets:
            continue

        p = last_price(sym)
        value = p * float(total)
        if value >= MIN_USDT_VALUE and sym not in open_syms:
            insert_open_trade(sym, buy_price=p, buy_qty=float(total), buy_usdt=value, buy_order_id="SYNC")
            send_telegram(f"🧠 Sync: تم اكتشاف {sym} وإضافته للذاكرة. قيمة≈{value:.2f}$")

def engine_cycle():
    open_syms = get_open_symbols()

    bal = exchange.fetch_balance()
    usdt_free = float((bal.get("USDT") or {}).get("free") or 0.0)
    set_status(usdt_free=usdt_free)

    # شراء
    if usdt_free >= MIN_USDT_FREE:
        tickers = exchange.fetch_tickers()
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

        candidates.sort(key=lambda x: x[1], reverse=True)
        if candidates:
            sym, pct, _ = candidates[0]
            buy = market_buy_by_usdt(sym, BUY_USDT)
            insert_open_trade(sym, buy_price=buy["price"], buy_qty=buy["qty"], buy_usdt=BUY_USDT, buy_order_id=buy["id"])
            send_telegram(f"✅ شراء: {sym} | pct={pct:.2f}% | price≈{buy['price']:.6f}")

    # بيع (هدف 10% / ستوب 5%)
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM trades WHERE status='OPEN'")
    opens = cur.fetchall()
    c.close()

    for tr in opens:
        sym = tr["symbol"]
        buy_price = float(tr["buy_price"] or 0)
        buy_qty = float(tr["buy_qty"] or 0)
        if buy_price <= 0 or buy_qty <= 0:
            continue

        p = last_price(sym)
        change = (p - buy_price) / buy_price * 100.0
        if change >= 10.0 or change <= -5.0:
            sell = market_sell_qty(sym, buy_qty)
            close_trade(sym, sell_price=sell["price"], sell_qty=sell["qty"], sell_order_id=sell["id"])
            send_telegram(f"📤 بيع: {sym} | change={change:.2f}% | sell≈{sell['price']:.6f}")

def main():
    init_db()
    send_telegram(f"🚀 Worker started | MODE={MODE}")
    while True:
        try:
            set_status(last_error="", notes="running")
            sync_wallet_to_db()
            engine_cycle()
        except Exception as e:
            set_status(last_error=str(e), notes="error")
            print("WORKER ERROR:", e)
        time.sleep(LOOP_SECONDS)

if __name__ == "__main__":
    main()
