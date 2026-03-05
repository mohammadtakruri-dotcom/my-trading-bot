import os, sqlite3, threading, time

DB_PATH = os.getenv("SQLITE_PATH", "bot.db")
_lock = threading.Lock()

def _conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with _lock:
        c = _conn()
        cur = c.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_status (
            id INTEGER PRIMARY KEY CHECK (id=1),
            mode TEXT,
            updated_at TEXT,
            notes TEXT,
            last_error TEXT
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            symbol TEXT PRIMARY KEY,
            entry_price REAL,
            qty REAL,
            updated_at TEXT
        )
        """)
        cur.execute("INSERT OR IGNORE INTO bot_status (id, mode, updated_at, notes, last_error) VALUES (1,'unknown',datetime('now'),'','')")
        c.commit()
        c.close()

def set_status(mode: str, notes: str = "", last_error: str = ""):
    with _lock:
        c = _conn()
        cur = c.cursor()
        cur.execute("""
            UPDATE bot_status
            SET mode=?, updated_at=datetime('now'), notes=?, last_error=?
            WHERE id=1
        """, (mode, notes, last_error))
        c.commit()
        c.close()

def upsert_position(symbol: str, entry_price: float, qty: float):
    with _lock:
        c = _conn()
        cur = c.cursor()
        cur.execute("""
            INSERT INTO positions(symbol, entry_price, qty, updated_at)
            VALUES(?,?,?,datetime('now'))
            ON CONFLICT(symbol) DO UPDATE SET
              entry_price=excluded.entry_price,
              qty=excluded.qty,
              updated_at=datetime('now')
        """, (symbol, entry_price, qty))
        c.commit()
        c.close()

def delete_position(symbol: str):
    with _lock:
        c = _conn()
        cur = c.cursor()
        cur.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
        c.commit()
        c.close()

def get_status():
    with _lock:
        c = _conn()
        cur = c.cursor()
        cur.execute("SELECT mode, updated_at, notes, last_error FROM bot_status WHERE id=1")
        row = cur.fetchone()
        c.close()
        return row

def get_positions():
    with _lock:
        c = _conn()
        cur = c.cursor()
        cur.execute("SELECT symbol, entry_price, qty, updated_at FROM positions ORDER BY symbol")
        rows = cur.fetchall()
        c.close()
        return rows
