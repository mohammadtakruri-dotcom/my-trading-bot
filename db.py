import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "bot.db")

def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = conn()
    cur = c.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bot_status (
        id INTEGER PRIMARY KEY,
        mode TEXT,
        symbol TEXT,
        last_price REAL,
        usdt_free REAL,
        asset_free REAL,
        in_position INTEGER,
        entry_price REAL,
        tp_price REAL,
        sl_price REAL,
        last_action TEXT,
        last_error TEXT,
        notes TEXT,
        updated_at TEXT
    )
    """)
    cur.execute("SELECT COUNT(*) AS n FROM bot_status WHERE id=1")
    n = cur.fetchone()["n"]
    if n == 0:
        cur.execute("""
            INSERT INTO bot_status
            (id, mode, symbol, last_price, usdt_free, asset_free, in_position, entry_price, tp_price, sl_price,
             last_action, last_error, notes, updated_at)
            VALUES
            (1, 'paper', 'BTCUSDT', 0, 0, 0, 0, NULL, NULL, NULL, 'init', NULL, '', ?)
        """, (datetime.utcnow().isoformat(),))
    c.commit()
    c.close()

def set_status(**kwargs):
    keys = list(kwargs.keys())
    if not keys:
        return
    c = conn()
    cur = c.cursor()
    fields = ", ".join([f"{k}=?" for k in keys] + ["updated_at=?"])
    vals = [kwargs[k] for k in keys] + [datetime.utcnow().isoformat()]
    cur.execute(f"UPDATE bot_status SET {fields} WHERE id=1", vals)
    c.commit()
    c.close()

def get_status():
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT * FROM bot_status WHERE id=1")
    row = cur.fetchone()
    c.close()
    return dict(row) if row else None
