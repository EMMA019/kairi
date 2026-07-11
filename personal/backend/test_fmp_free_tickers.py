import os
import requests
import concurrent.futures
import time

API_KEY = "DXqDuqu11pZKbbNzSOL5DozvUzqn7WSn"
TICKERS_FILE = r"D:\program\chat\personal\backend\data\rakuten_tickers.txt"

def test_ticker(ticker):
    url = f"https://financialmodelingprep.com/stable/historical-price-eod/full?symbol={ticker}&apikey={API_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return ticker, "200 OK (Allowed)"
        elif resp.status_code == 402:
            return ticker, "402 (Payment Required)"
        else:
            return ticker, f"{resp.status_code} Error"
    except Exception as e:
        return ticker, f"Failed: {str(e)}"

def main():
    if not os.path.exists(TICKERS_FILE):
        print("File not found")
        return
        
    with open(TICKERS_FILE, "r", encoding="utf-8") as f:
        tickers = [line.strip() for line in f if line.strip()]
        
    print(f"Loaded {len(tickers)} tickers. Testing a sample of 100 tickers...")
    import random
    random.seed(42)
    sample = random.sample(tickers, min(100, len(tickers)))
    
    results_map = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(test_ticker, sample)
        for ticker, status in results:
            if status not in results_map:
                results_map[status] = []
            results_map[status].append(ticker)
            time.sleep(0.05) # Rate limit protection
            
    print(f"\n--- Test Results (Sample size: {len(sample)}) ---")
    for status, t_list in results_map.items():
        print(f"\n[{status}]: {len(t_list)} tickers")
        print(f"Examples: {t_list[:10]}")

if __name__ == "__main__":
    main()
