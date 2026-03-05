import os
from flask import Flask, render_template, jsonify
from db import get_status, last_trades, init_db

# =========================
# Flask App
# =========================
app = Flask(__name__)

# =========================
# Initialize database once
# =========================
_db_ready = False

@app.before_request
def ensure_db():
    global _db_ready
    if not _db_ready:
        init_db()
        _db_ready = True


# =========================
# Dashboard
# =========================
@app.route("/")
def home():
    try:
        status = get_status()
        trades = last_trades(30)

        return render_template(
            "dashboard.html",
            st=status,
            trades=trades
        )
    except Exception as e:
        return f"Error loading dashboard: {str(e)}"


# =========================
# API: Status
# =========================
@app.route("/api/status")
def api_status():
    return jsonify(get_status())


# =========================
# API: Trades
# =========================
@app.route("/api/trades")
def api_trades():
    return jsonify(last_trades(50))


# =========================
# Health Check
# =========================
@app.route("/health")
def health():
    return {
        "status": "ok",
        "db_path": os.getenv("DB_PATH", "bot.sqlite3")
    }


# =========================
# Run Server (local)
# =========================
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
