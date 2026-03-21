import os
import time
import math
import traceback
from datetime import datetime
from collections import deque

import requests
import ccxt

from db import init_db, set_status, add_trade


# ================== Optional .env Loader ==================
def load_dotenv_file(path: str = ".env"):
    try:
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and os.getenv(k) is None:
                    os.environ[k] = v
    except Exception:
        pass


load_dotenv_file()


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


# ================== Helpers ==================
def fmt_usdt(x: float) -> str:
    sign = "+" if x > 0 else ""
    return f"{sign}{x:.2f} USDT"


def fmt_pct(x: float) -> str:
    sign = "+" if x > 0 else ""
    return f"{sign}{x:.2f}%"


def normalize_symbol(sym: str) -> str:
    s = sym.strip().upper()
    if "/" in s:
        return s
    if s.endswith("USDT"):
        return s[:-4] + "/USDT"
    if s.endswith("USDC"):
        return s[:-4] + "/USDC"
    return s


def pair_key(exchange_id: str, sym: str) -> str:
    return f"{exchange_id}:{sym}"


def split_symbol(sym: str):
    s = normalize_symbol(sym)
    if "/" in s:
        return s.split("/")
    return s, ""


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


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


def calc_atr_pct(highs, lows, closes, period=14):
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if len(trs) < period:
        return 0.0
    atr = sum(trs[-period:]) / period
    last_close = closes[-1]
    if last_close <= 0:
        return 0.0
    return (atr / last_close) * 100.0


def gross_pnl_pct(entry: float, price: float) -> float:
    if entry <= 0:
        return 0.0
    return ((price - entry) / entry) * 100.0


# ================== ENV ==================
TG_TOKEN = getenv_str("TG_TOKEN", "")
TG_ID = getenv_str("TG_ID", "")

ENABLE_TRADING = getenv_str("ENABLE_TRADING", "0")
LIVE_TRADING = getenv_str("LIVE_TRADING", "0")
MODE = "live" if (ENABLE_TRADING == "1" or LIVE_TRADING == "1") else "paper"

ACTIVE_EXCHANGES = getenv_str("ACTIVE_EXCHANGES", "binance,bybit")
ACTIVE_EXCHANGES = [x.strip().lower() for x in ACTIVE_EXCHANGES.split(",") if x.strip()]
ACTIVE_EXCHANGES = [x for x in ACTIVE_EXCHANGES if x in ("binance", "bybit")]
if not ACTIVE_EXCHANGES:
    ACTIVE_EXCHANGES = ["binance", "bybit"]

DEFAULT_SYMBOLS = (
    "BTCUSDT,ETHUSDT,XRPUSDT,BNBUSDT,SOLUSDT,ADAUSDT,DOGEUSDT,"
    "LINKUSDT,AVAXUSDT,DOTUSDT,LTCUSDT,BCHUSDT,ATOMUSDT,UNIUSDT,"
    "APTUSDT,NEARUSDT,ARBUSDT,OPUSDT,FILUSDT,ETCUSDT,SUIUSDT,TRXUSDT,PEPEUSDT"
)
SYMBOLS = getenv_str("SYMBOLS", DEFAULT_SYMBOLS)
SYMBOLS = [normalize_symbol(s) for s in SYMBOLS.split(",") if s.strip()]

BUY_USDT = getenv_float("BUY_USDT", 24.0)
BUY_USDT_MIN = getenv_float("BUY_USDT_MIN", 18.0)
BUY_USDT_MAX = getenv_float("BUY_USDT_MAX", 40.0)

TP_PCT = getenv_float("TP_PCT", 0.55)
SL_PCT = getenv_float("SL_PCT", 1.90)
CHECK_INTERVAL = getenv_float("CHECK_INTERVAL", 4.0)
MIN_USDT_FREE_TO_BUY = getenv_float("MIN_USDT_FREE_TO_BUY", 8.0)

MAX_OPEN_POSITIONS = getenv_int("MAX_OPEN_POSITIONS", 8)
MAX_NEW_BUYS_PER_CYCLE = getenv_int("MAX_NEW_BUYS_PER_CYCLE", 4)
COOLDOWN_SEC = getenv_int("COOLDOWN_SEC", 8)

FEE_PCT = getenv_float("FEE_PCT", 0.10)
SLIPPAGE_PCT = getenv_float("SLIPPAGE_PCT", 0.12)
MIN_NET_PROFIT_PCT = getenv_float("MIN_NET_PROFIT_PCT", 0.08)

BREAKEVEN_PCT = (2.0 * FEE_PCT) + SLIPPAGE_PCT
REQUIRED_GROSS_TP_PCT = max(TP_PCT, BREAKEVEN_PCT + MIN_NET_PROFIT_PCT)

HEARTBEAT_SEC = getenv_int("HEARTBEAT_SEC", 30)

KLINES_INTERVAL = getenv_str("KLINES_INTERVAL", "3m")
KLINES_LIMIT = getenv_int("KLINES_LIMIT", 220)
KLINES_REFRESH_SEC = getenv_int("KLINES_REFRESH_SEC", 15)

EMA_FAST = getenv_int("EMA_FAST", 5)
EMA_SLOW = getenv_int("EMA_SLOW", 13)
RSI_PERIOD = getenv_int("RSI_PERIOD", 14)

RSI_BUY_MIN = getenv_float("RSI_BUY_MIN", 28.0)
RSI_BUY_MAX = getenv_float("RSI_BUY_MAX", 82.0)

EXIT_ON_EMA_CROSSDOWN = getenv_str("EXIT_ON_EMA_CROSSDOWN", "1")
EXIT_RSI_OVERBOUGHT = getenv_float("EXIT_RSI_OVERBOUGHT", 86.0)

TREND_INTERVAL = getenv_str("TREND_INTERVAL", "15m")
TREND_LIMIT = getenv_int("TREND_LIMIT", 260)
TREND_EMA = getenv_int("TREND_EMA", 200)
TREND_REFRESH_SEC = getenv_int("TREND_REFRESH_SEC", 45)
REQUIRE_TREND_FILTER = getenv_str("REQUIRE_TREND_FILTER", "0")

MAX_SPREAD_PCT = getenv_float("MAX_SPREAD_PCT", 0.90)
MIN_24H_QUOTE_VOLUME = getenv_float("MIN_24H_QUOTE_VOLUME", 300000.0)

VOLUME_LOOKBACK = getenv_int("VOLUME_LOOKBACK", 20)
MIN_VOLUME_RATIO = getenv_float("MIN_VOLUME_RATIO", 0.05)
REQUIRE_BULL_CANDLE = getenv_str("REQUIRE_BULL_CANDLE", "0")

ENABLE_TRAILING = getenv_str("ENABLE_TRAILING", "1")
SMART_TRAILING = getenv_str("SMART_TRAILING", "1")

TRAIL_LVL1_ACTIVATE = getenv_float("TRAIL_LVL1_ACTIVATE", 0.35)
TRAIL_LVL1_GIVEBACK = getenv_float("TRAIL_LVL1_GIVEBACK", 0.22)
TRAIL_LVL2_ACTIVATE = getenv_float("TRAIL_LVL2_ACTIVATE", 0.80)
TRAIL_LVL2_GIVEBACK = getenv_float("TRAIL_LVL2_GIVEBACK", 0.18)
TRAIL_LVL3_ACTIVATE = getenv_float("TRAIL_LVL3_ACTIVATE", 1.50)
TRAIL_LVL3_GIVEBACK = getenv_float("TRAIL_LVL3_GIVEBACK", 0.14)

SYNC_EXISTING_POSITIONS = getenv_str("SYNC_EXISTING_POSITIONS", "1")
MANAGE_UNKNOWN_ENTRY = getenv_str("MANAGE_UNKNOWN_ENTRY", "1")
TRADES_FETCH_LIMIT = getenv_int("TRADES_FETCH_LIMIT", 1000)

EARLY_EXIT_MIN_NET_PCT = getenv_float("EARLY_EXIT_MIN_NET_PCT", 0.01)

