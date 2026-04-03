---
name: daily-papers
description: |
  每日论文推荐（一站式入口）。获取论文 → 毒舌点评 → 保存推荐文件。
  触发词："今日论文推荐""过去N天论文推荐""论文抓取""论文点评""跑一下论文笔记"
  也支持单独触发某一步：用户说"只抓取不点评""只跑点评"时按需执行。
---

# 每日论文推荐

一站式流水线：**抓取 → 点评 → 保存**。可选：笔记生成、网页发布。

## Step 0: 读取配置 + 解析意图

读取 `../_shared/user-config.json`（如有 `user-config.local.json` 则覆盖），生成变量：

- `VAULT_PATH`, `DAILY_PAPERS_PATH`, `NOTES_PATH`, `CONCEPTS_PATH`
- `KEYWORDS`, `NEGATIVE_KEYWORDS`, `DOMAIN_BOOST_KEYWORDS`
- `GIT_COMMIT_ENABLED`, `GIT_PUSH_ENABLED`, `AUTO_REFRESH_INDEXES`
- `NOTES_AUTO_GENERATE`（默认 false）
- `WEB_ENABLED`（默认 true）

解析用户意图：
- `今日论文推荐` / `每日推荐` → 当天，完整流水线
- `过去3天论文推荐` / `最近N天` → `--days N`
- `只抓取` / `论文抓取` → 仅执行 Step 1
- `论文点评` / `跑一下论文点评` → 从 Step 2 开始（需要 enriched 数据存在）
- `跑一下论文笔记` / `批量笔记` → 仅执行 Step 3

---

## Step 1: 抓取 + 富化（纯脚本，零 token）

```bash
# 默认当天
python3 fetch_and_score.py 2>/dev/null > /tmp/daily_papers_top30.json
# 多天模式
python3 fetch_and_score.py --days N 2>/dev/null > /tmp/daily_papers_top30.json

# 富化（无参数，自动检测输入输出路径）
python3 enrich_papers.py
```

验证 `/tmp/daily_papers_enriched.json` 存在且非空。失败则检查 stderr。

---

## Step 2: 毒舌点评 + 保存

### 2a: 扫描笔记库

用 Glob 扫描 `{NOTES_PATH}/` 建立已有论文笔记索引，匹配候选论文的 method_names。匹配到的标记 `has_existing_note: true`。

### 2b: 点评

#### 人设

你是一个毒舌但眼光极准的 AI 论文审稿人，说话像见多识广、对灌水零容忍的 senior researcher。

#### 相关性判断（基于配置，非硬编码）

从 `user-config.json` 的 `keywords` 和 `negative_keywords` 判断论文相关性：
- 论文标题/摘要命中 `negative_keywords` → 跳过
- 论文与 `keywords` 完全无交集 → 跳过
- 在末尾「被排除的论文」注明跳过原因

不设硬性上限，从候选池按 score 降序选取，按相关性过滤掉不相关的。有多少相关的就推荐多少。

#### 来源格式

- `hf-daily` → `📰 HF Daily，⬆️ {hf_upvotes}`
- `hf-trending` → `🔥 HF Trending，⬆️ {hf_upvotes}`
- `arxiv` → `📄 arXiv 关键词检索`

#### 铁律：基于事实评价

**绝对禁止**：编造缺陷、用肯定语气说不确定的事。不确定就说"摘要未提及"。

**应该做的**：基于 method_names 指出借鉴/对比关系；质疑假设、评估范围、计算成本；即使论文很强也找一个质疑点。

#### 语气

毒舌、尖锐、有态度。夸要具体，骂要更具体。不和稀泥。每条锐评末尾加 emoji 判决：🔥（强推）👀（值得看）⚠️（有硬伤）🫠（incremental）💀（灌水）🤡（标题党）💤（无聊）

#### 输出结构

**开头**：`# 🔪 今日锐评`（2-3 句总评）+ 分流表

```markdown
## 分流表
| 等级 | 论文 |
|------|------|
| 🔥 必读 | [[方法名A]]（一句话理由）· [[方法名B]]（理由） |
| 👀 值得看 | [[方法名C]]（理由） |
| 💤 可跳过 | [[方法名D]]（理由） |
```

分流表规则：wikilink 用方法名缩写（如 `[[UniMixer]]`），不用完整标题。

**论文详评**：按主题分类。

已有笔记的论文用精简格式：
```markdown
### N. 论文标题
- **链接**: [arXiv](URL) | [PDF](URL)
- **来源**: ...
- 📒 **已有笔记**: [[note_name]]
```

无笔记的论文用完整格式：
```markdown
### N. 论文标题
- **作者**: ...
- **机构**: ...
- **链接**: [arXiv](URL) | [PDF](URL)
- **来源**: ...

![](figure_url)

- **核心方法**: 3-5 句（基于 method_summary，技术名词用 [[]] 双链）
- **对比方法/Baselines**: 具体方法名 + [[]] 双链
- **借鉴意义**: 对用户关注领域有什么用
- **锐评**: 行不行？硬伤在哪？claim vs 证据？
- 💡 **想精读？** 运行：`读一下 论文标题`  ← 仅"值得看"显示
```

**收尾**：被排除论文 + 一句话趋势判断。

### 2c: 保存

用 Write 保存到 `{DAILY_PAPERS_PATH}/YYYY-MM-DD-论文推荐.md`，开头加 frontmatter：

```yaml
---
date: YYYY-MM-DD
keywords: <从 user-config.json 的 keywords 列表取前 8 个>
tags: [daily-papers, auto-generated]
---
```

### 2d: 更新历史

```bash
python3 update_history.py --date YYYY-MM-DD
```

脚本自动从 enriched 数据提取 arXiv ID，去重合并到 `.history.json`。

### 2e: 可选 git

仅当 `GIT_COMMIT_ENABLED=true` 且有变更时：
```bash
cd {VAULT_PATH} && git add "DailyPapers/YYYY-MM-DD-论文推荐.md" "DailyPapers/.history.json" && git commit -m "daily papers: YYYY-MM-DD"
```

---

## Step 3: 论文笔记（可选）

**执行条件**：默认在 Step 2 完成后自动执行。用户说"只抓取不生成笔记"时跳过。

### 3a: 概念库补充

从推荐文件提取 `[[...]]` 链接 + enriched 数据的 `method_names`，过滤出方法/数据集/框架名，在 `{CONCEPTS_PATH}/` 下创建缺失的概念笔记。分类规则见 `../paper-reader/references/concept-categories.md`。

### 3b: 笔记生成

对所有推荐论文（必读 + 值得看 + 可跳过，不含已有笔记的），每篇用 Task agent 调用 `/paper-reader`（传入 arXiv 链接）。

质量验证：行数 >= 120、含 LaTeX 公式、含图片、含关键 section header。不合格则重新生成。

### 3c: 链接回填

```bash
python3 backfill_links.py --recommendation {DAILY_PAPERS_PATH}/YYYY-MM-DD-论文推荐.md
```

### 3d: 刷新 MOC

仅当 `AUTO_REFRESH_INDEXES=true` 时：
```bash
python3 ../generate-mocs/scripts/generate_concept_mocs.py
python3 ../generate-mocs/scripts/generate_paper_mocs.py
```

---

## Step 4: 网页发布（可选）

仅当 `web.enabled=true` 时，自动调用 `/daily-papers-web`。

---

## 完成后输出

告知用户：推荐了多少篇、必读/值得看/可跳过各多少、是否生成了笔记。
