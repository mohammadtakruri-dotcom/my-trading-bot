import os
import time
import math
import traceback
from datetime import datetime
from collections import deque

import requests
from binance.client import Client
from binance.exceptions import BinanceAPIException

from db import init_db, set_status, add_trade


# ================== Safe ENV Parsers ==================
def getenv_str(name: str, default: str = "") -> str:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip()
    return v if v != "" else default


def getenv_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None:
        return float(default)
    v = v.strip()
    if v == "":
        return float(default)
    try:
        return float(v)
    except Exception:
        return float(default)


def getenv_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None:
        return int(default)
    v = v.strip()
    if v == "":
        return int(default)
    try:
        return int(float(v))
    except Exception:
        return int(default)


# ================== ENV ==================
BINANCE_API_KEY = getenv_str("BINANCE_API_KEY", "")
BINANCE_API_SECRET = getenv_str("BINANCE_API_SECRET", "")

TG_TOKEN = getenv_str("TG_TOKEN", "")
TG_ID = getenv_str("TG_ID", "")

ENABLE_TRADING = getenv_str("ENABLE_TRADING", "0")
LIVE_TRADING = getenv_str("LIVE_TRADING", "0")
MODE = "live" if (ENABLE_TRADING == "1" or LIVE_TRADING == "1") else "paper"

# تقليل الأزواج مؤقتًا لتحسين الجودة
DEFAULT_SYMBOLS = "BTCUSDT,ETHUSDT,XRPUSDT"
SYMBOLS = getenv_str("SYMBOLS", DEFAULT_SYMBOLS)
SYMBOLS = [s.strip().upper() for s in SYMBOLS.split(",") if s.strip()]

# ================== Strategy Params ==================
BUY_USDT = getenv_float("BUY_USDT", 12.0)

# نسخة أخف وأسرع من السابقة
TP_PCT = getenv_float("TP_PCT", 1.25)          # gross TP
SL_PCT = getenv_float("SL_PCT", 0.55)          # gross SL
CHECK_INTERVAL = getenv_float("CHECK_INTERVAL", 8.0)

MIN_USDT_FREE_TO_BUY = getenv_float("MIN_USDT_FREE_TO_BUY", 15.0)
MAX_OPEN_POSITIONS = getenv_int("MAX_OPEN_POSITIONS", 1)
COOLDOWN_SEC = getenv_int("COOLDOWN_SEC", 180)

# Fees / slippage
FEE_PCT = getenv_float("FEE_PCT", 0.10)
SLIPPAGE_PCT = getenv_float("SLIPPAGE_PCT", 0.12)
MIN_NET_PROFIT_PCT = getenv_float("MIN_NET_PROFIT_PCT", 0.35)

BREAKEVEN_PCT = (2.0 * FEE_PCT) + SLIPPAGE_PCT
REQUIRED_GROSS_TP_PCT = max(TP_PCT, BREAKEVEN_PCT + MIN_NET_PROFIT_PCT)

# Dust ignore
DUST_IGNORE = getenv_str("DUST_IGNORE", "1")
DUST_IGNORE_BUFFER = getenv_float("DUST_IGNORE_BUFFER", 0.30)

# Heartbeat
HEARTBEAT_SEC = getenv_int("HEARTBEAT_SEC", 30)
DEBUG_EVERY_SEC = getenv_int("DEBUG_EVERY_SEC", 180)

# Indicators - Entry timeframe
KLINES_INTERVAL = getenv_str("KLINES_INTERVAL", "3m")
KLINES_LIMIT = getenv_int("KLINES_LIMIT", 180)
KLINES_REFRESH_SEC = getenv_int("KLINES_REFRESH_SEC", 25)

EMA_FAST = getenv_int("EMA_FAST", 9)
EMA_SLOW = getenv_int("EMA_SLOW", 21)
RSI_PERIOD = getenv_int("RSI_PERIOD", 14)

RSI_BUY_MIN = getenv_float("RSI_BUY_MIN", 50.0)
RSI_BUY_MAX = getenv_float("RSI_BUY_MAX", 62.0)

EXIT_ON_EMA_CROSSDOWN = getenv_str("EXIT_ON_EMA_CROSSDOWN", "1")
EXIT_RSI_OVERBOUGHT = getenv_float("EXIT_RSI_OVERBOUGHT", 74.0)

# Trend filter - Higher timeframe
TREND_INTERVAL = getenv_str("TREND_INTERVAL", "15m")
TREND_LIMIT = getenv_int("TREND_LIMIT", 260)
TREND_EMA = getenv_int("TREND_EMA", 200)
TREND_REFRESH_SEC = getenv_int("TREND_REFRESH_SEC", 90)
REQUIRE_TREND_FILTER = getenv_str("REQUIRE_TREND_FILTER", "1")

# Market quality filters
MAX_SPREAD_PCT = getenv_float("MAX_SPREAD_PCT", 0.12)
MIN_24H_QUOTE_VOLUME = getenv_float("MIN_24H_QUOTE_VOLUME", 50000000.0)

# Volume / momentum filters
VOLUME_LOOKBACK = getenv_int("VOLUME_LOOKBACK", 20)
MIN_VOLUME_RATIO = getenv_float("MIN_VOLUME_RATIO", 0.90)
REQUIRE_BULL_CANDLE = getenv_str("REQUIRE_BULL_CANDLE", "1")

# Trailing
ENABLE_TRAILING = getenv_str("ENABLE_TRAILING", "1")
TRAILING_ACTIVATE_NET_PCT = getenv_float("TRAILING_ACTIVATE_NET_PCT", 0.45)
TRAILING_GIVEBACK_PCT = getenv_float("TRAILING_GIVEBACK_PCT", 0.18)