REPORT_INTERVAL_SEC = getenv_int("REPORT_INTERVAL_SEC", 86400)
SEND_REPORT_ON_EACH_SELL = getenv_str("SEND_REPORT_ON_EACH_SELL", "1")
SEND_DAILY_REPORT = getenv_str("SEND_DAILY_REPORT", "1")

BUY_SCORE_MIN = getenv_float("BUY_SCORE_MIN", 8.0)
MAX_CANDIDATES_PER_EXCHANGE = getenv_int("MAX_CANDIDATES_PER_EXCHANGE", 16)

AUTO_INCLUDE_WALLET_SYMBOLS = getenv_str("AUTO_INCLUDE_WALLET_SYMBOLS", "1")
ALLOW_ONE_BUY_PER_EXCHANGE = getenv_str("ALLOW_ONE_BUY_PER_EXCHANGE", "0")
STRICT_BEST_GLOBAL_ONLY = getenv_str("STRICT_BEST_GLOBAL_ONLY", "0")

OLD_POSITION_FORCE_SELL_PCT = getenv_float("OLD_POSITION_FORCE_SELL_PCT", -4.0)
OLD_POSITION_TAKE_PROFIT_PCT = getenv_float("OLD_POSITION_TAKE_PROFIT_PCT", 0.70)

TELEGRAM_TRADES_ONLY = getenv_str("TELEGRAM_TRADES_ONLY", "1")

MAX_HOLD_HOURS = getenv_float("MAX_HOLD_HOURS", 5.0)
HARD_MAX_HOLD_HOURS = getenv_float("HARD_MAX_HOLD_HOURS", 10.0)
TIME_EXIT_MIN_NET_PCT = getenv_float("TIME_EXIT_MIN_NET_PCT", 0.00)

ATR_PERIOD = getenv_int("ATR_PERIOD", 14)
ATR_MIN_PCT = getenv_float("ATR_MIN_PCT", 0.01)
ATR_MAX_PCT = getenv_float("ATR_MAX_PCT", 12.0)

ENABLE_PARTIAL_TP = getenv_str("ENABLE_PARTIAL_TP", "1")
PARTIAL_TP_NET_PCT = getenv_float("PARTIAL_TP_NET_PCT", 0.28)
PARTIAL_TP_SELL_RATIO = getenv_float("PARTIAL_TP_SELL_RATIO", 0.35)

ENABLE_BREAK_EVEN = getenv_str("ENABLE_BREAK_EVEN", "1")
BREAK_EVEN_ARM_NET_PCT = getenv_float("BREAK_EVEN_ARM_NET_PCT", 0.10)

MAX_DAILY_LOSS_USDT = getenv_float("MAX_DAILY_LOSS_USDT", 100000.0)
MAX_CONSECUTIVE_LOSSES = getenv_int("MAX_CONSECUTIVE_LOSSES", 999)
LOSS_PAUSE_MINUTES = getenv_int("LOSS_PAUSE_MINUTES", 5)

ENABLE_DYNAMIC_BUY_SIZE = getenv_str("ENABLE_DYNAMIC_BUY_SIZE", "1")
ENABLE_MARKET_REGIME_FILTER = getenv_str("ENABLE_MARKET_REGIME_FILTER", "0")
BTC_REGIME_SYMBOL = getenv_str("BTC_REGIME_SYMBOL", "BTCUSDT")
BTC_REGIME_INTERVAL = getenv_str("BTC_REGIME_INTERVAL", "15m")
BTC_REGIME_LIMIT = getenv_int("BTC_REGIME_LIMIT", 260)
BTC_REGIME_EMA = getenv_int("BTC_REGIME_EMA", 200)
BTC_REGIME_REFRESH_SEC = getenv_int("BTC_REGIME_REFRESH_SEC", 60)

REENTRY_AFTER_SELL_COOLDOWN_SEC = getenv_int("REENTRY_AFTER_SELL_COOLDOWN_SEC", 3)
PRINT_CANDIDATES = getenv_str("PRINT_CANDIDATES", "1")


# ================== Global State ==================
POSITIONS = {}
LAST_TRADE_TS = {}
STATE = {}
TREND_STATE = {}
MARKET_REGIME_STATE = {}

TRADING_GUARD = {
    "day_key": datetime.now().strftime("%Y-%m-%d"),
    "daily_pnl": 0.0,
    "consecutive_losses": 0,
    "pause_until_ts": 0,
}

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
    "symbols": {},
}


# ================== Cooldown ==================
def in_cooldown(key: str) -> bool:
    last_ts = int(LAST_TRADE_TS.get(key, 0) or 0)
    return (time.time() - last_ts) < COOLDOWN_SEC


def mark_trade(key: str, cooldown_override: int = None):
    cd = COOLDOWN_SEC if cooldown_override is None else int(cooldown_override)
    LAST_TRADE_TS[key] = int(time.time()) - max(0, COOLDOWN_SEC - cd)


def position_age_hours(key: str) -> float:
    pos = POSITIONS.get(key, {}) or {}
    opened_at = int(pos.get("opened_at", 0) or 0)
    if opened_at <= 0:
        return 0.0
    return (time.time() - opened_at) / 3600.0


# ================== Telegram ==================
def _telegram_allowed(msg: str) -> bool:
    if TELEGRAM_TRADES_ONLY != "1":
        return True
    allowed = (
        "BOUGHT",
        "SOLD",
        "إغلاق صفقة",
        "تقرير التداول",
        "تقرير التداول الآلي",
        "PAPER BOUGHT",
        "PAPER SOLD",
        "تم تشغيل البوت",
        "worker is running now",
        "⛔",
        "⚠️",
    )
    return any(x in msg for x in allowed)


