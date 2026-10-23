---
name: arxiv-writer
description: |
  arXiv 风格学术论文写作助手。从研究笔记、想法、实验结果生成完整 LaTeX 论文并编译 PDF。
  触发词："写论文""写 paper""生成论文""论文写作""draft a paper""write a paper"
  "帮我把这个写成论文""把实验结果整理成 paper""论文初稿"
  当用户提供研究思路、实验数据、或草稿并希望产出学术论文时，即使没说"arxiv"也应触发。
  不要与 paper-reader（读论文）或 daily-papers（论文推荐）混淆——本 skill 是"写"论文。
---

# arXiv 论文写作助手

将用户的研究笔记、想法、实验结果转化为结构完整、符合 arXiv 投稿规范的 LaTeX 论文。

## 工作流程概览

```
Step 0: 理解输入 & 收集信息
    ↓
Step 1: 生成大纲 → ★ 用户确认大纲（唯一的 HITL 节点）
    ↓
Phase 1: 论文生成（写作→图表→编译→质量自检）
    ↓
Phase 2: 可选图补充（Motivation Figure 等）
    ↓
Phase 3: 引用验证（Web Search 逐条核实 references.bib）
    ↓
Phase 4: 多专家评审（3-4 位 Reviewer 并行 + Meta-Review）
    ↓
Phase 5: 基于评审意见修订（全部 P0+P1+P2 自动修改 → 重新编译）
```

**全流程仅在大纲确认时暂停等待用户输入，其余 Phase 全部自动衔接执行，不暂停、不弹确认。**

---

## Step 0: 理解用户输入 & 收集信息

用户可能提供以下任何组合：
- 研究想法 / motivation
- 实验结果（表格、数字、图片路径）
- 方法描述或伪代码
- 相关论文列表
- 已有草稿片段

**必须收集的关键信息**（用户未提供则主动询问）：

| 信息 | 为什么需要 | 示例 |
|------|-----------|------|
| 论文标题（或暂定） | 确定 scope | "MARS: Multi-scale Adaptive Routing with Sparse experts" |
| 核心贡献 | 决定 story line | "提出新框架 / 新 loss / SOTA 结果" |
| 方法概述 | 写 Method section | 模型架构、训练策略、关键公式 |
| 实验设置 | 写 Experiments | 数据集、baselines、指标 |
| 主要结果 | 写 Results | 表格数据、对比数字 |
| 目标会议/期刊（可选） | 调整格式和页数 | NeurIPS / CVPR / ACL / AAAI |

---

## Step 1: 生成大纲

基于收集的信息，生成论文大纲供用户确认。

### 标准 arxiv 论文结构

```
1. Introduction
   - 问题背景与动机（为什么重要）
   - 现有方法的局限（gap 在哪）
   - 本文贡献（3 点左右，bullet list）
2. Related Work（学术会议放这里；工业论文可放 experiments 后面）
   - 按主题分组，不是简单罗列
   - 每组说清楚和本文的关系/区别
3. Preliminaries / Problem Formulation（可选，复杂方法或理论性强的论文需要）
   - 形式化问题定义、符号系统
   - 或数据驱动的 Empirical Analysis 来 motivate 方法设计
4. Method（或 Approach / Framework）
   - Overview 子节（先全局再局部）
   - 方法各模块详述
   - 训练/推理细节
   - 计算复杂度分析（如有工程贡献）
5. Experiments
   - Experimental Setup（数据集、baselines、metrics、实现细节）
   - Main Results（核心对比表）
   - Ablation Study
   - Analysis（可视化、case study 等）
   - Online A/B Test（工业论文）
6. Conclusion
   - 总结贡献
   - Limitations & Future Work
```

将大纲展示给用户，等待确认或修改后再继续。

---

## Step 2: 逐 Section 写作

确认大纲后，按以下顺序写作（这个顺序让信息依赖最合理）：

1. **Method** — 最核心，先写清楚再写其他
2. **Experiments** — 基于 method 描述实验
3. **Introduction** — 知道全貌后写 intro 更准确
4. **Related Work** — 对比定位
5. **Abstract** — 最后写，确保覆盖全文要点
6. **Conclusion** — 总结

