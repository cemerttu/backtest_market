import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

# ===============================
# CONFIGURATION
# ===============================
SYMBOL = "EURUSD"
TIMEFRAME = mt5.TIMEFRAME_M5       
CSV_FILE = "EURUSD_M1.csv"

UPDATE_INTERVAL = 10
LIVE_BARS = 300
MAX_DATA = 500

ATR_PERIOD = 14
LOW_ATR = 0.00025
HIGH_ATR = 0.00060

# ===============================
# LOAD CSV HISTORY
# ===============================
def load_csv_history():

    try:
        df = pd.read_csv(CSV_FILE)
        df["time"] = pd.to_datetime(df["time"])
        df.set_index("time", inplace=True)
        df = df[["open","high","low","close"]]
        return df
    except Exception as e:
        raise RuntimeError(f"Failed to load CSV: {e}")


# ===============================
# GET LIVE MT5 DATA
# ===============================
def get_live_data():

    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, LIVE_BARS)

    df = pd.DataFrame(rates)

    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)

    df = df[["open","high","low","close"]]

    return df


# ===============================
# INDICATORS
# ===============================
def calculate_indicators(df):

    if len(df) < 200:
        return df

    df["EMA20"] = df["close"].ewm(span=20).mean()
    df["EMA50"] = df["close"].ewm(span=50).mean()
    df["EMA200"] = df["close"].ewm(span=200).mean()

    delta = df["close"].diff()

    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    df["MACD"] = df["close"].ewm(span=12).mean() - df["close"].ewm(span=26).mean()
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9).mean()

    # TRUE RANGE
    hl = df["high"] - df["low"]
    hc = abs(df["high"] - df["close"].shift())
    lc = abs(df["low"] - df["close"].shift())

    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)

    df["ATR"] = tr.ewm(alpha=1/ATR_PERIOD, adjust=False).mean()

    # BOLLINGER BANDS
    df["BB_MID"] = df["close"].rolling(20).mean()
    df["BB_STD"] = df["close"].rolling(20).std()

    df["BB_UPPER"] = df["BB_MID"] + 2 * df["BB_STD"]
    df["BB_LOWER"] = df["BB_MID"] - 2 * df["BB_STD"]

    # BREAKOUT LEVELS
    df["HIGH20"] = df["high"].rolling(20).max()
    df["LOW20"] = df["low"].rolling(20).min()

    return df


# ===============================
# SIGNAL ENGINE
# ===============================
def generate_signal(df):

    if len(df) < 200:
        return "NEUTRAL", "NONE", "LOW"

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # ----------------
    # TREND SCORE
    # ----------------
    trend_score = 0

    trend_score += 1 if last["close"] > last["EMA200"] else -1
    trend_score += 1 if last["EMA20"] > last["EMA50"] else -1
    trend_score += 1 if last["MACD"] > last["MACD_SIGNAL"] else -1

    # ----------------
    # BREAKOUT
    # ----------------
    breakout_signal = None

    if last["close"] > df["HIGH20"].iloc[-2]:
        breakout_signal = "BUY"

    elif last["close"] < df["LOW20"].iloc[-2]:
        breakout_signal = "SELL"

    # ----------------
    # REVERSAL
    # ----------------
    reversal_signal = None

    if last["RSI"] < 30 and last["close"] <= last["BB_LOWER"]:
        reversal_signal = "BUY"

    elif last["RSI"] > 70 and last["close"] >= last["BB_UPPER"]:
        reversal_signal = "SELL"

    # ----------------
    # VOLATILITY
    # ----------------
    atr = last["ATR"]

    if atr > HIGH_ATR:
        volatility = "HIGH"
    elif atr < LOW_ATR:
        volatility = "LOW"
    else:
        volatility = "NORMAL"

    # ----------------
    # SIGNAL PRIORITY
    # ----------------
    if breakout_signal:
        return breakout_signal, "BREAKOUT", volatility

    if reversal_signal:
        return reversal_signal, "REVERSAL", volatility

    if trend_score >= 2:
        return "BUY", "TREND", volatility

    if trend_score <= -2:
        return "SELL", "TREND", volatility

    return "NEUTRAL", "NONE", volatility


# ===============================
# COMBINE CSV + LIVE DATA
# ===============================
def get_combined_data():

    history = load_csv_history()

    live = get_live_data()

    df = pd.concat([history, live])

    df = df[~df.index.duplicated(keep="last")]

    df.sort_index(inplace=True)

    df = df.tail(MAX_DATA)

    return df


# ===============================
# MAIN LIVE LOOP
# ===============================
try:

    if not mt5.initialize():
        raise RuntimeError("MT5 initialization failed")

    account = mt5.account_info()

    print("Connected to MT5")
    print("Account:", account.login)
    print("Balance:", account.balance)

    print("\nStarting Live Signal Engine...\n")

    last_candle = None

    while True:

        df = get_combined_data()

        current_candle = df.index[-1]

        # wait for candle close
        if current_candle == last_candle:
            time.sleep(UPDATE_INTERVAL)
            continue

        last_candle = current_candle

        df = calculate_indicators(df)

        signal, mode, vol = generate_signal(df)

        price = df.iloc[-1]["close"]

        now = datetime.now().strftime("%H:%M:%S")

        print("=" * 70)
        print(f"Time: {now}")
        print(f"Candle: {current_candle}")
        print(f"Price: {price:.5f}")
        print(f"Signal: {signal}")
        print(f"Mode: {mode}")
        print(f"Volatility: {vol}")
        print("=" * 70)

        time.sleep(UPDATE_INTERVAL)

except KeyboardInterrupt:

    print("Bot Stopped")

finally:

    mt5.shutdown()