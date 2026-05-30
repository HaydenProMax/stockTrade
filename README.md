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

