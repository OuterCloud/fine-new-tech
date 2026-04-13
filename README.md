# DailyPulse · 每日脉搏

> AI 驱动的技术简报与深度调研平台

聚合 **GitHub Trending**、**Hacker News**、**arXiv**、**Product Hunt** 与**财经要闻**五大来源，一键生成结构化双语简报；支持输入任意主题进行深度调研，追问修订，一键发布到 GitHub Pages。

---

## 功能特性

- **多源聚合** — 并发抓取 5 大数据源，生成中英双语每日简报
- **深度调研** — 输入任意主题，AI 流式生成结构化调研报告并保存
- **追问修订** — 对简报或调研报告提出疑问，AI 修订并覆盖保存
- **发布到 GitHub Pages** — 简报和调研报告均可一键发布为 Jekyll 博客
- **Web 配置管理** — 所有配置项（API Key、模型、抓取数量等）可在页面上修改，无需编辑文件
- **实时进度** — 生成过程通过 SSE 实时推送状态，调研支持流式输出
- **Hash 路由** — 刷新页面保持当前视图，支持浏览器前进后退
- **零前端构建** — 纯 HTML + 原生 JS，无需 Node.js 或打包工具

## 技术栈

| 层级        | 技术                                                  |
| ----------- | ----------------------------------------------------- |
| Web 框架    | FastAPI + uvicorn                                     |
| HTTP 客户端 | httpx（异步）                                         |
| HTML 解析   | BeautifulSoup4 + lxml                                 |
| AI 生成     | 任意 OpenAI 兼容 API（硅基流动 / DeepSeek / Groq 等） |
| 配置管理    | pydantic-settings + Web UI                            |
| 前端渲染    | marked.js + github-markdown-css（CDN）                |

---

## 快速开始

### 前置条件

- Python 3.10+
- 任一 LLM API Key（国内可直连，推荐选项见下方配置说明）

### 1. 部署

```bash
git clone <repo-url>
cd fine-new-tech

# 一键部署（创建虚拟环境、安装依赖、初始化配置）
bash deploy.sh
```

### 2. 配置

编辑 `.env` 填入 API Key，或启动后在 Web 界面「设置」页面修改：

```env
# 方案一：硅基流动（国内直连，有免费额度）
API_KEY=your_siliconflow_key_here
API_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=deepseek-ai/DeepSeek-V3

# 方案二：DeepSeek
# API_KEY=your_deepseek_key_here
# API_BASE_URL=https://api.deepseek.com/v1
# LLM_MODEL=deepseek-chat

# 方案三：Groq（需能访问境外）
# API_KEY=your_groq_key_here
# API_BASE_URL=https://api.groq.com/openai/v1
# LLM_MODEL=llama-3.3-70b-versatile
```

### 3. 启动服务

```bash
bash service.sh start
```

浏览器访问 [http://localhost:8000](http://localhost:8000) 即可使用。

---

## 服务管理

```bash
bash service.sh start               # 启动（默认 0.0.0.0:8000）
bash service.sh start --port 9000   # 指定端口
bash service.sh start --dev         # 开发模式（热重载）
bash service.sh stop                # 停止
bash service.sh restart             # 重启
bash service.sh status              # 查看状态
bash service.sh logs -f             # 实时追踪日志
```

---

## 发布到 GitHub Pages

1. 在 GitHub 创建一个空仓库
2. 进入仓库 **Settings → Pages**，Source 选 `Deploy from a branch`，Branch 选 `main`
3. 在 Web 界面「设置」页面填写仓库地址和 GitHub Token（需 `repo` 权限）
4. 点击「发布到 GitHub Pages」按钮

简报和调研报告都会被发布。

---

## 项目结构

```
fine-new-tech/
├── deploy.sh              # 部署脚本
├── service.sh             # 服务管理脚本
├── requirements.txt
├── .env.example
├── app/
│   ├── main.py            # FastAPI 入口，路由，SSE 端点
│   ├── config.py          # 配置管理（读写 .env + Web API）
│   ├── models.py          # 数据模型
│   ├── summarizer.py      # LLM 集成（简报生成 / 调研 / 修订）
│   ├── report_store.py    # 报告文件读写（简报 + 调研）
│   ├── publisher.py       # GitHub Pages 发布
│   ├── fetchers/
│   │   ├── github_trending.py
│   │   ├── hacker_news.py
│   │   ├── arxiv.py
│   │   ├── finance_news.py
│   │   └── product_hunt.py
│   └── static/
│       ├── index.html
│       ├── style.css
│       └── app.js
├── _site_template/        # Jekyll 站点模板
└── reports/               # 生成的报告（不纳入版本控制）
    └── 2026-04-19/
        ├── zh.md          # 中文简报
        ├── en.md          # 英文简报
        └── research-1.md  # 调研报告
```

---

## API 端点

| 方法     | 路径                          | 说明                       |
| -------- | ----------------------------- | -------------------------- |
| `GET`    | `/`                           | Web UI                     |
| `GET`    | `/api/reports`                | 简报列表                   |
| `GET`    | `/api/reports/{date}?lang=zh` | 获取指定日期简报           |
| `DELETE` | `/api/reports/{date}`         | 删除指定日期简报           |
| `POST`   | `/api/generate`               | 生成今日简报（SSE）        |
| `POST`   | `/api/reports/refine`         | 追问修订简报（SSE）        |
| `GET`    | `/api/researches`             | 调研报告列表               |
| `GET`    | `/api/researches/{date}/{id}` | 获取调研报告               |
| `DELETE` | `/api/researches/{date}/{id}` | 删除调研报告               |
| `POST`   | `/api/research`               | 发起调研（SSE 流式）       |
| `POST`   | `/api/research/refine`        | 追问修订调研报告（SSE）    |
| `GET`    | `/api/settings`               | 获取配置（敏感字段脱敏）   |
| `PUT`    | `/api/settings`               | 更新配置                   |
| `POST`   | `/api/publish`                | 发布到 GitHub Pages（SSE） |

---

## 许可证

MIT
