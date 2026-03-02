import os
from flask import Flask, render_template, jsonify
from db import init_db, get_status

app = Flask(__name__, template_folder="templates")

# Flask 3: no before_first_request
_db_inited = False

@app.before_request
def _ensure_db_once():
    global _db_inited
    if not _db_inited:
        init_db()
        _db_inited = True

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/api/status")
def api_status():
    return jsonify(get_status())

@app.get("/")
def dashboard():
    status = get_status()
    app_name = os.environ.get("APP_NAME", "My Trading Bot")
    return render_template("dashboard.html", app_name=app_name, status=status)
