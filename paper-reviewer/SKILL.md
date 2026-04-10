---
name: paper-reviewer
description: |
  多视角学术论文评审与优化。模拟 3-4 位不同偏好的审稿人对论文进行独立评审，
  汇总反馈并给出修改建议。
  触发词："审论文""review paper""论文评审""帮我审一下""模拟审稿""reviewer feedback"
  "论文有什么问题""检查论文质量""paper review""审稿意见"
  当用户写完论文初稿、想要改进论文质量、或准备投稿前自查时使用。
  与 arxiv-writer（写论文）配合：先写后审，审后改。
---

# 多视角论文评审

模拟顶会审稿流程：多位风格迥异的 reviewer 独立评审，产出结构化反馈 + 可执行的修改建议。

---

## 评审流程

```
读取论文 → 3-4 位 Reviewer 独立评审 → Meta-Review 汇总 → 生成修改计划
```

---

## Step 0: 读取论文

接受以下输入：
- LaTeX 源文件目录路径（优先，可读各 section）
- PDF 文件路径
- 用户粘贴的论文文本

读取全文后，确定论文领域和目标 venue（如有），据此选择 reviewer 组合。

---

## Step 1: 独立评审

启动 **3-4 位 Reviewer**，每位独立完成评审。使用 Agent 工具并行执行以提高效率。

### Reviewer 池

从以下 6 位 reviewer 中选择 3-4 位，根据论文类型组合：

---

#### Reviewer 1: "The Formalist" — 方法论严谨派

**人设**: 顶校理论方向教授，发过多篇 oral。对数学表述极其挑剔，认为没有严谨 formulation 的工作不值得发表。

**关注点**:
- 问题定义是否严谨、符号系统是否全文一致
- 公式推导是否正确，假设是否显式声明
- 方法 novelty：是否只是简单组合已有模块？核心创新点的理论依据是什么？
- contribution claim 是否与实际内容匹配
- 与 privileged information learning / causal inference 等理论框架的关系

**具体审查项（从顶会论文规范中提炼）**:
- [ ] 每个公式的所有变量是否在首次出现时定义，包含维度标注
- [ ] 符号系统是否一致（矩阵粗体大写、向量粗体小写、标量斜体）
- [ ] Method section 是否有 Overview 子节提供全局视图
- [ ] 多任务 loss 的加权组合是否有理论或经验 justification
- [ ] 计算复杂度是否分析（与 baseline 对比）
- [ ] Introduction 的 challenges 与 Method 子模块是否一一对应

**评分标准**: Soundness (1-4), Novelty (1-4)

**输出格式**:
```
## Reviewer 1: The Formalist
**Overall Score**: X/10
**Confidence**: X/5
**Summary**: 2-3 句概括
**Strengths**: [S1] ... [S2] ...
**Weaknesses**: [W1] ... [W2] ... [W3] ...
**Questions**: [Q1] ... [Q2] ...
**Suggestions**: 具体修改建议（指明对应 section 和行号）
```

---

#### Reviewer 2: "The Experimentalist" — 实验至上派

**人设**: 工业界 research scientist，年审 50+ 篇论文。只看实验说不说话，对 cherry-pick 结果零容忍。

**关注点**:
- Baseline 是否充分、是否包含最新 SOTA
- 实验数据是否完整：需要 mean±std、统计显著性、多次运行
- 消融实验是否覆盖每个 claimed contribution
- 数据集规模和描述是否详尽
- 是否有 reproducibility 问题（缺超参数、缺代码）
- 数字是否自洽（表格之间、正文与表格之间）
- 是否有编造数据的嫌疑（过于整齐的数字、缺 variance）

**具体审查项（从顶会论文实验规范中提炼）**:
- [ ] Baselines 是否按技术路线分层列出（如通用/多任务/多域三层）
- [ ] 每个 baseline 是否说明了原始论文、适配方式、以及公平比较的措施
- [ ] 结果表行排列是否从弱到强，便于展示性能递进
- [ ] Ablation 行数是否 ≥ 方法的组件数
- [ ] 超参数是否做了 sensitivity analysis（曲线图优于离散表格）
- [ ] 数据集统计表是否完整（用户数、物品数、交互数、稀疏度、时间跨度）
- [ ] 工业论文：是否有 online A/B test，是否报告了流量比、时长、业务指标
- [ ] 工业论文：是否有成本分析（推理延迟、训练成本是否增加）
- [ ] 是否同时报告了多个指标（如 AUC + LogLoss，而非只有一个）
- [ ] 正文中引用的数字是否与表格数字完全一致

**评分标准**: Empirical Quality (1-4), Reproducibility (1-4)

**输出格式**: 同上

---

#### Reviewer 3: "The Storyteller" — 写作表达派

**人设**: NLP 方向资深教授，以 mentoring 著称。认为好的 paper 首先是好的 story，技术再强写不清楚也是 reject。

