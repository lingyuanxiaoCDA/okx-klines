#!/usr/bin/env python3
"""
OKX K-line data fetcher - GitHub Actions version
Uses Binance API (accessible globally) to fetch historical K-line data,
then converts to OKX format for compatibility.
"""

import json
import time
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Binance Futures API (accessible from GitHub Actions, no API key needed for klines)
BINANCE_API = "https://fapi.binance.com/fapi/v1/klines"

# Symbol mapping: OKX -> Binance
SYMBOL_MAP = {
    "BTC-USDT-SWAP": "BTCUSDT",
    "ETH-USDT-SWAP": "ETHUSDT",
    "SOL-USDT-SWAP": "SOLUSDT",
    "DOGE-USDT-SWAP": "DOGEUSDT",
    "LINK-USDT-SWAP": "LINKUSDT",
}

# Period mapping: (Binance interval, OKX symbol, file tag, max candles)
PERIODS = [
    ("1m",   "1m",    "1m",    60000),   # ~41.7 days
    ("5m",   "5m",    "5m",    60000),   # ~208 days
    ("15m",  "15m",   "15m",   30000),   # ~312 days
    ("30m",  "30m",   "30m",   30000),   # ~625 days
    ("1h",   "1H",    "1H",    30000),   # ~1250 days
    ("4h",   "4H",    "4H",    10000),   # ~1666 days
    ("1d",   "1D",    "1D",    3000),    # ~8.2 years
]

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def fetch_binance_klines(symbol: str, interval: str, start_time: int, end_time: int, limit: int = 1500) -> list:
    """Fetch klines from Binance Futures API. Returns list of raw kline arrays.
    
    Binance kline format: [openTime, open, high, low, close, volume, closeTime, 
                           quoteAssetVolume, numberOfTrades, takerBuyBaseVolume, 
                           takerBuyQuoteVolume, ignore]
    """
    url = f"{BINANCE_API}?symbol={symbol}&interval={interval}&startTime={start_time}&endTime={end_time}&limit={limit}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data


def fetch_all_klines(binance_symbol: str, interval: str, max_count: int) -> list:
    """Fetch large amounts of historical klines from Binance using pagination."""
    all_klines = []
    
    # Binance max 1500 per request for futures
    batch_size = 1500
    
    # Calculate interval in milliseconds
    interval_ms = {
        "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
        "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
    }[interval]
    
    # Start from the most recent and go backwards
    end_time = int(time.time() * 1000)
    
    while len(all_klines) < max_count:
        # Calculate start time: go back batch_size * interval_ms
        start_time = end_time - (batch_size * interval_ms)
        
        try:
            batch = fetch_binance_klines(binance_symbol, interval, start_time, end_time, batch_size)
        except Exception as e:
            print(f"  Warning: {e}, retrying in 3s...")
            time.sleep(3)
            # Retry once
            try:
                batch = fetch_binance_klines(binance_symbol, interval, start_time, end_time, batch_size)
            except Exception as e2:
                print(f"  Error: {e2}, stopping")
                break
        
        if not batch:
            print(f"  No more data (got {len(all_klines)} klines)")
            break
        
        # Binance returns ascending order (oldest first)
        # Prepend to all_klines
        all_klines = batch + all_klines
        
        # Deduplicate by openTime
        seen = set()
        unique = []
        for k in all_klines:
            if k[0] not in seen:
                seen.add(k[0])
                unique.append(k)
        all_klines = unique
        
        # Move end_time to before the oldest kline in this batch
        oldest_ts = batch[0][0]
        end_time = oldest_ts - 1
        
        if len(batch) < batch_size:
            # Less than full batch means no more historical data
            print(f"  Partial batch ({len(batch)} < {batch_size}), no more data")
            break
        
        print(f"  Progress: {len(all_klines)}/{max_count} klines ({binance_symbol} {interval})")
        time.sleep(0.2)  # Rate limit
    
    # Sort ascending and trim
    all_klines.sort(key=lambda x: x[0])
    return all_klines[:max_count]


def save_klines(okx_symbol: str, period_tag: str, klines: list):
    """Save kline data as JSON file in OKX-like format."""
    coin = okx_symbol.split("-")[0].lower()
    filename = f"data_{coin}_{period_tag}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    # Convert Binance format to OKX-like format
    formatted = []
    for k in klines:
        formatted.append({
            "ts": int(k[0]),
            "time": datetime.fromtimestamp(int(k[0]) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "vol": float(k[5]),
            "volCcy": float(k[7]),  # quote volume
            "confirm": "1",
        })
    
    output = {
        "symbol": okx_symbol,
        "source": "binance_futures",
        "period": period_tag,
        "count": len(formatted),
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "data": formatted,
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))
    
    return filename, len(formatted)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    results = []
    for okx_symbol, binance_symbol in SYMBOL_MAP.items():
        for interval, okx_bar, tag, max_count in PERIODS:
            print(f"\nFetching {okx_symbol} ({binance_symbol}) {tag} (target: {max_count} klines)...")
            try:
                klines = fetch_all_klines(binance_symbol, interval, max_count)
                if klines:
                    filename, count = save_klines(okx_symbol, tag, klines)
                    print(f"  OK: {filename}: {count} klines")
                    results.append((filename, count, "OK"))
                else:
                    print(f"  FAIL: no data")
                    results.append((f"data_{okx_symbol.split('-')[0].lower()}_{tag}.json", 0, "NO_DATA"))
            except Exception as e:
                print(f"  ERROR: {e}")
                results.append((f"data_{okx_symbol.split('-')[0].lower()}_{tag}.json", 0, f"ERROR: {e}"))
    
    # Print summary
    print("\n" + "=" * 60)
    print("Data Fetch Summary")
    print("=" * 60)
    total_ok = 0
    total_klines = 0
    for filename, count, status in results:
        icon = "OK" if status == "OK" else "FAIL"
        print(f"  [{icon}] {filename}: {count} klines [{status}]")
        if status == "OK":
            total_ok += 1
            total_klines += count
    print(f"\nTotal: {total_ok}/{len(results)} files, {total_klines} klines")
    
    if total_ok == 0:
        exit(1)


if __name__ == "__main__":
    main()
