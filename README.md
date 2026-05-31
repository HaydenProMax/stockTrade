# fund-signal

指数基金回撤分层提醒系统。

## 开发模式

- Windows 本地开发
- Ubuntu venv + cron/systemd 部署
- Python 3.10+
- YAML + `.env` 配置驱动
- SQLite 记录信号、建议和默认执行金额
- 飞书 webhook 推送

## 常用命令

```powershell
python -m fund_signal.cli check
python -m fund_signal.cli notify-test
python -m fund_signal.cli run --mode noon
python -m fund_signal.cli run --mode afternoon --send
python -m fund_signal.cli run --mode us_weekly --send
```

安全演练，不写入执行记录：

```powershell
python -m fund_signal.cli run --mode afternoon --dry-run
python -m fund_signal.cli run --mode afternoon --dry-run --send
python -m fund_signal.cli run --mode us_weekly --dry-run --send
```

`dry-run` 会：

- 抓取真实行情
- 计算真实信号
- 生成真实飞书格式
- 可选发送飞书
- 不保存 run/signal/allocation
- 不占用当月 5500 元预算

## 飞书配置

`.env`：

```dotenv
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...
FEISHU_WEBHOOK_SECRET=your_signing_secret
```

启用签名校验时必须填写 `FEISHU_WEBHOOK_SECRET`。

## 当前策略要点

- 全组合月投入硬上限：5500 元
- 红利低波：固定底仓 + 回撤加仓
- 纳指100：三只每日 10 元长期定投，`021778` 每月 400 元策略/月末补投
- 日经225：两只每日 10 元长期定投
- 中证A500：500 元/月策略执行
- 恒生科技：500 元/月策略执行
- 全球科技互联：1000 元/月，优先买 `006373`，再买 `021842`
- 策略行情缓存最多允许过期 1 个中国交易日
- 中午 12:00 观察，下午 14:30 执行
- 每周六 09:00 可推送美股周收盘观察，只观察不执行

## 测试

```powershell
python -m pytest
python -m compileall .\src\fund_signal
```
