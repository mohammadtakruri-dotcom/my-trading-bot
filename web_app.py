# web_app.py
import os
from flask import Flask, render_template, jsonify
from db import conn, init_db, now_iso

app = Flask(__name__)
init_db()

@app.route("/")
def dashboard():
    c = conn()
    cur = c.cursor(dictionary=True)

    cur.execute("SELECT * FROM bot_status WHERE id=1")
    status = cur.fetchone() or {}

    cur.execute("SELECT * FROM trades WHERE status='OPEN' ORDER BY id DESC LIMIT 100")
    open_trades = cur.fetchall()

    cur.execute("SELECT * FROM trades WHERE status='CLOSED' ORDER BY id DESC LIMIT 100")
    closed_trades = cur.fetchall()

    c.close()
    return render_template("dashboard.html",
                           status=status,
                           open_trades=open_trades,
                           closed_trades=closed_trades,
                           now=now_iso())

@app.route("/api/status")
def api_status():
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM bot_status WHERE id=1")
    row = cur.fetchone()
    c.close()
    return jsonify(row or {})

@app.route("/api/trades/open")
def api_trades_open():
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT * FROM trades WHERE status='OPEN' ORDER BY id DESC LIMIT 200")
    rows = cur.fetchall()
    c.close()
    return jsonify(rows)

@app.route("/health")
def health():
    return {"status": "ok", "time": now_iso()}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
