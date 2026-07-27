# OKX K-line Data (GitHub Actions)

Auto-fetch OKX perpetual swap K-line data via GitHub Actions.

## Symbols
BTC-USDT-SWAP, ETH-USDT-SWAP, SOL-USDT-SWAP, DOGE-USDT-SWAP, LINK-USDT-SWAP

## Periods
1m, 5m, 15m, 30m, 1H, 4H, 1D

## Schedule
Every 6 hours via GitHub Actions cron.

## Data Format
JSON files in `data/` directory:
```json
{
  "symbol": "BTC-USDT-SWAP",
  "period": "1H",
  "count": 30000,
  "fetched_at": "2026-07-27 16:00:00 UTC",
  "data": [
    {"ts": 1620000000000, "time": "2021-05-03 00:00:00", "open": 56000.5, "high": 56100.0, "low": 55900.0, "close": 56050.0, "vol": 1234.5, "volCcy": 5678.9, "confirm": "1"}
  ]
}
```

## Local Pull
```bash
git pull origin main
# Data files in data/
```
