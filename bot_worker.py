import os, time, random, requests
import ccxt
from db import init_db, set_status, open_symbols, insert_open_trade, close_trade, list_trades

MODE = os.getenv("MODE", "paper").lower()          # paper / live
BUY_USDT = float(os.getenv("BUY_USDT", "15"))
TP_PCT = float(os.getenv("TP_PCT", "0.10"))        # 10%
SL_PCT = float(os.getenv("SL_PCT", "0.05"))        # 5%
SLEEP_SEC = int(os.getenv("SLEEP_SEC", "60"))
MIN_HOLD_USD = float(os.getenv("MIN_HOLD_USD", "10"))

TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_ID = os.getenv("TG_ID", "")

API_KEY = os.getenv("BINANCE_API_KEY", "")
SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")

def send_telegram(msg: str):
    if not TG_TOKEN or not TG_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_ID, "text": msg}, timeout=5)
    except:
        pass

def safe_float(x, default=0.0):
    try:
        return float(x)
    except:
        return default

def make_exchange():
    return ccxt.binance({
        "apiKey": API_KEY,
        "secret": SECRET_KEY,
        "enableRateLimit": True,
        "options": {"defaultType": "spot"}
    })

def qty_from_usdt(price, usdt):
    return usdt / price if price > 0 else 0.0

def pick_symbols(exchange):
    tickers = exchange.fetch_tickers()
    cands = []
    for sym, t in tickers.items():
        if not sym.endswith("/USDT"):
            continue
        last = safe_float(t.get("last"))
        pct = safe_float(t.get("percentage"))
        if last <= 0:
            continue
        if 3.0 <= pct <= 15.0:
            cands.append(sym)
    random.shuffle(cands)
    return cands[:20]

def sync_from_wallet(exchange):
    """يسجل العملات الموجودة فعلياً في المحفظة إذا لم تكن مسجلة OPEN."""
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
                    insert_open_trade(sym, last, amt, usd_val, buy_order_id="SYNC")
                    send_telegram(f"🧠 Sync: {sym} قيمة≈{usd_val:.2f} USDT تم تسجيلها OPEN")
            except:
                continue
    except:
        pass

def monitor_positions(exchange):
    open_trades = list_trades(status="OPEN", limit=300)
    for t in open_trades:
        sym = t["symbol"]
        buy_price = safe_float(t.get("buy_price"))
        qty = safe_float(t.get("buy_qty"))
        if buy_price <= 0 or qty <= 0:
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
            if MODE == "live":
                if not API_KEY or not SECRET_KEY:
                    set_status(last_error="MODE=live لكن مفاتيح Binance غير موجودة", notes="أوقف البيع للحماية")
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
            tag = "TP ✅" if last >= tp else "SL 🛑"
            send_telegram(f"📤 {tag} بيع: {sym} @ {last:.6f} qty={qty:.6f}")

def main():
    init_db()
    exchange = make_exchange()
    send_telegram(f"🚀 Bot started | MODE={MODE}")

    while True:
        try:
            bal = exchange.fetch_balance()
            usdt_free = safe_float(bal.get("free", {}).get("USDT", 0.0))
            set_status(mode=MODE, usdt_free=usdt_free, last_error="", notes="running")

            sync_from_wallet(exchange)
            monitor_positions(exchange)

            opens = open_symbols()
            if len(opens) < 5 and usdt_free >= BUY_USDT:
                for sym in pick_symbols(exchange):
                    if sym in opens:
                        continue
                    try:
                        last = safe_float(exchange.fetch_ticker(sym).get("last"))
                    except:
                        continue
                    if last <= 0:
                        continue

                    qty = qty_from_usdt(last, BUY_USDT)
                    if qty <= 0:
                        continue

                    if MODE == "live":
                        if not API_KEY or not SECRET_KEY:
                            set_status(last_error="MODE=live لكن مفاتيح Binance غير موجودة", notes="أوقف الشراء للحماية")
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
                    send_telegram(f"✅ شراء ({MODE}): {sym} @ {last:.6f} qty={qty:.6f}")
                    break

        except Exception as e:
            set_status(last_error=str(e), notes="loop exception")

        time.sleep(SLEEP_SEC)

if __name__ == "__main__":
    main()
