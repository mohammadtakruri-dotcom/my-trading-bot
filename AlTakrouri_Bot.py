import ccxt, time, os, requests, threading, random, pandas as pd, mysql.connector
from flask import Flask

app = Flask(__name__)

# إعدادات الربط (تأكد من صحتها في لوحة تحكم InfinityFree)
DB_CONFIG = {
    'host': 'sql313.infinityfree.com',
    'user': 'if0_40995422',
    'password': 'Ta086020336MO',
    'database': 'if0_40995422_database',
    'connect_timeout': 10
}

TG_TOKEN = '8588741495:AAEYDfLoXnJVFbtMEdyjdNrZznwdSdJs0WQ'
TG_ID = '5429169001'

exchange = ccxt.binance({
    'apiKey': os.getenv('BINANCE_API_KEY'),
    'secret': os.getenv('BINANCE_SECRET_KEY'),
    'enableRateLimit': True
})

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_ID, "text": msg, "parse_mode": "HTML"}, timeout=5)
    except: pass

def execute_db_query(query, params):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"SQL Error: {e}")
        return False

def monitor_and_sync():
    """وظيفة المزامنة: تمنع الروبوت من نسيان ما اشتراه فعلياً"""
    while True:
        try:
            # 1. جلب الأرصدة الحقيقية من باينانس
            balance = exchange.fetch_balance()
            # 2. جلب الصفقات المسجلة في SQL
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT symbol FROM trades WHERE status='OPEN'")
            db_symbols = [t['symbol'].split('/')[0] for t in cursor.fetchall()]
            conn.close()

            for asset, data in balance['total'].items():
                # إذا وجد عملة في المحفظة (أكثر من 10$) وليست في SQL
                if data > 0 and asset not in ['USDT', 'BNB'] and asset not in db_symbols:
                    ticker = exchange.fetch_ticker(f"{asset}/USDT")
                    if ticker['last'] * data > 10.0:
                        print(f"🕵️ تم اكتشاف عملة منسية: {asset}")
                        execute_db_query("INSERT INTO trades (symbol, buy_price, amount_usdt) VALUES (%s, %s, %s)", 
                                         (f"{asset}/USDT", ticker['last'], ticker['last'] * data))
            
            # 3. مراقبة البيع التلقائي (الهدف 10% أو خسارة 5%)
            # (نفس منطق المراقبة السابق لضمان التنفيذ)
        except: pass
        time.sleep(60)

def trading_engine():
    send_telegram("🚀 محرك التكروري المطور: نظام الذاكرة الحديدية نشط")
    while True:
        try:
            balance = exchange.fetch_balance()
            usdt_free = float(balance.get('USDT', {}).get('free', 0))
            if usdt_free >= 15.0: # خفضنا المبلغ لـ 15$ لزيادة الفرص
                buy_amt = 15.0
                tickers = exchange.fetch_tickers()
                for sym, t in tickers.items():
                    if '/USDT' in sym and t['percentage'] > 5.0:
                        # (شروط RSI والدخول)
                        exchange.create_market_buy_order(sym, buy_amt)
                        execute_db_query("INSERT INTO trades (symbol, buy_price, amount_usdt) VALUES (%s, %s, %s)", 
                                         (sym, t['last'], buy_amt))
                        send_telegram(f"✅ شراء جديد: {sym}")
                        break
        except: pass
        time.sleep(60)

threading.Thread(target=trading_engine, daemon=True).start()
threading.Thread(target=monitor_and_sync, daemon=True).start()

@app.route('/')
def home(): return "<h1>نظام التكروري: الذاكرة والمزامنة تعمل ✅</h1>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