**关注点**:
- 论文 story 是否连贯：motivation → gap → method → results 是否一条线
- Introduction 是否能在 3 分钟内让读者理解全貌
- 图表是否自解释（不看正文能否理解）
- 术语和符号是否前后一致
- 段落之间是否有逻辑跳跃
- Related Work 是否公平引用、定位是否清晰
- Abstract 和 Conclusion 是否对应
- 语法、拼写、格式问题

**具体审查项（从 13 篇顶会论文的写作模式中提炼）**:
- [ ] Introduction 是否遵循 5 段式结构（背景→局限→idea→预览→贡献）
- [ ] Introduction 的 gap 是否具体、可量化（不是笼统的 "existing methods have limitations"）
- [ ] Contribution bullets 是否每条可追溯到论文中的具体 section 或实验
- [ ] Figure 1 是否为问题/动机图（而非直接放架构图）
- [ ] 架构图中模块名称是否与 Method 子节标题完全一致
- [ ] Abstract 是否包含 5 要素（背景、gap、方法、范围、核心结果数字）
- [ ] 是否有不必要的 section 过渡句（"In the next section, we describe..."）
- [ ] Related Work 是否按技术维度分组而非按论文分组
- [ ] Conclusion 是否引入了新结果或新引用（不应该）
- [ ] 全文是否有首字母缩写在首次出现时未展开

**评分标准**: Clarity (1-4), Presentation (1-4)

**输出格式**: 同上

---

#### Reviewer 4: "The Skeptic" — 怀疑主义者

**人设**: 经常给 borderline reject 的 senior reviewer。对任何 claim 都要 double check，最擅长找逻辑漏洞。

**关注点**:
- 哪些 claim 缺乏证据支撑？
- 方法的局限性是否被刻意回避？
- 实验 setting 是否有利于提出的方法？是否有 unfair comparison？
- 公式或方法描述是否有歧义，可以被理解为不同的实现？
- 与已有工作的区别是否被夸大？
- 在什么条件下方法会失败？论文是否讨论了？
- 引用是否存在虚假引用？

**具体审查项（从真实审稿中常见的 killer questions 提炼）**:
- [ ] "To the best of our knowledge, this is the first..." — 是否真的是 first？web search 核实
- [ ] Baseline 适配是否公平：backbone 是否相同？超参数是否同等调优？
- [ ] 方法的计算开销是否与 baseline 在同一量级？如果高很多，是否在同 FLOPs 下也做了比较？
- [ ] 消融中移除某组件后的下降幅度是否合理？如果下降极小，该组件的贡献是否被夸大？
- [ ] 工业论文：offline improvement 与 online improvement 是否方向一致？如果不一致，原因是什么？
- [ ] 论文是否讨论了方法失败的条件（failure cases / limitations）？
- [ ] 引用核实：对可疑引用进行 web search 确认是否真实存在
- [ ] 数据泄露检查：训练集是否可能包含测试集信息？时间切分是否合理？

**评分标准**: Soundness (1-4), Significance (1-4)

**输出格式**: 同上

---

#### Reviewer 5: "The Practitioner" — 工程实践派

**人设**: 大厂算法 leader，关注方法能不能用、好不好落地。对纯 toy experiment 没有耐心。

**关注点**:
- 方法复杂度：训练成本、推理延迟、额外存储
- 在真实系统中部署的可行性
- 是否需要额外数据/标注/预训练模型
- 两阶段 vs 端到端的工程 trade-off
- 线上实验设计是否合理（A/B test 时长、流量比、指标选择）
- 模型的 scalability 和 generalization 到其他场景

**具体审查项（从工业论文部署规范中提炼）**:
- [ ] 是否有推理延迟/吞吐量数据？与 baseline 在同一硬件上对比
- [ ] 成本中性声明是否有数据支撑（"training cost unchanged, inference cost reduced by X%"）
- [ ] 方法是否 model-agnostic？是否在多个 backbone 上验证了兼容性？
- [ ] 是否有 scaling law 分析（模型大小 / FLOPs vs 性能曲线）？
- [ ] 预计算/预存储策略是否可行（存储量、更新频率）
- [ ] 在线 A/B test 中的流量比是否足够（通常 ≥ 5%），时长是否足够（通常 ≥ 7 天）

**评分标准**: Practicality (1-4), Impact (1-4)

**输出格式**: 同上

---

#### Reviewer 6: "The Newcomer" — 领域新人视角

**人设**: 相关但不完全对口的博士生，第一次审这个方向的论文。代表的是"非专家读者"的理解难度。

**关注点**:
- 读完论文能否自己实现这个方法？
- 哪些地方需要额外背景知识才能理解？
- 术语/缩写是否在首次出现时定义？
- 方法的 intuition 是否清晰？为什么要这样做？
- 图表是否帮助理解还是增加困惑？

**具体审查项**:
- [ ] Method Overview 子节是否存在？是否看完就能画出系统流程图？
- [ ] 是否有 Algorithm 伪代码帮助理解训练流程？
- [ ] 架构图是否自解释（不读正文能理解 70% 以上）
- [ ] 每个设计选择是否解释了 "why"（为什么选 A 不选 B）
- [ ] Preliminaries/Background 是否足够让非专家跟上后续内容

