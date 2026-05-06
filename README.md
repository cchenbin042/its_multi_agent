# ITS Multi-Agent Knowledge Platform

基于 RAG（检索增强生成）架构的智能知识库问答平台，支持文档上传、多路混合检索、LLM 流式问答与 Agent 深度推理。

## 核心特性

- **多路混合检索** — 向量语义搜索 + BM25 关键词检索 + 标题 Jaccard 匹配，通过 RRF（Reciprocal Rank Fusion）融合三路结果，配合 Cross-Encoder 精排，显著提升召回精度
- **双模式问答** — 标准模式（检索 → 生成）和 Agent 深度推理模式（ReAct，多步工具调用），支持 SSE 流式输出
- **查询扩展** — 同义词扩展 + LLM 查询改写，自动生成多角度搜索变体，提高复杂问题的命中率
- **去品牌化** — LLM 输出后自动执行品牌/型号名称替换，配合 prompt 指令双重保障
- **多格式文档支持** — 支持 Markdown、PDF、DOCX、CSV、TXT 格式上传，自动解析分块向量化
- **会话管理** — 多轮对话上下文记忆，对话历史持久化与回溯
- **反馈闭环** — 用户评分收集 + 反馈统计分析，驱动知识库持续优化
- **Docker 化部署** — 前后端一体化 Docker Compose 编排，开箱即用

## 技术栈

| 层次 | 技术 |
|------|------|
| 后端框架 | Python 3.11, FastAPI, Uvicorn |
| 向量数据库 | ChromaDB (langchain-chroma) |
| LLM / Embedding | LangChain + OpenAI 兼容 API（SiliconFlow） |
| LLM 模型 | DeepSeek-V3.2 |
| Embedding 模型 | Qwen3-Embedding-8B |
| Reranker 模型 | BAAI/bge-reranker-v2-m3 |
| 中文分词 | jieba |
| 文档解析 | Unstructured, PyPDF2, docx2txt, BeautifulSoup4, Markdownify |
| 前端 | Vue 3, Vite 5, Element Plus, Vue Router |
| 容器化 | Docker, Docker Compose, Nginx |

## 快速开始

### 前置条件

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose（可选，用于容器化部署）

### 1. 克隆仓库

```bash
git clone https://github.com/cchenbin042/its_multi_agent.git
cd its_multi_agent
```

### 2. 配置环境变量

在 `backend/its_knowledge/` 目录下创建 `.env` 文件：

```env
API_KEY=sk-your-api-key
BASE_URL=https://api.siliconflow.cn/v1
MODEL=deepseek-ai/DeepSeek-V3.2
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
KNOWLEDGE_BASE_URL=https://iknow.lenovo.com.cn
RERANK_API_URL=https://api.siliconflow.cn/v1/rerank
RERANK_MODEL=BAAI/bge-reranker-v2-m3
```

### 3. 启动后端

```bash
cd backend/its_knowledge
pip install -r requirements.txt
python api/main.py
```

API 服务运行在 `http://127.0.0.1:8001`。

也可以使用 uvicorn 直接启动：

```bash
uvicorn api.main:create_fast_api --host 127.0.0.1 --port 8001 --factory
```

### 4. 启动前端

```bash
cd front/knowlege_platform_ui
npm install
npm run dev
```

前端开发服务器运行在 `http://localhost:3000`，自动代理 `/api` 到后端。

### 5. 导入知识库数据

**方式一：从外部 API 爬取**

```bash
cd backend/its_knowledge
python cli/crawl_cli.py    # 爬取知识库内容到 data/crawl/
python cli/upload_cli.py   # 批量导入到向量数据库
```

**方式二：通过 Web 界面上传**

访问 `http://localhost:3000/knowledge`，拖拽或选择文件上传。

## 项目结构

```
its_multi_agent/
├── backend/its_knowledge/
│   ├── api/
│   │   ├── main.py                  # FastAPI 应用入口（工厂模式）
│   │   └── routers.py               # 所有 API 路由定义
│   ├── config/
│   │   └── settings.py              # Pydantic 配置管理（100+ 配置项）
│   ├── services/
│   │   ├── retrieval_service.py     # 多路混合检索编排（核心）
│   │   ├── query_service.py         # LLM 答案生成
│   │   ├── agent_service.py         # ReAct Agent 深度推理
│   │   ├── bm25_service.py          # BM25 正文检索
│   │   ├── rrf_fusion_service.py    # Reciprocal Rank Fusion
│   │   ├── reranker_service.py      # Cross-Encoder 精排
│   │   ├── query_expansion_service.py  # 查询扩展
│   │   ├── session_manager.py       # 对话会话管理
│   │   ├── analytics_service.py     # 查询分析 + 反馈统计
│   │   ├── web_search_service.py    # 网络搜索兜底
│   │   └── ingestion/
│   │       └── ingestion_processor.py  # 文档加载/分块/向量化
│   ├── repositories/
│   │   ├── vector_store_repository.py  # Chroma 向量库操作
│   │   ├── full_document_repository.py # 全文档集合仓储
│   │   └── file_repository.py        # 文件 I/O + MD5 去重
│   ├── schemas/
│   │   └── schema.py                # Pydantic 请求/响应模型
│   ├── crawler/
│   │   ├── client.py                # 外部知识库 API 客户端
│   │   └── parser.py                # HTML → Markdown 解析器
│   ├── cli/
│   │   ├── crawl_cli.py             # 爬取 CLI
│   │   └── upload_cli.py            # 批量导入 CLI
│   ├── utils/
│   │   ├── brand_anonymizer.py      # 去品牌化后处理
│   │   ├── markdown_utils.py        # Markdown 解析工具
│   │   ├── text_utils.py            # 文本处理
│   │   ├── document_converter.py    # 文档格式转换
│   │   └── logging_config.py        # 日志配置
│   └── data/
│       ├── synonyms.json            # 同义词词典
│       └── brand_map.json           # 去品牌化映射表
├── front/knowlege_platform_ui/
│   └── src/
│       ├── views/
│       │   ├── Chat.vue             # 问答交互页面
│       │   ├── Knowledge.vue        # 文件上传页面
│       │   ├── Admin.vue            # 文档管理页面
│       │   └── Stats.vue            # 分析统计页面
│       ├── components/
│       │   ├── MessageItem.vue      # 消息气泡组件
│       │   ├── RetrievalSteps.vue   # 检索步骤可视化
│       │   ├── AgentSteps.vue       # Agent 推理过程可视化
│       │   └── StepItem.vue         # 步骤状态组件
│       ├── api/
│       │   ├── knowledge.js         # SSE 流式 API 封装
│       │   └── request.js           # Axios 实例
│       ├── composables/
│       │   └── useTimer.js          # 高精度计时器
│       └── router/
│           └── index.js             # Vue Router 路由配置
├── docker/
│   ├── backend.Dockerfile           # 后端 Docker 构建
│   ├── frontend.Dockerfile          # 前端多阶段构建
│   └── nginx.conf                   # Nginx 反向代理 + SSE 配置
├── docker-compose.yml               # Docker Compose 编排
└── requirements.txt                 # Python 依赖
```