# Wallet sync / manual positions
SYNC_EXISTING_POSITIONS = getenv_str("SYNC_EXISTING_POSITIONS", "1")
MANAGE_UNKNOWN_ENTRY = getenv_str("MANAGE_UNKNOWN_ENTRY", "1")
TRADES_FETCH_LIMIT = getenv_int("TRADES_FETCH_LIMIT", 1000)

# Early exit
EARLY_EXIT_MIN_NET_PCT = getenv_float("EARLY_EXIT_MIN_NET_PCT", 0.18)

# ================== Arabic Report Settings ==================
REPORT_INTERVAL_SEC = getenv_int("REPORT_INTERVAL_SEC", 86400)
SEND_REPORT_ON_EACH_SELL = getenv_str("SEND_REPORT_ON_EACH_SELL", "1")
SEND_DAILY_REPORT = getenv_str("SEND_DAILY_REPORT", "1")

REPORT_STATE = {
    "started_at": int(time.time()),
    "last_report_ts": int(time.time()),
    "buys": 0,
    "sells": 0,
    "wins": 0,
    "losses": 0,
    "total_profit_usdt": 0.0,
    "best_trade": None,
    "worst_trade": None,
    "symbols": {}
}


# ================== Telegram ==================
def tg_send(msg: str):
    if not TG_TOKEN or not TG_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(
            url,
            timeout=15,
            data={
                "chat_id": TG_ID,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
        )
    except Exception:
        pass


# ================== Arabic Reporting Helpers ==================
def fmt_usdt(x: float) -> str:
    sign = "+" if x > 0 else ""
    return f"{sign}{x:.2f} USDT"


def fmt_pct(x: float) -> str:
    sign = "+" if x > 0 else ""
    return f"{sign}{x:.2f}%"


def estimate_trade_pnl_usdt(entry: float, exit_price: float, qty: float) -> float:
    if entry <= 0 or exit_price <= 0 or qty <= 0:
        return 0.0

    buy_cost = entry * qty
    sell_value = exit_price * qty

    buy_fee = buy_cost * (FEE_PCT / 100.0)
    sell_fee = sell_value * (FEE_PCT / 100.0)

    pnl = sell_value - buy_cost - buy_fee - sell_fee
    return pnl


def update_report_stats_on_buy(sym: str):
    REPORT_STATE["buys"] += 1
    REPORT_STATE["symbols"].setdefault(sym, {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "profit": 0.0
    })


def update_report_stats_on_sell(sym: str, pnl_usdt: float):
    REPORT_STATE["sells"] += 1
    REPORT_STATE["total_profit_usdt"] += pnl_usdt

    bucket = REPORT_STATE["symbols"].setdefault(sym, {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "profit": 0.0
    })

    bucket["trades"] += 1
    bucket["profit"] += pnl_usdt

    if pnl_usdt >= 0:
        REPORT_STATE["wins"] += 1
        bucket["wins"] += 1
    else:
        REPORT_STATE["losses"] += 1
        bucket["losses"] += 1

    best_trade = REPORT_STATE["best_trade"]
    worst_trade = REPORT_STATE["worst_trade"]

    if best_trade is None or pnl_usdt > best_trade["pnl"]:
        REPORT_STATE["best_trade"] = {"symbol": sym, "pnl": pnl_usdt}

    if worst_trade is None or pnl_usdt < worst_trade["pnl"]:
        REPORT_STATE["worst_trade"] = {"symbol": sym, "pnl": pnl_usdt}


def build_symbol_ranking_text():
    rows = []
    data = REPORT_STATE["symbols"]

    ranked = sorted(
        data.items(),
        key=lambda kv: kv[1].get("profit", 0.0),
        reverse=True
    )

    for sym, st in ranked[:5]:
        rows.append(
            f"• <b>{sym}</b>: {fmt_usdt(st['profit'])} | "
            f"صفقات: {st['trades']} | ✅ {st['wins']} | ❌ {st['losses']}"
        )

    return "\n".join(rows) if rows else "• لا توجد صفقات مغلقة بعد"


def build_arabic_analysis():
    total = REPORT_STATE["sells"]
    wins = REPORT_STATE["wins"]
    profit = REPORT_STATE["total_profit_usdt"]

    if total == 0:
        return "لا توجد صفقات بيع مغلقة بعد، لذلك ما زال الحكم على الأداء مبكرًا."

    win_rate = (wins / total) * 100 if total > 0 else 0.0
    notes = []

    if profit > 0:
        notes.append("الأداء العام إيجابي وصافي النتيجة حتى الآن رابح.")
    elif profit < 0:
        notes.append("الأداء العام سلبي حاليًا ويحتاج إلى مراجعة إعدادات الدخول والخروج.")
    else:
        notes.append("الأداء متعادل تقريبًا حتى الآن.")

    if win_rate >= 65:
        notes.append("نسبة النجاح جيدة وتدل على أن شروط الدخول منضبطة نسبيًا.")
    elif win_rate >= 50:
        notes.append("نسبة النجاح مقبولة، لكن يمكن تحسين التصفية قبل الدخول.")
    else:
        notes.append("نسبة النجاح منخفضة، والأفضل تقليل عدد الأزواج أو التشدد قليلًا في الإشارات الضعيفة.")

    if profit > 5:
        notes.append("الربح اليومي جيد، حافظ على نفس حجم الصفقة حاليًا دون زيادة متسرعة.")
    elif profit < -3:
        notes.append("يفضل تخفيف المخاطرة أو إيقاف بعض الأزواج مؤقتًا حتى يعود الأداء للاستقرار.")

    return "\n- " + "\n- ".join(notes)


def build_daily_report_message():
    elapsed_sec = max(1, int(time.time()) - REPORT_STATE["started_at"])
    hours = elapsed_sec / 3600.0
    total_closed = REPORT_STATE["sells"]
    wins = REPORT_STATE["wins"]
    losses = REPORT_STATE["losses"]
    total_profit = REPORT_STATE["total_profit_usdt"]
    win_rate = (wins / total_closed * 100.0) if total_closed > 0 else 0.0

    best_trade = REPORT_STATE["best_trade"]
    worst_trade = REPORT_STATE["worst_trade"]

    best_text = (
        f"{best_trade['symbol']} {fmt_usdt(best_trade['pnl'])}"
        if best_trade else "لا يوجد"
    )
    worst_text = (
        f"{worst_trade['symbol']} {fmt_usdt(worst_trade['pnl'])}"
        if worst_trade else "لا يوجد"
    )

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    msg = (
        "📊 <b>تقرير التداول الآلي</b>\n\n"
        f"📅 <b>وقت التقرير:</b> {now_str}\n"
        f"🕒 <b>الفترة:</b> آخر {hours:.1f} ساعة\n"
        f"🟢 <b>عمليات الشراء:</b> {REPORT_STATE['buys']}\n"
        f"🔴 <b>الصفقات المغلقة:</b> {total_closed}\n"
        f"✅ <b>الصفقات الرابحة:</b> {wins}\n"
        f"❌ <b>الصفقات الخاسرة:</b> {losses}\n"
        f"🎯 <b>نسبة النجاح:</b> {win_rate:.1f}%\n"
        f"💰 <b>صافي الربح:</b> {fmt_usdt(total_profit)}\n"
        f"🏆 <b>أفضل صفقة:</b> {best_text}\n"
        f"⚠️ <b>أسوأ صفقة:</b> {worst_text}\n\n"
        f"📌 <b>ترتيب الأزواج:</b>\n{build_symbol_ranking_text()}\n\n"
        f"🧠 <b>التحليل:</b>{build_arabic_analysis()}"
    )
    return msg


def send_periodic_report_if_due():
    if SEND_DAILY_REPORT != "1":
        return

    now = int(time.time())
    last_ts = int(REPORT_STATE.get("last_report_ts", now))

    if (now - last_ts) >= REPORT_INTERVAL_SEC:
        tg_send(build_daily_report_message())
        REPORT_STATE["last_report_ts"] = now


def send_sell_analysis_message(sym: str, qty: float, entry: float, exit_price: float, reason: str):
    pnl_usdt = estimate_trade_pnl_usdt(entry, exit_price, qty)
    gross_pct = gross_pnl_pct(entry, exit_price) if entry > 0 else 0.0
    net_pct_est = gross_pct - (2.0 * FEE_PCT)

    direction = "ربح" if pnl_usdt >= 0 else "خسارة"

    msg = (
        f"📉 <b>إغلاق صفقة {sym}</b>\n\n"
        f"📦 <b>الكمية:</b> {qty:.6f}\n"
        f"📥 <b>سعر الدخول:</b> {entry:.6f}\n"
        f"📤 <b>سعر الخروج:</b> {exit_price:.6f}\n"
        f"📊 <b>النتيجة:</b> {direction}\n"
        f"💵 <b>الربح/الخسارة التقريبي:</b> {fmt_usdt(pnl_usdt)}\n"
        f"📈 <b>التغير الإجمالي:</b> {fmt_pct(gross_pct)}\n"
        f"🧾 <b>التغير الصافي التقريبي بعد الرسوم:</b> {fmt_pct(net_pct_est)}\n"
        f"📝 <b>سبب الخروج:</b> {reason}"
    )
    tg_send(msg)


# ================== Binance Helpers ==================
def make_client():
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        raise RuntimeError("Missing BINANCE_API_KEY / BINANCE_API_SECRET")
    c = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
    c.ping()
    return c


def get_price(client: Client, symbol: str) -> float:
    return float(client.get_symbol_ticker(symbol=symbol)["price"])


def get_bid_ask(client: Client, symbol: str):
    t = client.get_orderbook_ticker(symbol=symbol)
    bid = float(t["bidPrice"])
    ask = float(t["askPrice"])
    return bid, ask


def get_spread_pct(client: Client, symbol: str) -> float:
    bid, ask = get_bid_ask(client, symbol)
    if bid <= 0 or ask <= 0:
        return 999.0
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return 999.0
    return ((ask - bid) / mid) * 100.0


def get_24h_quote_volume(client: Client, symbol: str) -> float:
    try:
        t = client.get_ticker(symbol=symbol)
        return float(t.get("quoteVolume", 0) or 0)
    except Exception:
        return 0.0


def base_asset(symbol: str) -> str:
    return symbol[:-4] if symbol.endswith("USDT") else symbol


def get_balance_free(client: Client, asset: str) -> float:
    b = client.get_asset_balance(asset=asset)
    return float(b["free"]) if b else 0.0


def format_qty(q: float) -> str:
    s = f"{q:.8f}".rstrip("0").rstrip(".")
    return s if s else "0"


def round_step(qty: float, step: float) -> float:
    if step == 0:
        return qty
    return math.floor(qty / step) * step


def get_lot_step(client: Client, symbol: str):
    info = client.get_symbol_info(symbol)
    if not info:
        raise RuntimeError(f"symbol info not found: {symbol}")

    step = 0.0
    min_qty = 0.0
    min_notional = 0.0

    for f in info.get("filters", []):
        if f.get("filterType") == "LOT_SIZE":
            step = float(f.get("stepSize", 0) or 0)
            min_qty = float(f.get("minQty", 0) or 0)

        if f.get("filterType") in ("MIN_NOTIONAL", "NOTIONAL"):
            mn = f.get("minNotional") or f.get("notional") or 0
            try:
                min_notional = float(mn)
            except Exception:
                min_notional = 0.0

    return step, min_qty, min_notional


def market_buy(client: Client, symbol: str, usdt_amount: float):
    return client.create_order(
        symbol=symbol,
        side="BUY",
        type="MARKET",
        quoteOrderQty=f"{usdt_amount:.2f}",
    )


def market_sell(client: Client, symbol: str, qty: float):
    return client.create_order(
        symbol=symbol,
        side="SELL",
        type="MARKET",
        quantity=format_qty(qty),
    )


def avg_fill_price_from_order(order) -> float:
    try:
        fills = order.get("fills", [])
        if not fills:
            executed_qty = float(order.get("executedQty", 0) or 0)
            cummulative_quote_qty = float(order.get("cummulativeQuoteQty", 0) or 0)
            if executed_qty > 0:
                return cummulative_quote_qty / executed_qty
            return 0.0

        total_qty = 0.0
        total_quote = 0.0
        for f in fills:
            p = float(f.get("price", 0) or 0)
            q = float(f.get("qty", 0) or 0)
            total_qty += q
            total_quote += p * q

        if total_qty > 0:
            return total_quote / total_qty
        return 0.0
    except Exception:
        return 0.0


def executed_qty_from_order(order) -> float:
    try:
        qty = float(order.get("executedQty", 0) or 0)
        if qty > 0:
            return qty

        fills = order.get("fills", [])
        total = 0.0
        for f in fills:
            total += float(f.get("qty", 0) or 0)
        return total
    except Exception:
        return 0.0


# ================== Indicators ==================
def ema(prev_ema: float, price: float, period: int) -> float:
    k = 2 / (period + 1)
    return price * k + prev_ema * (1 - k)


def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 0.0

    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses += (-diff)

    if losses == 0:
        return 100.0

    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs))


