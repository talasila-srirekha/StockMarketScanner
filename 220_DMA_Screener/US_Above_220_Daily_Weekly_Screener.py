
import yfinance as yf
import pandas as pd
import numpy as np
import time
import datetime
import requests
import os

# ==========================================
# 📱 TELEGRAM CONFIGURATION
# ==========================================
ENABLE_TELEGRAM = True  # Set to False if you want to turn off alerts
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") 
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# ==========================================

def send_telegram_message(message, token, chat_id):
    """Sends a message to a specific Telegram chat."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=payload)
        print("\nSuccessfully sent results to Telegram.")
    except Exception as e:
        print(f"Failed to send to Telegram: {e}")

def get_sp500_tickers():
    """Fetches the latest S&P 500 list from Wikipedia."""
    print("Fetching S&P 500 ticker list...")
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        tables = pd.read_html(url, storage_options={'User-Agent': headers['User-Agent']})
        df = tables[0]
        # yfinance uses '-' instead of '.' for share classes, e.g. BRK.B -> BRK-B
        tickers = [str(s).replace('.', '-') for s in df['Symbol'].tolist()]
        return tickers
    except Exception as e:
        print(f"Could not download ticker list: {e}")
        # Fallback list just in case Wikipedia is unreachable
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
                "JPM", "V", "UNH"]

def scan_dual_timeframe(tickers, batch_size=50):
    signals = []

    # Need at least 6 years of data to calculate a 220 WEEKLY moving average
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=6*365)

    total_batches = (len(tickers) + batch_size - 1) // batch_size

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        print(f"Scanning Batch {(i // batch_size) + 1}/{total_batches} ({len(batch)} stocks)...")

        data = yf.download(batch, start=start_date, end=end_date, group_by='ticker', progress=False, auto_adjust=False)

        #print (data)

        if data.empty:
            continue

        for ticker in batch:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    if ticker not in data.columns.levels[0]:
                        continue
                    df_daily = data[ticker].copy()
                else:
                    df_daily = data.copy()

                df_daily.dropna(subset=['Close'], inplace=True)

                if len(df_daily) < 1100:
                    continue

                # ---------- DAILY ----------
                df_daily['220_DMA'] = df_daily['Close'].rolling(window=220).mean()
                latest_daily_close = float(df_daily['Close'].iloc[-1])
                latest_220_dma = float(df_daily['220_DMA'].iloc[-1])

                # ---------- WEEKLY ----------
                df_weekly = df_daily['Close'].resample('W-FRI').last().to_frame()
                df_weekly.dropna(inplace=True)
                df_weekly['220_WMA'] = df_weekly['Close'].rolling(window=220).mean()

                latest_220_wma = float(df_weekly['220_WMA'].iloc[-1])

                if np.isnan(latest_220_wma) or np.isnan(latest_220_dma):
                    continue

                # ---------- STATUS ----------
                closed_above_daily = latest_daily_close > latest_220_dma
                closed_above_weekly = latest_daily_close > latest_220_wma

                pct_from_dma = ((latest_daily_close - latest_220_dma) / latest_220_dma) * 100
                pct_from_wma = ((latest_daily_close - latest_220_wma) / latest_220_wma) * 100

                signals.append({
                    'Ticker': ticker,
                    'Current Price': round(latest_daily_close, 2),
                    '220 DMA': round(latest_220_dma, 2),
                    '220 WMA': round(latest_220_wma, 2),
                    'Above Daily DMA?': "Yes" if closed_above_daily else "No",
                    'Above Weekly WMA?': "Yes" if closed_above_weekly else "No",
                    '% From DMA': round(pct_from_dma, 2),
                    '% From WMA': round(pct_from_wma, 2)
                })

            except Exception:
                continue

        time.sleep(1)

    return pd.DataFrame(signals)

if __name__ == "__main__":
    print("--- High Probability Dual-Timeframe Scanner (S&P 500) ---")

    tickers_to_scan = get_sp500_tickers()

    if tickers_to_scan:
        print(f"\nSuccessfully loaded {len(tickers_to_scan)} tickers. Beginning scan...\n")
        results = scan_dual_timeframe(tickers=tickers_to_scan, batch_size=50)

        if not results.empty:
            min_dist = 1.0
            max_dist = 7.0

            # Both % From DMA and % From WMA must independently sit in the
            # 1-7% band - this is what prevents stocks that are way above
            # one MA (e.g. 28%) but only barely above the other from slipping in.
            holy_grail_setups = results[
                (results['Above Daily DMA?'] == 'Yes') &
                (results['Above Weekly WMA?'] == 'Yes') &
                (results['% From DMA'] >= min_dist) &
                (results['% From DMA'] <= max_dist) &
                (results['% From WMA'] >= min_dist) &
                (results['% From WMA'] <= max_dist)
            ]

            print("\n" + "=" * 95)
            print(f"💡 Found {len(holy_grail_setups)} stocks matching EXACT criteria:")
            print(f"   - Closed Above 220 Daily DMA (by {min_dist}%-{max_dist}%)")
            print(f"   - Closed Above 220 Weekly WMA (by {min_dist}%-{max_dist}%)")
            print("=" * 95)

            telegram_msg = "<b>🚀 S&P 500 - Cross Over 220 DMA & WMA Setup:</b>\n\n"

            if not holy_grail_setups.empty:
                holy_grail_setups = holy_grail_setups.sort_values(by='% From WMA')
                print(holy_grail_setups[['Ticker', 'Current Price', '220 DMA', '220 WMA', '% From DMA', '% From WMA']].to_string(index=False))
                telegram_msg += "<pre>" + holy_grail_setups[['Ticker', 'Current Price', '% From DMA', '% From WMA']].to_string(index=False) + "</pre>"
            else:
                print("No stocks match these strict criteria right now.")
                telegram_msg += "<pre> No stocks match these strict criteria right now.</pre>"
                
            send_telegram_message(telegram_msg, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        else:
            print("\nNo valid data found. Check your internet connection or stock tickers.")