---

### Introduction 写作模板

Introduction 是论文最重要的 section，决定 reviewer 第一印象。遵循以下 5 段式结构（从 13 篇顶会论文中提炼）：

**第 1 段：领域背景 + 业务价值**
- 用一句话建立领域重要性（"X is critical for..."）
- 如果是工业论文，给出规模数字（DAU、日均请求量等）

**第 2 段：现有方法概述 + 具体局限**
- 梳理 1-2 类现有方法的核心思路
- 指出每类方法的具体缺陷，用编号标注（Challenge 1: ... Challenge 2: ...）
- 好的 gap 是量化的、具体的（如 "Sinkhorn 的 O(SN²) 复杂度"、"仅 18% 的样本对可用于排序学习"），不是笼统的 "existing methods have limitations"

**第 3 段：本文方法的核心 idea（1-2 句话概括）**
- "In this paper, we propose [Method Name], which..."
- 点明解决上述 gap 的关键机制

**第 4 段：方法简述**
- 如果方法有多阶段/多模块，在此预览各组件功能
- 可引用整体框架图或动机图

**第 5 段：贡献列表（3-4 个 bullet points）**
- 第一条：问题定义或 formulation 贡献（最强 novelty claim）
- 第二条：方法贡献（与 challenge 编号对应）
- 第三条：实验验证（含具体数字、部署规模）
- 每条贡献必须可在论文中找到对应的 section 或实验

**关键原则**：Introduction 中列出的 challenges/problems 必须与 Method section 的子模块一一对应。读者应能从每个 challenge 画箭头到一个具体的方法组件。

---

### Method Section 写作模板

Method section 的组织直接决定论文的清晰度。从高质量论文中提炼的结构规范：

**1. Overview 子节（必须有）**

在展开细节前，先用一个 Overview 子节描述全局：
- 列出所有模块/阶段的名称和功能（一句话一个）
- 说明模块之间的输入-输出连接关系
- 引用整体框架图
- 在最核心/最有创新性的模块子节中引用网络结构图
- 如果方法有多阶段（如 teacher-student、pre-train/fine-tune），明确标注阶段划分

**2. 各模块子节**

每个模块的子节遵循固定结构：
1. 该模块解决什么问题（回指 Introduction 中的 challenge）
2. 先前方法在此处的做法及其不足（1-2 句对比）
3. 本文的做法（文字描述 → 公式 → 符号定义）
4. 设计选择的 justification（为什么选 A 不选 B）

**3. 公式规范**

- 每个公式前用一句话说明要定义什么量
- 公式后立即 inline 定义所有符号，包括维度标注（如 $\mathbf{X} \in \mathbb{R}^{n \times d}$）
- 符号系统全文一致：矩阵粗体大写、向量粗体小写、标量斜体
- 公式编号用 `\label{eq:xxx}` + `\eqref{eq:xxx}` 交叉引用
- 多任务 loss 在 Method 最后一个子节给出加权组合形式

**4. 方法类型决定的组织变体**

| 方法类型 | 组织方式 | 代表论文 |
|---------|---------|---------|
| 多阶段训练（distillation, pre-train/fine-tune）| 按训练阶段分子节 | Diff-MSR, FLIP |
| 多模块并行（multi-task, multi-tower）| 先 Overview 总览，再逐模块展开 | PEPNet, HT-GNN |
| 训练/推理不同（RL, imitation learning）| 分 Training Stage / Inference Stage 两大子节 | SEC |
| 理论驱动 | 先形式化定义/定理，再推导算法 | ESPFormer, BBP |

**5. 可选但加分的内容**

- **Algorithm 伪代码**：如果方法有超过 3 个阶段的训练流程，提供 Algorithm 伪代码，阶段标签与子节标题对齐
- **计算复杂度分析**：用 O(·) 分析与 baseline 的计算开销对比，尤其是工业论文
- **工程优化子节**：工业论文可专设子节描述部署优化（embedding 管理、推理加速、负载均衡等），附具体吞吐量/延迟数字

