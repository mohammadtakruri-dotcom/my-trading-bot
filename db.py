# db.py
import os
import mysql.connector
from datetime import datetime, timezone

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "database": os.getenv("DB_NAME"),
    "connect_timeout": 10,
}

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def conn():
    return mysql.connector.connect(**DB_CONFIG)

def init_db():
    c = conn()
    cur = c.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INT AUTO_INCREMENT PRIMARY KEY,
        symbol VARCHAR(30) NOT NULL,
        status VARCHAR(10) NOT NULL DEFAULT 'OPEN',   -- OPEN/CLOSED
        buy_price DOUBLE,
        buy_qty DOUBLE,
        buy_usdt DOUBLE,
        buy_order_id VARCHAR(64),
        buy_time VARCHAR(40),
        sell_price DOUBLE,
        sell_qty DOUBLE,
        sell_order_id VARCHAR(64),
        sell_time VARCHAR(40)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS bot_status (
        id INT PRIMARY KEY,
        mode VARCHAR(10),
        last_run VARCHAR(40),
        last_error TEXT,
        usdt_free DOUBLE,
        notes TEXT
    )
    """)

    # صف واحد ثابت
    cur.execute("INSERT IGNORE INTO bot_status(id, mode, last_run, last_error, usdt_free, notes) VALUES(1,%s,%s,%s,%s,%s)",
                (os.getenv("MODE","paper"), now_iso(), "", 0.0, "initialized"))

    c.commit()
    c.close()
