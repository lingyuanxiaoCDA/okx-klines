#!/usr/bin/env python3
"""
OKX K-line data fetcher - GitHub Actions version
Uses OKX /market/candles endpoint with proper before pagination.
"""

import json
import time
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

# OKX candles API - supports before/after pagination
OKX_API = "https://www.okx.com/api/v5/market/candles"

# Symbol list
SYMBOLS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "DOGE-USDT-SWAP", "LINK-USDT-SWAP"]

# Period mapping: (OKX bar param, file tag, max candles, interval_ms)
PERIODS = [
    ("1m",  "1m",  60000, 60_000),
    ("5m",  "5m",  60000, 300_000),
    ("15m", "15m", 30000, 900_000),
    ("30m", "30m", 30000, 1_800_000),
    ("1H",  "1H",  30000, 3_600_000),
    ("4H",  "4H",  10000, 14_400_000),
    ("1D",  "1D",  3000,  86_400_000),
]

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def fetch_page(symbol: str, bar: str, before: str = None) -> list:
    """Fetch a page of candles from OKX /market/candles.
    
    The 'before' parameter: pagination of records to return records earlier than 
    the requested ts (i.e., older records). Pass the oldest ts from previous batch.
    
    OKX /market/candles returns up to 300 candles, newest first.
    """
    url = f"{OKX_API}?instId={symbol}&bar={bar}&limit=300"
    if before:
        url += f"&before={before}"
    
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    })
    
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    
    if data.get("code") != "0":
        raise RuntimeError(f"OKX API error: {data.get('msg', 'unknown')}")
    
    return data.get("data", [])


def fetch_all_candles(symbol: str, bar: str, max_count: int, interval_ms: int) -> list:
    """Fetch historical candles using before pagination.
    
    OKX /market/candles returns newest first (descending ts).
    Use 'before' = oldest ts from previous batch to get older data.
    """
    all_candles = []
    seen_ts = set()
    
    # First request: latest candles
    batch = fetch_page(symbol, bar)
    if not batch:
        print(f"  No data returned")
        return []
    
    for c in batch:
        ts = c[0]
        if ts not in seen_ts:
            seen_ts.add(ts)
            all_candles.append(c)
    
    print(f"  Initial: {len(all_candles)} candles (ts range: {batch[-1][0]} ~ {batch[0][0]})")
    
    # Paginate backwards
    empty_count = 0
    while len(all_candles) < max_count and empty_count < 3:
        # Use the OLDEST timestamp from all collected as 'before'
        oldest_ts = str(min(int(c[0]) for c in all_candles))
        
        try:
            batch = fetch_page(symbol, bar, before=oldest_ts)
        except Exception as e:
            print(f"  Warning: {e}, retry in 3s...")
            time.sleep(3)
            empty_count += 1
            continue
        
        if not batch:
            print(f"  Empty batch, no more data ({len(all_candles)} total)")
            break
        
        # Count new candles
        new_count = 0
        oldest_in_batch = batch[-1][0]
        newest_in_batch = batch[0][0]
        
        for c in batch:
            ts = c[0]
            if ts not in seen_ts:
                seen_ts.add(ts)
                all_candles.append(c)
                new_count += 1
        
        if new_count == 0:
            print(f"  All duplicates (batch ts: {oldest_in_batch} ~ {newest_in_batch}), trying older...")
            empty_count += 1
            # Try going further back by subtracting interval
            oldest_ts = str(int(oldest_ts) - interval_ms * 300)
            try:
                batch = fetch_page(symbol, bar, before=oldest_ts)
                new_count = 0
                for c in batch:
                    ts = c[0]
                    if ts not in seen_ts:
                        seen_ts.add(ts)
                        all_candles.append(c)
                        new_count += 1
                if new_count == 0:
                    print(f"  Still duplicates, giving up")
                    break
                print(f"  Recovered: +{new_count} candles")
                empty_count = 0
            except Exception as e:
                print(f"  Fallback failed: {e}")
                break
        else:
            empty_count = 0
        
        if len(all_candles) % 3000 < 300:
            print(f"  Progress: {len(all_candles)}/{max_count}")
        
        time.sleep(0.15)
    
    # Sort ascending
    all_candles.sort(key=lambda x: int(x[0]))
    return all_candles[:max_count]


def save_candles(symbol: str, period_tag: str, candles: list):
    """Save K-line data as JSON file."""
    coin = symbol.split("-")[0].lower()
    filename = f"data_{coin}_{period_tag}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    formatted = []
    for c in candles:
        ts = int(c[0])
        formatted.append({
            "ts": ts,
            "time": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "vol": float(c[5]),
            "volCcy": float(c[6]),
            "confirm": c[8] if len(c) > 8 else "1",
        })
    
    output = {
        "symbol": symbol,
        "source": "okx_market_candles",
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
    for symbol in SYMBOLS:
        for bar, tag, max_count, interval_ms in PERIODS:
            print(f"\nFetching {symbol} {tag} (target: {max_count})...")
            try:
                candles = fetch_all_candles(symbol, bar, max_count, interval_ms)
                if candles:
                    filename, count = save_candles(symbol, tag, candles)
                    print(f"  OK: {filename}: {count} candles")
                    results.append((filename, count, "OK"))
                else:
                    print(f"  FAIL: no data")
                    results.append((f"data_{symbol.split('-')[0].lower()}_{tag}.json", 0, "NO_DATA"))
            except Exception as e:
                print(f"  ERROR: {e}")
                results.append((f"data_{symbol.split('-')[0].lower()}_{tag}.json", 0, f"ERROR: {e}"))
    
    print("\n" + "=" * 60)
    print("Data Fetch Summary")
    print("=" * 60)
    total_ok = 0
    total_candles = 0
    for filename, count, status in results:
        icon = "OK" if status == "OK" else "FAIL"
        print(f"  [{icon}] {filename}: {count} [{status}]")
        if status == "OK":
            total_ok += 1
            total_candles += count
    print(f"\nTotal: {total_ok}/{len(results)} files, {total_candles} candles")


if __name__ == "__main__":
    main()
