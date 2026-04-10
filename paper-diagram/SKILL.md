---
name: paper-diagram
description: |
  学术论文网络架构示意图生成。读取论文 Method section 或用户描述的模型结构，
  自动生成专业的 TikZ 架构图。支持两种模式：
  (1) JSON 描述 → tikz_generator.py 自动布局（推荐，自动碰撞检测）
  (2) 直接手写 TikZ（复杂自定义场景）
  触发词："画架构图""生成示意图""画网络结构图""draw architecture diagram"
  "帮我画个模型图""论文配图""framework figure""method diagram"
  当用户正在写论文且提到需要配图、示意图、框架图时也应触发。
  与 arxiv-writer（写论文正文）配合使用，本 skill 专注于图的生成。
---

# 学术论文架构示意图生成

从论文方法描述或模型结构自动生成专业 TikZ 架构图，输出可直接嵌入 LaTeX 论文。

---

## 推荐方式：JSON → tikz_generator.py 自动生成

**优先使用此方式**，自动处理布局、碰撞检测、样式规范。

### Step 0: 理解模型结构

**输入来源**（按优先级）：
1. 用户直接描述的模型结构
2. 论文 Method section 的 `.tex` 文件
3. 用户提供的草图/截图
4. 用户提供的技术文档

**提取关键信息**：
- 模型有几个主要模块？各模块名称？
- 数据流方向（通常自底向上或自左向右）
- 输入有哪些？输出有哪些？
- 模块间的连接关系（串行/并行/残差/跳连）
- 是否有多阶段训练（frozen/trainable 区分）
- 是否有 zoom-in 子图需求

### Step 1: 生成 JSON 图描述

将模型结构转换为 JSON 文件，格式参考 `~/.claude/skills/arxiv-writer/scripts/tikz_schema.json`。

核心字段：
- `nodes`：每个模块一个节点，指定 `id`、`label`、`type`（决定颜色）、`row`/`col`（逻辑网格位置）、`group`（分组）、`dim`（维度标注）
- `edges`：连接关系，支持 `default`/`fork`/`residual`/`dashed`/`signal` 五种样式
- `groups`：stage 分组框
- `zoom_in`：可选的 zoom-in 子图

**节点类型与默认样式**：

| type | 填充色 | 默认宽度 | 用途 |
|------|--------|---------|------|
| `input` | gray!8 | 8.0cm | 输入层 |
| `encoder` | orange!12 | 2.2cm | 编码器/特征提取 |
| `core` | blue!10 | 2.2cm | 核心创新模块 |
| `output` | green!10 | 1.2cm | 输出节点 |
| `loss` | red!12 | 2.0cm | 损失函数 |
| `prediction` | green!15 | 1.8cm | 预测头 |
| `frozen` | gray!10 | 2.2cm | 冻结模块（虚线边框）|
| `gate` | purple!10 | 2.4cm | 门控/路由 |
| `pool` | blue!6 | 1.8cm | 池化层 |
| `concat` | green!10 | 4.0cm | 拼接层 |

### Step 2: 运行生成器

```bash
python3 ~/.claude/skills/arxiv-writer/scripts/tikz_generator.py figures/<name>.json -o figures/<name>.tex
```

脚本自动输出：
- 布局坐标计算日志
- 碰撞检测结果
- 边交叉警告
- 完整 TikZ `.tex` 文件

### Step 3: 编译验证

编译 PDF 确认图正确显示。如需微调：
- 调整 JSON 中的 `layout_config`（`row_gap`/`col_gap`/`inter_group_gap`）
- 调整个别节点的 `min_width`/`min_height`
- 重新运行生成器

### Step 4: 信息完整性检查

- [ ] 所有 Method 中提到的模块都出现在图中
- [ ] 所有数据流方向与文字描述一致
- [ ] 图中的符号与正文一致
- [ ] 有完整的 caption 和 label
- [ ] 编译通过，图在页面内完整显示

---

## 备选方式：直接手写 TikZ

仅在以下场景使用：
- 需要非常规布局（圆形、树状、非网格）
- JSON schema 不支持的特殊连接方式
- 对已有 TikZ 代码的小幅修改

手写时遵循以下规范：

### 样式规范

| 元素 | 样式 |
|------|------|
| 输入节点 | `fill=yellow!15`，圆角 |
| 编码器 | `fill=orange!15`，圆角 |
| 可训练模块 | `fill=blue!10`，圆角 |
| 冻结模块 | `fill=gray!10, dashed` |
| 数据流箭头 | `->`, `thick`, `black!70` |
| 蒸馏信号 | `dashed`, `red!60` |

### 三级字号体系

| 层级 | 用途 | 字号 |
|------|------|------|
| L1 模块名 | box 内主标签 | `\footnotesize` |
| L2 子模块 | zoom-in 内部 | `\scriptsize` |
| L3 注释 | 维度标注 | `\tiny` |

### 关键规则

- 所有 dim 注释节点必须命名并加入 `fit` 列表
- 分组标签用独立 `\node` + `anchor=south west`，不用 `label={...}`
- 不使用 `\resizebox{\textwidth}{!}`，用 `scale` 参数
- 编译后目视检查重叠

---

## 常见图类型

| 类型 | 用途 | 布局 |
|------|------|------|
| 多阶段对比 | teacher-student, two-stage | 左右分栏，竖虚线分隔 |
| 层次模块 | encoder-decoder, U-Net | 自底向上 |
| 多分支并行 | multi-task, multi-tower | 底部共享，中间分叉 |
| 序列流水线 | temporal, pipeline | 自左向右 |