---

### Experiments Section 写作模板

实验部分是论文说服力的核心。遵循以下结构：

**1. Experimental Setup**

- **数据集**：给出完整统计表（用户数、物品数、交互数、稀疏度、时间跨度）。工业数据集需说明脱敏处理
- **评价指标**：定义每个指标并说明为什么选它。同时报 AUC 和 LogLoss（分类任务）或 NRMSE 和 NMAE（回归任务）
- **Baselines**：按技术路线分组列出（如"通用模型 / 多任务模型 / 多域模型"三层分类）。每个 baseline 用一句话说明原始论文、原始任务、以及为公平比较做了什么适配
- **实现细节**：学习率、优化器、batch size、训练轮数、硬件环境。如果做了多次运行，说明次数

**2. Main Results（可用 RQ 结构组织）**

- 结果表设计：行为方法（从弱到强排列），列为数据集×指标
- 最佳结果 **加粗**，次优 \underline{下划线}
- 如有统计显著性，用 * 标注 p < 0.05
- 工业论文可加 "Rel.Impr" 列（相对提升百分比），方便读者直接看提升幅度
- 结果讨论：不要只复述数字，要解释 *为什么* 本方法更好（与 Method 中的设计选择对应）

**3. Ablation Study**

- 标准格式：每移除一个组件一行（"w/o [ComponentName]"），组件数 = 行数
- 多层级消融更好：先消融模块级（w/o module A），再消融设计选择级（如 w/o field-level masking → token-level masking）
- 如果方法有超参数，用连续曲线图展示（不用离散表格）
- 工业论文可在 online A/B 表中做增量消融（逐步叠加组件，展示 cumulative gain）

**4. Analysis（可视化 + 深度分析）**

好的 analysis 可以从以下选择：
- t-SNE / UMAP embedding 可视化（展示表征质量）
- 注意力热力图（展示模型关注了什么）
- 按数据稀疏度/用户活跃度分组分析（展示对不同子群的效果）
- Case study（具体样本的预测分析）
- Scaling law 曲线（FLOPs vs 性能，展示方法的扩展性）

**5. Online A/B Test（工业论文必须有）**

- 报告内容：流量分桶比例、实验时长、核心业务指标（不仅是模型指标）
- 格式：百分比提升 vs 上线基线（已运行 N 年/月的生产模型）
- 加上规模上下文：如 "0.1% Watch Time improvement is significant at Kuaishou's scale"
- 统计显著性：p-value < 0.05 或 confidence interval
- 成本分析：推理延迟、训练成本是否增加（工业论文的 gate criterion）

---

### Related Work 写作规范

- 按技术维度分组（不按论文分组）
- 每组：先总结该方向的核心思路 → 列举代表性工作 → 明确本文与该方向的区别/关系
- 不要对他人工作做负面评价，只说 "focuses on... / differs from ours in..."
- 位置选择：
  - 学术会议（ICML/NeurIPS/ACL）：通常放 Introduction 后面
  - 工业会议（KDD/CIKM/RecSys）：可以放 Experiments 后面

---

### Figure 使用规范

论文中的图分为**必选图**和**可选图**两类：

#### 必选图（每篇论文都必须生成）

| Figure | 用途 | 放置位置 | 说明 |
|--------|------|---------|------|
| **整体框架图** | **方法全局总览**（所有模块 + 数据流 + 阶段划分） | Method Overview | 展示方法的完整 pipeline，模块间输入输出关系一目了然。模块名称必须与 Method 子节标题完全一致 |
| **网络结构图** | **核心模块的详细网络架构**（层级、维度、连接方式） | Method 对应子节 | 展示方法中最关键/最有创新性的模块的内部结构。如 attention 机制、encoder-decoder 结构、特殊层的细节。整体框架图中用一个 box 表示的模块，在此图中展开为详细网络结构 |

这两张图的关系：**框架图是宏观 pipeline，网络结构图是微观 zoom-in**。读者先从框架图理解方法全局，再从网络结构图理解关键模块的内部设计。

