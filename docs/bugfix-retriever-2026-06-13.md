# 知识检索（retriever）Bug 修复记录

- 日期：2026-06-13
- 涉及文件：`src/fund_signal/retriever.py`
- 触发场景：`ask` / `knowledge-search` 命令的本地知识检索（RAG）
- 验证：`tests/test_retriever.py`、`tests/test_advisor.py`、`tests/test_knowledge.py` 共 18 个用例全部通过

本次审查未发现会导致崩溃或数据写坏的 bug，但发现两个**会让检索结果明显变差**的逻辑 bug，均已修复。

---

## Bug 1：偏好路径加分越过了「相关性」门槛，无关片段涌入结果

### 位置
`src/fund_signal/retriever.py` · `retrieve_markdown()`

### 现象
当问题里命中了某只基金（如 `021778`），`advisor` 会把该基金文档路径作为
`preferred_paths` 传进来。本意是：**在命中关键词的片段里，让这只基金的片段排在前面**。

但实际效果是：这只基金文档的**每一个章节**都会被塞进检索结果——包括还没填写、内容是
`待补充官方说明` 的空模板章节，把真正相关的片段挤出了前 N 名。

### 根因
`+10` 的偏好加分被加在了 `if score > 0` 这个「是否命中关键词」的门槛**之前**：

```python
# 修复前
score = _score_chunk(heading, text, terms)   # 没命中关键词时为 0
if path.resolve() in preferred:
    score += 10                               # 空章节也被抬到 10
if score > 0:                                 # 于是恒成立
    hits.append(...)                          # 偏好文档的所有章节都进结果
```

对偏好文档而言 `score` 恒 ≥ 10，门槛形同虚设，导致「全量收录该文档所有章节」。

### 修复
先用关键词得分过门槛，**命中后再加偏好分**：

```python
# 修复后
for path in _knowledge_paths(root):
    is_preferred = path.resolve() in preferred
    for heading, text in _markdown_chunks(path):
        score = _score_chunk(heading, text, terms)
        if score <= 0:        # 没命中关键词的片段直接跳过
            continue
        if is_preferred:      # 命中之后再加偏好权重，用于排序
            score += 10
        hits.append(KnowledgeHit(path=path, heading=heading, text=text, score=score))
```

### 影响
- 偏好加分恢复成「**对命中片段排序加权**」的设计本意。
- 不再把空模板章节（`待补充…`）当作相关知识返回，输出更干净、更相关。

---

## Bug 2：中文查询不分词，整段汉字被当成一个词，几乎匹配不到

### 位置
`src/fund_signal/retriever.py` · `_query_terms()`

### 现象
中文问题里的连续汉字片段被当成**一个完整词条**去匹配文档，命中率极低。

例如问 `纳指100的费用是多少`，旧逻辑产出的词条是：

```
["100", "纳指", "的费用是多少"]
```

其中 `的费用是多少` 这种长串几乎不可能在任何文档片段里原样出现，等于白搜；
最终「相关知识片段」常常为空，而且是**静默**的——用户看不出是检索没生效。

### 根因
中文没有空格分词，旧代码用 `[一-鿿]{2,}` 直接把每一段连续汉字
整体抓成一个词条：

```python
# 修复前
chinese_terms = re.findall(r"[一-鿿]{2,}", query)
```

### 修复
把每段连续汉字拆成**重叠的二元组（bigram）**——这是中日韩文本最常用的轻量索引/检索单元：

```python
# 修复后
chinese_terms: list[str] = []
for run in re.findall(r"[一-鿿]{2,}", query):
    chinese_terms.extend(run[index : index + 2] for index in range(len(run) - 1))
```

效果示例（`纳指100的费用是多少`）：

```
["100", "纳指", "的费", "费用", "用是", "是多", "多少"]
```

`费用`、`多少` 这类二元组能稳定命中文档，召回大幅提升。

> 说明：仍保留 `{2,}` 的限制（忽略孤立单字），避免引入「的」「是」这类单字噪声。

### 影响
- 自由表述的中文问题能正常检索到相关知识，RAG 主功能恢复可用。
- 对英文/数字词条（如基金代码 `021778`）无影响——它们走另一条 ASCII 规则。

---

## 关于「未修复」的部分（仅说明，非 bug）

审查中还注意到一处**疑似** bug，经核对后**排除**：

- `advisor._latest_run_context()` 用 `id` 选出最新一次运行，却用 `(run_date, mode)`
  去取 signals / allocations，初看像是会跨运行混入重复数据。
- 但 `storage.save_signals` / `save_allocations` 在写入前会按 `(run_date, mode)`
  先 DELETE 再 INSERT，表中同一 `(run_date, mode)` 永远只有一份数据，故不存在重复。**判定为非 bug。**

另有几处代码重复（`_first_heading` / `_first_markdown_heading` 多处实现、
`advisor` 内联的相对路径逻辑与 `_display_path` 重复），属于可清理项而非 bug，本次未改动。
