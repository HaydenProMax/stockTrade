# fund-signal

场外基金加仓提醒系统。

## 开发模式

- Windows 本地开发
- Ubuntu venv + cron/systemd 部署
- Python 3.11+
- 配置驱动
- SQLite 状态存储

## 运行示例

```powershell
python -m fund_signal run --mode noon
python -m fund_signal run --mode afternoon
python -m fund_signal check
```

## 数据源配置

默认数据源：

- 海外 ETF/指数代理：Yahoo chart / yfinance
- A 股指数、ETF、港股指数：AKShare
- 离线兜底：CSV cache

Alpha Vantage 作为可选备用源，需要在 `.env` 中配置：

```dotenv
ALPHAVANTAGE_API_KEY=your_api_key
```

飞书推送需要配置：

```dotenv
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...
FEISHU_WEBHOOK_SECRET=optional_signing_secret
```
