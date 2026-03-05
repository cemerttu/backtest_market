import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

mt5.initialize()

rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 199999)
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
df.to_csv("EURUSD_M30.csv", index=False)

mt5.shutdown()
print("✅ CSV saved")
