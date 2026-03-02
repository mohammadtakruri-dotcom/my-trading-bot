import os
from flask import Flask, render_template
from db import init_db, get_status, list_trades

app = Flask(__name__)

@app.before_first_request
def _init():
    init_db()

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/")
def dashboard():
    status = get_status()
    open_trades = list_trades(status="OPEN", limit=100)
    closed_trades = list_trades(status="CLOSED", limit=100)

    # إحصائيات بسيطة
    total_pnl = sum(float(t.get("pnl_usdt") or 0.0) for t in closed_trades)
    wins = sum(1 for t in closed_trades if float(t.get("pnl_usdt") or 0.0) > 0)
    losses = sum(1 for t in closed_trades if float(t.get("pnl_usdt") or 0.0) < 0)

    return render_template(
        "dashboard.html",
        status=status,
        open_trades=open_trades,
        closed_trades=closed_trades,
        total_pnl=total_pnl,
        wins=wins,
        losses=losses,
        app_name=os.getenv("APP_NAME", "Takruri Trading Bot")
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
