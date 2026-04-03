---
name: daily-papers-web
description: |
  将每日论文推荐发布到 GitHub Pages 静态网页。
  当用户说"发布论文网页""更新论文网页""生成论文网页"时使用。
  
  自动将 DailyPapers/ 下的所有推荐 Markdown 转为 HTML 静态站点，
  支持历史浏览，然后推送到 GitHub Pages 仓库。
---

# 论文网页发布 (Markdown → HTML → GitHub Pages)

你是论文网页发布系统。将 Obsidian 推荐文件转为 HTML 静态站点并推送到 GitHub Pages。

## Step 0: 读取共享配置

读取 `../_shared/user-config.json`，获取：

- `VAULT_PATH`
- `DAILY_PAPERS_PATH = {VAULT_PATH}/{daily_papers_folder}`
- `WEB_ENABLED = web.enabled`（默认 true）
- `GITHUB_PAGES_REPO = web.github_pages_repo`
- `OUTPUT_DIR = web.output_dir`（默认 "daily-papers"）

## 工作流程

### Step 0.5: 检查推荐文件是否存在

检查 `{DAILY_PAPERS_PATH}/` 下是否存在今天的推荐文件 `YYYY-MM-DD-论文推荐.md`。

- 如果**不存在**：提示用户先运行 `今日论文推荐`，然后停止
- 如果**已存在**：跳过，直接进入 Step 1

### Step 1: 生成静态站点

```bash
python3 ../daily-papers-web/generate_site.py
```

脚本会：
- 扫描 `{DAILY_PAPERS_PATH}/` 下所有 `*-论文推荐.md` 文件
- 生成 `index.html`（首页，日期列表 + 摘要）
- 生成每日详情页 `YYYY-MM-DD.html`
- 输出到 `{GITHUB_PAGES_REPO}/{OUTPUT_DIR}/`

如果 `GITHUB_PAGES_REPO` 未配置，输出到 `{VAULT_PATH}/_site/`。

### Step 2: 推送到 GitHub Pages

仅当 `GITHUB_PAGES_REPO` 已配置且目录是 git 仓库时执行：

```bash
cd {GITHUB_PAGES_REPO}
git add {OUTPUT_DIR}/
git commit -m "update daily papers: $(date +%Y-%m-%d)"
git push
```

### Step 3: 打开浏览器预览

生成完成后，打开 GitHub Pages 地址：

```bash
open https://matianbao.github.io/daily-papers-site/daily-papers/
```

如果 `GITHUB_PAGES_REPO` 未配置，则打开本地文件：

```bash
open {OUTPUT_PATH}/index.html
```

### Step 4: 告知用户

- 生成了多少天的页面
- 如果推送成功，给出 GitHub Pages URL

## 注意事项

- 如果 `web.enabled` 为 false，跳过不执行
- 如果 GitHub Pages 仓库未配置，只生成本地 HTML，不推送
- 可以随时手动运行 `发布论文网页` 重新生成全部页面
