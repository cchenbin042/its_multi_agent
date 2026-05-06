from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    API_KEY: str = os.environ.get("API_KEY")
    BASE_URL: str = os.environ.get("BASE_URL")
    MODEL: str = os.environ.get("MODEL")
    EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL")

    
    # knowledge/config
    KNOWLEDGE_BASE_URL:str=os.environ.get("KNOWLEDGE_BASE_URL")
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    # knowledge
    _project_root = os.path.dirname(_current_dir)
    
    VECTOR_STORE_PATH: str = os.path.join(_project_root, "chroma_kb")
    
    # Default directories
    CRAWL_OUTPUT_DIR: str = os.path.join(_project_root, "data", "crawl")
    # Using 'data/crawl' as the default location for markdown files
    MD_FOLDER_PATH: str = CRAWL_OUTPUT_DIR
    TMP_FOLDER_PATH: str = os.path.join(_project_root, "data", "tmp")
    # Text splitting configuration
    # 修复：调整分块大小以保留完整解决方案步骤
    CHUNK_SIZE: int = 2500      # 增大到2500，避免切断完整步骤
    CHUNK_OVERLAP: int = 300    # 增大重叠以保留更多上下文

    MAX_WORKERS: int = 10
    PARALLEL_WORKERS: int = 4           # 检索并行线程数
    
    # Retrieval configuration
    TOP_ROUGH: int = 100                # 向量召回候选数量（提高以覆盖更多潜在相关内容）
    TOP_FINAL: int = 8                  # 最终输出数量（P0优化：从30降到8，配合分数阈值过滤）
    RERANK_SCORE_THRESHOLD: float = 0.15  # Rerank 分数阈值（降低以减少空结果概率）
    MIN_FINAL_DOCS: int = 3              # 数量兜底：阈值过滤后最少保留文档数

    # Retrieval score weights
    VECTOR_WEIGHT: float = 0.4   # 向量检索权重
    TITLE_WEIGHT: float = 0.6    # 标题匹配权重（增加标题匹配影响力）

    # 性能优化配置（新增）
    QUERY_CACHE_SIZE: int = 100           # 查询缓存最大数量
    QUERY_CACHE_TTL: int = 300            # 查询缓存过期时间（秒）
    FULL_DOC_COLLECTION: str = "its-knowledge-full"  # 全文档集合名称

    # ===== 检索优化新增配置 =====

    # BM25 粗排参数
    BM25_K1: float = 1.5                  # BM25 词频饱和参数
    BM25_B: float = 0.75                  # BM25 长度惩罚参数
    BM25_AVG_TITLE_LENGTH: float = 20.0   # 平均标题长度（用于 BM25）

    # RRF 融合参数
    USE_RRF_FUSION: bool = True           # 启用 RRF 融合（推荐）
    RRF_K: int = 60                       # RRF 常数，典型值 50-100

    # 语义扩展参数
    ENABLE_SYNONYM_EXPANSION: bool = True  # 启用同义词扩展
    SYNONYM_FILE_PATH: str = os.path.join(_project_root, "data", "synonyms.json")  # 同义词文件路径

    # 查询扩展参数
    MAX_EXPANSION_QUERIES: int = 1        # 扩展查询最大数量（减少以降低API调用次数）
    LLM_REWRITE_THRESHOLD: int = 30       # 触发 LLM 改写的问题长度阈值
    ENABLE_LLM_REWRITE: bool = True        # 启用 LLM 改写

    # Chunk 动态选择参数
    CHUNK_SIMILARITY_THRESHOLD: float = 0.3  # Chunk 相似度阈值
    MAX_CHUNKS_PER_DOC: int = 5              # 单文档最多 Chunk 数
    MIN_CHUNKS_PER_DOC: int = 1              # 单文档最少 Chunk 数

    # Cross-Encoder Rerank 参数
    RERANK_API_URL: str = os.environ.get("RERANK_API_URL", "")
    RERANK_MODEL: str = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    TOP_RERANK: int = 100                     # 精排候选数量（大幅提高以覆盖关键词召回结果）
    ENABLE_RERANK: bool = True                # 启用 Rerank 精排

    # Web Search 兜底参数
    ENABLE_WEB_SEARCH: bool = False
    WEB_SEARCH_API_KEY: str = os.environ.get("WEB_SEARCH_API_KEY", "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")
    WEB_SEARCH_MAX_RESULTS: int = 5

    # 去品牌化后处理
    BRAND_MAP_FILE: str = os.path.join(_project_root, "data", "brand_map.json")

    # Agent 工具配置
    AGENT_TOOL_MAX_CHARS: int = 2500

    # 上下文 token 预算配置
    CONTEXT_TOKEN_LIMIT: int = 6000
    CONTEXT_TOKEN_FLOOR: int = 200

    # BM25 正文检索配置
    BM25_ENABLED: bool = True
    BM25_TOP_K: int = 50
    BM25_WEIGHT: float = 0.5

    class Config:
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        extra = "ignore"
# 实例化操作
settings = Settings()
