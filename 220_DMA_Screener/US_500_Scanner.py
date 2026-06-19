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
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") 
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# ==========================================

def get_sp500_tickers():
    """
    Fetches the current S&P 500 list from Wikipedia.
    Cleans up tickers for Yahoo Finance compatibility (e.g., BRK.B -> BRK-B).
    """
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Read the first table on the Wikipedia page
        tables = pd.read_html(io.StringIO(response.text))
        df = tables[0]
        
        # Extract symbols and fix dot notation for Yahoo Finance
        tickers = df['Symbol'].str.replace('.', '-', regex=False).tolist()
        return tickers
        
    except Exception as e:
        print(f"Warning: Could not fetch S&P 500 list from Wikipedia ({e}).")
        print("Falling back to a standard mega-cap sample list.")
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "BRK-B", "JPM", "V"]

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
                    'Stock': ticker,  # No .NS to remove here!
                    'Cross Date': date_crossed,
                    'Price ($)': round(curr_close, 2), # Updated to USD
                    'Vol %': vol_pct,
                    'RSI': curr_rsi
                })
                
        except Exception:
            continue
            
    return batch_results

def old_send_telegram_message(df):
    """
    Formats the DataFrame as an ASCII table and sends it to Telegram.
    """
    if not ENABLE_TELEGRAM or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("-> Telegram alerts disabled or credentials missing. Skipping message.")
        return

    # Use 'simple' format for Telegram as it renders best on mobile devices
    table_string = tabulate(df, headers='keys', tablefmt='simple', showindex=False)
    message_text = f"<b>🚨 S&P 500: 220-DMA Crossovers (Last 3 Days)</b>\n\n<pre>{table_string}</pre>"
    
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
        

def send_telegram_message(df):
    """
    Formats the DataFrame as an ASCII table with strict word-wrapping for Telegram.
    """
    if not ENABLE_TELEGRAM or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("-> Telegram alerts disabled or credentials missing. Skipping message.")
        return

    # --- 1. Create a mobile-friendly copy of the DataFrame ---
    mobile_df = df.copy()
    
    # Compress the Date (Drop the Year: "2026-06-18" -> "06-18")
    mobile_df['Cross Date'] = pd.to_datetime(mobile_df['Cross Date']).dt.strftime('%m-%d')
    
    # Rename columns to be as short as possible to save horizontal space
    mobile_df.rename(columns={
        'Stock': 'Stock',
        'Cross Date': 'Date', 
        'Price': 'Price',
        'Vol %': 'Vol%',
        'RSI': 'RSI'
    }, inplace=True)

    # --- 2. Apply Strict Word Wrapping ---
    # maxcolwidths forces long text to wrap to the next line instead of pushing columns off-screen.
    # We restrict the 'Stock' column to a maximum of 10 characters before it wraps.
    table_string = tabulate(
        mobile_df, 
        headers='keys', 
        tablefmt='simple', 
        showindex=False,
        disable_numparse=True,
        maxcolwidths=[10, 5, 7, 5, 4] # Maximum characters allowed per column
    )
    
    message_text = f"<b>🚨 S&P 500: 220-DMA Crossovers (Last 3 Days)</b>\n\n<pre>{table_string}</pre>"
    
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
    tickers = get_sp500_tickers()
    output_filename = "sp500_batch_crossover_3day.csv"
    
    if os.path.exists(output_filename):
        os.remove(output_filename)
        
    all_results = []
    batch_size = 50
    # Define the IST timezone (UTC + 5 hours and 30 minutes)
    ist_timezone = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

    # Get today's date in exactly IST, then add 1 day
    end_date = datetime.datetime.now(ist_timezone).date() + datetime.timedelta(days=1)
    #end_date = datetime.date.today()
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
            
        # Optional: Short cooldown to avoid rate limits
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
        
        # Print beautifully formatted table to the console
        print("\n" + tabulate(final_df, headers='keys', tablefmt='pretty', showindex=True) + "\n")
        print(f"💾 Scan Complete! Data saved to '{output_filename}'")
        
        # Trigger Telegram Alert
        send_telegram_message(final_df)
    else:
        print("Scan Complete. No stocks matched the strategy today.")
        
        # Optional: Send a message even if no stocks were found
        if ENABLE_TELEGRAM and TELEGRAM_BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
            empty_msg = "<b>📊 S&P 500 Scan Complete</b>\nNo stocks crossed their 220-DMA in the last 3 days."
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                          data={'chat_id': TELEGRAM_CHAT_ID, 'text': empty_msg, 'parse_mode': 'HTML'})

if __name__ == "__main__":
    main()