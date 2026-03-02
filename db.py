# db.py (SQLite)
import os, sqlite3
from datetime import datetime, timezone

DB_PATH = os.getenv("SQLITE_PATH", "/tmp/trading.db")  # /tmp للتجربة

def now_iso():
    return datetime.now(timezone.utc).isoformat()

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
        status TEXT NOT NULL DEFAULT 'OPEN',
        buy_price REAL,
        buy_qty REAL,
        buy_usdt REAL,
        buy_order_id TEXT,
        buy_time TEXT,
        sell_price REAL,
        sell_qty REAL,
        sell_order_id TEXT,
        sell_time TEXT
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
    """, (os.getenv("MODE","paper"), now_iso(), "", 0.0, "initialized"))

    c.commit()
    c.close()
