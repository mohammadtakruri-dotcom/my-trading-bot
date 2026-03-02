from flask import Flask, render_template
from db import get_status, last_trades, init_db

app = Flask(__name__)
init_db()

@app.get("/")
def home():
    st = get_status()
    trades = last_trades(30)
    return render_template("dashboard.html", st=st, trades=trades)