**评分标准**: Accessibility (1-4), Self-containedness (1-4)

**输出格式**: 同上

---

### Reviewer 组合推荐

| 论文类型 | 推荐组合 |
|---------|---------|
| 方法+理论 | Formalist + Experimentalist + Skeptic + Storyteller |
| 工业系统 | Experimentalist + Practitioner + Skeptic + Storyteller |
| 偏写作/survey | Storyteller + Newcomer + Formalist + Skeptic |
| 通用默认 | Formalist + Experimentalist + Storyteller + Skeptic |

用户可指定使用哪些 reviewer，否则根据论文类型自动选择。

---

## Step 2: Meta-Review 汇总

所有 reviewer 评审完成后，以 Area Chair 角色汇总：

```
## Meta-Review

### Overall Assessment
论文定位、主要优缺点概述

### Consensus Strengths（多位 reviewer 认同的优点）
- ...

### Consensus Weaknesses（多位 reviewer 认同的问题）
- ... [Severity: Critical/Major/Minor]

### Conflicting Views（reviewer 之间有分歧的点）
- ...

### Structural Check（论文结构规范性）
基于从 13 篇顶会论文中提炼的结构规范，检查以下项目：

| 检查项 | 状态 | 说明 |
|--------|------|------|
| Introduction 5 段式结构 | Pass/Fail | |
| Challenges ↔ Method 模块对应 | Pass/Fail | |
| Method Overview 子节存在 | Pass/Fail | |
| Figure 1 为动机图 | Pass/Fail | |
| 架构图模块名 = 子节标题 | Pass/Fail | |
| Baselines 分层分类 | Pass/Fail | |
| Ablation 覆盖所有组件 | Pass/Fail | |
| Abstract 含 5 要素 | Pass/Fail | |
| 数据集统计表完整 | Pass/Fail | |

### Score Summary
| Reviewer | Score | Confidence |
|----------|-------|------------|
| R1       | X/10  | X/5        |
| ...      |       |            |
| **Avg**  | X/10  |            |

### Decision Recommendation
Accept / Borderline Accept / Borderline Reject / Reject
```

---

## Step 3: 生成修改计划

将所有 weakness 和 suggestion 转化为**可执行的修改任务**，按优先级排序：

```
## Revision Plan

### P0 — Critical（不修则 reject）
1. [W2-R2, W1-R4] 具体描述 → 具体修改方案 → 涉及 section
2. ...

### P1 — Major（显著提升录用概率）
1. ...

### P2 — Minor（锦上添花）
1. ...

### Estimated Effort
- P0: ~X hours
- P1: ~X hours
- P2: ~X hours
```

**优先级判断准则（从真实审稿模式中提炼）**：

| 问题类型 | 默认优先级 | 说明 |
|---------|-----------|------|
| 数据编造/数据不一致 | P0 | 正文数字与表格不符、缺 variance 的"过于整齐"数字 |
| 虚假引用 | P0 | 引用不存在的论文 |
| 公式错误 / 符号不一致 | P0 | 推导错误、未定义变量 |
| Baseline 不公平或过时 | P0 | 缺最新 SOTA、backbone 不统一 |
| Ablation 不完整 | P1 | 组件数 > 消融行数 |
| Introduction 结构问题 | P1 | Gap 不具体、challenges 与 method 不对应 |
| 缺 Figure 1 动机图 | P1 | 直接放架构图作为 Figure 1 |
| 缺统计显著性 | P1 | 无 p-value 或 confidence interval |
| 写作细节 | P2 | 语法、格式、缩写未展开 |
| 缺 Algorithm 伪代码 | P2 | 复杂流程缺伪代码辅助 |

---

## Step 4: 执行修改（可选）

用户确认修改计划后，逐项执行修改：
1. 按 P0 → P1 → P2 顺序修改
2. 每修改一项，标注对应哪个 reviewer 的哪个 weakness
3. 修改后重新编译 PDF
4. 如有需要，可再跑一轮快速评审验证修改效果

---

## 注意事项

- **不要手下留情**：评审的价值在于发现问题，温和的评审没有意义。每个 reviewer 至少给 2 个 weakness
- **区分事实性问题和主观偏好**：事实性错误（数据不一致、公式错误）是 P0，风格偏好是 P2
- **引用核实**：Skeptic reviewer 必须检查引用是否真实存在（通过 web search 核实可疑引用）
- **数据自洽性**：Experimentalist 必须交叉验证所有数字（正文 vs 表格 vs abstract）
- **并行执行**：使用 Agent 工具并行运行多个 reviewer，提高效率
- **评审语言**：reviewer 输出用英文（模拟真实审稿），Meta-Review 和修改计划用用户偏好语言
- **结构规范对照**：Meta-Review 中加入结构规范性检查表，基于顶会论文的写作范式
