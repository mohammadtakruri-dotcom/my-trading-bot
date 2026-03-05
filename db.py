import os, sqlite3, time

DB_PATH = os.getenv("DB_PATH", "bot.sqlite3")

def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    # safer for frequent writes
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA synchronous=NORMAL;")
    return c

def init_db():
    c = conn()
    cur = c.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bot_status(
        id INTEGER PRIMARY KEY CHECK (id=1),
        mode TEXT,
        last_heartbeat INTEGER,
        symbol TEXT,
        price REAL,
        pnl REAL,
        position_qty REAL,
        position_entry REAL,
        last_action TEXT,
        last_error TEXT
    )
    """)
    cur.execute("""
    INSERT OR IGNORE INTO bot_status(id, mode, last_heartbeat, symbol, price, pnl, position_qty, position_entry, last_action, last_error)
    VALUES(1, 'paper', 0, '', 0, 0, 0, 0, '', '')
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS trades(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER,
        symbol TEXT,
        side TEXT,
        qty REAL,
        price REAL,
        note TEXT
    )
    """)
    c.commit()
    c.close()

def set_status(**kw):
    if not kw:
        return
    fields = []
    vals = []
    for k, v in kw.items():
        fields.append(f"{k}=?")
        vals.append(v)
    vals.append(1)
    sql = f"UPDATE bot_status SET {', '.join(fields)} WHERE id=?"
    c = conn()
    c.execute(sql, vals)
    c.commit()
    c.close()

def add_trade(symbol, side, qty, price, note=""):
    c = conn()
    c.execute(
        "INSERT INTO trades(ts, symbol, side, qty, price, note) VALUES(?,?,?,?,?,?)",
        (int(time.time()), symbol, side, float(qty), float(price), note),
    )
    c.commit()
    c.close()

def get_status():
    c = conn()
    row = c.execute("SELECT * FROM bot_status WHERE id=1").fetchone()
    c.close()
    return dict(row) if row else {}

def last_trades(limit=50):
    c = conn()
    rows = c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]