def get_klines_interval(val: str):
    m = {
        "1m": Client.KLINE_INTERVAL_1MINUTE,
        "3m": Client.KLINE_INTERVAL_3MINUTE,
        "5m": Client.KLINE_INTERVAL_5MINUTE,
        "15m": Client.KLINE_INTERVAL_15MINUTE,
    }
    return m.get(val, Client.KLINE_INTERVAL_3MINUTE)


# ================== Risk / State ==================
POSITIONS = {}
LAST_TRADE_TS = {}
STATE = {}
TREND_STATE = {}
LAST_DEBUG_TS = {}


def in_cooldown(sym: str) -> bool:
    last_ts = int(LAST_TRADE_TS.get(sym, 0) or 0)
    return (time.time() - last_ts) < COOLDOWN_SEC


def mark_trade(sym: str):
    LAST_TRADE_TS[sym] = int(time.time())


def is_dust(qty: float, price: float, min_notional: float) -> bool:
    if qty <= 0:
        return False
    if min_notional <= 0:
        return False
    return (qty * price) < (min_notional - DUST_IGNORE_BUFFER)


def count_open_positions_wallet(client: Client) -> int:
    cnt = 0
    for sym in SYMBOLS:
        try:
            asset = base_asset(sym)
            qty = get_balance_free(client, asset)
            price = get_price(client, sym)
            _, _, min_notional = get_lot_step(client, sym)

            if DUST_IGNORE == "1" and is_dust(qty, price, min_notional):
                continue

            if qty > 0:
                cnt += 1
        except Exception:
            continue
    return cnt