#### 可选图（视论文需求自适应生成）

| Figure | 用途 | 何时需要 |
|--------|------|---------|
| 问题示意图/动机图 | 用真实数据可视化问题的严重性 | Introduction 中需要直观展示 gap/challenge 时 |
| 实验分析图 | 超参数曲线、t-SNE 可视化、attention 热力图等 | 实验分析需要图表辅助说明时 |
| 对比示意图 | 现有方法 vs 本文方法的对比 | 方法差异需要视觉化对比时 |
| 系统部署图 | 线上系统架构、serving pipeline | 工业论文描述部署架构时 |

可选图根据论文内容自动判断是否需要，不强制生成。

#### 图的设计原则

- 多阶段方法用竖虚线分隔阶段（左右对比），同行对齐
- 如果模块太多，用 zoom-in inset 设计（左侧全局 + 右侧局部放大）
- 框架图和网络结构图之间用一致的颜色编码和模块命名
- 网络结构图中标注张量维度（如 $\mathbb{R}^{n \times d}$）和关键操作（如 softmax、concat）

---

### Abstract 写作规范

Abstract 应包含以下 5 个要素，每个 1-2 句话（总计 150-250 词）：

1. **问题上下文**：一句话建立领域重要性
2. **现有方法局限**：一句话点明 gap
3. **本文方法机制**：2-3 句话描述核心做法
4. **实验范围**：一句话（数据集数量、baseline 数量）
5. **核心结果**：一句话（具体数字，工业论文含业务指标）

不要在 Abstract 中引入 Introduction 中未提到的符号。

---

### 写作原则

**论文命名**：
- 论文标题必须包含一个由核心方法名首字母或前几个字母组成的缩写（acronym），作为论文的"品牌名"
- 缩写应简短（3-5 个字母）、易记、与方法含义紧密关联
- 最好是一个有含义的英文单词（如 MARS, MUSE, FEAST），增强记忆点
- 标题格式：`ACRONYM: Full Method Name for Task Description`
- 示例：`MARS: Multi-scale Adaptive Routing with Sparse Experts for Feature Interaction Learning`
- 在正文中用 `\newcommand{\ours}{\textsc{ACRONYM}}` 定义，后续用 `\ours{}` 引用

**语言风格**：
- 学术英语，简洁精确，避免口语化
- 主动语态优先（"We propose..." 而非 "It is proposed that..."）
- 避免过度 claim（"significantly outperforms" 需要有统计显著性支撑）
- 术语首次出现给全称 + 缩写，后续用缩写
- 不使用 section 过渡句（"In the next section, we describe..."），用标题本身做过渡

**引用**：
- 用 `\cite{author2024keyword}` 格式
- BibTeX key 格式：`第一作者姓氏 + 年份 + 关键词`
- 引用放在句末标点前

---

## Step 2.5: 生成图示（Phase 1 内）— fireworks-tech-graph SVG → PNG

Method section 写完后，**至少**生成以下两张图：

1. **整体框架图**（必选）：展示方法的完整 pipeline
2. **网络结构图**（必选）：最核心模块的内部网络结构

此外，根据论文内容自适应判断是否需要可选图（动机图、实验分析图、对比图等）。

### 图生成方式：调用 fireworks-tech-graph skill 生成 SVG + PNG

**不要手写 TikZ 或直接写 SVG。** 调用 `/fireworks-tech-graph` skill 生成高质量技术图，输出 SVG 和 PNG。

#### 1. 准备图描述

为每张图准备清晰的自然语言描述，包含：
- 所有模块/组件名称（必须与 Method 子节标题一致）
- 模块之间的数据流、控制流、连接关系
- 需要标注的维度信息（如 $\mathbb{R}^{n \times d}$）
- 分阶段/分组信息（如 Stage 1: Encoding, Stage 2: Decoding）

#### 2. 调用 skill 生成图

对每张图，调用 `/fireworks-tech-graph` skill，指定：
- 图表类型（Architecture Diagram / Data Flow / Flowchart 等）
- 视觉风格（默认 Style 4: Notion Clean，适合学术论文；或 Style 1: Flat Icon）
- 输出路径：`figures/framework.svg` / `figures/network.svg` 等

