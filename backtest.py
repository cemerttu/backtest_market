import pandas as pd
import numpy as np
from datetime import datetime

# ===============================
# CONFIGURATION
# ===============================
CSV_FILE = "EURUSD_M1.csv"
STAKE = 10           # fixed bet size per trade
PAYOUT = 0.90        # binary option payout
EXPIRY_MINUTES = 30     # how many minutes until option expires

ATR_PERIOD = 14
LOW_ATR = 0.00025    # filter out when market is too quiet
HIGH_ATR = 0.00035   # filter out when market is too volatile
MIN_SCORE = 4        # only trade when |score| >= MIN_SCORE

# ===============================
# LOAD DATA
# ===============================
df = pd.read_csv(CSV_FILE)
df['time'] = pd.to_datetime(df['time'])
df.set_index('time', inplace=True)
df['position'] = None
df['trade_result'] = None

# ===============================
# INDICATORS
# ===============================
def calculate_indicators(df):
    # EMA
    df['EMA20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['EMA200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # MACD
    df['MACD'] = df['close'].ewm(span=12, adjust=False).mean() - df['close'].ewm(span=26, adjust=False).mean()
    df['MACD_SIGNAL'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # ATR
    hl = df['high'] - df['low']
    hc = abs(df['high'] - df['close'].shift())
    lc = abs(df['low'] - df['close'].shift())
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(ATR_PERIOD).mean()
    
    # Bollinger Bands
    df['BB_MID'] = df['close'].rolling(20).mean()
    df['BB_STD'] = df['close'].rolling(20).std()
    df['BB_UPPER'] = df['BB_MID'] + 2 * df['BB_STD']
    df['BB_LOWER'] = df['BB_MID'] - 2 * df['BB_STD']
    
    # High/Low 20
    df['HIGH20'] = df['high'].rolling(20).max()
    df['LOW20'] = df['low'].rolling(20).min()
    
    return df

# ===============================
# SIGNAL GENERATOR
# ===============================
def generate_signal(last, prev):
    # ATR volatility
    atr = last['ATR']
    if atr > HIGH_ATR: vol_status = "HIGH"
    elif atr < LOW_ATR: vol_status = "LOW"
    else: vol_status = "NORMAL"
    
    # Reversal score
    reversal_score = 0
    if last['RSI'] < 30 and last['close'] <= last['BB_LOWER']:
        reversal_score += 2
    if last['RSI'] > 70 and last['close'] >= last['BB_UPPER']:
        reversal_score -= 2
    
    # Trend score
    trend_score = 0
    trend_score += 1 if last['close'] > last['EMA200'] else -1
    trend_score += 1 if last['EMA20'] > last['EMA50'] else -1
    trend_score += 1 if last['MACD'] > last['MACD_SIGNAL'] else -1
    
    # Breakout score
    breakout_score = 0
    if last['close'] > prev['HIGH20']:
        breakout_score += 2
    elif last['close'] < prev['LOW20']:
        breakout_score -= 2
    
    total_score = reversal_score + trend_score + breakout_score
    
    # apply user-configurable threshold so that only stronger signals are taken
    if total_score >= MIN_SCORE:
        return "BUY", total_score, vol_status
    elif total_score <= -MIN_SCORE:
        return "SELL", total_score, vol_status
    else:
        return "NEUTRAL", total_score, vol_status

# ===============================
# TRADE SIMULATION
# ===============================
def simulate_trade(df, idx, signal):
    open_price = df.iloc[idx-1]['close']
    expiry_idx = min(idx + EXPIRY_MINUTES, len(df)-1)
    close_price = df.iloc[expiry_idx]['close']
    
    win = (signal == "BUY" and close_price > open_price) or \
          (signal == "SELL" and close_price < open_price)
    
    df.at[df.index[idx], 'position'] = signal
    df.at[df.index[idx], 'trade_result'] = "WIN" if win else "LOSS"
    return win, open_price, close_price

# ===============================
# BACKTEST
# ===============================
df = calculate_indicators(df)
results = []

for idx in range(20, len(df)-EXPIRY_MINUTES):
    last = df.iloc[idx-1]
    prev = df.iloc[idx-2]
    
    signal, score, vol = generate_signal(last, prev)
    
    if signal in ["BUY", "SELL"]:
        win, open_price, close_price = simulate_trade(df, idx, signal)
        results.append({
            "time": df.index[idx],
            "signal": signal,
            "score": score,
            "volatility": vol,
            "open": open_price,
            "close": close_price,
            "result": "WIN" if win else "LOSS"
        })
        print(f"{df.index[idx]} | {signal} | Score: {score} | {vol} | Open: {open_price:.5f} | Close: {close_price:.5f} | {'WIN' if win else 'LOSS'}")

# ===============================
# SUMMARY
# ===============================
total_trades = len(results)
wins = sum(1 for r in results if r['result'] == "WIN")
losses = total_trades - wins
win_rate = (wins/total_trades*100) if total_trades else 0
profit = wins*STAKE*PAYOUT - losses*STAKE

print("\n================= BACKTEST RESULTS =================")
print(f"Total Trades: {total_trades}")
print(f"Wins: {wins} | Losses: {losses} | Win Rate: {win_rate:.2f}%")
print(f"Total Profit: ${profit:.2f}")
print("=====================================================")

# additional diagnostics to help with tuning
if total_trades:
    from collections import defaultdict
    score_stats = defaultdict(lambda: {'count':0,'wins':0,'profit':0.0})
    for r in results:
        sc = r['score']
        win = 1 if r['result']=='WIN' else 0
        score_stats[sc]['count'] += 1
        score_stats[sc]['wins'] += win
        score_stats[sc]['profit'] += (STAKE*PAYOUT if win else -STAKE)
    print("\nStats by signal score:")
    for sc in sorted(score_stats):
        st = score_stats[sc]
        wr = st['wins']/st['count']*100
        print(f" score {sc:+} | trades {st['count']:5d} | win {wr:5.1f}% | profit {st['profit']:8.2f}")
    # compute stats by volatility
    vol_stats = defaultdict(lambda: {'count':0,'wins':0,'profit':0.0})
    for r in results:
        v = r['volatility']
        win = 1 if r['result']=='WIN' else 0
        vol_stats[v]['count'] += 1
        vol_stats[v]['wins'] += win
        vol_stats[v]['profit'] += (STAKE*PAYOUT if win else -STAKE)
    print("\nStats by volatility:")
    for v in sorted(vol_stats):
        st = vol_stats[v]
        wr = st['wins']/st['count']*100
        print(f" {v:7} | trades {st['count']:5d} | win {wr:5.1f}% | profit {st['profit']:8.2f}")
    avg_win = (STAKE*PAYOUT)
    avg_loss = STAKE
    expectancy = (wins/total_trades)*avg_win - (losses/total_trades)*avg_loss
    print(f"\nExpectancy per trade: ${expectancy:.2f} (positive is good)")
    print("(You can increase MIN_SCORE or tweak filters to lift the win rate.)")