def tg_send(msg: str):
    if not _telegram_allowed(msg):
        return False
    if not TG_TOKEN or not TG_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        r = requests.post(
            url,
            timeout=15,
            data={
                "chat_id": TG_ID,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
        return r.status_code == 200
    except Exception:
        return False


# ================== Trading Guard ==================
def reset_daily_guard_if_needed():
    today = datetime.now().strftime("%Y-%m-%d")
    if TRADING_GUARD["day_key"] != today:
        TRADING_GUARD["day_key"] = today
        TRADING_GUARD["daily_pnl"] = 0.0
        TRADING_GUARD["consecutive_losses"] = 0
        TRADING_GUARD["pause_until_ts"] = 0


def trading_paused() -> bool:
    reset_daily_guard_if_needed()
    now = int(time.time())
    if TRADING_GUARD["daily_pnl"] <= -abs(MAX_DAILY_LOSS_USDT):
        return True
    if now < int(TRADING_GUARD["pause_until_ts"] or 0):
        return True
    return False


def trading_pause_reason() -> str:
    now = int(time.time())
    if TRADING_GUARD["daily_pnl"] <= -abs(MAX_DAILY_LOSS_USDT):
        return f"تم الوصول للحد اليومي للخسارة {fmt_usdt(TRADING_GUARD['daily_pnl'])}"
    if now < int(TRADING_GUARD["pause_until_ts"] or 0):
        mins = max(1, int((TRADING_GUARD["pause_until_ts"] - now) / 60))
        return f"توقف مؤقت بعد خسائر متتالية لمدة {mins} دقيقة"
    return ""


def register_closed_trade_guard(pnl_usdt: float):
    reset_daily_guard_if_needed()
    TRADING_GUARD["daily_pnl"] += pnl_usdt
    if pnl_usdt < 0:
        TRADING_GUARD["consecutive_losses"] += 1
    else:
        TRADING_GUARD["consecutive_losses"] = 0

    if TRADING_GUARD["consecutive_losses"] >= MAX_CONSECUTIVE_LOSSES:
        TRADING_GUARD["pause_until_ts"] = int(time.time()) + (LOSS_PAUSE_MINUTES * 60)
        tg_send(
            "⚠️ <b>تم إيقاف الشراء مؤقتًا</b>\n"
            f"بسبب {TRADING_GUARD['consecutive_losses']} خسائر متتالية.\n"
            f"مدة التوقف: {LOSS_PAUSE_MINUTES} دقيقة."
        )


# ================== Reporting ==================
def estimate_trade_pnl_usdt(entry: float, exit_price: float, qty: float) -> float:
    if entry <= 0 or exit_price <= 0 or qty <= 0:
        return 0.0
    buy_cost = entry * qty
    sell_value = exit_price * qty
    buy_fee = buy_cost * (FEE_PCT / 100.0)
    sell_fee = sell_value * (FEE_PCT / 100.0)
    return sell_value - buy_cost - buy_fee - sell_fee


def update_report_stats_on_buy(lbl: str):
    REPORT_STATE["buys"] += 1
    REPORT_STATE["symbols"].setdefault(lbl, {"trades": 0, "wins": 0, "losses": 0, "profit": 0.0})


def update_report_stats_on_sell(lbl: str, pnl_usdt: float):
    REPORT_STATE["sells"] += 1
    REPORT_STATE["total_profit_usdt"] += pnl_usdt

    bucket = REPORT_STATE["symbols"].setdefault(lbl, {"trades": 0, "wins": 0, "losses": 0, "profit": 0.0})
    bucket["trades"] += 1
    bucket["profit"] += pnl_usdt

    if pnl_usdt >= 0:
        REPORT_STATE["wins"] += 1
        bucket["wins"] += 1
    else:
        REPORT_STATE["losses"] += 1
        bucket["losses"] += 1

    if REPORT_STATE["best_trade"] is None or pnl_usdt > REPORT_STATE["best_trade"]["pnl"]:
        REPORT_STATE["best_trade"] = {"symbol": lbl, "pnl": pnl_usdt}
    if REPORT_STATE["worst_trade"] is None or pnl_usdt < REPORT_STATE["worst_trade"]["pnl"]:
        REPORT_STATE["worst_trade"] = {"symbol": lbl, "pnl": pnl_usdt}


def build_symbol_ranking_text():
    ranked = sorted(REPORT_STATE["symbols"].items(), key=lambda kv: kv[1].get("profit", 0.0), reverse=True)
    rows = []
    for sym, st in ranked[:5]:
        rows.append(
            f"• <b>{sym}</b>: {fmt_usdt(st['profit'])} | صفقات: {st['trades']} | ✅ {st['wins']} | ❌ {st['losses']}"
        )
    return "\n".join(rows) if rows else "• لا توجد صفقات مغلقة بعد"


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

    best_text = f"{best_trade['symbol']} {fmt_usdt(best_trade['pnl'])}" if best_trade else "لا يوجد"
    worst_text = f"{worst_trade['symbol']} {fmt_usdt(worst_trade['pnl'])}" if worst_trade else "لا يوجد"

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    paused_text = "نعم" if trading_paused() else "لا"
    pause_reason = trading_pause_reason() if trading_paused() else "لا يوجد"

    return (
        "📊 <b>تقرير التداول الآلي</b>\n\n"
        f"📅 <b>وقت التقرير:</b> {now_str}\n"
        f"🕒 <b>الفترة:</b> آخر {hours:.1f} ساعة\n"
        f"🟢 <b>عمليات الشراء:</b> {REPORT_STATE['buys']}\n"
        f"🔴 <b>الصفقات المغلقة:</b> {total_closed}\n"
        f"✅ <b>الصفقات الرابحة:</b> {wins}\n"
        f"❌ <b>الصفقات الخاسرة:</b> {losses}\n"
        f"🎯 <b>نسبة النجاح:</b> {win_rate:.1f}%\n"
        f"💰 <b>صافي الربح:</b> {fmt_usdt(total_profit)}\n"
        f"📉 <b>ربح/خسارة اليوم:</b> {fmt_usdt(TRADING_GUARD['daily_pnl'])}\n"
        f"⛔ <b>توقف الشراء:</b> {paused_text}\n"
        f"📝 <b>السبب:</b> {pause_reason}\n"
        f"🏆 <b>أفضل صفقة:</b> {best_text}\n"
        f"⚠️ <b>أسوأ صفقة:</b> {worst_text}\n\n"
        f"📌 <b>ترتيب الأزواج:</b>\n{build_symbol_ranking_text()}"
    )


def send_periodic_report_if_due():
    if SEND_DAILY_REPORT != "1":
        return
    now = int(time.time())
    last_ts = int(REPORT_STATE.get("last_report_ts", now))
    if (now - last_ts) >= REPORT_INTERVAL_SEC:
        tg_send(build_daily_report_message())
        REPORT_STATE["last_report_ts"] = now


def send_sell_analysis_message(lbl: str, qty: float, entry: float, exit_price: float, reason: str):
    pnl_usdt = estimate_trade_pnl_usdt(entry, exit_price, qty)
    gross_pct = gross_pnl_pct(entry, exit_price) if entry > 0 else 0.0
    net_pct_est = gross_pct - (2.0 * FEE_PCT)

    direction = "ربح" if pnl_usdt >= 0 else "خسارة"

    msg = (
        f"📉 <b>إغلاق صفقة {lbl}</b>\n\n"
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


# ================== Exchange ==================
def make_exchange(exchange_id: str):
    exchange_id = exchange_id.lower()

    if exchange_id == "binance":
        api_key = getenv_str("BINANCE_API_KEY", "")
        secret = getenv_str("BINANCE_API_SECRET", "")
        if MODE == "live" and (not api_key or not secret):
            raise RuntimeError("BINANCE_API_KEY أو BINANCE_API_SECRET غير موجودين")
        ex = ccxt.binance({
            "apiKey": api_key,
            "secret": secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })

    elif exchange_id == "bybit":
        api_key = getenv_str("BYBIT_API_KEY", "")
        secret = getenv_str("BYBIT_API_SECRET", "")
        if MODE == "live" and (not api_key or not secret):
            raise RuntimeError("BYBIT_API_KEY أو BYBIT_API_SECRET غير موجودين")
        ex = ccxt.bybit({
            "apiKey": api_key,
            "secret": secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
    else:
        raise RuntimeError(f"Unsupported exchange: {exchange_id}")

    ex.load_markets()
    return ex


def make_all_exchanges():
    result = {}
    for ex_id in ACTIVE_EXCHANGES:
        try:
            result[ex_id] = make_exchange(ex_id)
            print(f"✅ connected: {ex_id}")
        except Exception as e:
            print(f"❌ failed to connect {ex_id}: {e}")
    return result


# ================== Market Helpers ==================
def get_price(exchange, symbol: str) -> float:
    t = exchange.fetch_ticker(symbol)
    last = t.get("last")
    if last is None:
        bid = t.get("bid")
        ask = t.get("ask")
        if bid and ask:
            return float((bid + ask) / 2.0)
        raise RuntimeError(f"last price unavailable for {exchange.id} {symbol}")
    return float(last)


def get_bid_ask(exchange, symbol: str):
    t = exchange.fetch_ticker(symbol)
    bid = float(t.get("bid") or 0.0)
    ask = float(t.get("ask") or 0.0)

    if bid <= 0 or ask <= 0:
        ob = exchange.fetch_order_book(symbol, 5)
        bids = ob.get("bids") or []
        asks = ob.get("asks") or []
        bid = float(bids[0][0]) if bids else 0.0
        ask = float(asks[0][0]) if asks else 0.0

    return bid, ask


def get_spread_pct(exchange, symbol: str) -> float:
    bid, ask = get_bid_ask(exchange, symbol)
    if bid <= 0 or ask <= 0:
        return 999.0
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return 999.0
    return ((ask - bid) / mid) * 100.0


def get_24h_quote_volume(exchange, symbol: str) -> float:
    try:
        t = exchange.fetch_ticker(symbol)
        return float(t.get("quoteVolume") or 0.0)
    except Exception:
        return 0.0


def get_balance_free(exchange, asset: str) -> float:
    bal = exchange.fetch_balance()
    free_map = bal.get("free", {}) or {}
    return float(free_map.get(asset, 0.0) or 0.0)


def get_market(exchange, symbol: str):
    if symbol not in exchange.markets:
        exchange.load_markets(True)
    return exchange.market(symbol)


def get_lot_step(exchange, symbol: str):
    market = get_market(exchange, symbol)
    limits = market.get("limits", {}) or {}
    amt_limits = limits.get("amount", {}) or {}
    cost_limits = limits.get("cost", {}) or {}
    return 0.0, float(amt_limits.get("min") or 0.0), float(cost_limits.get("min") or 0.0)


def amount_to_precision_num(exchange, symbol: str, amount: float) -> float:
    return float(exchange.amount_to_precision(symbol, amount))


def round_step(exchange, symbol: str, qty: float) -> float:
    try:
        return amount_to_precision_num(exchange, symbol, qty)
    except Exception:
        return qty


def market_buy(exchange, symbol: str, usdt_amount: float, market_price_hint: float):
    raw_amount = usdt_amount / market_price_hint
    amount = amount_to_precision_num(exchange, symbol, raw_amount)
    if amount <= 0:
        raise RuntimeError(f"Invalid buy amount for {exchange.id} {symbol}")
    return exchange.create_order(symbol, "market", "buy", amount)


def market_sell(exchange, symbol: str, qty: float):
    qty = amount_to_precision_num(exchange, symbol, qty)
    if qty <= 0:
        raise RuntimeError(f"Invalid sell amount for {exchange.id} {symbol}")
    return exchange.create_order(symbol, "market", "sell", qty)


def avg_fill_price_from_order(exchange, order, symbol: str) -> float:
    try:
        avg = order.get("average")
        if avg:
            return float(avg)

        filled = float(order.get("filled") or 0.0)
        cost = float(order.get("cost") or 0.0)
        if filled > 0 and cost > 0:
            return cost / filled

        oid = order.get("id")
        if oid:
            fetched = exchange.fetch_order(oid, symbol)
            avg = fetched.get("average")
            if avg:
                return float(avg)
            filled = float(fetched.get("filled") or 0.0)
            cost = float(fetched.get("cost") or 0.0)
            if filled > 0 and cost > 0:
                return cost / filled
        return 0.0
    except Exception:
        return 0.0


def executed_qty_from_order(exchange, order, symbol: str) -> float:
    try:
        filled = float(order.get("filled") or 0.0)
        if filled > 0:
            return filled
        oid = order.get("id")
        if oid:
            fetched = exchange.fetch_order(oid, symbol)
            return float(fetched.get("filled") or 0.0)
        return 0.0
    except Exception:
        return 0.0


# ================== Position Sync ==================
def is_dust(qty: float, price: float, min_notional: float) -> bool:
    if qty <= 0 or min_notional <= 0:
        return False
    return (qty * price) < (min_notional - 0.3)


def count_bot_open_positions(exchange_id: str) -> int:
    cnt = 0
    prefix = f"{exchange_id}:"
    for key, pos in POSITIONS.items():
        if key.startswith(prefix) and float(pos.get("qty", 0.0) or 0.0) > 0 and bool(pos.get("opened_by_bot", False)):
            cnt += 1
    return cnt


def build_position_from_trades(exchange, exchange_id: str, sym: str):
    base, _ = split_symbol(sym)
    wallet_qty = get_balance_free(exchange, base)
    if wallet_qty <= 0:
        return None

    try:
        trades = exchange.fetch_my_trades(sym, limit=TRADES_FETCH_LIMIT)
    except Exception:
        trades = []

    if not trades:
        if MANAGE_UNKNOWN_ENTRY == "1":
            price = get_price(exchange, sym)
            return {
                "entry": price,
                "qty": wallet_qty,
                "peak_net": 0.0,
                "highest_price": price,
                "entry_known": False,
                "source": "fallback",
                "opened_by_bot": False,
                "opened_at": 0,
                "state": "open",
                "partial_tp_done": False,
                "break_even_armed": False,
            }
        return None

    qty = 0.0
    cost = 0.0
    trades = sorted(trades, key=lambda x: int(x.get("timestamp", 0) or 0))

    for tr in trades:
        tr_qty = float(tr.get("amount", 0) or 0)
        tr_price = float(tr.get("price", 0) or 0)
        side = str(tr.get("side", "")).lower()
        if tr_qty <= 0 or tr_price <= 0:
            continue

        if side == "buy":
            qty += tr_qty
            cost += tr_qty * tr_price
        elif side == "sell":
            if qty <= 0:
                qty = 0.0
                cost = 0.0
                continue
            avg_entry = cost / qty if qty > 0 else 0.0
            sell_qty = min(qty, tr_qty)
            qty -= sell_qty
            cost -= sell_qty * avg_entry
            if qty <= 1e-12:
                qty = 0.0
                cost = 0.0

    if qty <= 0:
        if MANAGE_UNKNOWN_ENTRY == "1":
            price = get_price(exchange, sym)
            return {
                "entry": price,
                "qty": wallet_qty,
                "peak_net": 0.0,
                "highest_price": price,
                "entry_known": False,
                "source": "fallback",
                "opened_by_bot": False,
                "opened_at": 0,
                "state": "open",
                "partial_tp_done": False,
                "break_even_armed": False,
            }
        return None

    price = get_price(exchange, sym)
    return {
        "entry": cost / qty if qty > 0 else 0.0,
        "qty": wallet_qty,
        "peak_net": 0.0,
        "highest_price": price,
        "entry_known": True,
        "source": "history",
        "opened_by_bot": False,
        "opened_at": 0,
        "state": "open",
        "partial_tp_done": False,
        "break_even_armed": False,
    }


def sync_one_position(exchange, exchange_id: str, sym: str):
    key = pair_key(exchange_id, sym)
    base, _ = split_symbol(sym)
    qty = get_balance_free(exchange, base)

    if qty <= 0:
        POSITIONS.pop(key, None)
        return None

    price = get_price(exchange, sym)
    _, _, min_notional = get_lot_step(exchange, sym)

    if is_dust(qty, price, min_notional):
        POSITIONS.pop(key, None)
        return None

    old = POSITIONS.get(key, {})
    pos = build_position_from_trades(exchange, exchange_id, sym)
    if not pos:
        return None

    pos["peak_net"] = float(old.get("peak_net", 0.0) or 0.0)
    pos["highest_price"] = max(
        price,
        float(old.get("highest_price", 0.0) or 0.0),
        float(pos.get("highest_price", 0.0) or 0.0),
    )
    pos["opened_by_bot"] = bool(old.get("opened_by_bot", False))
    pos["opened_at"] = int(old.get("opened_at", 0) or 0)
    pos["state"] = str(old.get("state", "open") or "open")
    pos["partial_tp_done"] = bool(old.get("partial_tp_done", False))
    pos["break_even_armed"] = bool(old.get("break_even_armed", False))
    POSITIONS[key] = pos
    return pos


def sync_wallet_positions(exchange, exchange_id: str, symbols):
    if SYNC_EXISTING_POSITIONS != "1":
        return
    for sym in symbols:
        try:
            sync_one_position(exchange, exchange_id, sym)
        except Exception:
            continue


def extend_symbols_with_wallet_balances(exchange, symbols):
    try:
        if AUTO_INCLUDE_WALLET_SYMBOLS != "1":
            return symbols

        bal = exchange.fetch_balance()
        free_map = bal.get("free", {}) or {}

        result = list(symbols)
        seen = set(result)

        for asset, qty in free_map.items():
            try:
                qty = float(qty or 0.0)
            except Exception:
                qty = 0.0
            if qty <= 0:
                continue
            if asset.upper() in ("USDT", "USDC"):
                continue

            cand = f"{asset.upper()}/USDT"
            if cand in exchange.markets and cand not in seen:
                result.append(cand)
                seen.add(cand)

        return result
    except Exception:
        return symbols


# ================== Indicators ==================
def refresh_indicators(exchange, exchange_id: str, sym: str):
    key = pair_key(exchange_id, sym)
    now = int(time.time())

    st = STATE.setdefault(
        key,
        {
            "closes": deque(maxlen=600),
            "opens": deque(maxlen=600),
            "highs": deque(maxlen=600),
            "lows": deque(maxlen=600),
            "volumes": deque(maxlen=600),
            "last_klines_ts": 0,
            "ema_fast": 0.0,
            "ema_slow": 0.0,
            "prev_ema_fast": 0.0,
            "prev_ema_slow": 0.0,
            "rsi": 0.0,
            "atr_pct": 0.0,
            "last_close": 0.0,
            "last_open": 0.0,
            "last_volume": 0.0,
            "avg_volume": 0.0,
            "volume_ratio": 0.0,
            "warm": False,
        },
    )

    if (now - st["last_klines_ts"]) < KLINES_REFRESH_SEC and st["warm"]:
        return st

    kl = exchange.fetch_ohlcv(sym, timeframe=KLINES_INTERVAL, limit=KLINES_LIMIT)
    if len(kl) >= 2:
        kl = kl[:-1]

    opens = [float(k[1]) for k in kl]
    highs = [float(k[2]) for k in kl]
    lows = [float(k[3]) for k in kl]
    closes = [float(k[4]) for k in kl]
    volumes = [float(k[5]) for k in kl]

    st["closes"].clear()
    st["opens"].clear()
    st["highs"].clear()
    st["lows"].clear()
    st["volumes"].clear()

    for x in opens:
        st["opens"].append(x)
    for x in highs:
        st["highs"].append(x)
    for x in lows:
        st["lows"].append(x)
    for x in closes:
        st["closes"].append(x)
    for x in volumes:
        st["volumes"].append(x)

    st["last_close"] = st["closes"][-1] if st["closes"] else 0.0
    st["last_open"] = st["opens"][-1] if st["opens"] else 0.0
    st["last_volume"] = st["volumes"][-1] if st["volumes"] else 0.0
    st["rsi"] = calc_rsi(list(st["closes"]), RSI_PERIOD)
    st["atr_pct"] = calc_atr_pct(list(st["highs"]), list(st["lows"]), list(st["closes"]), ATR_PERIOD)

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

        prev_close_list = close_list[:-1] if len(close_list) >= EMA_SLOW + 1 else close_list
        pef_init = sum(prev_close_list[:EMA_FAST]) / EMA_FAST
        pes_init = sum(prev_close_list[:EMA_SLOW]) / EMA_SLOW

        pef = pef_init
        for p in prev_close_list[EMA_FAST:]:
            pef = ema(pef, p, EMA_FAST)

        pes = pes_init
        for p in prev_close_list[EMA_SLOW:]:
            pes = ema(pes, p, EMA_SLOW)

        st["prev_ema_fast"] = pef
        st["prev_ema_slow"] = pes
        st["ema_fast"] = ef
        st["ema_slow"] = es
        st["warm"] = True

    st["last_klines_ts"] = now
    return st


def refresh_trend(exchange, exchange_id: str, sym: str):
    key = pair_key(exchange_id, sym)
    now = int(time.time())

    st = TREND_STATE.setdefault(
        key,
        {
            "last_ts": 0,
            "trend_ema": 0.0,
            "last_close": 0.0,
            "trend_ok": False,
            "warm": False,
        },
    )

    if (now - st["last_ts"]) < TREND_REFRESH_SEC and st["warm"]:
        return st

    try:
        kl = exchange.fetch_ohlcv(sym, timeframe=TREND_INTERVAL, limit=TREND_LIMIT)
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
    except Exception:
        pass

    st["last_ts"] = now
    return st


def refresh_market_regime(exchange):
    regime_symbol = normalize_symbol(BTC_REGIME_SYMBOL)
    key = f"{exchange.id}:{regime_symbol}"
    now = int(time.time())

    st = MARKET_REGIME_STATE.setdefault(
        key,
        {"last_ts": 0, "warm": False, "ema": 0.0, "close": 0.0, "bullish": True},
    )

    if (now - st["last_ts"]) < BTC_REGIME_REFRESH_SEC and st["warm"]:
        return st

    try:
        if regime_symbol not in exchange.markets:
            exchange.load_markets(True)
        kl = exchange.fetch_ohlcv(regime_symbol, timeframe=BTC_REGIME_INTERVAL, limit=BTC_REGIME_LIMIT)
        if len(kl) >= 2:
            kl = kl[:-1]
        closes = [float(k[4]) for k in kl]
        if len(closes) >= BTC_REGIME_EMA:
            ema_val = sum(closes[:BTC_REGIME_EMA]) / BTC_REGIME_EMA
            for p in closes[BTC_REGIME_EMA:]:
                ema_val = ema(ema_val, p, BTC_REGIME_EMA)
            st["ema"] = ema_val
            st["close"] = closes[-1]
            st["bullish"] = closes[-1] > ema_val
            st["warm"] = True
    except Exception:
        pass

    st["last_ts"] = now
    return st


# ================== Strategy ==================
def should_buy_scalp(st, trend_st, spread_pct: float, quote_volume_24h: float, regime_ok: bool = True) -> bool:
    if not st.get("warm"):
        return False

    if REQUIRE_TREND_FILTER == "1":
        if not trend_st.get("warm") or not trend_st.get("trend_ok"):
            return False

    if ENABLE_MARKET_REGIME_FILTER == "1" and not regime_ok:
        return False

    if spread_pct > MAX_SPREAD_PCT or quote_volume_24h < MIN_24H_QUOTE_VOLUME:
        return False

    atr_pct = float(st.get("atr_pct", 0.0))
    if atr_pct < ATR_MIN_PCT or atr_pct > ATR_MAX_PCT:
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
    bounce_buy = rsi <= 34 and close >= open_
    rsi_ok = RSI_BUY_MIN <= rsi <= RSI_BUY_MAX
    bull_candle_ok = (close >= open_) if REQUIRE_BULL_CANDLE == "1" else True
    volume_ok = vol_ratio >= MIN_VOLUME_RATIO

    return (
        (cross_up and rsi_ok and bull_candle_ok and volume_ok)
        or (aligned_up and rsi_ok and bull_candle_ok and vol_ratio >= 0.02)
        or bounce_buy
    )


def should_exit_early(st) -> bool:
    if not st.get("warm"):
        return False

    pef = st["prev_ema_fast"]
    pes = st["prev_ema_slow"]
    ef = st["ema_fast"]
    es = st["ema_slow"]
    rsi = st["rsi"]
    close = st["last_close"]

    if EXIT_ON_EMA_CROSSDOWN == "1" and (pef >= pes) and (ef < es):
        return True
    if rsi >= EXIT_RSI_OVERBOUGHT:
        return True
    if close < ef and rsi < 45:
        return True
    return False


def update_trailing_state(key: str, price: float, net: float):
    pos = POSITIONS.get(key)
    if not pos:
        return
    if price > float(pos.get("highest_price", 0.0) or 0.0):
        pos["highest_price"] = price
    if net > float(pos.get("peak_net", -999.0)):
        pos["peak_net"] = net
    if ENABLE_BREAK_EVEN == "1" and net >= BREAK_EVEN_ARM_NET_PCT:
        pos["break_even_armed"] = True


def trailing_exit_triggered(key: str, net: float) -> bool:
    if ENABLE_TRAILING != "1":
        return False

    pos = POSITIONS.get(key)
    if not pos:
        return False

    peak_net = float(pos.get("peak_net", -999.0))

    if SMART_TRAILING == "1":
        giveback = None
        if peak_net >= TRAIL_LVL3_ACTIVATE:
            giveback = TRAIL_LVL3_GIVEBACK
        elif peak_net >= TRAIL_LVL2_ACTIVATE:
            giveback = TRAIL_LVL2_GIVEBACK
        elif peak_net >= TRAIL_LVL1_ACTIVATE:
            giveback = TRAIL_LVL1_GIVEBACK

        if giveback is None:
            return False

        return (peak_net - net) >= giveback

    return False


def calc_buy_score(st, trend_st, spread_pct: float, quote_volume_24h: float, regime_ok: bool = True) -> float:
    if not st.get("warm"):
        return 0.0

    if REQUIRE_TREND_FILTER == "1":
        if not trend_st.get("warm") or not trend_st.get("trend_ok"):
            return 0.0

    if ENABLE_MARKET_REGIME_FILTER == "1" and not regime_ok:
        return 0.0

    if spread_pct > MAX_SPREAD_PCT or quote_volume_24h < MIN_24H_QUOTE_VOLUME:
        return 0.0

    atr_pct = float(st.get("atr_pct", 0.0))
    if atr_pct < ATR_MIN_PCT or atr_pct > ATR_MAX_PCT:
        return 0.0

    rsi = float(st.get("rsi", 0.0))
    vol_ratio = float(st.get("volume_ratio", 0.0))
    ef = float(st.get("ema_fast", 0.0))
    es = float(st.get("ema_slow", 0.0))
    pef = float(st.get("prev_ema_fast", 0.0))
    pes = float(st.get("prev_ema_slow", 0.0))
    close = float(st.get("last_close", 0.0))
    open_ = float(st.get("last_open", 0.0))

    cross_up = (pef <= pes) and (ef > es)
    aligned_up = ef > es and close > ef
    bounce_buy = rsi <= 34 and close >= open_
    bull_candle = close >= open_

    score = 0.0
    score += 30 if cross_up else (18 if aligned_up else 0)
    score += 15 if bounce_buy else 0
    score += 22 if RSI_BUY_MIN <= rsi <= RSI_BUY_MAX else (12 if 20 <= rsi <= 88 else 0)
    score += clamp((vol_ratio - 0.05) * 20, 0, 16)
    score += 8 if bull_candle or REQUIRE_BULL_CANDLE != "1" else 0
    score += clamp((MAX_SPREAD_PCT - spread_pct) * 60, 0, 10)
    if quote_volume_24h >= MIN_24H_QUOTE_VOLUME:
        score += max(0.0, min(10.0, math.log10(max(quote_volume_24h, 1)) - 5.0))
    if trend_st.get("trend_ok"):
        score += 5
    if regime_ok:
        score += 4
    if 0.03 <= atr_pct <= 6.0:
        score += 10

    return clamp(score, 0.0, 100.0)


def adaptive_buy_usdt(score: float, atr_pct: float) -> float:
    if ENABLE_DYNAMIC_BUY_SIZE != "1":
        return BUY_USDT

    score_factor = clamp((score - BUY_SCORE_MIN) / max(1.0, (100.0 - BUY_SCORE_MIN)), 0.0, 1.0)

    if atr_pct <= 0:
        vol_factor = 1.0
    elif atr_pct < 0.15:
        vol_factor = 0.90
    elif atr_pct <= 2.50:
        vol_factor = 1.20
    elif atr_pct <= 5.00:
        vol_factor = 1.00
    else:
        vol_factor = 0.80

    raw = BUY_USDT_MIN + ((BUY_USDT_MAX - BUY_USDT_MIN) * score_factor * vol_factor)
    return clamp(raw, BUY_USDT_MIN, BUY_USDT_MAX)


# ================== Trading ==================
def safe_buy(exchange, exchange_id: str, sym: str, market_price_hint: float, buy_score: float = 0.0, atr_pct: float = 0.0) -> bool:
    key = pair_key(exchange_id, sym)
    lbl = f"{exchange_id} {sym}"

    if trading_paused():
        return False

    buy_amount_usdt = adaptive_buy_usdt(buy_score, atr_pct)

    if MODE != "live":
        qty_paper = buy_amount_usdt / market_price_hint
        POSITIONS[key] = {
            "entry": market_price_hint,
            "qty": qty_paper,
            "peak_net": 0.0,
            "highest_price": market_price_hint,
            "entry_known": True,
            "source": "paper",
            "opened_by_bot": True,
            "opened_at": int(time.time()),
            "state": "open",
            "partial_tp_done": False,
            "break_even_armed": False,
            "buy_score": buy_score,
            "atr_pct": atr_pct,
        }
        add_trade(lbl, "BUY", qty_paper, market_price_hint, f"PAPER aggressive buy score={buy_score:.1f} atr={atr_pct:.2f}%")
        update_report_stats_on_buy(lbl)
        tg_send(
            f"🟢 PAPER BOUGHT {lbl}\n"
            f"qty={qty_paper:.6f}\nentry={market_price_hint:.6f}\n"
            f"score={buy_score:.1f}\nATR={atr_pct:.2f}%\nUSDT={buy_amount_usdt:.2f}"
        )
        return True

    _, _, min_notional = get_lot_step(exchange, sym)
    if min_notional > 0 and buy_amount_usdt < (min_notional + 0.5):
        return False

    usdt_free = get_balance_free(exchange, "USDT")
    if usdt_free < max(MIN_USDT_FREE_TO_BUY, buy_amount_usdt):
        return False

    order = market_buy(exchange, sym, buy_amount_usdt, market_price_hint)
    time.sleep(1)

    exec_price = avg_fill_price_from_order(exchange, order, sym) or market_price_hint
    exec_qty = executed_qty_from_order(exchange, order, sym)

    if exec_qty <= 0:
        time.sleep(2)
        pos = sync_one_position(exchange, exchange_id, sym)
        if pos and float(pos.get("qty", 0) or 0) > 0:
            pos["opened_by_bot"] = True
            pos["opened_at"] = int(time.time())
            pos["state"] = "open"
            pos["partial_tp_done"] = False
            pos["break_even_armed"] = False
            pos["buy_score"] = buy_score
            pos["atr_pct"] = atr_pct
            POSITIONS[key] = pos
            exec_qty = float(pos.get("qty", 0) or 0)
            exec_price = float(pos.get("entry", market_price_hint) or market_price_hint)
            add_trade(lbl, "BUY", exec_qty, exec_price, f"LIVE aggressive buy (synced) score={buy_score:.1f} atr={atr_pct:.2f}%")
            update_report_stats_on_buy(lbl)
            tg_send(
                f"🟢 BOUGHT {lbl}\nqty={exec_qty:.6f}\nentry≈{exec_price:.6f}\n"
                f"score={buy_score:.1f}\nATR={atr_pct:.2f}%\nUSDT={buy_amount_usdt:.2f}"
            )
            return True
        return False

    add_trade(lbl, "BUY", exec_qty, exec_price, f"LIVE aggressive buy score={buy_score:.1f} atr={atr_pct:.2f}%")
    POSITIONS[key] = {
        "entry": exec_price,
        "qty": exec_qty,
        "peak_net": 0.0,
        "highest_price": exec_price,
        "entry_known": True,
        "source": "live",
        "opened_by_bot": True,
        "opened_at": int(time.time()),
        "state": "open",
        "partial_tp_done": False,
        "break_even_armed": False,
        "buy_score": buy_score,
        "atr_pct": atr_pct,
    }
    update_report_stats_on_buy(lbl)
    tg_send(
        f"🟢 BOUGHT {lbl}\nqty={exec_qty:.6f}\nentry={exec_price:.6f}\n"
        f"score={buy_score:.1f}\nATR={atr_pct:.2f}%\nUSDT={buy_amount_usdt:.2f}"
    )
    return True


def safe_sell(exchange, exchange_id: str, sym: str, price: float, reason: str, force_qty: float = None) -> bool:
    key = pair_key(exchange_id, sym)
    lbl = f"{exchange_id} {sym}"

    base, _ = split_symbol(sym)
    qty_wallet = get_balance_free(exchange, base)
    if qty_wallet <= 0:
        return False

    pos_before = dict(POSITIONS.get(key, {}) or {})
    entry_before = float(pos_before.get("entry", 0.0) or 0.0)

    _, min_qty, min_notional = get_lot_step(exchange, sym)
    sell_qty = qty_wallet if force_qty is None else min(qty_wallet, float(force_qty))
    sell_qty = round_step(exchange, sym, sell_qty)
    notional = sell_qty * price

    if sell_qty <= 0:
        return False
    if min_qty > 0 and sell_qty < min_qty:
        return False
    if min_notional > 0 and notional < min_notional:
        return False

    is_partial = force_qty is not None and sell_qty < qty_wallet

    if MODE != "live":
        add_trade(lbl, "SELL", sell_qty, price, f"PAPER {reason}")
        pnl_usdt = estimate_trade_pnl_usdt(entry_before, price, sell_qty) if entry_before > 0 else 0.0
        update_report_stats_on_sell(lbl, pnl_usdt)
        register_closed_trade_guard(pnl_usdt)

        if SEND_REPORT_ON_EACH_SELL == "1" and entry_before > 0:
            send_sell_analysis_message(lbl, sell_qty, entry_before, price, f"PAPER {reason}")

        if is_partial:
            remain = max(0.0, qty_wallet - sell_qty)
            if remain > 0:
                POSITIONS[key]["qty"] = remain
                POSITIONS[key]["partial_tp_done"] = True
                POSITIONS[key]["state"] = "partial"
                return True

        POSITIONS.pop(key, None)
        return True

    order = market_sell(exchange, sym, sell_qty)
    exec_price = avg_fill_price_from_order(exchange, order, sym) or price
    exec_qty = executed_qty_from_order(exchange, order, sym) or sell_qty

    add_trade(lbl, "SELL", exec_qty, exec_price, reason)
    pnl_usdt = estimate_trade_pnl_usdt(entry_before, exec_price, exec_qty) if entry_before > 0 else 0.0
    update_report_stats_on_sell(lbl, pnl_usdt)
    register_closed_trade_guard(pnl_usdt)

    if SEND_REPORT_ON_EACH_SELL == "1" and entry_before > 0:
        send_sell_analysis_message(lbl, exec_qty, entry_before, exec_price, reason)
    else:
        tg_send(f"🔴 SOLD {lbl} qty={exec_qty:.6f} exit={exec_price:.6f}")

    time.sleep(1)
    sync_one_position(exchange, exchange_id, sym)

    remaining = get_balance_free(exchange, base)
    if remaining <= 0:
        POSITIONS.pop(key, None)
    else:
        if key in POSITIONS:
            POSITIONS[key]["qty"] = remaining
            if is_partial:
                POSITIONS[key]["partial_tp_done"] = True
                POSITIONS[key]["state"] = "partial"

    return True


# ================== Candidate Scan ==================
def collect_exchange_candidates(exchange, exchange_id: str, symbols):
    candidates = []

    if trading_paused():
        return candidates

    usdt_free = get_balance_free(exchange, "USDT")
    bot_open = count_bot_open_positions(exchange_id)

    if bot_open >= MAX_OPEN_POSITIONS or usdt_free < MIN_USDT_FREE_TO_BUY:
        return candidates

    regime_st = refresh_market_regime(exchange)
    regime_ok = bool(regime_st.get("bullish", True))

    for sym in symbols:
        key = pair_key(exchange_id, sym)

        if in_cooldown(key):
            continue

        base, _ = split_symbol(sym)
        qty_wallet = get_balance_free(exchange, base)
        if qty_wallet > 0:
            continue

        try:
            st_ind = refresh_indicators(exchange, exchange_id, sym)
            trend_st = refresh_trend(exchange, exchange_id, sym)

            price = get_price(exchange, sym)
            spread_pct = get_spread_pct(exchange, sym)
            vol_24h = get_24h_quote_volume(exchange, sym)

            score = calc_buy_score(st_ind, trend_st, spread_pct, vol_24h, regime_ok=regime_ok)
            signal = should_buy_scalp(st_ind, trend_st, spread_pct, vol_24h, regime_ok=regime_ok)

            if PRINT_CANDIDATES == "1":
                print(
                    f"CANDIDATE {exchange_id} {sym} | "
                    f"signal={signal} score={score:.2f} need>={BUY_SCORE_MIN:.2f} | "
                    f"rsi={st_ind.get('rsi',0):.2f} | volRatio={st_ind.get('volume_ratio',0):.2f} | "
                    f"spread={spread_pct:.3f} | vol24h={vol_24h:.0f} | "
                    f"atr={st_ind.get('atr_pct',0):.2f}% | trend_ok={trend_st.get('trend_ok', False)} | regime_ok={regime_ok}"
                )

            if signal and score >= BUY_SCORE_MIN:
                candidates.append(
                    {
                        "exchange": exchange_id,
                        "symbol": sym,
                        "key": key,
                        "score": score,
                        "price": price,
                        "atr_pct": float(st_ind.get("atr_pct", 0.0) or 0.0),
                    }
                )
        except Exception as e:
            print(f"SKIP {exchange_id} {sym}: {e}")
            continue

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:MAX_CANDIDATES_PER_EXCHANGE]


# ================== Exchange Cycle ==================
def process_exchange(exchange, exchange_id: str, symbols):
    usdt_free = get_balance_free(exchange, "USDT")
    bot_open = count_bot_open_positions(exchange_id)
    regime_st = refresh_market_regime(exchange)
    regime_ok = bool(regime_st.get("bullish", True))

    for sym in symbols:
        key = pair_key(exchange_id, sym)

        try:
            st_ind = refresh_indicators(exchange, exchange_id, sym)
            trend_st = refresh_trend(exchange, exchange_id, sym)

            price = get_price(exchange, sym)
            spread_pct = get_spread_pct(exchange, sym)
            vol_24h = get_24h_quote_volume(exchange, sym)

            base, _ = split_symbol(sym)
            qty_wallet = get_balance_free(exchange, base)
            _, _, min_notional = get_lot_step(exchange, sym)

            qty_effective = 0.0 if is_dust(qty_wallet, price, min_notional) else qty_wallet

            if qty_effective > 0:
                if key not in POSITIONS:
                    sync_one_position(exchange, exchange_id, sym)
                else:
                    POSITIONS[key]["qty"] = qty_effective

            pos_info = POSITIONS.get(key, {}) or {}
            entry = float(pos_info.get("entry", 0.0) or 0.0)
            gross = gross_pnl_pct(entry, price) if qty_effective > 0 and entry > 0 else 0.0
            net = gross - BREAKEVEN_PCT if qty_effective > 0 and entry > 0 else 0.0

            if qty_effective > 0:
                update_trailing_state(key, price, net)

            set_status(
                mode=MODE,
                last_heartbeat=int(time.time()),
                symbol=f"{exchange_id} {sym}",
                price=price,
                pnl=round(net, 4),
                position_qty=qty_effective,
                position_entry=entry,
                last_action=(
                    f"tick exch={exchange_id} usdt_free={usdt_free:.2f} bot_open={bot_open} "
                    f"rsi={st_ind.get('rsi', 0):.1f} gross={gross:.2f}% net={net:.2f}% "
                    f"trend_ok={trend_st.get('trend_ok', False)} regime_ok={regime_ok} "
                    f"spread={spread_pct:.3f}% vol24h={vol_24h:.0f} "
                    f"volRatio={st_ind.get('volume_ratio', 0):.2f} atr={st_ind.get('atr_pct', 0):.2f}% "
                    f"paused={trading_paused()}"
                ),
                last_error="",
            )

            if qty_effective > 0 and not in_cooldown(key):
                age_h = position_age_hours(key)
                opened_by_bot = bool(pos_info.get("opened_by_bot", False))
                partial_tp_done = bool(pos_info.get("partial_tp_done", False))
                break_even_armed = bool(pos_info.get("break_even_armed", False))

                if opened_by_bot:
                    if age_h >= HARD_MAX_HOLD_HOURS:
                        if safe_sell(exchange, exchange_id, sym, price, f"TIME EXIT hard {age_h:.1f}h net={net:.2f}%"):
                            mark_trade(key, REENTRY_AFTER_SELL_COOLDOWN_SEC)
                            time.sleep(1)
                        continue

                    if age_h >= MAX_HOLD_HOURS and net < TIME_EXIT_MIN_NET_PCT:
                        if safe_sell(exchange, exchange_id, sym, price, f"TIME EXIT soft {age_h:.1f}h net={net:.2f}%"):
                            mark_trade(key, REENTRY_AFTER_SELL_COOLDOWN_SEC)
                            time.sleep(1)
                        continue

                if ENABLE_PARTIAL_TP == "1" and not partial_tp_done and net >= PARTIAL_TP_NET_PCT:
                    part_qty = qty_effective * PARTIAL_TP_SELL_RATIO
                    if safe_sell(exchange, exchange_id, sym, price, f"PARTIAL TP net={net:.2f}%", force_qty=part_qty):
                        mark_trade(key, 3)
                        time.sleep(1)
                    continue

                if gross >= REQUIRED_GROSS_TP_PCT and net >= MIN_NET_PROFIT_PCT:
                    if safe_sell(exchange, exchange_id, sym, price, f"SCALP TP gross={gross:.2f}% net={net:.2f}%"):
                        mark_trade(key, REENTRY_AFTER_SELL_COOLDOWN_SEC)
                        time.sleep(1)
                    continue

                if ENABLE_TRAILING == "1" and trailing_exit_triggered(key, net):
                    peak_net = float(POSITIONS.get(key, {}).get("peak_net", 0.0) or 0.0)
                    giveback_used = TRAIL_LVL1_GIVEBACK
                    if peak_net >= TRAIL_LVL3_ACTIVATE:
                        giveback_used = TRAIL_LVL3_GIVEBACK
                    elif peak_net >= TRAIL_LVL2_ACTIVATE:
                        giveback_used = TRAIL_LVL2_GIVEBACK

                    if safe_sell(exchange, exchange_id, sym, price, f"SMART TRAILING peak_net={peak_net:.2f}% net={net:.2f}% giveback={giveback_used:.2f}%"):
                        mark_trade(key, REENTRY_AFTER_SELL_COOLDOWN_SEC)
                        time.sleep(1)
                    continue

                if ENABLE_BREAK_EVEN == "1" and break_even_armed and net <= 0.00:
                    if safe_sell(exchange, exchange_id, sym, price, f"BREAK EVEN EXIT net={net:.2f}%"):
                        mark_trade(key, REENTRY_AFTER_SELL_COOLDOWN_SEC)
                        time.sleep(1)
                    continue

                if gross <= -SL_PCT:
                    if safe_sell(exchange, exchange_id, sym, price, f"SCALP SL gross={gross:.2f}% net={net:.2f}%"):
                        mark_trade(key, REENTRY_AFTER_SELL_COOLDOWN_SEC)
                        time.sleep(1)
                    continue

                if should_exit_early(st_ind) and net >= EARLY_EXIT_MIN_NET_PCT:
                    if safe_sell(exchange, exchange_id, sym, price, f"SCALP early-exit gross={gross:.2f}% net={net:.2f}%"):
                        mark_trade(key, REENTRY_AFTER_SELL_COOLDOWN_SEC)
                        time.sleep(1)
                    continue

                if entry > 0 and gross <= OLD_POSITION_FORCE_SELL_PCT:
                    if safe_sell(exchange, exchange_id, sym, price, f"OLD POSITION FORCE SELL gross={gross:.2f}%"):
                        mark_trade(key, REENTRY_AFTER_SELL_COOLDOWN_SEC)
                        time.sleep(1)
                    continue

                if entry > 0 and gross >= OLD_POSITION_TAKE_PROFIT_PCT:
                    if safe_sell(exchange, exchange_id, sym, price, f"OLD POSITION TP gross={gross:.2f}%"):
                        mark_trade(key, REENTRY_AFTER_SELL_COOLDOWN_SEC)
                        time.sleep(1)
                    continue

        except Exception as e:
            print(f"PROCESS ERROR {exchange_id} {sym}: {e}")
            continue


# ================== Main ==================
def main():
    init_db()
    reset_daily_guard_if_needed()

    print(f"🤖 BOT WORKER STARTED MODE={MODE}")
    print(f"🤖 EXCHANGES={','.join(ACTIVE_EXCHANGES)}")
    print(f"🤖 SYMBOLS={','.join(SYMBOLS)}")

    tg_send(
        f"🤖 <b>تم تشغيل البوت</b>\n"
        f"الوضع الحالي: <b>{MODE}</b>\n"
        f"المنصات: <b>{', '.join(ACTIVE_EXCHANGES)}</b>\n"
        f"عدد الأزواج الأساسية: <b>{len(SYMBOLS)}</b>\n"
        f"النمط: <b>هجومي جدًا</b>"
    )

    exchanges = make_all_exchanges()
    if not exchanges:
        raise RuntimeError("No exchange connected successfully.")

    exchange_symbols = {}
    for ex_id, ex in exchanges.items():
        valid_symbols = [s for s in SYMBOLS if s in ex.markets]
        exchange_symbols[ex_id] = extend_symbols_with_wallet_balances(ex, valid_symbols)
        print(f"📌 {ex_id} managed symbols: {', '.join(exchange_symbols[ex_id])}")

    tg_send("✅ TEST: Multi-exchange worker is running now.")

    for ex_id, ex in exchanges.items():
        sync_wallet_positions(ex, ex_id, exchange_symbols[ex_id])

    last_hb = 0
    last_pause_warn_ts = 0

    while True:
        try:
            reset_daily_guard_if_needed()
            now = int(time.time())

            if now - last_hb >= HEARTBEAT_SEC:
                last_hb = now
                hb_parts = []
                for ex_id, ex in exchanges.items():
                    try:
                        usdt_free_dbg = get_balance_free(ex, "USDT")
                        bot_open = count_bot_open_positions(ex_id)
                        hb_parts.append(f"{ex_id}: USDT={usdt_free_dbg:.2f} bot_open={bot_open}")
                    except Exception:
                        hb_parts.append(f"{ex_id}: ERR")
                print(
                    f"💓 HEARTBEAT {now} | " + " | ".join(hb_parts) +
                    f" | daily_pnl={TRADING_GUARD['daily_pnl']:.2f} | paused={trading_paused()}"
                )

            if trading_paused() and (now - last_pause_warn_ts >= 300):
                last_pause_warn_ts = now
                msg = f"⛔ BUYING PAUSED: {trading_pause_reason()}"
                print(msg)
                tg_send(msg)

            send_periodic_report_if_due()

            all_candidates = []

            for ex_id, ex in exchanges.items():
                try:
                    process_exchange(ex, ex_id, exchange_symbols[ex_id])
                except Exception as ex_err:
                    err = f"{ex_id} {type(ex_err).__name__}: {ex_err}"
                    print("❌", err)
                    print(traceback.format_exc())
                    try:
                        set_status(last_error=err, last_action="error")
                    except Exception:
                        pass
                    time.sleep(3)

            if not trading_paused():
                for ex_id, ex in exchanges.items():
                    try:
                        all_candidates.extend(collect_exchange_candidates(ex, ex_id, exchange_symbols[ex_id]))
                    except Exception:
                        continue

                buys_done = 0

                if STRICT_BEST_GLOBAL_ONLY == "1":
                    chosen = sorted(all_candidates, key=lambda x: x["score"], reverse=True)[:1]
                else:
                    chosen = sorted(all_candidates, key=lambda x: x["score"], reverse=True)

                for best in chosen:
                    if buys_done >= MAX_NEW_BUYS_PER_CYCLE:
                        break

                    best_ex_id = best["exchange"]
                    best_ex = exchanges.get(best_ex_id)
                    if not best_ex:
                        continue

                    best_key = best["key"]
                    bot_open = count_bot_open_positions(best_ex_id)
                    usdt_free = get_balance_free(best_ex, "USDT")

                    if bot_open < MAX_OPEN_POSITIONS and usdt_free >= MIN_USDT_FREE_TO_BUY and not in_cooldown(best_key):
                        if safe_buy(
                            best_ex,
                            best_ex_id,
                            best["symbol"],
                            best["price"],
                            buy_score=float(best.get("score", 0.0) or 0.0),
                            atr_pct=float(best.get("atr_pct", 0.0) or 0.0),
                        ):
                            mark_trade(best_key)
                            buys_done += 1
            else:
                try:
                    set_status(last_action=f"buy-paused: {trading_pause_reason()}", last_error="")
                except Exception:
                    pass

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print("❌", err)
            print(traceback.format_exc())
            try:
                set_status(last_error=err, last_action="error")
            except Exception:
                pass
            time.sleep(5)


if __name__ == "__main__":
    main()
