# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指导。

## 项目概述


。

## 架构

### 后端 (`backend/its_knowledge/`)
- **FastAPI API**: `api/main.py` 创建应用，`api/routers.py` 定义 `/upload` 和 `/query` 端点
- **服务层**:
  - `ingestion/ingestion_processor.py`: 文档加载、分块、向量化
  - `retrieval_service.py`: 两阶段检索（向量搜索 + 标题匹配并重排序）
  - `query_service.py`: 基于检索上下文的 LLM 答案生成
  - `crawler/`: Client 从外部 API 获取数据，Parser 将 HTML 转换为 Markdown
- **仓储层**:
  - `vector_store_repository.py`: 使用 LangChain 进行 Chroma 数据库操作
  - `file_repository.py`: 文件 I/O 和基于 MD5 哈希的去重
- **配置**: `config/settings.py` 使用 pydantic-settings 管理环境变量（API_KEY, BASE_URL, MODEL, EMBEDDING_MODEL）

### 前端 (`front/knowlege_platform_ui/`)
- Vue 3 + Vite + Element Plus + Vue Router
- 视图: `Knowledge.vue`（文件上传）、`Chat.vue`（问答界面）
- API 代理: `/api` -> `http://127.0.0.1:8001`

### 数据流
1. **爬取**: `cli/crawl_cli.py` 从联想 API 获取知识内容，保存为 `.md` 文件
2. **导入**: `cli/upload_cli.py` 批量处理 `.md` 文件并导入 Chroma 向量数据库
3. **查询**: 用户问题 -> 向量搜索 + 标题匹配 -> 重排序 -> LLM 生成答案

## 开发命令

### 后端
```bash
# 在 backend/its_knowledge 目录下运行
cd backend/its_knowledge

# 启动 API 服务器（端口 8001）
python api/main.py

# 或直接使用 uvicorn
uvicorn api.main:create_fast_api --host 127.0.0.1 --port 8001 --factory

# 爬取知识库内容
python cli/crawl_cli.py

# 批量上传文档到向量数据库
python cli/upload_cli.py
```

### 前端
```bash
cd front/knowlege_platform_ui

# 安装依赖
npm install

# 启动开发服务器（端口 3000，代理到后端 8001）
npm run dev

# 构建生产版本
npm run build
```

### 环境配置
- 后端需要在 `backend/its_knowledge/` 目录下配置 `.env` 文件，包含: `API_KEY`、`BASE_URL`、`MODEL`、`EMBEDDING_MODEL`、`KNOWLEDGE_BASE_URL`
- 向量数据库持久化存储在 `backend/its_knowledge/chroma_kb/`
- Markdown 文件存储在 `backend/its_knowledge/data/crawl/`

## 核心模式

### 检索策略（两阶段）
1. **向量搜索**: 使用嵌入模型进行 Chroma 相似度搜索
2. **标题匹配**: Jaccard 相似度（字符级 + 词语级）-> 使用 TF-IDF 余弦相似度重排序
3. **合并去重**: 合并候选项，移除重复，重新评分获取最终 top-k

### 文档分块
- 小文件（<3000 字符）: 单个分块
- 大文件: 使用自定义分隔符的 `RecursiveCharacterTextSplitter`（`\n##`、`\n**`、`\n\n` 等）
- 标题注入: 每个分块添加 `文档来源:{title}` 前缀以保留上下文

### 导入约定
后端使用以 `backend.its_knowledge` 开头的绝对导入。`__init__.py` 会将父目录添加到 `sys.path`。


# Debug Rule（强制执行）

1. 收到 Bug 描述时：
   - 第一步：只分析，不修改代码
   - 第二步：列出 Root Cause 假设（至少 2 个）
   - 第三步：向我确认后再动手修改

2. 禁止行为：
   - 禁止“试一试型修改”
   - 禁止无日志、无复现路径的猜测


# 引入andrej-karpathy-skills 插件
echo "" >> CLAUDE.md
curl https://raw.githubusercontent.com/forrestchang/andrej-karpathy-skills/main/CLAUDE.md >> CLAUDE.md