```
/fireworks-tech-graph
类型：Architecture Diagram
风格：Style 4 (Notion Clean)
输出：figures/framework
描述：[方法的完整 pipeline 描述，包含所有模块名称和数据流]
```

Skill 会自动：
- 根据描述生成结构化 SVG
- 通过 `rsvg-convert` 验证 SVG 语法
- 导出 1920px 宽 PNG（2x retina）

#### 3. 嵌入论文

在 Method section 中用 `\includegraphics` 引入 PNG：

```latex
\begin{figure}[t]
\centering
\includegraphics[width=\textwidth]{figures/framework.png}
\caption{Overview of the proposed framework.}
\label{fig:framework}
\end{figure}
```

双栏跨栏图使用 `figure*` 环境：

```latex
\begin{figure*}[t]
\centering
\includegraphics[width=\textwidth]{figures/framework.png}
\caption{Overall architecture of \ours{}.}
\label{fig:framework}
\end{figure*}
```

#### 信息完整性检查（仍需人工判断）

- [ ] 图中展示的模块与 Method 正文描述一致
- [ ] 图中的数学符号与正文一致
- [ ] 有完整的 caption 和 label
- [ ] PNG 文件存在且在 PDF 中完整显示
- [ ] SVG 已通过 rsvg-convert 验证

---

## Step 3: 生成 LaTeX 源文件

### 目录结构

在用户指定目录（默认 `~/Desktop/paper-draft/`）下创建：

```
paper-draft/
├── main.tex          # 主文件
├── references.bib    # 参考文献
├── figures/          # 图片目录
├── sections/         # 各 section（可选，小论文可全写 main.tex）
│   ├── introduction.tex
│   ├── related_work.tex
│   ├── method.tex
│   ├── experiments.tex
│   └── conclusion.tex
└── compile.sh        # 一键编译脚本
```

### LaTeX 模板选择

根据目标会议/期刊选择模板：

- **无特定目标 / 通用 arxiv**：用 skill 自带模板 `templates/arxiv-default.tex`
- **特定会议**：告知用户去官网下载模板，skill 负责填充内容

读取并使用 `templates/arxiv-default.tex` 作为 main.tex 的骨架。将写好的内容填入各 section。

### 结果表设计规范

```latex
% 标准结果表模板
\begin{table}[t]
\caption{Main results on [Dataset]. Best in \textbf{bold}, second best \underline{underlined}.
* denotes statistical significance (p < 0.05).}
\label{tab:main}
\centering
\resizebox{\columnwidth}{!}{%  % 或 \textwidth（双栏跨栏）
\begin{tabular}{l|cc|cc}
\toprule
Method & \multicolumn{2}{c|}{Dataset A} & \multicolumn{2}{c}{Dataset B} \\
       & AUC & LogLoss & AUC & LogLoss \\
\midrule
% Baseline tier 1: 通用方法
DeepFM & 0.7812 & 0.4523 & ... & ... \\
% Baseline tier 2: 同类方法
ESMM   & 0.7856 & 0.4487 & ... & ... \\
\midrule
% 本文方法
\textbf{Ours} & \textbf{0.7923}* & \textbf{0.4401}* & ... & ... \\
\bottomrule
\end{tabular}%
}
\end{table}
```

### references.bib

为所有引用的论文生成 BibTeX 条目。格式规范：
- 从 arXiv 或 Semantic Scholar 查找准确的引用信息
- 包含 title, author, booktitle/journal, year, pages（如有）
- 如果用户提供了引用列表，逐条转为 BibTeX

---

## Step 4: 编译 PDF

```bash
cd <paper-dir> && bash compile.sh
```

编译脚本会自动处理多次编译（pdflatex → bibtex → pdflatex × 2）。

如果编译失败：
1. 读取 `.log` 文件定位错误
2. 修复 LaTeX 源文件中的问题
3. 重新编译
4. 最多尝试 3 次自动修复

编译成功后告知用户 PDF 路径。

---

