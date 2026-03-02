import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "data/app.db")

def ensure_dir():
    d = os.path.dirname(DB_PATH)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

@contextmanager
def get_conn():
    ensure_dir()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_status (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            mode TEXT,
            is_running INTEGER,
            updated_at TEXT,
            usdt_free REAL,
            last_price REAL,
            last_error TEXT,
            notes TEXT
        )
        """)
        # Ensure row exists
        row = conn.execute("SELECT id FROM bot_status WHERE id=1").fetchone()
        if row is None:
            conn.execute("""
            INSERT INTO bot_status (id, mode, is_running, updated_at, usdt_free, last_price, last_error, notes)
            VALUES (1, 'paper', 0, '', 0, 0, '', '')
            """)

def set_status(
    mode=None,
    is_running=None,
    updated_at=None,
    usdt_free=None,
    last_price=None,
    last_error=None,
    notes=None
):
    init_db()
    fields = []
    vals = []

    def add(field, value):
        fields.append(f"{field}=?")
        vals.append(value)

    if mode is not None: add("mode", mode)
    if is_running is not None: add("is_running", 1 if is_running else 0)
    if updated_at is not None: add("updated_at", updated_at)
    if usdt_free is not None: add("usdt_free", float(usdt_free))
    if last_price is not None: add("last_price", float(last_price))
    if last_error is not None: add("last_error", str(last_error)[:4000])
    if notes is not None: add("notes", str(notes)[:4000])

    if not fields:
        return

    sql = f"UPDATE bot_status SET {', '.join(fields)} WHERE id=1"
    with get_conn() as conn:
        conn.execute(sql, vals)

def get_status():
    init_db()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM bot_status WHERE id=1").fetchone()
        return dict(row) if row else {}
