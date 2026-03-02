# db.py
import os
import sqlite3
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "bot.db")

def _conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    con = _conn()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS bot_status (
        id INTEGER PRIMARY KEY CHECK (id=1),
        mode TEXT,
        now_iso TEXT,
        usdt_free REAL,
        last_price REAL,
        last_error TEXT,
        notes TEXT
    )
    """)
    cur.execute("INSERT OR IGNORE INTO bot_status (id, mode, now_iso, usdt_free, last_price, last_error, notes) VALUES (1,'paper','','',0,'','')")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS position (
        id INTEGER PRIMARY KEY CHECK (id=1),
        symbol TEXT,
        side TEXT,
        qty REAL,
        entry_price REAL,
        entry_time TEXT,
        is_open INTEGER
    )
    """)
    cur.execute("INSERT OR IGNORE INTO position (id, symbol, side, qty, entry_price, entry_time, is_open) VALUES (1,'','',0,0,'',0)")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        action TEXT,
        qty REAL,
        price REAL,
        time TEXT,
        note TEXT
    )
    """)

    con.commit()
    con.close()

def set_status(mode, usdt_free, last_price, last_error="", notes=""):
    con = _conn()
    cur = con.cursor()
    cur.execute("""
        UPDATE bot_status
        SET mode=?, now_iso=?, usdt_free=?, last_price=?, last_error=?, notes=?
        WHERE id=1
    """, (mode, datetime.utcnow().isoformat(), float(usdt_free), float(last_price), str(last_error)[:500], str(notes)[:500]))
    con.commit()
    con.close()

def get_position():
    con = _conn()
    cur = con.cursor()
    row = cur.execute("SELECT symbol, side, qty, entry_price, entry_time, is_open FROM position WHERE id=1").fetchone()
    con.close()
    if not row:
        return {"is_open": 0}
    return {
        "symbol": row[0],
        "side": row[1],
        "qty": float(row[2]),
        "entry_price": float(row[3]),
        "entry_time": row[4],
        "is_open": int(row[5]),
    }

def open_position(symbol, side, qty, entry_price):
    con = _conn()
    cur = con.cursor()
    cur.execute("""
        UPDATE position
        SET symbol=?, side=?, qty=?, entry_price=?, entry_time=?, is_open=1
        WHERE id=1
    """, (symbol, side, float(qty), float(entry_price), datetime.utcnow().isoformat()))
    con.commit()
    con.close()

def close_position():
    con = _conn()
    cur = con.cursor()
    cur.execute("""
        UPDATE position
        SET is_open=0
        WHERE id=1
    """)
    con.commit()
    con.close()

def add_trade(symbol, action, qty, price, note=""):
    con = _conn()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO trades(symbol, action, qty, price, time, note)
        VALUES (?,?,?,?,?,?)
    """, (symbol, action, float(qty), float(price), datetime.utcnow().isoformat(), str(note)[:500]))
    con.commit()
    con.close()
