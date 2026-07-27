#!/usr/bin/env python3
"""
OKX K-line data fetcher - GitHub Actions version
Uses Bybit v5 API (accessible globally, no API key needed for klines) to fetch
historical K-line data, then saves in OKX-compatible format.
"""

import json
import time
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Bybit v5 API (accessible from GitHub Actions, no API key for public endpoints)
BYBIT_API = "https://api.bybit.com/v5/market/kline"

# Symbol mapping: OKX -> Bybit
SYMBOL_MAP = {
    "BTC-USDT-SWAP": "BTCUSDT",
    "ETH-USDT-SWAP": "ETHUSDT",
    "SOL-USDT-SWAP": "SOLUSDT",
    "DOGE-USDT-SWAP": "DOGEUSDT",
    "LINK-USDT-SWAP": "LINKUSDT",
}

# Period mapping: (Bybit interval, file tag, max candles)
# Bybit intervals: 1,3,5,15,30,60,120,240,360,720,D,W,M
PERIODS = [
    ("1",   "1m",    60000),   # ~41.7 days
    ("5",   "5m",    60000),   # ~208 days
    ("15",  "15m",   30000),   # ~312 days
    ("30",  "30m",   30000),   # ~625 days
    ("60",  "1H",    30000),   # ~1250 days
    ("240", "4H",    10000),   # ~1666 days
    ("D",   "1D",    3000),    # ~8.2 years
]

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def fetch_bybit_klines(symbol: str, interval: str, start_ts: int, category: str = "linear") -> list:
    """Fetch klines from Bybit v5 API. Returns list of [ts, open, high, low, close, vol, ...].
    
    Bybit kline format: [start_time(ms), open, high, low, close, volume, turnover]
    Returns up to 1000 klines per request.
    """
    url = f"{BYBIT_API}?category={category}&symbol={symbol}&interval={interval}&start={start_ts}&limit=1000"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    
    if data.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {data.get('retMsg', 'unknown')}")
    
    result = data.get("result", {})
    return result.get("list", [])


def fetch_all_klines(bybit_symbol: str, interval: str, max_count: int) -> list:
    """Fetch large amounts of historical klines from Bybit using pagination."""
    all_klines = []
    batch_size = 1000  # Bybit max 1000 per request
    
    # Calculate interval in milliseconds
    interval_ms = {
        "1": 60_000, "5": 300_000, "15": 900_000, "30": 1_800_000,
        "60": 3_600_000, "240": 14_400_000, "D": 86_400_000,
    }[interval]
    
    # Start from far enough back to get max_count klines
    now_ms = int(time.time() * 1000)
    start_ts = now_ms - (max_count * interval_ms)
    
    while len(all_klines) < max_count:
        try:
            batch = fetch_bybit_klines(bybit_symbol, interval, start_ts)
        except Exception as e:
            print(f"  Warning: {e}, retrying in 3s...")
            time.sleep(3)
            try:
                batch = fetch_bybit_klines(bybit_symbol, interval, start_ts)
            except Exception as e2:
                print(f"  Error: {e2}, stopping")
                break
        
        if not batch:
            print(f"  No more data (got {len(all_klines)} klines)")
            break
        
        # Bybit returns descending order (newest first), prepend batch
        # Deduplicate by timestamp
        seen = {k[0] for k in all_klines}
        new_klines = [k for k in batch if k[0] not in seen]
        
        if not new_klines:
            print(f"  No new data, stopping")
            break
        
        all_klines.extend(new_klines)
        
        # Get the newest timestamp from this batch to advance start_ts
        # Bybit returns newest first, so batch[0] is newest
        newest_ts = int(batch[0][0])
        start_ts = newest_ts + interval_ms  # Move past the newest kline
        
        if len(batch) < batch_size:
            print(f"  Partial batch ({len(batch)} < {batch_size})")
            # Don't break - Bybit may return less than 1000 for older data
        
        print(f"  Progress: {len(all_klines)}/{max_count} klines ({bybit_symbol} {interval})")
        time.sleep(0.2)  # Rate limit
    
    # Sort ascending by timestamp and trim
    all_klines.sort(key=lambda x: int(x[0]))
    return all_klines[:max_count]


def save_klines(okx_symbol: str, period_tag: str, klines: list):
    """Save kline data as JSON file in OKX-like format."""
    coin = okx_symbol.split("-")[0].lower()
    filename = f"data_{coin}_{period_tag}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    # Convert Bybit format to OKX-like format
    # Bybit: [startTime, open, high, low, close, volume, turnover]
    formatted = []
    for k in klines:
        ts = int(k[0])
        formatted.append({
            "ts": ts,
            "time": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "vol": float(k[5]),
            "volCcy": float(k[6]) if len(k) > 6 else 0.0,
            "confirm": "1",
        })
    
    output = {
        "symbol": okx_symbol,
        "source": "bybit_v5",
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
    for okx_symbol, bybit_symbol in SYMBOL_MAP.items():
        for interval, tag, max_count in PERIODS:
            print(f"\nFetching {okx_symbol} ({bybit_symbol}) {tag} (target: {max_count} klines)...")
            try:
                klines = fetch_all_klines(bybit_symbol, interval, max_count)
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
