import os
from flask import Flask

app = Flask(__name__)

@app.route("/health")
def health():
    return "ok", 200

@app.route("/")
def home():
    return "<h1>Takruri Bot is running ✅</h1>", 200

# ملاحظة: لا يوجد before_first_request هنا نهائياً
