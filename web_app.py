from flask import Flask

app = Flask(__name__)

@app.route("/health")
def health():
    return "ok", 200

@app.route("/")
def home():
    return "<h1>my-trading-bot is running ✅</h1>", 200