# ================== Position From Trade History ==================
def build_position_from_trades(client: Client, sym: str):
    asset = base_asset(sym)
    wallet_qty = get_balance_free(client, asset)

    if wallet_qty <= 0:
        return None

    try:
        trades = client.get_my_trades(symbol=sym, limit=TRADES_FETCH_LIMIT)
    except Exception:
        trades = []

    if not trades:
        if MANAGE_UNKNOWN_ENTRY == "1":
            price = get_price(client, sym)
            return {
                "entry": price,
                "qty": wallet_qty,
                "peak_net": 0.0,
                "highest_price": price,
                "entry_known": False,
                "source": "fallback",
            }
        return None

    qty = 0.0
    cost = 0.0
    trades = sorted(trades, key=lambda x: int(x.get("time", 0) or 0))

    for tr in trades:
        tr_qty = float(tr.get("qty", 0) or 0)
        tr_price = float(tr.get("price", 0) or 0)
        is_buyer = bool(tr.get("isBuyer", False))

        if tr_qty <= 0 or tr_price <= 0:
            continue

        if is_buyer:
            qty += tr_qty
            cost += tr_qty * tr_price
        else:
            if qty <= 0:
                qty = 0.0
                cost = 0.0
                continue

            avg_entry = (cost / qty) if qty > 0 else 0.0
            sell_qty = min(qty, tr_qty)
            qty -= sell_qty
            cost -= sell_qty * avg_entry

            if qty <= 1e-12:
                qty = 0.0
                cost = 0.0

    if qty <= 0:
        if MANAGE_UNKNOWN_ENTRY == "1":
            price = get_price(client, sym)
            return {
                "entry": price,
                "qty": wallet_qty,
                "peak_net": 0.0,
                "highest_price": price,
                "entry_known": False,
                "source": "fallback",
            }
        return None

    avg_entry = cost / qty if qty > 0 else 0.0

    if wallet_qty > 0 and avg_entry > 0:
        price = get_price(client, sym)
        return {
            "entry": avg_entry,
            "qty": wallet_qty,
            "peak_net": 0.0,
            "highest_price": price,
            "entry_known": True,
            "source": "history",
        }

    return None