## Step 5: 迭代修改

论文写作是迭代过程。用户可能要求：
- "Introduction 的 motivation 不够强，加强一下"
- "加一个 ablation study"
- "Related Work 少了 XXX 这个方向"
- "公式 3 推导有问题"
- "换成 NeurIPS 格式"

对每次修改：
1. 只改对应部分，不动其他 section
2. 改完重新编译
3. 告知用户改了什么

**Phase 1 到此结束。** Phase 1 输出物：完整的 LaTeX 源文件 + 至少两张图（整体框架图 + 网络结构图）+ 编译通过的 PDF。

---

## 质量检查清单（Phase 1 完成时自动执行）

- [ ] Abstract 是否在 150-250 词之间，包含 5 要素（背景、gap、方法、范围、结果）
- [ ] Introduction 的 challenges 是否与 Method 子模块一一对应
- [ ] Introduction 贡献列表是否每条都有论文中的对应 section/实验
- [ ] Method Overview 子节是否存在且概述了所有模块
- [ ] 所有公式变量是否已定义（含维度标注）
- [ ] 所有图表是否在正文中被引用
- [ ] **整体框架图**已通过 fireworks-tech-graph 生成 SVG+PNG，rsvg-convert 验证通过
- [ ] **网络结构图**已通过 fireworks-tech-graph 生成 SVG+PNG，rsvg-convert 验证通过
- [ ] 可选图（动机图等）已根据需求判断是否生成
- [ ] 结果表中 baselines 是否按技术路线分层列出
- [ ] Ablation 行数是否 ≥ 方法组件数
- [ ] 参考文献格式是否统一
- [ ] 无 `??` 未解析引用
- [ ] 无 overfull/underfull box 警告（严重的）
- [ ] 页数是否符合目标会议要求（如有）

---

# Phase 1 → Phase 2 自动衔接

Phase 1 完成后，**自动执行质量清单自检**（不暂停）。如有 Fail 项，自动修复后重新编译，直到全部 Pass。然后直接进入 Phase 2。

---

# ═══════════════════════════════════════════════
# Phase 2: 可选图补充（Motivation Figure 等）
# ═══════════════════════════════════════════════

Phase 1 质量自检通过后，自动启动 Phase 2。

## 目标

如果论文需要 Motivation Figure 或其他可选图（动机示意图、对比图等），在此阶段补充生成。

## 生成方式

同 Step 2.5，调用 `/fireworks-tech-graph` skill 生成 SVG + PNG：

1. 准备图描述（如问题两面对比、关键数字、现有方法 vs 本文方法等）
2. 调用 `/fireworks-tech-graph`，指定类型和风格（默认 Style 4: Notion Clean）
3. 输出到 `figures/motivation.svg` + `figures/motivation.png`
4. 在 Introduction 中用 `\includegraphics{figures/motivation.png}` 引入
5. 编译验证

Phase 2 完成后直接进入 Phase 3。

---

# ═══════════════════════════════════════════════
# Phase 3: 引用验证
# ═══════════════════════════════════════════════

Phase 2 完成后，自动启动 Phase 3。

## 目标

通过 **Web Search** 逐条核实 `references.bib` 中的每条引用，确保没有虚假引用。

## 执行方式

通过 **Agent 工具**启动子 agent，prompt 中需包含：
- `references.bib` 的完整内容
- 要求对每条引用执行 web search 核实：标题、作者、venue、年份
- 输出格式：每条引用的 verdict（REAL / FAKE / SUSPICIOUS）+ 修正建议

## 验证标准

| Verdict | 条件 | 处理方式 |
|---------|------|---------|
| **REAL** | 标题、作者、venue 全部匹配 | 保留，补全缺失字段（如 pages、doi） |
| **SUSPICIOUS** | 标题或作者部分匹配，venue 不确定 | 标注 `[TODO: verify]`，给出最接近的真实论文 |
| **FAKE** | 无法在任何学术索引中找到 | 删除并替换为同主题的真实论文 |

## 自动修复

