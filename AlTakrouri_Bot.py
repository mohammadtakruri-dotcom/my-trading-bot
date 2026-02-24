import ccxt, time, os, requests, threading, random, pandas as pd, mysql.connector
from flask import Flask

app = Flask(__name__)

# إعدادات الربط - تأكد من مطابقتها للوحة التحكم
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
        # إرسال تنبيه إذا فشل الحفظ في SQL لتعرف ماذا اشترى الروبوت
        send_telegram(f"⚠️ <b>تنبيه SQL:</b> تم تنفيذ الصفقة في باينانس ولكن فشل الحفظ في القاعدة.\nالخطأ: {e}")
        return False

def calculate_rsi(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        delta = df['c'].diff()
        up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
        rs = up.ewm(com=13).mean() / down.ewm(com=13).mean()
        rsi = 100 - (100 / (1 + rs)).iloc[-1]
        return rsi if not pd.isna(rsi) else None
    except: return None

def monitor_trades():
    while True:
        try:
            # نحاول جلب الصفقات من القاعدة، إذا فشل نرسل تنبيه
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM trades WHERE status IN ('OPEN', 'PENDING_SELL')")
            trades = cursor.fetchall()
            conn.close()
            for trade in trades:
                ticker = exchange.fetch_ticker(trade['symbol'])
                current_p = ticker.get('last')
                if current_p:
                    change = ((current_p - trade['buy_price']) / trade['buy_price']) * 100
                    if change >= 10.0 or change <= -5.0 or trade['status'] == 'PENDING_SELL':
                        balance = exchange.fetch_balance()
                        amt = balance.get(trade['symbol'].split('/')[0], {}).get('free', 0)
                        if amt > 0:
                            exchange.create_market_sell_order(trade['symbol'], amt)
                            execute_db_query("UPDATE trades SET sell_price=%s, status='CLOSED', profit_pct=%s WHERE id=%s", (current_p, round(change, 2), trade['id']))
                            send_telegram(f"💰 <b>تم البيع!</b>\nالعملة: {trade['symbol']}\nالربح: {change:.2f}%")
        except: pass
        time.sleep(30)

def trading_engine():
    send_telegram("🚀 <b>محرك التكروري يعمل (نظام الحماية من أعطال SQL نشط)</b>")
    while True:
        try:
            balance = exchange.fetch_balance()
            usdt_free = float(balance.get('USDT', {}).get('free', 0))
            if usdt_free >= 25.0: # المبلغ الذي حددته
                buy_amt = 25.0
                tickers = exchange.fetch_tickers()
                for sym, t in tickers.items():
                    change = t.get('percentage')
                    last_p = t.get('last')
                    if '/USDT' in sym and change is not None and change > 5.0:
                        rsi = calculate_rsi(sym)
                        if rsi is not None and rsi < 70:
                            exchange.create_market_buy_order(sym, buy_amt)
                            # محاولة الحفظ في SQL
                            saved = execute_db_query("INSERT INTO trades (symbol, buy_price, amount_usdt) VALUES (%s, %s, %s)", (sym, last_p, buy_amt))
                            msg = f"✅ <b>شراء ناجح</b>\nالعملة: {sym}\nالمبلغ: {buy_amt}$"
                            if not saved: msg += "\n⚠️ (لم تُسجل في الصفحة - خطأ SQL)"
                            send_telegram(msg)
                            break
        except Exception as e: print(f"Error: {e}")
        time.sleep(60)

threading.Thread(target=trading_engine, daemon=True).start()
threading.Thread(target=monitor_trades, daemon=True).start()

@app.route('/')
def home(): return "<h1>رادار التكروري: المحرك مستقر ✅</h1>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