def sync_one_position(client: Client, sym: str):
    asset = base_asset(sym)
    qty = get_balance_free(client, asset)

    if qty <= 0:
        POSITIONS.pop(sym, None)
        return None

    price = get_price(client, sym)
    _, _, min_notional = get_lot_step(client, sym)

    if DUST_IGNORE == "1" and is_dust(qty, price, min_notional):
        POSITIONS.pop(sym, None)
        return None

    old = POSITIONS.get(sym, {})
    pos = build_position_from_trades(client, sym)
    if not pos:
        return None

    pos["peak_net"] = float(old.get("peak_net", 0.0) or 0.0)
    pos["highest_price"] = max(
        price,
        float(old.get("highest_price", 0.0) or 0.0),
        float(pos.get("highest_price", 0.0) or 0.0)
    )
    POSITIONS[sym] = pos
    return pos


def sync_wallet_positions(client: Client):
    if SYNC_EXISTING_POSITIONS != "1":
        return

    synced = []

    for sym in SYMBOLS:
        try:
            pos = sync_one_position(client, sym)
            if pos:
                synced.append(
                    f"{sym} qty={pos['qty']:.6f} entry≈{pos['entry']:.6f} source={pos.get('source', '?')}"
                )
        except Exception:
            continue

    if synced:
        msg = "🔄 <b>تمت مزامنة المراكز الموجودة بالمحفظة:</b>\n" + "\n".join(synced)
        print(msg)
        tg_send(msg)


# ================== Indicators Refresh ==================
def refresh_indicators(client: Client, sym: str):
    now = int(time.time())
    st = STATE.setdefault(sym, {
        "closes": deque(maxlen=500),
        "opens": deque(maxlen=500),
        "volumes": deque(maxlen=500),
        "last_klines_ts": 0,
        "ema_fast": 0.0,
        "ema_slow": 0.0,
        "prev_ema_fast": 0.0,
        "prev_ema_slow": 0.0,
        "rsi": 0.0,
        "last_close": 0.0,
        "last_open": 0.0,
        "last_volume": 0.0,
        "avg_volume": 0.0,
        "volume_ratio": 0.0,
        "warm": False
    })

    if (now - st["last_klines_ts"]) < KLINES_REFRESH_SEC and st["warm"]:
        return st

    interval = get_klines_interval(KLINES_INTERVAL)
    kl = client.get_klines(symbol=sym, interval=interval, limit=KLINES_LIMIT)

    if len(kl) >= 2:
        kl = kl[:-1]

    opens = [float(k[1]) for k in kl]
    closes = [float(k[4]) for k in kl]
    volumes = [float(k[5]) for k in kl]

    st["closes"].clear()
    st["opens"].clear()
    st["volumes"].clear()

    for x in opens:
        st["opens"].append(x)
    for x in closes:
        st["closes"].append(x)
    for x in volumes:
        st["volumes"].append(x)

    st["last_close"] = st["closes"][-1] if st["closes"] else 0.0
    st["last_open"] = st["opens"][-1] if st["opens"] else 0.0
    st["last_volume"] = st["volumes"][-1] if st["volumes"] else 0.0
    st["rsi"] = calc_rsi(list(st["closes"]), RSI_PERIOD)

    vols = list(st["volumes"])
    if len(vols) >= max(2, VOLUME_LOOKBACK):
        base_vols = vols[-(VOLUME_LOOKBACK + 1):-1]
        avg_vol = sum(base_vols) / len(base_vols) if base_vols else 0.0
        st["avg_volume"] = avg_vol
        st["volume_ratio"] = (st["last_volume"] / avg_vol) if avg_vol > 0 else 0.0

    if len(st["closes"]) >= EMA_SLOW:
        close_list = list(st["closes"])

        fast_init = sum(close_list[:EMA_FAST]) / EMA_FAST
        slow_init = sum(close_list[:EMA_SLOW]) / EMA_SLOW

        ef = fast_init
        for p in close_list[EMA_FAST:]:
            ef = ema(ef, p, EMA_FAST)

        es = slow_init
        for p in close_list[EMA_SLOW:]:
            es = ema(es, p, EMA_SLOW)

        if len(close_list) >= EMA_SLOW + 1:
            prev_close_list = close_list[:-1]

            pef_init = sum(prev_close_list[:EMA_FAST]) / EMA_FAST
            pes_init = sum(prev_close_list[:EMA_SLOW]) / EMA_SLOW

            pef = pef_init
            for p in prev_close_list[EMA_FAST:]:
                pef = ema(pef, p, EMA_FAST)

            pes = pes_init
            for p in prev_close_list[EMA_SLOW:]:
                pes = ema(pes, p, EMA_SLOW)
        else:
            pef = ef
            pes = es

        st["prev_ema_fast"] = pef
        st["prev_ema_slow"] = pes
        st["ema_fast"] = ef
        st["ema_slow"] = es
        st["warm"] = True

    st["last_klines_ts"] = now
    return st


def refresh_trend(client: Client, sym: str):
    now = int(time.time())
    st = TREND_STATE.setdefault(sym, {
        "last_ts": 0,
        "trend_ema": 0.0,
        "last_close": 0.0,
        "trend_ok": False,
        "warm": False
    })

    if (now - st["last_ts"]) < TREND_REFRESH_SEC and st["warm"]:
        return st

    interval = get_klines_interval(TREND_INTERVAL)
    kl = client.get_klines(symbol=sym, interval=interval, limit=TREND_LIMIT)

    if len(kl) >= 2:
        kl = kl[:-1]

    closes = [float(k[4]) for k in kl]

    if len(closes) >= TREND_EMA:
        ema_val = sum(closes[:TREND_EMA]) / TREND_EMA
        for p in closes[TREND_EMA:]:
            ema_val = ema(ema_val, p, TREND_EMA)

        st["trend_ema"] = ema_val
        st["last_close"] = closes[-1]
        st["trend_ok"] = closes[-1] > ema_val
        st["warm"] = True

    st["last_ts"] = now
    return st


