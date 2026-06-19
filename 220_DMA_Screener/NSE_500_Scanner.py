import pandas as pd
import yfinance as yf
import numpy as np
import datetime
import requests
import io
import time
import warnings
import os
from tabulate import tabulate

# Suppress standard yfinance warnings for cleaner console output
warnings.filterwarnings('ignore')

# ==========================================
# 📱 TELEGRAM CONFIGURATION
# ==========================================
ENABLE_TELEGRAM = True  # Set to False if you want to turn off alerts
TELEGRAM_BOT_TOKEN = os.getenv("DMA_TELEGRAM_BOT_TOKEN") 
TELEGRAM_CHAT_ID = os.getenv("DMA_TELEGRAM_CHAT_ID")
# ==========================================

def get_nifty500_tickers():
    """
    Fetches the NIFTY 500 list directly from the NSE website.
    """
    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'text/csv'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        return [str(symbol) + ".NS" for symbol in df['Symbol']]
    except Exception as e:
        print(f"Warning: NSE Website blocked automated ticker download ({e}).")
        return ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", 
                "SBI.NS", "ITC.NS", "LARSEN.NS", "BAJFINANCE.NS", "BHARTIARTL.NS", "MGL.NS"]

def process_batch(batch_tickers, batch_num, start_date, end_date):
    """
    Processes a single batch of tickers looking for recent 220 DMA crossovers.
    """
    batch_results = []
    print(f"\n--- Processing Batch {batch_num} ({len(batch_tickers)} stocks) ---")
    
    for ticker in batch_tickers:
        try:
            data = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)
            
            if data.empty or len(data) < 220:
                continue
                
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [col[0] for col in data.columns]
                
            data['220_DMA'] = data['Close'].rolling(window=220).mean()
            data['20_Avg_Vol'] = data['Volume'].rolling(window=20).mean()
            
            delta = data['Close'].diff()
            gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
            loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
            rs = gain / loss
            data['RSI'] = 100 - (100 / (1 + rs))
            
            data = data.dropna(subset=['220_DMA', 'RSI', '20_Avg_Vol'])
            
            if len(data) < 3: 
                continue
                
            crossover_mask = (data['Close'].shift(1) <= data['220_DMA'].shift(1)) & \
                             (data['Close'] > data['220_DMA'])
            
            curr_close = float(data['Close'].iloc[-1])
            curr_dma = float(data['220_DMA'].iloc[-1])
            
            if crossover_mask.iloc[-3:].any() and (curr_close > curr_dma):
                recent_crossovers = data.iloc[-3:][crossover_mask.iloc[-3:]]
                date_crossed = recent_crossovers.index[-1].strftime('%Y-%m-%d')
                
                curr_volume = int(data['Volume'].iloc[-1])
                avg_volume = float(data['20_Avg_Vol'].iloc[-1])
                vol_pct = round((curr_volume / avg_volume) * 100, 1) if avg_volume > 0 else 0.0
                curr_rsi = round(float(data['RSI'].iloc[-1]), 1)
                
                batch_results.append({
                    'Stock': ticker.replace('.NS', ''),
                    'Cross Date': date_crossed,
                    'Current Price': round(curr_close, 2),
                    'Vol %': vol_pct,
                    'RSI': curr_rsi
                })
                
        except Exception:
            continue
            
    return batch_results

def send_telegram_message(df):
    """
    Formats the DataFrame as an ASCII table and sends it to Telegram.
    """
    if not ENABLE_TELEGRAM or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("-> Telegram alerts disabled or credentials missing. Skipping message.")
        return

    # Use 'simple' format for Telegram as it renders best on mobile devices
    table_string = tabulate(df, headers='keys', tablefmt='simple', showindex=True)
    message_text = f"<b>🚨 NIFTY 500: 220-DMA Crossovers (Last 3 Days)</b>\n\n<pre>{table_string}</pre>"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message_text,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        print("✅ Results successfully sent to Telegram!")
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

def main():
    tickers = get_nifty500_tickers()
    output_filename = "nifty500_batch_crossover_3day.csv"
    
    if os.path.exists(output_filename):
        os.remove(output_filename)
        
    all_results = []
    batch_size = 50
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=600) 
    
    print(f"Total Tickers Found: {len(tickers)}")
    print(f"Splitting analysis into batches of {batch_size}...")
    
    for i in range(0, len(tickers), batch_size):
        batch_num = (i // batch_size) + 1
        current_batch_tickers = tickers[i:i + batch_size]
        batch_output = process_batch(current_batch_tickers, batch_num, start_date, end_date)
        
        if batch_output:
            all_results.extend(batch_output)
            df_temp = pd.DataFrame(all_results)
            df_temp.to_csv(output_filename, index=False)
            print(f"-> Found {len(batch_output)} match(es) in Batch {batch_num}.")
        else:
            print(f"-> No matches found in Batch {batch_num}.")
            
        if i + batch_size < len(tickers):
            time.sleep(3)
            
    print("\n======================= FINAL REPORT =======================")
    if all_results:
        final_df = pd.DataFrame(all_results)
        final_df = final_df.sort_values(by='Cross Date', ascending=True)
        final_df.index = np.arange(1, len(final_df) + 1)
        final_df.index.name = 'Sr No'
        
        # Save to CSV
        final_df.to_csv(output_filename)
        
        # --- NEW: Print beautifully formatted table to the console ---
        print("\n" + tabulate(final_df, headers='keys', tablefmt='pretty', showindex=True) + "\n")
        print(f"💾 Scan Complete! Data saved to '{output_filename}'")
        
        # Trigger Telegram Alert
        send_telegram_message(final_df)
    else:
        print("Scan Complete. No stocks matched the strategy today.")
        
        # Optional: Send a message even if no stocks were found
        if ENABLE_TELEGRAM and TELEGRAM_BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
            empty_msg = "<b>📊 NIFTY 500 Scan Complete</b>\nNo stocks crossed their 220-DMA in the last 3 days."
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                          data={'chat_id': TELEGRAM_CHAT_ID, 'text': empty_msg, 'parse_mode': 'HTML'})

if __name__ == "__main__":
    main()