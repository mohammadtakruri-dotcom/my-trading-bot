import os
import sqlite3
from datetime import datetime, timezone

# للتجربة المجانية: /tmp (قد لا يكون دائم بعد restart)
DB_PATH = os.getenv("SQLITE_PATH", "/tmp/trading.db")

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = conn()
    cur = c.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN',          -- OPEN/CLOSED
        buy_price REAL,
        buy_qty REAL,
        buy_usdt REAL,
        buy_order_id TEXT,
        buy_time TEXT,
        sell_price REAL,
        sell_qty REAL,
        sell_order_id TEXT,
        sell_time TEXT,
        pnl_usdt REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS bot_status (
        id INTEGER PRIMARY KEY,
        mode TEXT,
        last_run TEXT,
        last_error TEXT,
        usdt_free REAL,
        notes TEXT
    )
    """)

    cur.execute("""
    INSERT OR IGNORE INTO bot_status(id, mode, last_run, last_error, usdt_free, notes)
    VALUES(1, ?, ?, ?, ?, ?)
    """, (os.getenv("MODE", "paper"), now_iso(), "", 0.0, "initialized"))

    c.commit()
    c.close()

def set_status(mode=None, usdt_free=None, last_error=None, notes=None):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT * FROM bot_status WHERE id=1")
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO bot_status(id, mode, last_run, last_error, usdt_free, notes) VALUES(1,?,?,?,?,?)",
                    (mode or os.getenv("MODE","paper"), now_iso(), last_error or "", usdt_free or 0.0, notes or ""))
    else:
        cur.execute("""
            UPDATE bot_status
               SET mode = COALESCE(?, mode),
                   last_run = ?,
                   usdt_free = COALESCE(?, usdt_free),
                   last_error = COALESCE(?, last_error),
                   notes = COALESCE(?, notes)
             WHERE id=1
        """, (mode, now_iso(), usdt_free, last_error, notes))
    c.commit()
    c.close()

def get_status():
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT * FROM bot_status WHERE id=1")
    row = cur.fetchone()
    c.close()
    return dict(row) if row else {}

def insert_open_trade(symbol, buy_price, buy_qty, buy_usdt, buy_order_id=None):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO trades(symbol,status,buy_price,buy_qty,buy_usdt,buy_order_id,buy_time)
        VALUES(?,?,?,?,?,?,?)
    """, (symbol, "OPEN", buy_price, buy_qty, buy_usdt, buy_order_id, now_iso()))
    c.commit()
    c.close()

def close_trade(symbol, sell_price, sell_qty, sell_order_id=None):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        SELECT id, buy_usdt, buy_qty, buy_price
          FROM trades
         WHERE symbol=? AND status='OPEN'
         ORDER BY id DESC
         LIMIT 1
    """, (symbol,))
    row = cur.fetchone()
    if row:
        trade_id = row["id"]
        buy_usdt = float(row["buy_usdt"] or 0.0)
        # تقدير PnL بالدولار حسب السعر
        pnl = (sell_price * sell_qty) - buy_usdt
        cur.execute("""
            UPDATE trades
               SET status='CLOSED',
                   sell_price=?,
                   sell_qty=?,
                   sell_order_id=?,
                   sell_time=?,
                   pnl_usdt=?
             WHERE id=?
        """, (sell_price, sell_qty, sell_order_id, now_iso(), pnl, trade_id))
        c.commit()
    c.close()

def list_trades(status=None, limit=200):
    c = conn()
    cur = c.cursor()
    if status:
        cur.execute("SELECT * FROM trades WHERE status=? ORDER BY id DESC LIMIT ?", (status, int(limit)))
    else:
        cur.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (int(limit),))
    rows = [dict(r) for r in cur.fetchall()]
    c.close()
    return rows

def open_symbols():
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT symbol FROM trades WHERE status='OPEN'")
    rows = {r[0] for r in cur.fetchall()}
    c.close()
    return rows
