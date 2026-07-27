#!/usr/bin/env python3
"""
OKX K-line data fetcher - GitHub Actions version
Fetches multi-symbol multi-period K-line data from OKX public API, saves as JSON.
"""

import json
import time
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

# OKX public API
OKX_API = "https://www.okx.com/api/v5/market/candles"

# Symbol list
SYMBOLS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "DOGE-USDT-SWAP", "LINK-USDT-SWAP"]

# Period mapping: (OKX bar param, file tag, max candles)
PERIODS = [
    ("1m",    "1m",    60000),   # ~41.7 days
    ("5m",    "5m",    60000),   # ~208 days
    ("15m",   "15m",   30000),   # ~312 days
    ("30m",   "30m",   30000),   # ~625 days
    ("1H",    "1H",    30000),   # ~1250 days
    ("4H",    "4H",    10000),   # ~1666 days
    ("1D",    "1D",    3000),    # ~8.2 years
]

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def fetch_candles(symbol: str, bar: str, limit: int = 300) -> list:
    """Fetch a single batch of K-line data from OKX (max 300 candles)."""
    url = f"{OKX_API}?instId={symbol}&bar={bar}&limit={limit}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != "0":
        raise RuntimeError(f"OKX API error: {data.get('msg', 'unknown')}")
    return data.get("data", [])


def fetch_all_candles(symbol: str, bar: str, max_count: int) -> list:
    """Paginate to fetch large amounts of K-line data."""
    all_candles = []
    seen_ts = set()

    # First request (from latest going backwards)
    batch = fetch_candles(symbol, bar, 300)
    if not batch:
        return []

    for candle in batch:
        ts = candle[0]
        if ts not in seen_ts:
            seen_ts.add(ts)
            all_candles.append(candle)

    # Use oldest K-line timestamp as 'before' parameter to continue backwards
    while len(all_candles) < max_count:
        oldest_ts = min(c[0] for c in batch)
        url = f"{OKX_API}?instId={symbol}&bar={bar}&limit=300&before={oldest_ts}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            print(f"  Warning: network error: {e}, retrying in 3s...")
            time.sleep(3)
            continue

        if data.get("code") != "0":
            print(f"  Warning: API error: {data.get('msg')}, retrying in 3s...")
            time.sleep(3)
            continue

        batch = data.get("data", [])
        if not batch:
            break  # No more data

        new_count = 0
        for candle in batch:
            ts = candle[0]
            if ts not in seen_ts:
                seen_ts.add(ts)
                all_candles.append(candle)
                new_count += 1

        if new_count == 0:
            break  # No new data

        print(f"  Fetched {len(all_candles)}/{max_count} candles ({symbol} {bar})")
        time.sleep(0.2)  # Avoid rate limits

    # Sort by timestamp ascending
    all_candles.sort(key=lambda x: x[0])
    return all_candles[:max_count]


def save_candles(symbol: str, period_tag: str, candles: list):
    """Save K-line data as JSON file."""
    coin = symbol.split("-")[0].lower()
    filename = f"data_{coin}_{period_tag}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)

    # OKX K-line format: [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
    # Convert to clean format
    formatted = []
    for c in candles:
        formatted.append({
            "ts": int(c[0]),
            "time": datetime.fromtimestamp(int(c[0]) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
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
        for bar, tag, max_count in PERIODS:
            print(f"\nFetching {symbol} {tag} (target: {max_count} candles)...")
            try:
                candles = fetch_all_candles(symbol, bar, max_count)
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

    # Print summary
    print("\n" + "=" * 60)
    print("Data Fetch Summary")
    print("=" * 60)
    total_ok = 0
    for filename, count, status in results:
        icon = "OK" if status == "OK" else "FAIL"
        print(f"  [{icon}] {filename}: {count} candles [{status}]")
        if status == "OK":
            total_ok += 1
    print(f"\nTotal: {total_ok}/{len(results)} files succeeded")

    # Exit with error if nothing succeeded
    if total_ok == 0:
        exit(1)


if __name__ == "__main__":
    main()