## API 文档

### 查询接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/query` | 标准查询（非流式），返回完整回答 |
| POST | `/query/stream` | 流式查询（SSE），推送检索步骤 + token 流 |
| POST | `/query/agent` | Agent 深度推理（SSE），多步工具调用 + 思考过程 |

### 文档管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/upload` | 上传文档（.md / .txt / .pdf / .docx / .csv） |
| GET | `/documents` | 文档列表（分页 + 标题搜索） |
| GET | `/documents/{title}` | 文档内容预览 |
| DELETE | `/documents/{title}` | 按标题删除文档 |

### 会话与反馈

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/conversations` | 历史会话列表 |
| GET | `/conversations/{session_id}` | 会话消息详情 |
| DELETE | `/conversations/{session_id}` | 删除会话 |
| POST | `/feedback` | 提交用户反馈 |
| GET | `/feedback/stats` | 反馈统计分析 |

### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/stats` | 查询聚合统计 |
| POST | `/cache/clear` | 清空查询缓存 |

## 检索流程

```
用户问题
  ├── 查询扩展（同义词 + LLM 改写）
  ├── 批量 Embedding（一次 API 调用）
  │
  ├── 多路并行检索 ──────────────────┐
  │   ├── 向量语义搜索（Chroma）      │
  │   ├── BM25 关键词检索（正文）      ├── RRF 融合
  │   └── 标题 Jaccard + BM25 匹配   │
  │                                   │
  ├── 去重 + 粗排 ────────────────────┘
  ├── Cross-Encoder 精排（BGE-Reranker）
  ├── 分数阈值过滤 + 数量兜底
  ├── （可选）Web Search 兜底
  │
  └── LLM 答案生成（Token 预算动态分配）
       └── 去品牌化后处理
```

## Docker 部署

```bash
docker-compose up -d
```

- **后端**：Python 3.11-slim，Uvicorn，`0.0.0.0:8001`
- **前端**：Node 20 构建 → Nginx Alpine 静态服务，`0.0.0.0:80`，反向代理 `/api` → 后端
- **数据卷**：`chroma_data`（向量库）、`crawl_data`（爬取文件）

## 配置说明

核心配置项（`backend/its_knowledge/config/settings.py`）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `CHUNK_SIZE` | 2500 | 文档分块大小（字符） |
| `CHUNK_OVERLAP` | 300 | 分块重叠大小 |
| `TOP_ROUGH` | 100 | 向量召回候选数 |
| `TOP_FINAL` | 8 | 最终输出文档数 |
| `TOP_RERANK` | 100 | Rerank 候选数 |
| `RERANK_SCORE_THRESHOLD` | 0.15 | Rerank 分数阈值 |
| `CONTEXT_TOKEN_LIMIT` | 6000 | LLM 上下文 token 预算 |
| `BM25_ENABLED` | True | 启用 BM25 正文检索 |
| `BM25_TOP_K` | 50 | BM25 返回候选数 |
| `ENABLE_RERANK` | True | 启用 Cross-Encoder 精排 |
| `ENABLE_SYNONYM_EXPANSION` | True | 启用同义词扩展 |
| `ENABLE_LLM_REWRITE` | True | 启用 LLM 查询改写 |
| `USE_RRF_FUSION` | True | 启用 RRF 多路融合 |
| `QUERY_CACHE_SIZE` | 100 | 查询缓存容量 |
| `QUERY_CACHE_TTL` | 300 | 查询缓存 TTL（秒） |
| `AGENT_TOOL_MAX_CHARS` | 2500 | Agent 工具单篇最大字符数 |
| `MAX_EXPANSION_QUERIES` | 1 | 扩展查询最大数量 |
| `PARALLEL_WORKERS` | 4 | 检索并行线程数 |

完整配置见 `backend/its_knowledge/config/settings.py`。

## License

MIT
