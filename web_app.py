# web_app.py
from flask import Flask, jsonify
import sqlite3
import os

app = Flask(__name__)
DB_PATH = os.environ.get("DB_PATH", "bot.db")

def _conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

@app.get("/")
def home():
    con = _conn()
    cur = con.cursor()

    status = cur.execute("SELECT mode, now_iso, usdt_free, last_price, last_error, notes FROM bot_status WHERE id=1").fetchone()
    pos = cur.execute("SELECT symbol, side, qty, entry_price, entry_time, is_open FROM position WHERE id=1").fetchone()
    last_trades = cur.execute("SELECT symbol, action, qty, price, time, note FROM trades ORDER BY id DESC LIMIT 10").fetchall()

    con.close()

    data = {
        "status": {
            "mode": status[0], "now": status[1], "usdt_free": status[2],
            "last_price": status[3], "last_error": status[4], "notes": status[5],
        },
        "position": {
            "symbol": pos[0], "side": pos[1], "qty": pos[2], "entry_price": pos[3],
            "entry_time": pos[4], "is_open": pos[5],
        },
        "last_trades": [
            {"symbol": r[0], "action": r[1], "qty": r[2], "price": r[3], "time": r[4], "note": r[5]}
            for r in last_trades
        ]
    }
    return jsonify(data)
