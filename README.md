# 技能奇遇 (Skill Encounter)

> AI 驱动的轻社交 × 就业技能模拟平台 | MVP v0.1

## 这是什么

「技能奇遇」是一个面向在校大学生的 AI 练习平台。选择一个场景（如产品经理面试），AI 扮演面试官与你实时对话，练习结束后获得结构化反馈。内置 RAG 知识库让 AI 真正懂行业、懂面试。

## 快速启动

### 1. 配置 LLM API

```bash
cp .env.example .env
# 编辑 .env，填入你的 LLM API Key 和 Base URL
```

支持任意 OpenAI 兼容接口（GLM-4、DeepSeek、GPT-4 等）。

### 2. 一键启动

```bash
docker-compose up --build
```

### 3. 打开浏览器

访问 http://localhost:8000

## 项目结构

```
skill-encounter/
├── backend/           # FastAPI 后端
│   ├── app/
│   │   ├── main.py    # 入口
│   │   ├── config.py  # 配置
│   │   ├── routers/   # API 路由
│   │   ├── services/  # LLM / RAG / Evaluator
│   │   ├── models/    # Pydantic schemas
│   │   └── data/      # 种子知识库
│   └── Dockerfile
├── frontend/          # 静态前端
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
└── docker-compose.yml
```

## 技术栈

- **后端**: Python / FastAPI / LangChain / ChromaDB
- **前端**: 原生 HTML + CSS + JavaScript
- **LLM**: 兼容 OpenAI API 格式（GLM-4 / DeepSeek / GPT-4）
- **部署**: Docker Compose

## MVP 范围

- ✅ 产品经理面试场景（含 RAG 知识库）
- ✅ 结构化反馈（4 维度评分）
- ✅ 可扩展场景架构
- 🔜 更多场景（即兴演讲、技术面）
- 🔜 用户画像与成长追踪
- 🔜 真人匹配对练
