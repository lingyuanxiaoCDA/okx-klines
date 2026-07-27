#!/usr/bin/env python3
"""
OKX K线数据抓取脚本 - GitHub Actions 版本
从 OKX 公共 API 获取多币种多周期 K 线数据，保存为 JSON 文件。
"""

import json
import time
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

# OKX 公共 API
OKX_API = "https://www.okx.com/api/v5/market/candles"

# 币种列表
SYMBOLS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "DOGE-USDT-SWAP", "LINK-USDT-SWAP"]

# 周期映射: (OKX bar参数, 文件名标识, 最大K线数)
PERIODS = [
    ("1m",    "1m",    60000),   # ~41.7天
    ("5m",    "5m",    60000),   # ~208天
    ("15m",   "15m",   30000),   # ~312天
    ("30m",   "30m",   30000),   # ~625天
    ("1H",    "1H",    30000),   # ~1250天
    ("4H",    "4H",    10000),   # ~1666天
    ("1D",    "1D",    3000),    # ~8.2年
]

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def fetch_candles(symbol: str, bar: str, limit: int = 300) -> list:
    """从 OKX 获取单次 K 线数据（最多300根）"""
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
    """分页获取大量 K 线数据"""
    all_candles = []
    seen_ts = set()
    
    # 首次请求（从最新开始往前翻）
    batch = fetch_candles(symbol, bar, 300)
    if not batch:
        return []
    
    for candle in batch:
        ts = candle[0]
        if ts not in seen_ts:
            seen_ts.add(ts)
            all_candles.append(candle)
    
    # 用最早的K线时间戳作为 before 参数继续往前翻
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
            print(f"  ⚠️ 网络错误: {e}, 等待3秒后重试...")
            time.sleep(3)
            continue
        
        if data.get("code") != "0":
            print(f"  ⚠️ API错误: {data.get('msg')}, 等待3秒后重试...")
            time.sleep(3)
            continue
        
        batch = data.get("data", [])
        if not batch:
            break  # 没有更多数据了
        
        new_count = 0
        for candle in batch:
            ts = candle[0]
            if ts not in seen_ts:
                seen_ts.add(ts)
                all_candles.append(candle)
                new_count += 1
        
        if new_count == 0:
            break  # 没有新数据了
        
        print(f"  已获取 {len(all_candles)}/{max_count} 根 ({symbol} {bar})")
        time.sleep(0.2)  # 避免触发频率限制
    
    # 按时间戳升序排列
    all_candles.sort(key=lambda x: x[0])
    return all_candles[:max_count]


def save_candles(symbol: str, period_tag: str, candles: list):
    """保存 K 线数据为 JSON 文件"""
    coin = symbol.split("-")[0].lower()
    filename = f"data_{coin}_{period_tag}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    # OKX K线格式: [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
    # 转为简洁格式
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
            print(f"\n📊 获取 {symbol} {tag} (目标: {max_count} 根)...")
            try:
                candles = fetch_all_candles(symbol, bar, max_count)
                if candles:
                    filename, count = save_candles(symbol, tag, candles)
                    print(f"  ✅ {filename}: {count} 根 K线")
                    results.append((filename, count, "OK"))
                else:
                    print(f"  ❌ 无数据")
                    results.append((f"data_{symbol.split('-')[0].lower()}_{tag}.json", 0, "NO_DATA"))
            except Exception as e:
                print(f"  ❌ 错误: {e}")
                results.append((f"data_{symbol.split('-')[0].lower()}_{tag}.json", 0, f"ERROR: {e}"))
    
    # 打印汇总
    print("\n" + "=" * 60)
    print("📈 数据获取汇总")
    print("=" * 60)
    total_ok = 0
    for filename, count, status in results:
        icon = "✅" if status == "OK" else "❌"
        print(f"  {icon} {filename}: {count} 根 [{status}]")
        if status == "OK":
            total_ok += 1
    print(f"\n总计: {total_ok}/{len(results)} 个文件成功")
    
    # 如果没有任何成功，返回非0退出码让 Actions 标记失败
    if total_ok == 0:
        exit(1)


if __name__ == "__main__":
    main()