# ================== Strategy ==================
def should_buy_scalp(st, trend_st, spread_pct: float, quote_volume_24h: float) -> bool:
    if not st.get("warm"):
        return False

    if REQUIRE_TREND_FILTER == "1":
        if not trend_st.get("warm"):
            return False
        if not trend_st.get("trend_ok"):
            return False

    if spread_pct > MAX_SPREAD_PCT:
        return False

    if quote_volume_24h < MIN_24H_QUOTE_VOLUME:
        return False

    ef = st["ema_fast"]
    es = st["ema_slow"]
    pef = st["prev_ema_fast"]
    pes = st["prev_ema_slow"]
    rsi = st["rsi"]
    close = st["last_close"]
    open_ = st.get("last_open", 0.0)
    vol_ratio = st.get("volume_ratio", 0.0)

    cross_up = (pef <= pes) and (ef > es)
    aligned_up = ef > es and close > ef
    rsi_ok = (RSI_BUY_MIN <= rsi <= RSI_BUY_MAX)
    bull_candle_ok = (close >= open_) if REQUIRE_BULL_CANDLE == "1" else True
    volume_ok = vol_ratio >= MIN_VOLUME_RATIO

    signal = (
        cross_up and rsi_ok and bull_candle_ok and volume_ok
    ) or (
        aligned_up and rsi_ok and bull_candle_ok and vol_ratio >= 0.95 and rsi <= 58
    )

    return signal


def should_exit_early(st) -> bool:
    if not st.get("warm"):
        return False

    pef = st["prev_ema_fast"]
    pes = st["prev_ema_slow"]
    ef = st["ema_fast"]
    es = st["ema_slow"]
    rsi = st["rsi"]
    close = st["last_close"]

    if EXIT_ON_EMA_CROSSDOWN == "1":
        cross_down = (pef >= pes) and (ef < es)
        if cross_down:
            return True

    if rsi >= EXIT_RSI_OVERBOUGHT:
        return True

    if close < ef and rsi < 50:
        return True

    return False


def gross_pnl_pct(entry: float, price: float) -> float:
    if entry <= 0:
        return 0.0
    return ((price - entry) / entry) * 100.0


def net_pnl_pct(gross_pnl: float) -> float:
    return gross_pnl - BREAKEVEN_PCT


def update_trailing_state(sym: str, price: float, net: float):
    pos = POSITIONS.get(sym)
    if not pos:
        return

    highest_price = float(pos.get("highest_price", 0.0) or 0.0)
    if price > highest_price:
        pos["highest_price"] = price

    peak_net = float(pos.get("peak_net", -999.0))
    if net > peak_net:
        pos["peak_net"] = net


def trailing_exit_triggered(sym: str, net: float) -> bool:
    if ENABLE_TRAILING != "1":
        return False

    pos = POSITIONS.get(sym)
    if not pos:
        return False

    peak_net = float(pos.get("peak_net", -999.0))
    if peak_net < TRAILING_ACTIVATE_NET_PCT:
        return False

    giveback = peak_net - net
    return giveback >= TRAILING_GIVEBACK_PCT


# ================== Trading Actions ==================
def safe_buy(client: Client, sym: str, market_price_hint: float) -> bool:
    if MODE != "live":
        qty_paper = BUY_USDT / market_price_hint
        old = POSITIONS.get(sym, {})
        old_qty = float(old.get("qty", 0.0) or 0.0)
        old_entry = float(old.get("entry", 0.0) or 0.0)

        new_qty = old_qty + qty_paper
        if new_qty > 0:
            new_entry = ((old_qty * old_entry) + (qty_paper * market_price_hint)) / new_qty
        else:
            new_entry = market_price_hint

        POSITIONS[sym] = {
            "entry": new_entry,
            "qty": new_qty,
            "peak_net": 0.0,
            "highest_price": market_price_hint,
            "entry_known": True,
            "source": "paper",
        }
        add_trade(sym, "BUY", qty_paper, market_price_hint, "PAPER scalp buy")
        update_report_stats_on_buy(sym)
        tg_send(f"🟢 PAPER BOUGHT {sym} qty={qty_paper:.6f} entry={market_price_hint:.6f}")
        return True

    _, _, min_notional = get_lot_step(client, sym)
    if min_notional > 0 and BUY_USDT < (min_notional + 1.0):
        tg_send(f"⚠️ BUY blocked {sym}: BUY_USDT too small vs minNotional={min_notional}")
        return False

    usdt_free = get_balance_free(client, "USDT")
    if usdt_free < max(MIN_USDT_FREE_TO_BUY, BUY_USDT):
        tg_send(f"⚠️ Not enough USDT to buy {sym}: free={usdt_free:.2f}")
        return False

    tg_send(f"🟢 SCALP BUY {sym} amount={BUY_USDT:.2f} USDT (MODE=live)")
    order = market_buy(client, sym, BUY_USDT)
    time.sleep(1)

    exec_price = avg_fill_price_from_order(order) or market_price_hint
    exec_qty = executed_qty_from_order(order)

    if exec_qty <= 0:
        tg_send(f"⚠️ BUY sent but executedQty not found for {sym}")
        sync_one_position(client, sym)
        return False

    add_trade(sym, "BUY", exec_qty, exec_price, "LIVE scalp buy")
    update_report_stats_on_buy(sym)

    pos = sync_one_position(client, sym)
    if pos:
        tg_send(
            f"✅ BOUGHT {sym} new_qty={exec_qty:.6f} "
            f"position_qty={pos['qty']:.6f} entry≈{pos['entry']:.6f}"
        )
    else:
        tg_send(f"✅ BOUGHT {sym} qty={exec_qty:.6f} entry={exec_price:.6f}")

    return True


