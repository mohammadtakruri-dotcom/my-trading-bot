from flask import Flask, jsonify, render_template
from db import init_db, get_status

app = Flask(__name__)

# ✅ بديل صحيح عن before_first_request (لأنه أحيانًا يسبب مشاكل حسب نسخة Flask)
_db_ready = False

@app.before_request
def _ensure_db():
    global _db_ready
    if not _db_ready:
        init_db()
        _db_ready = True

@app.get("/health")
def health():
    return "ok", 200

@app.get("/api/status")
def api_status():
    s = get_status()
    return jsonify(s or {})

@app.get("/")
def index():
    s = get_status() or {}
    return render_template("dashboard.html", s=s)
