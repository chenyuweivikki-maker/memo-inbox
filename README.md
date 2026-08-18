# 灵感收件箱

> 打字 / 粘贴 → AI 自动分类 → 带日期归档为 Markdown 文件。

随手记下的灵感，丢进去就帮你分好类、归档好，之后随时可迁移到 Obsidian。

## ✨ 功能

- 📥 首页只有一个输入框：打字或粘贴内容（支持中文），点「丢进去」（或 Cmd+Enter）
- 🤖 AI 自动分类：按当前分类列表动态分类（自媒体选题 / 好句 / 小说灵感 / 摘录 / Todo / 日记 / 碎碎念 …），失败自动重试 2 次
- 🏷️ 自动打主题标签，文件名带日期
- 🗂️ 左侧分类栏筛选（手机端抽屉式），按日期倒序；分类可添加 / 改名 / 排序 / 删除（右键或长按分类项），改名时数据自动迁移
- 🐱 极简黑白风 UI，首页一只黑白色线条小猫动态图（SVG）
- 📤 导出 zip：全部 / 单分类（侧边栏「导出当前分类」）
- 🗑️ 每条内容可删除（带确认，防误删）

## 🚀 启动

```bash
python3 -m uvicorn app:app --host 0.0.0.0 --port 8787
```

- 电脑浏览器打开：http://localhost:8787
- 手机（同一 WiFi）打开：`http://<电脑IP>:8787`
- 云端（Railway 等）：`web: uvicorn app:app --host 0.0.0.0 --port $PORT`（见 `Procfile`）

## 🤖 AI 配置

- 环境变量优先：`ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`（云端部署用）
- 本地无环境变量时，回退读取 `~/.claude/settings.json` 中的 `env` 配置
- 模型：`claude-haiku-4-5`（便宜、快、不思考，分类足够）
- key 不在前端出现，也不在仓库中

## 📁 目录结构

```
memo-app/
├── app.py              # 后端：接收内容 → 调 AI 分类 → 存文件
├── categories.json     # 分类列表（可管理：添加 / 改名 / 排序 / 删除）
├── static/
│   └── index.html      # 前端页面（极简黑白风，手机端）
├── memos/              # 数据（按分类分文件夹，文件名带日期）
│   ├── 日记/
│   ├── 自媒体选题/
│   ├── 好句/
│   ├── 小说灵感/
│   ├── 摘录/
│   ├── Todo/
│   └── 其他/
└── requirements.txt    # fastapi + uvicorn
```

## 🛠️ 技术栈

- 后端：Python FastAPI + uvicorn，无数据库、无外部依赖（除 FastAPI/uvicorn）
- 数据：Markdown 文件，可随时迁移到 Obsidian
- AI：Anthropic Claude（claude-haiku-4-5）

## 🗺️ Roadmap

- [ ] 语音输入（手机录音 → 转文字）
- [ ] 子标签细分（哪本小说、什么主题）
- [ ] 部署到云端（随时手机访问，不依赖电脑开机）
- [ ] 搜索功能