def safe_sell(client: Client, sym: str, price: float, reason: str) -> bool:
    asset = base_asset(sym)
    qty_wallet = get_balance_free(client, asset)
    if qty_wallet <= 0:
        return False

    pos_before = dict(POSITIONS.get(sym, {}) or {})
    entry_before = float(pos_before.get("entry", 0.0) or 0.0)

    step, min_qty, min_notional = get_lot_step(client, sym)
    sell_qty = round_step(qty_wallet, step)
    notional = sell_qty * price

    if sell_qty <= 0:
        return False

    if sell_qty < min_qty:
        tg_send(f"⚠️ SELL blocked {sym}: sell_qty={sell_qty} < minQty={min_qty}")
        return False

    if min_notional > 0 and notional < min_notional:
        tg_send(f"⚠️ SELL blocked {sym}: dust notional={notional:.4f} < {min_notional}")
        return False

    if MODE != "live":
        add_trade(sym, "SELL", sell_qty, price, f"PAPER {reason}")

        pnl_usdt = estimate_trade_pnl_usdt(entry_before, price, sell_qty) if entry_before > 0 else 0.0
        update_report_stats_on_sell(sym, pnl_usdt)

        if SEND_REPORT_ON_EACH_SELL == "1" and entry_before > 0:
            send_sell_analysis_message(sym, sell_qty, entry_before, price, f"PAPER {reason}")

        tg_send(f"✅ PAPER SOLD {sym} qty={sell_qty:.6f} ({reason})")
        POSITIONS.pop(sym, None)
        return True

    order = market_sell(client, sym, sell_qty)
    exec_price = avg_fill_price_from_order(order) or price
    exec_qty = executed_qty_from_order(order) or sell_qty

    add_trade(sym, "SELL", exec_qty, exec_price, reason)

    pnl_usdt = estimate_trade_pnl_usdt(entry_before, exec_price, exec_qty) if entry_before > 0 else 0.0
    update_report_stats_on_sell(sym, pnl_usdt)

    tg_send(f"✅ SOLD {sym} qty={exec_qty:.6f} notional≈{exec_qty * exec_price:.2f} ({reason})")

    if SEND_REPORT_ON_EACH_SELL == "1" and entry_before > 0:
        send_sell_analysis_message(sym, exec_qty, entry_before, exec_price, reason)

    time.sleep(1)
    sync_one_position(client, sym)
    if get_balance_free(client, asset) <= 0:
        POSITIONS.pop(sym, None)

    return True


# ================== Debug ==================
def maybe_debug_log(sym: str, text: str):
    now = int(time.time())
    last = LAST_DEBUG_TS.get(sym, 0)
    if now - last >= DEBUG_EVERY_SEC:
        LAST_DEBUG_TS[sym] = now
        print(text)


