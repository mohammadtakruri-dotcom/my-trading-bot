import os
from flask import Flask, render_template
from db import init_db, get_status, list_trades

app = Flask(__name__)

# إنشاء قاعدة البيانات عند بدء التطبيق
init_db()

@app.route("/health")
def health():
    return {"ok": True}

@app.route("/")
def dashboard():
    status = get_status()
    open_trades = list_trades(status="OPEN", limit=100)
    closed_trades = list_trades(status="CLOSED", limit=100)

    total_pnl = sum(float(t.get("pnl_usdt") or 0.0) for t in closed_trades)
    wins = sum(1 for t in closed_trades if float(t.get("pnl_usdt") or 0.0) > 0)
    losses = sum(1 for t in closed_trades if float(t.get("pnl_usdt") or 0.0) < 0)

    return render_template(
        "dashboard.html",
        app_name=os.getenv("APP_NAME", "Takruri Trading Bot"),
        status=status,
        open_trades=open_trades,
        closed_trades=closed_trades,
        total_pnl=total_pnl,
        wins=wins,
        losses=losses
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
