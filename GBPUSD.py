
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# ===============================
# CONFIGURATION
# ===============================
SYMBOL = "GBPUSD"
TIMEFRAME = mt5.TIMEFRAME_M1
LOOKBACK_BARS = 20000
UPDATE_INTERVAL = 2

# Binary settings
STAKE = 10
PAYOUT = 0.85
EXPIRY_MINUTES = 2

ATR_PERIOD = 14
LOW_ATR = 0.00025
HIGH_ATR = 0.00060

MAGIC_NUMBER = 123456

# ===============================
# MT5 INITIALIZE
# ===============================
if not mt5.initialize():
    raise RuntimeError("MT5 initialization failed")

account_info = mt5.account_info()
print(f"🚀 Connected | Account: {account_info.login} | Balance: {account_info.balance}")

# ===============================
# FETCH DATA
# ===============================
def get_data():
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, LOOKBACK_BARS)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

# ===============================
# INDICATORS
# ===============================
def calculate_indicators(df):

    # EMA TREND
    df["EMA20"] = df["close"].ewm(span=20).mean()
    df["EMA50"] = df["close"].ewm(span=50).mean()
    df["EMA200"] = df["close"].ewm(span=200).mean()

    # RSI
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + rs))

    # MACD
    df["MACD"] = df["close"].ewm(span=12).mean() - df["close"].ewm(span=26).mean()
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9).mean()

    # ATR
    hl = df["high"] - df["low"]
    hc = abs(df["high"] - df["close"].shift())
    lc = abs(df["low"] - df["close"].shift())
    tr = np.maximum(hl, np.maximum(hc, lc))
    df["ATR"] = pd.Series(tr).rolling(ATR_PERIOD).mean()

    # Bollinger Bands
    df["BB_MID"] = df["close"].rolling(20).mean()
    df["BB_STD"] = df["close"].rolling(20).std()
    df["BB_UPPER"] = df["BB_MID"] + 2 * df["BB_STD"]
    df["BB_LOWER"] = df["BB_MID"] - 2 * df["BB_STD"]

    # Breakout Levels
    df["HIGH20"] = df["high"].rolling(20).max()
    df["LOW20"] = df["low"].rolling(20).min()

    return df

# ===============================
# SIGNAL ENGINE
# ===============================
def generate_signal(df):

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # TREND SCORE
    trend_score = 0
    trend_score += 1 if last["close"] > last["EMA200"] else -1
    trend_score += 1 if last["EMA20"] > last["EMA50"] else -1
    trend_score += 1 if last["MACD"] > last["MACD_SIGNAL"] else -1

    # BREAKOUT
    breakout_signal = None
    if last["close"] > prev["HIGH20"]:
        breakout_signal = "BUY"
    elif last["close"] < prev["LOW20"]:
        breakout_signal = "SELL"

    # REVERSAL
    reversal_signal = None
    if last["RSI"] < 30 and last["close"] <= last["BB_LOWER"]:
        reversal_signal = "BUY"
    elif last["RSI"] > 70 and last["close"] >= last["BB_UPPER"]:
        reversal_signal = "SELL"

    # ATR FILTER
    atr = last["ATR"]
    if atr > HIGH_ATR:
        vol_status = "HIGH"
    elif atr < LOW_ATR:
        vol_status = "LOW"
    else:
        vol_status = "NORMAL"

    # FINAL DECISION
    if breakout_signal:
        return breakout_signal, "BREAKOUT", vol_status

    if reversal_signal:
        return reversal_signal, "REVERSAL", vol_status

    if trend_score >= 2:
        return "BUY", "TREND", vol_status

    if trend_score <= -2:
        return "SELL", "TREND", vol_status

    return "NEUTRAL", "NONE", vol_status

# ===============================
# LOT SIZE
# ===============================
def calculate_lot():
    return round(STAKE / 100, 2)

# ===============================
# POSITION CHECK
# ===============================
def position_exists():
    positions = mt5.positions_get(symbol=SYMBOL)
    return positions is not None and len(positions) > 0

# ===============================
# OPEN TRADE
# ===============================
def open_trade(signal, lot):

    tick = mt5.symbol_info_tick(SYMBOL)

    if signal == "BUY":
        entry_price = tick.ask
        order_type = mt5.ORDER_TYPE_BUY
    else:
        entry_price = tick.bid
        order_type = mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lot,
        "type": order_type,
        "price": entry_price,
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "Binary Trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    mt5.order_send(request)
    print("🚀 Trade opened at:", round(entry_price, 5))

    # EXPIRY TIMER
    start = time.time()
    expiry_seconds = EXPIRY_MINUTES * 60

    while True:
        elapsed = int(time.time() - start)
        remaining = expiry_seconds - elapsed
        if remaining <= 0:
            break

        mins = remaining // 60
        secs = remaining % 60

        tick = mt5.symbol_info_tick(SYMBOL)
        current_price = tick.bid if signal == "BUY" else tick.ask

        status = "WIN ✅" if (
            (signal == "BUY" and current_price > entry_price) or
            (signal == "SELL" and current_price < entry_price)
        ) else "LOSS ❌"

        print(
            f"⏳ {mins:02d}:{secs:02d} | Entry: {entry_price:.5f} | "
            f"Current: {current_price:.5f} | {status}",
            end="\r"
        )

        time.sleep(1)

    print("\n⏰ EXPIRY REACHED")

    # CLOSE POSITION
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        pos = positions[0]
        tick = mt5.symbol_info_tick(SYMBOL)

        close_price = tick.bid if pos.type == 0 else tick.ask

        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": pos.volume,
            "type": mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
            "position": pos.ticket,
            "price": close_price,
            "deviation": 20,
            "magic": MAGIC_NUMBER,
        }

        mt5.order_send(close_request)

        win = (
            (signal == "BUY" and close_price > entry_price) or
            (signal == "SELL" and close_price < entry_price)
        )

        if win:
            print(f"🎉 WIN! +${STAKE * PAYOUT:.2f}")
        else:
            print(f"💀 LOSS! -${STAKE}")

# ===============================
# MAIN LOOP
# ===============================
try:
    print("\n📡 AUTO TRADING STARTED...\n")

    while True:

        df = calculate_indicators(get_data())
        signal, mode, vol = generate_signal(df)

        price = df.iloc[-1]["close"]
        real_time = datetime.now().strftime("%H:%M:%S")
        lot = calculate_lot()

        print("=" * 70)
        print(f"⏰ {real_time} | Price: {price:.5f}")
        print(f"📊 Signal: {signal} | Mode: {mode} | Volatility: {vol}")
        print("=" * 70)

        if not position_exists() and signal in ["BUY", "SELL"]:
            open_trade(signal, lot)
        else:
            print("⛔ No trade or position exists")

        time.sleep(UPDATE_INTERVAL)

except KeyboardInterrupt:
    print("Stopped")

finally:
    mt5.shutdown()