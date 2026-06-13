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
python -m fund_signal.cli build-knowledge
python -m fund_signal.cli knowledge-list
python -m fund_signal.cli knowledge-search "021778 月末补投"
python -m fund_signal.cli fund-docs-init
python -m fund_signal.cli fund-docs-audit
python -m fund_signal.cli fund-docs-audit --strict
python -m fund_signal.cli fund-docs-import 021778 费用 .\tmp\021778_fees.md --source-url "https://example.com" --material-date 2026-06-01 --download-date 2026-06-03
python -m fund_signal.cli external-docs-import sec_finra etf-fees .\tmp\sec_etf_fees.md --source-url "https://example.com" --material-date 2026-06-01 --download-date 2026-06-03
python -m fund_signal.cli ask "今天 021778 要买吗？"
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
- 纳指100：`270042` 每日 10 元固定定投，另有 1000 元/月智能买入；配置中资产组月预算为 1260 元，用于覆盖固定定投 260 元 + 智能买入 1000 元
- 日经225：`020712` 每日 10 元长期定投
- 中证A500：500 元/月策略执行
- 恒生科技：500 元/月策略执行
- 全球科技互联：500 元/月，买入 `006373`
- 策略行情缓存最多允许过期 1 个中国交易日
- 中午 12:00 观察，下午 14:30 执行
- 每周六 09:00 可推送美股周收盘观察，只观察不执行

## 个人策略知识层

生成本地 RAG/问答使用的个人策略摘要：

```powershell
python -m fund_signal.cli build-knowledge
```

默认输出：

```text
knowledge/personal_strategy.md
```

这份文件由 `config/*.yaml` 和 `strategy_records/*.md` 生成，用于解释个人策略、预算纪律、资产组和基金计划。实时买入建议仍以程序计算结果和 SQLite 记录为准。

本地策略问答：

```powershell
python -m fund_signal.cli ask "今天 021778 要买吗？"
python -m fund_signal.cli ask "纳指100 有没有超预算？"
```

`ask` 会读取本地配置和 SQLite 最近一次成功运行结果，解释匹配到的资产组、基金计划、最近信号和 allocation。`--dry-run` 不会写入 SQLite，因此不会成为 `ask` 的依据。

`ask` 还会检索本地 Markdown 知识源：

```text
knowledge/**/*.md
strategy_records/*.md
```

外部资料可以按说明放入 `knowledge/external/`，例如 Bogleheads、SEC/FINRA、IRS、基金官方文件。当前是关键词检索，后续可替换为向量检索。

查看当前可检索知识源：

```powershell
python -m fund_signal.cli knowledge-list
```

直接搜索本地知识库：

```powershell
python -m fund_signal.cli knowledge-search "021778 月末补投"
```

初始化基金官方资料模板：

```powershell
python -m fund_signal.cli fund-docs-init
```

默认输出到：

```text
knowledge/external/fund_docs/
```

命令会从 `config/assets.yaml` 读取基金列表，为每只基金生成一个 Markdown 模板；已存在的文件不会覆盖。问到具体基金代码时，`ask` 会优先检索对应的 `fund_docs/<基金代码>.md`。

检查基金资料补全进度：

```powershell
python -m fund_signal.cli fund-docs-audit
```

审计会检查基金文件是否缺失、来源/资料日期/下载日期是否为空、必要章节是否存在，以及是否仍包含 `待补充`。

严谨模式会额外检查：

```powershell
python -m fund_signal.cli fund-docs-audit --strict
```

`--strict` 会拒绝第三方来源、缺少官方披露文件证据、以及“以最新招募说明书为准”这类占位式口径。用于确认基金资料是否达到可长期引用的官方资料级别。

把本地整理好的 Markdown 片段导入某只基金的指定章节：

```powershell
python -m fund_signal.cli fund-docs-import 021778 费用 .\tmp\021778_fees.md --source-url "https://example.com" --material-date 2026-06-01 --download-date 2026-06-03
```

支持的章节：`基金事实`、`跟踪指数`、`持仓信息`、`费用`、`申购限制`、`分红与税务`、`风险提示`。导入会替换目标章节内容，并更新文件顶部的来源和日期元数据。

导入通用外部 Markdown 资料：

```powershell
python -m fund_signal.cli external-docs-import sec_finra etf-fees .\tmp\sec_etf_fees.md --source-url "https://example.com" --material-date 2026-06-01 --download-date 2026-06-03
```

默认输出到：

```text
knowledge/external/<category>/<slug>.md
```

适合导入 Bogleheads、SEC/FINRA、IRS、FRED 说明文档等长期资料。默认不覆盖已有文件；需要替换时加 `--overwrite`。

## 测试

```powershell
python -m pytest
python -m compileall .\src\fund_signal
```

## Ubuntu 部署

首次部署：

```bash
REPO_URL=https://github.com/you/fund-signal.git PROJECT_DIR=$HOME/fund-signal bash deploy/deploy_ubuntu.sh
```

后续更新：

```bash
PROJECT_DIR=$HOME/fund-signal bash deploy/update_ubuntu.sh
```

脚本会：

- 创建或复用项目目录
- 创建 `.venv`
- 安装依赖
- 初始化 `data/cache` 和 `logs`
- 从 `.env.example` 创建 `.env`，但不会覆盖已有 `.env`
- 运行 `check`、`pytest` 和一次 `afternoon --dry-run`

定时任务示例：

```text
deploy/crontab.example
```
