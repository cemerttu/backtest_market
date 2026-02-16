import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# ===============================
# MT5 CONFIGURATION
# ===============================
SYMBOL = "EURUSD"
TIMEFRAME = mt5.TIMEFRAME_M1  # 1-minute candles
SPREAD_PIPS = 0.00010         # 1 pip spread

# Risk Management
TP_PIPS = 0.0010    # 10 pips Take Profit
SL_PIPS = 0.0008    # 8 pips Stop Loss
MAX_HOLD_BARS = 24  # Max 24 minutes for M1

# Fetch last N candles for indicators
LOOKBACK_BARS = 200

# Update interval (seconds)
UPDATE_INTERVAL = 5

# ===============================
# INITIALIZE MT5
# ===============================
if not mt5.initialize():
    raise RuntimeError(f"❌ MT5 initialization failed: {mt5.last_error()}")

print(f"🚀 Connected to MT5 | Account: {mt5.account_info().login} | Server: {mt5.account_info().server}")

# ===============================
# FUNCTION TO FETCH LAST N BARS
# ===============================
def get_latest_data(symbol, timeframe, n_bars):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n_bars)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

# ===============================
# FUNCTION TO CALCULATE INDICATORS
# ===============================
def calculate_indicators(df):
    df["EMA20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["EMA50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["close"].ewm(span=200, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    df["MACD"] = df["close"].ewm(span=12, adjust=False).mean() - df["close"].ewm(span=26, adjust=False).mean()
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()
    return df

# ===============================
# FUNCTION TO GENERATE LIVE SIGNAL
# ===============================
def generate_signal(df):
    last = df.iloc[-1]
    score = 0
    # Trend
    score += 1 if last["close"] > last["EMA200"] else -1
    # EMA crossover
    score += 1 if last["EMA20"] > last["EMA50"] else -1
    # MACD
    score += 1 if last["MACD"] > last["MACD_SIGNAL"] else -1
    # RSI
    score += 1 if last["RSI"] < 40 else -1 if last["RSI"] > 60 else 0

    if score >= 3:
        return "STRONG BUY", score
    elif score <= -3:
        return "STRONG SELL", score
    elif score >= 2:
        return "BUY (Moderate)", score
    elif score <= -2:
        return "SELL (Moderate)", score
    else:
        return "NEUTRAL", score

# ===============================
# MAIN LOOP FOR LIVE SIGNAL
# ===============================
try:
    print("📡 Starting live signal updates (press Ctrl+C to stop)...\n")
    while True:
        df = get_latest_data(SYMBOL, TIMEFRAME, LOOKBACK_BARS)
        if df is None:
            print("⚠️ Failed to fetch data. Retrying...")
            time.sleep(UPDATE_INTERVAL)
            continue

        df = calculate_indicators(df)
        live_signal, score = generate_signal(df)
        last_price = df.iloc[-1]["close"]
        timestamp = df.index[-1].strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"[{timestamp}] Price: {last_price:.5f} | Signal: {live_signal} | Score: {score}/4")

        time.sleep(UPDATE_INTERVAL)

except KeyboardInterrupt:
    print("\n🛑 Stopped by user.")

finally:
    mt5.shutdown()
