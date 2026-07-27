# OKX K线数据自动抓取仓库

## 用途
通过 GitHub Actions 在海外服务器上自动抓取 OKX 合约 K 线数据，绕过 GFW 限制。
本地 `git pull` 即可获取最新数据。

## 数据覆盖
- **币种**: BTC, ETH, SOL, DOGE, LINK (均 USDT 永续合约)
- **周期**: 1m / 5m / 15m / 30m / 1H / 4H / 1D
- **数量**: 1m-5m 6万根, 15m-1H 3万根, 4H 1万根, 1D 3千根

## 使用方法

### 1. 创建 GitHub 仓库
在 GitHub 上创建一个新仓库（建议 Private），名为 `okx-klines`。

### 2. 推送代码
```powershell
cd C:\Users\21257\.openclaw\workspace\okx-klines-github
git init
git add .
git commit -m "Initial: OKX klines fetcher"
git remote add origin https://github.com/<你的用户名>/okx-klines.git
git push -u origin main
```

### 3. 启用 Actions
进入仓库 Settings → Actions → General → 确认 Actions 权限为 "Allow all actions"。

### 4. 手动触发首次抓取
进入仓库 Actions 页 → "Fetch OKX K-line Data" → "Run workflow" → "Run workflow"。

### 5. 本地拉取数据
```powershell
cd C:\Users\21257\.openclaw\workspace\okx-klines-github
git pull
# 数据在 data/ 目录下
```

## 自动更新
配置后每 6 小时自动运行一次，无需干预。

## 文件结构
```
├── fetch_klines.py              # 数据抓取脚本
├── .github/workflows/
│   └── fetch_klines.yml         # GitHub Actions 工作流
├── data/                        # K线数据 JSON 文件
│   ├── data_btc_1m.json
│   ├── data_btc_5m.json
│   └── ...
└── README.md
```
