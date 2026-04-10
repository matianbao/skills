---
name: roundtable-web
description: |
  将圆桌会议记录发布到静态网页。扫描 Roundtable/ 目录下的会议纪要 Markdown，
  生成可浏览的 HTML 静态站点，支持会议列表、专家统计、详情页。
  触发词："发布圆桌网页""圆桌网页""roundtable web""生成会议网页"
---

# 圆桌会议网页发布 (Markdown → HTML)

将圆桌会议纪要转为 HTML 静态站点。

## Step 0: 读取配置

读取 `../_shared/user-config.json`，获取：

- `VAULT_PATH = paths.obsidian_vault`
- `ROUNDTABLE_DIR = {VAULT_PATH}/{roundtable.save_dir}`（默认 `Roundtable`）
- `WEB_ENABLED = roundtable.web.enabled`（默认 true）
- `OUTPUT_DIR = roundtable.web.output_dir`（默认 `roundtable`）
- `GITHUB_PAGES_REPO = web.github_pages_repo`（复用全局配置）

## Step 0.5: 检查会议记录

检查 `{ROUNDTABLE_DIR}/` 下是否存在 `.md` 会议纪要文件。

- 如果**不存在**：提示用户先运行 `/roundtable` 生成会议纪要
- 如果**已存在**：继续 Step 1

## Step 1: 生成静态站点

```bash
python3 ../roundtable-web/generate_site.py
```

脚本会：
- 扫描 `{ROUNDTABLE_DIR}/` 下所有 `.md` 文件
- 增量构建：只重新生成源文件有修改的页面（用 `--force` 强制全量重建）
- 生成 `index.html`（Dashboard 首页，会议列表 + 专家统计）
- 生成每场会议详情页 `{date}-{topic}.html`
- 拷贝 `style.css`、`roundtable.js` 到输出目录
- 输出到 `{GITHUB_PAGES_REPO}/{OUTPUT_DIR}/`

## Step 2: 推送到 GitHub Pages

仅当 `GITHUB_PAGES_REPO` 已配置且目录是 git 仓库时执行：

```bash
cd {GITHUB_PAGES_REPO}
git add {OUTPUT_DIR}/
git diff --cached --quiet && echo "No changes to commit" && exit 0
git commit -m "update roundtable $(date +%Y-%m-%d): {rebuilt_count} pages rebuilt"
git push || echo "Push failed. Please check your git credentials."
```

## Step 3: 打开浏览器预览

```bash
open {OUTPUT_PATH}/index.html
```

## Step 4: 告知用户

- 生成了多少场会议页面（增量/缓存）
- 如果推送成功，给出访问 URL
