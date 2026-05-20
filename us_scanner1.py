import yfinance as yf
import pandas as pd
import requests
import warnings
import time
import logging
from io import StringIO

# --- CLEAN TERMINAL SETTINGS ---
warnings.filterwarnings('ignore')
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# --- CONFIGURATION ---
BATCH_SIZE = 50

def get_sp500_tickers():
    """Dynamically fetches the live S&P 500 ticker list bypassing Wikipedia's bot blockers"""
    print("📥 Fetching the live S&P 500 ticker list...")
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        tables = pd.read_html(StringIO(response.text))
        for table in tables:
            if 'Symbol' in table.columns:
                tickers = [str(sym).replace('.', '-') for sym in table['Symbol'].tolist()]
                print(f"✅ Successfully loaded {len(tickers)} S&P 500 stocks.")
                return tickers
    except Exception as e:
        print(f"❌ Failed to fetch S&P 500 list: {e}")
        return []

def run_volatility_analysis():
    all_tickers = get_sp500_tickers()

    if not all_tickers:
        print("Aborting scan. Ticker list is empty.")
        return

    matched_stocks = []
    total_stocks = len(all_tickers)
    total_steps = (total_stocks + BATCH_SIZE - 1) // BATCH_SIZE

    print(f"\n⚡ Processing {total_stocks} S&P 500 stocks for Range Expansion & Trade Analysis...")
    print("⚠️ Note: Scanning will take about 1 to 2 minutes. Please wait...\n")

    start_time = time.time()

    for i in range(0, total_stocks, BATCH_SIZE):
        batch = all_tickers[i:i+BATCH_SIZE]
        current_step = (i // BATCH_SIZE) + 1

        print(f"🔄 Running Step {current_step}/{total_steps}...", end="\r")

        try:
            # 3mo period ensures enough data for weekly/monthly calculations + 10d volume average
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

                # --- FILTER 5: Minimum Liquidity ($10M Dollar Volume) ---
                dollar_volume = latest['Volume'] * latest['Close']
                cond5 = dollar_volume >= 10000000
                if not cond5: continue

                # --- FILTER 6: Strong Support Hold ---
                threshold = prev_1['Close'] - abs(prev_1['Close'] / 222)
                cond6 = latest['Low'] > threshold
                if not cond6: continue

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

                # Format Data for Output
                matched_stocks.append({
                    'Ticker': ticker,
                    'Pattern': 'Range Breakout',
                    'Entry ($)': round(entry_price, 2),
                    'Stop Loss ($)': round(stop_loss, 2),
                    'Target ($)': round(target_price, 2),
                    'Cur Vol (M)': round(latest['Volume'] / 1000000, 2),
                    'Vol Chg 10d (%)': f"{round(vol_change_pct, 1)}%"
                })

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
        # First strip the '%' and convert to float for proper sorting
        results['Sort_Vol'] = results['Vol Chg 10d (%)'].str.replace('%', '').astype(float)
        results = results.sort_values(by="Sort_Vol", ascending=False).drop('Sort_Vol', axis=1)

        print("\n🔥 S&P 500 TRADE ANALYSIS & MOMENTUM ALERTS: 🔥\n")
        # Format pandas to print nicely
        print(results.to_string(index=False, justify='center'))
    else:
        print("\n😴 Market Setup Alert: No S&P 500 stocks matched this specific setup today.")
    print("="*85)

if __name__ == "__main__":
    run_volatility_analysis()