验证完成后：
1. 将所有 FAKE 引用替换为推荐的真实引用
2. 更新 citation key（如果 key 格式变了，全文搜索替换）
3. 补全 REAL 引用的缺失字段
4. 重新编译确认无 undefined citation

---

# ═══════════════════════════════════════════════
# Phase 4: 多专家评审
# ═══════════════════════════════════════════════

Phase 3 完成后，自动启动 Phase 4。

## 目标

调用 `/paper-reviewer` skill（或等效流程）对论文进行多视角模拟评审。

## 执行流程

1. **选择 Reviewer 组合**：根据论文类型自动选择 3-4 位 reviewer
   - 工业论文：Experimentalist + Practitioner + Skeptic + Storyteller
   - 方法论文：Formalist + Experimentalist + Skeptic + Storyteller
   - 通用：Formalist + Experimentalist + Storyteller + Skeptic

2. **并行评审**：通过 Agent 工具并行启动 3-4 个 reviewer agent，各自独立评审

3. **Meta-Review 汇总**：以 Area Chair 角色汇总
   - Consensus Strengths / Weaknesses
   - Structural Check（9 项检查表）
   - Score Summary + Decision Recommendation

4. **生成修改计划**：将所有 weakness 转化为优先级排序的修改任务

### 修改计划格式

```
### P0 -- Critical（不修则 reject）
1. [W2-R2, W1-R4] 具体描述 → 具体修改方案 → 涉及 section

### P1 -- Major（显著提升录用概率）
1. ...

### P2 -- Minor（锦上添花）
1. ...
```

### 优先级判断准则

| 问题类型 | 默认优先级 |
|---------|-----------|
| 数据编造/数据不一致 | P0 |
| 虚假引用 | P0（Phase 3 应已修复） |
| 公式错误/符号不一致 | P0 |
| Baseline 不公平或过时 | P0 |
| Ablation 不完整 | P1 |
| Introduction 结构问题 | P1 |
| 缺统计显著性 | P1 |
| 写作细节/格式 | P2 |

---

# Phase 4 → Phase 5 自动衔接

Phase 4 完成后，**自动将完整评审报告写入论文目录**（`paper-draft/论文名/review-report.md`），然后直接进入 Phase 5，**默认执行全部 P0 + P1 + P2 修改**。

---

# ═══════════════════════════════════════════════
# Phase 5: 基于评审意见修订
# ═══════════════════════════════════════════════

Phase 4 完成后，自动启动 Phase 5，执行全部 P0 + P1 + P2 修改。

## 执行流程

1. **按 P0 → P1 → P2 顺序逐项修改全部评审意见**
   - 每修改一项，标注对应哪个 reviewer 的哪个 weakness
   - 修改涉及公式/数据的，同步更新 Abstract 和 Conclusion 中的对应描述
   - 不要动未被评审指出的部分

2. **重新编译 PDF**
   - 全量编译：pdflatex → bibtex → pdflatex × 2
   - 确认无 undefined references、无编译 error

3. **输出修订日志**
   - 列出每项修改：`[P0-1] W2-R2: <修改内容> → <涉及文件:行号>`
   - 统计：P0 修复 X 项，P1 修复 X 项，P2 修复 X 项

4. **可选：再次快速评审**
   - 如果 P0 修改较多，可再跑一轮简化评审验证效果
   - 只需 1-2 位 reviewer 快速扫描修改部分

## Phase 5 完成标志

- 所有 P0 + P1 + P2 issue 已修复
- PDF 编译通过，无 error / warning
- 修订日志已输出
- 告知用户最终 PDF 路径和修订摘要

---

## 注意事项

- 不要编造实验数据——如果用户没给数据，用占位符 `\textbf{XX.X}` 标注待填
- 不要虚构引用——Phase 3 会核实所有引用，但生成时也应尽量使用确信存在的论文
- Related Work 中对他人工作的描述要客观公正
- 如果用户提供的信息不足以写某个 section，明确告知缺什么，而不是瞎编
- 所有图（整体框架图、网络结构图和可选的 motivation figure）都必须通过 fireworks-tech-graph 生成并经 rsvg-convert 验证后才能交付
