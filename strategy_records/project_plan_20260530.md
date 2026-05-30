# 指数基金加仓提醒系统项目计划

版本时间：2026-05-30
状态：MVP 开发前架构规划

## 1. 项目目标

构建一个场外基金加仓提醒系统。

核心能力：

- 每日 11:30 ~ 11:40 推送午间观察信号
- 每日 14:30 ~ 14:45 推送下午执行建议
- 使用指数回撤、均线过滤、预算约束生成加仓建议
- 检查基金申购状态、暂停申购和限购信息
- 通过飞书推送具体基金级别建议
- Windows 本地开发，Ubuntu 服务器部署

不做：

- 不自动下单
- 不做网页界面
- 不在第一版强制 Docker 化
- 不把策略逻辑和行情抓取异常混在一起

## 2. 开发与部署模式

```text
Windows 本地开发
Python 跨平台实现
Ubuntu venv 部署
cron 或 systemd timer 定时运行
后续可选 Docker 化
```

约束：

```text
所有路径使用 pathlib
所有时间显式使用 Asia/Shanghai
密钥写入 .env
不依赖 Windows 计划任务
不依赖桌面 GUI
不使用绝对路径
网络失败需要降级处理
```

## 3. 目录结构

```text
fund-signal/
  config/
    assets.yaml
    strategy.yaml
    budget.yaml
    calendars.yaml
  data/
    fund_signal.sqlite
    cache/
  src/
    fund_signal/
      __init__.py
      cli.py
      config.py
      calendar.py
      market_data.py
      providers/
        __init__.py
        yfinance_provider.py
        akshare_provider.py
        csv_provider.py
      fund_rules.py
      strategy.py
      allocator.py
      storage.py
      notifier_feishu.py
      runner.py
  tests/
  .env.example
  pyproject.toml
  README.md
```

## 4. 配置边界

### 4.1 assets.yaml

保存基金和资产元数据。

```text
基金代码
基金名称
资产组
跟踪指数
指数代码
市场
是否 QDII
是否主动基金
是否指数增强
申购截止时间
是否启用
组内分配比例
```

### 4.2 strategy.yaml

保存策略参数。

```text
波动分类
回撤阈值
触发 U 数
均线过滤规则
全球科技互联代理规则
主动 QDII 降权规则
```

### 4.3 budget.yaml

保存预算约束。

```text
1U 对应金额
单资产组单日上限
单资产组单月上限
科技成长总预算
全组合总预算
单基金上限
```

### 4.4 calendars.yaml

保存交易日和节假日配置。

第一版可以简化为：

```text
中国交易日
手动排除节假日
手动额外开放日
```

后续扩展：

```text
A股交易日
港股交易日
美股交易日
日本交易日
QDII 申购日
```

## 5. 行情源 Provider 抽象

行情源是系统主要风险点，必须和策略逻辑解耦。

Provider 目录：

```text
providers/
  yfinance_provider.py
  akshare_provider.py
  csv_provider.py
```

统一返回结构：

```text
date
open
high
low
close
volume
source
```

Provider 职责：

```text
yfinance_provider.py：海外指数、港股指数、日股指数
akshare_provider.py：A股指数、基金净值、基金申购状态
csv_provider.py：离线回测、故障兜底、手动导入
```

market_data.py 只负责调度 provider：

```text
按资产配置选择首选 provider
首选失败时按 fallback 顺序重试
返回统一行情结构
记录数据来源和异常
```

策略模块不直接调用 yfinance 或 AKShare。

## 6. SQLite 状态存储

第一版使用 SQLite，不用纯 CSV 管预算和运行状态。

数据库：

```text
data/fund_signal.sqlite
```

建议表：

```text
prices
fund_navs
fund_purchase_status
signals
allocations
runs
notifications
executions
```

### 6.1 runs

记录每次运行。

```text
id
run_date
mode
started_at
finished_at
status
error_message
```

mode：

```text
noon
afternoon
manual
backtest
```

### 6.2 notifications

用于飞书推送幂等和去重。

```text
id
run_date
mode
asset_group
signal_hash
notified_at
status
response_code
response_body
```

同一天、同模式、同资产组、同 signal_hash 不重复推送。

### 6.3 executions

记录人工执行结果。

```text
id
trade_date
fund_code
asset_group
suggested_u
executed_u
executed_amount
nav
status
notes
```

第一版可以先记录建议，人工执行金额后续再补录。

## 7. 幂等与重试

cron、网络超时、飞书 webhook 超时都可能导致重复运行。

规则：

```text
每次运行生成 run_id
每条资产组信号生成 signal_hash
发送飞书前检查 notifications
已成功发送的同一信号不重复发送
失败状态允许重试
重试不改变原始 signal_hash
```

signal_hash 输入：

```text
run_date
mode
asset_group
fund_codes
triggered_units
final_units
drawdown_band
trend_state
budget_state
purchase_status
```

## 8. 交易日模块

calendar.py 是一等模块。

第一版职责：

```text
判断今天是否需要推送
判断当前 mode 是否允许运行
读取 calendars.yaml 手动节假日
支持中国交易日优先
```

第一版简化规则：

```text
如果不是中国工作日，不推送
如果在手动节假日列表，不推送
如果在手动额外开放日列表，允许推送
```

后续扩展：

```text
根据资产市场判断数据新鲜度
识别美股假期
识别港股假期
识别日本假期
识别 QDII 基金是否可申购
```

## 9. 基金规则模块

fund_rules.py 负责基金层面的可执行性判断。

数据源：

```text
AKShare fund_purchase_em()
```

检查字段：

```text
申购状态
赎回状态
下一开放日
购买起点
日累计限定金额
手续费
```

规则：

```text
开放申购：保留策略建议
暂停申购：最终建议改为不执行
限制大额申购：按限额修正最终建议
状态缺失或接口异常：标记“申购状态未确认”，不自动放大建议
```

## 10. 核心运行流程

```text
cli.py
  ↓
runner.py
  ↓
calendar.py 判断是否运行
  ↓
market_data.py 获取指数行情和基金净值
  ↓
strategy.py 计算回撤、均线、触发 U 数
  ↓
allocator.py 拆分到具体基金并套用预算
  ↓
fund_rules.py 检查申购状态和限额
  ↓
storage.py 写入 signals / allocations / runs
  ↓
notifier_feishu.py 幂等检查后推送
```

## 11. MVP 范围

第一版必须完成：

```text
配置读取
provider 抽象
行情获取
回撤和均线计算
资产组信号生成
预算约束
基金申购状态检查
SQLite 状态记录
飞书推送
幂等去重
手动运行 noon / afternoon
```

第一版暂不完成：

```text
复杂回测
网页界面
自动下单
Docker 部署
多用户
自动同步真实持仓
```

## 12. 开工条件

可以开始 MVP 开发。

仍需后续手动配置，但不阻塞开发：

```text
1U 对应人民币金额
同一资产组内基金分配比例
飞书 webhook 地址
节假日手动列表
```