# ================== Main ==================
def main():
    init_db()

    print(f"🤖 BOT WORKER STARTED MODE={MODE}")
    tg_send(f"🤖 <b>تم تشغيل البوت</b>\nالوضع الحالي: <b>{MODE}</b>")

    if TP_PCT < (BREAKEVEN_PCT + MIN_NET_PROFIT_PCT):
        tg_send(
            f"⚠️ TP_PCT={TP_PCT:.2f}% صغير نسبيًا.\n"
            f"Breakeven≈{BREAKEVEN_PCT:.2f}%\n"
            f"MinNet={MIN_NET_PROFIT_PCT:.2f}%\n"
            f"RequiredGrossTP≈{REQUIRED_GROSS_TP_PCT:.2f}%"
        )

    client = make_client()
    tg_send("✅ TEST: Worker is running now.")

    sync_wallet_positions(client)

    last_hb = 0

    while True:
        try:
            now = int(time.time())

            if now - last_hb >= HEARTBEAT_SEC:
                last_hb = now
                usdt_free_dbg = get_balance_free(client, "USDT")
                print(f"💓 HEARTBEAT {now} | USDT_free={usdt_free_dbg:.2f} | symbols={','.join(SYMBOLS)}")

            send_periodic_report_if_due()

            usdt_free = get_balance_free(client, "USDT")
            open_pos = count_open_positions_wallet(client)

            for sym in SYMBOLS:
                st_ind = refresh_indicators(client, sym)
                trend_st = refresh_trend(client, sym)

                price = get_price(client, sym)
                spread_pct = get_spread_pct(client, sym)
                vol_24h = get_24h_quote_volume(client, sym)

                asset = base_asset(sym)
                qty_wallet = get_balance_free(client, asset)
                _, _, min_notional = get_lot_step(client, sym)

                if DUST_IGNORE == "1" and is_dust(qty_wallet, price, min_notional):
                    qty_effective = 0.0
                else:
                    qty_effective = qty_wallet

                if qty_effective > 0:
                    if sym not in POSITIONS:
                        sync_one_position(client, sym)
                    else:
                        POSITIONS[sym]["qty"] = qty_effective

                entry = float(POSITIONS.get(sym, {}).get("entry", 0.0) or 0.0)
                gross = gross_pnl_pct(entry, price) if qty_effective > 0 and entry > 0 else 0.0
                net = net_pnl_pct(gross) if qty_effective > 0 and entry > 0 else 0.0

                if qty_effective > 0:
                    update_trailing_state(sym, price, net)

                set_status(
                    mode=MODE,
                    last_heartbeat=int(time.time()),
                    symbol=sym,
                    price=price,
                    pnl=round(net, 4),
                    position_qty=qty_effective,
                    position_entry=entry,
                    last_action=(
                        f"tick usdt_free={usdt_free:.2f} open_pos={open_pos} "
                        f"rsi={st_ind.get('rsi', 0):.1f} gross={gross:.2f}% net={net:.2f}% "
                        f"trend_ok={trend_st.get('trend_ok', False)} spread={spread_pct:.3f}% "
                        f"vol24h={vol_24h:.0f} volRatio={st_ind.get('volume_ratio', 0):.2f} "
                        f"reqTP≈{REQUIRED_GROSS_TP_PCT:.2f}%"
                    ),
                    last_error=""
                )

                # ================== SELL ==================
                if qty_effective > 0:
                    if not in_cooldown(sym):
                        if gross >= REQUIRED_GROSS_TP_PCT and net >= MIN_NET_PROFIT_PCT:
                            tg_send(
                                f"✅ TP {sym} gross={gross:.2f}% net={net:.2f}% "
                                f"(fees≈{BREAKEVEN_PCT:.2f}%) -> SELL"
                            )
                            if safe_sell(client, sym, price, f"SCALP TP gross={gross:.2f}% net={net:.2f}%"):
                                mark_trade(sym)
                                time.sleep(1)
                            continue

                        if ENABLE_TRAILING == "1" and trailing_exit_triggered(sym, net):
                            peak_net = float(POSITIONS.get(sym, {}).get("peak_net", 0.0) or 0.0)
                            tg_send(f"📉 Trailing exit {sym} peak_net={peak_net:.2f}% net={net:.2f}% -> SELL")
                            if safe_sell(client, sym, price, f"SCALP trailing peak_net={peak_net:.2f}% net={net:.2f}%"):
                                mark_trade(sym)
                                time.sleep(1)
                            continue

                        if gross <= -SL_PCT:
                            tg_send(f"🛑 SL {sym} gross={gross:.2f}% net={net:.2f}% -> SELL")
                            if safe_sell(client, sym, price, f"SCALP SL gross={gross:.2f}% net={net:.2f}%"):
                                mark_trade(sym)
                                time.sleep(1)
                            continue

                        if should_exit_early(st_ind) and net >= EARLY_EXIT_MIN_NET_PCT:
                            tg_send(f"⚡ Early exit {sym} gross={gross:.2f}% net={net:.2f}% -> SELL")
                            if safe_sell(client, sym, price, f"SCALP early-exit gross={gross:.2f}% net={net:.2f}%"):
                                mark_trade(sym)
                                time.sleep(1)
                            continue

                    maybe_debug_log(
                        sym,
                        f"[{sym}] HOLD "
                        f"price={price:.6f} qty={qty_effective:.8f} entry={entry:.6f} "
                        f"gross={gross:.2f}% net={net:.2f}% "
                        f"peak_net={POSITIONS.get(sym, {}).get('peak_net', 0.0):.2f}% "
                        f"rsi={st_ind.get('rsi', 0):.2f} "
                        f"volRatio={st_ind.get('volume_ratio', 0):.2f} "
                        f"trend_ok={trend_st.get('trend_ok', False)} "
                        f"spread={spread_pct:.3f}% vol24h={vol_24h:.0f}"
                    )
                    continue

                # ================== BUY ==================
                open_pos = count_open_positions_wallet(client)
                buy_signal = should_buy_scalp(st_ind, trend_st, spread_pct, vol_24h)

                if open_pos >= MAX_OPEN_POSITIONS:
                    maybe_debug_log(sym, f"[{sym}] BUY blocked: open_pos={open_pos} >= MAX_OPEN_POSITIONS={MAX_OPEN_POSITIONS}")
                    continue

                if usdt_free < MIN_USDT_FREE_TO_BUY:
                    maybe_debug_log(sym, f"[{sym}] BUY blocked: usdt_free={usdt_free:.2f} < MIN_USDT_FREE_TO_BUY={MIN_USDT_FREE_TO_BUY}")
                    continue

                if in_cooldown(sym):
                    maybe_debug_log(sym, f"[{sym}] BUY blocked: cooldown active")
                    continue

                if not st_ind.get("warm", False):
                    maybe_debug_log(sym, f"[{sym}] BUY blocked: indicators not warm yet")
                    continue

                if REQUIRE_TREND_FILTER == "1" and not trend_st.get("warm", False):
                    maybe_debug_log(sym, f"[{sym}] BUY blocked: trend not warm yet")
                    continue

                if not buy_signal:
                    maybe_debug_log(
                        sym,
                        f"[{sym}] NO BUY SIGNAL | "
                        f"price={price:.6f} rsi={st_ind.get('rsi', 0):.2f} "
                        f"ema_fast={st_ind.get('ema_fast', 0):.6f} "
                        f"ema_slow={st_ind.get('ema_slow', 0):.6f} "
                        f"volRatio={st_ind.get('volume_ratio', 0):.2f} "
                        f"trend_ok={trend_st.get('trend_ok', False)} "
                        f"spread={spread_pct:.3f}% vol24h={vol_24h:.0f}"
                    )
                    continue

                tg_send(
                    f"🟢 SCALP SIGNAL {sym} | rsi={st_ind['rsi']:.1f} "
                    f"ema{EMA_FAST}={st_ind['ema_fast']:.6f} ema{EMA_SLOW}={st_ind['ema_slow']:.6f} "
                    f"trendEMA{TREND_EMA}={trend_st.get('trend_ema', 0):.6f} "
                    f"volRatio={st_ind.get('volume_ratio', 0):.2f} "
                    f"spread={spread_pct:.3f}% reqTP≈{REQUIRED_GROSS_TP_PCT:.2f}%"
                )

                if safe_buy(client, sym, price):
                    mark_trade(sym)
                    usdt_free = get_balance_free(client, "USDT")

                time.sleep(1)

            time.sleep(CHECK_INTERVAL)

        except BinanceAPIException as e:
            err = f"Binance API Error: {e}"
            print("❌", err)
            print(traceback.format_exc())
            tg_send("❌ " + err)
            set_status(last_error=err, last_action="error")
            time.sleep(10)

        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print("❌", err)
            print(traceback.format_exc())
            tg_send("❌ " + err)
            set_status(last_error=err, last_action="error")
            time.sleep(10)


if __name__ == "__main__":
    main()
