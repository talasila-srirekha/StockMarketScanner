import yfinance as yf
import pandas as pd
import requests
import warnings
import time
import logging
from io import StringIO
import os

# --- CLEAN TERMINAL SETTINGS ---
warnings.filterwarnings('ignore')
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# --- CONFIGURATION ---
BATCH_SIZE = 50

def get_nifty500_tickers():
    """Dynamically fetches the live NIFTY 500 ticker list directly from official Index repositories"""
    print("📥 Fetching the live NIFTY 500 ticker list...")
    try:
        url = 'https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        # Load CSV data
        df = pd.read_csv(StringIO(response.text))
        
        if 'Symbol' in df.columns:
            # Append .NS for Yahoo Finance compatibility with National Stock Exchange of India
            tickers = [f"{str(sym).strip()}.NS" for sym in df['Symbol'].tolist()]
            print(f"✅ Successfully loaded {len(tickers)} NIFTY 500 stocks.")
            return tickers
        else:
            raise ValueError("Could not locate 'Symbol' column in the source data.")
            
    except Exception as e:
        print(f"❌ Failed to fetch NIFTY 500 list: {e}")
        print("💡 Falling back to a small hardcoded sample list...")
        return ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"]

def calculate_rsi(df, period=14):
    """Calculates the Relative Strength Index (RSI)"""
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    # Use exponential moving average (matches standard charting platforms)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def run_volatility_analysis():
    all_tickers = get_nifty500_tickers()

    if not all_tickers:
        print("Aborting scan. Ticker list is empty.")
        return

    matched_stocks = []
    total_stocks = len(all_tickers)
    total_steps = (total_stocks + BATCH_SIZE - 1) // BATCH_SIZE

    print(f"\n⚡ Processing {total_stocks} Indian stocks for Range Expansion & Trade Analysis...")
    print("⚠️ Note: Scanning will take about 60 to 90 seconds. Please wait...\n")

    start_time = time.time()

    for i in range(0, total_stocks, BATCH_SIZE):
        batch = all_tickers[i:i+BATCH_SIZE]
        current_step = (i // BATCH_SIZE) + 1

        print(f"🔄 Running Step {current_step}/{total_steps}...", end="\r")

        try:
            # 3mo period ensures enough data for weekly/monthly calculations, 10d volume average, and RSI calculation
            data = yf.download(batch, period="3mo", group_by="ticker", progress=False)
        except Exception:
            continue

        for ticker in batch:
            try:
                if len(batch) == 1:
                    df = data.dropna()
                else:
                    if ticker not in data.columns.levels[0]:
                        continue
                    df = data[ticker].dropna()

                # Require at least 15 days of data for safe SMA and volatility lookbacks
                if len(df) < 15:
                    continue

                # --- CALCULATE RSI ---
                df['RSI'] = calculate_rsi(df)

                # --- EXTRACT DATA ---
                latest_date = df.index[-1]
                latest = df.iloc[-1]
                prev_1 = df.iloc[-2]

                ranges = df['High'] - df['Low']
                current_range = ranges.iloc[-1]

                # --- FILTER 1: Volatility Expansion (Range > past 4 days) ---
                cond1 = (
                    current_range > ranges.iloc[-2] and
                    current_range > ranges.iloc[-3] and
                    current_range > ranges.iloc[-4] and
                    current_range > ranges.iloc[-5]
                )
                if not cond1: continue

                # --- FILTER 2: Bullish Day ---
                cond2 = latest['Close'] > latest['Open']
                if not cond2: continue

                # --- CALCULATE WEEKLY AND MONTHLY OPENS ---
                current_year = latest_date.year
                current_month = latest_date.month
                current_iso_week = latest_date.isocalendar()[1]
                current_iso_year = latest_date.isocalendar()[0]

                month_df = df[(df.index.year == current_year) & (df.index.month == current_month)]