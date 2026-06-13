# 外部投资知识源

这个目录用于存放可被本地 `ask` 命令检索的外部 Markdown 资料。

建议目录：

```text
knowledge/external/
  bogleheads/
  sec_finra/
  irs/
  fund_docs/
```

放入原则：

- 优先使用官方或高质量长期资料，不放短期新闻。
- 每个文件顶部保留来源 URL、下载日期、资料日期。
- 基金事实文件按基金代码命名，例如 `fund_docs/021778.md`。
- 税务、监管、投资原则资料不要和个人策略混在同一个文件里。

第一批建议资料：

- Bogleheads：资产配置、再平衡、三基金组合、税务效率。
- SEC / Investor.gov：共同基金、ETF、费用、风险、招募说明书。
- FINRA：基金类型、ETF/ETP 风险、费用教育。
- IRS Pub 550：投资收入、分红、资本利得和持有期。
- 基金官方文件：prospectus、annual report、holdings、分红信息。

当前实现是本地 Markdown 关键词检索。后续可以在不改变目录结构的情况下替换为 embedding/vector store。
