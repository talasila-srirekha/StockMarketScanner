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
                if month_df.empty: continue
                monthly_open = month_df.iloc[0]['Open']

                week_df = df[(df.index.isocalendar().year == current_iso_year) & (df.index.isocalendar().week == current_iso_week)]
                if week_df.empty: continue
                weekly_open = week_df.iloc[0]['Open']

                # --- FILTER 3 & 4: Bullish Week & Month ---
                cond3 = latest['Close'] > weekly_open
                cond4 = latest['Close'] > monthly_open
                if not (cond3 and cond4): continue

                # --- FILTER 5: Minimum Liquidity (Adjusted to ₹5 Crore for Nifty 500) ---
                turnover_inr = latest['Volume'] * latest['Close']
                cond5 = turnover_inr >= 50000000
                if not cond5: continue

                # --- FILTER 6: Strong Support Hold ---
                threshold = prev_1['Close'] - abs(prev_1['Close'] / 222)
                cond6 = latest['Low'] > threshold
                if not cond6: continue

                # --- FILTER 7: Momentum (RSI > 40) ---
                cond7 = latest['RSI'] > 40
                if not cond7: continue

                # ==========================================
                # 📈 TRADE MANAGEMENT & PATTERN ANALYSIS
                # ==========================================

                # Volume Analysis (vs 10-Day Average)
                avg_vol_10d = df['Volume'].iloc[-10:].mean()
                vol_change_pct = ((latest['Volume'] / avg_vol_10d) - 1) * 100

                # Entry, Stop Loss, and Target (1:2 Risk/Reward)
                entry_price = latest['Close']

                # Stop loss placed slightly below today's low to avoid wicks
                stop_loss = latest['Low'] * 0.998

                # Calculate risk. Fallback to 1% risk if Low == Close (very rare)
                risk_amount = max(entry_price - stop_loss, entry_price * 0.01)

                # Project Target at 2x Risk
                target_price = entry_price + (risk_amount * 2)

                # Format Data for Output (Stripping .NS for cleaner visual lists)
                clean_ticker = ticker.replace('.NS', '')

                matched_stocks.append({
                    'Ticker': clean_ticker,
                    'Pattern': 'Range Breakout',
                    'RSI': round(latest['RSI'], 2),
                    'Entry (₹)': round(entry_price, 2),
                    'Stop Loss (₹)': round(stop_loss, 2),
                    'Target (₹)': round(target_price, 2),
                    'Cur Vol (M)': round(latest['Volume'] / 1000000, 2),
                    'Vol Chg 10d (%)': f"{round(vol_change_pct, 1)}%"
                })

            # ---> THIS IS THE MISSING BLOCK THAT CAUSED YOUR ERROR <---
            except Exception:
                continue

        time.sleep(1)

    # --- FINAL REPORT GENERATION ---
    runtime = round((time.time() - start_time), 1)

    print(" " * 60, end="\r") # Clear loading line
    print("\n" + "="*85)
    print(f"🏁 SCAN COMPLETE — Processed in {runtime} seconds.")
    print("="*85)

    if matched_stocks:
        results = pd.DataFrame(matched_stocks)
        # Sort by the most massive volume surges
        results['Sort_Vol'] = results['Vol Chg 10d (%)'].str.replace('%', '').astype(float)
        results = results.sort_values(by="Sort_Vol", ascending=False).drop('Sort_Vol', axis=1)

        print("\n🔥 NIFTY 500 TRADE ANALYSIS & MOMENTUM ALERTS: 🔥\n")
        # Format pandas to print nicely in terminal
        print(results.to_string(index=False, justify='center'))

        # --- TELEGRAM FORMATTING ---
        telegram_message = "🔥 <b>NIFTY 500 Momentum Alerts</b> 🔥\n\n"

        for _, row in results.iterrows():
            telegram_message += (
                f"🟢 <b>{row['Ticker']}</b> ({row['Pattern']})\n"
                f"RSI: {row['RSI']}\n"
                f"Entry: ₹{row['Entry (₹)']}\n"
                f"SL: ₹{row['Stop Loss (₹)']}\n"
                f"Target: ₹{row['Target (₹)']}\n"
                f"Cur Vol: {row['Cur Vol (M)']}M\n"
                f"Vol Surge: {row['Vol Chg 10d (%)']}\n\n"
            )

        BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

        if BOT_TOKEN and CHAT_ID:
            send_telegram_message(telegram_message, BOT_TOKEN, CHAT_ID)
        else:
            print("\n⚠️ Note: Telegram credentials not found in environment variables. Message not sent.")

    else:
        telegram_message = "🔥 <b>NIFTY 500 Momentum Alerts</b> 🔥\n\n"
        telegram_message += "Market Setup Alert: No Indian stocks matched this specific setup today."

        BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

        if BOT_TOKEN and CHAT_ID:
            send_telegram_message(telegram_message, BOT_TOKEN, CHAT_ID)

        print("\n😴 Market Setup Alert: No Indian stocks matched this specific setup today.")
    print("="*85)

def send_telegram_message(message, bot_token, chat_id):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        print(f"Error sending to telegram: {e}")

if __name__ == "__main__":
    run_volatility_analysis()