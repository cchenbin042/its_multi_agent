import re
import json
import hashlib
import time
import threading
import numpy as np
from typing import List, Dict, Any, Tuple, Callable, Optional
from dataclasses import dataclass, field
from langchain_core.documents import Document
import logging
import jieba
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from cachetools import TTLCache
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.its_knowledge.repositories.vector_store_repository import VectorStoreRepository
from backend.its_knowledge.repositories.full_document_repository import FullDocumentRepository
from backend.its_knowledge.services.ingestion.ingestion_processor import IngestionProcessor
from backend.its_knowledge.services.rrf_fusion_service import RRFFusionService
from backend.its_knowledge.services.query_expansion_service import QueryExpansionService
from backend.its_knowledge.services.reranker_service import RerankerService
from backend.its_knowledge.services.web_search_service import WebSearchService
from backend.its_knowledge.services.bm25_service import Bm25Service
from backend.its_knowledge.config.settings import settings
from backend.its_knowledge.utils.markdown_utils import MarkDownUtils
from backend.its_knowledge.services.score_utils import normalize_vector_score


@dataclass
class StepEvent:
    """步骤事件（用于 SSE 推送）"""
    step: str           # 步骤标识: query_understanding / knowledge_retrieval / reranking / answer_generation
    status: str         # started / completed / error
    duration_ms: int = 0
    detail: dict = field(default_factory=dict)


# 类型别名：步骤回调函数
StepCallback = Optional[Callable[[StepEvent], None]]


logger = logging.getLogger(__name__)


class RetrievalService:
    """
    负责检索的类（检索器）
    """

    def __init__(self):
        """
        初始化向量数据库和优化服务
        """
        self.chroma_vector = VectorStoreRepository()
        self.spliter = IngestionProcessor()
        self.full_doc_store = FullDocumentRepository()

        # 实例级别缓存
        self._query_cache = TTLCache(
            maxsize=settings.QUERY_CACHE_SIZE,
            ttl=settings.QUERY_CACHE_TTL
        )

        # P1优化：标题元数据和向量启动时缓存
        self._title_metadata_cache: List[Dict[str, Any]] = []
        self._title_vector_cache: Dict[str, np.ndarray] = {}  # title -> vector
        self._idf_table: Dict[str, float] = {}  # word -> IDF value
        self._refresh_metadata_cache()

        # 优化服务
        self.rrf_service = RRFFusionService()
        self.query_expansion = QueryExpansionService()
        self.reranker = RerankerService()
        self._web_search = None
        self._bm25_service: Optional[Bm25Service] = None
        self._bm25_doc_contents: List[str] = []
        self._bm25_doc_metadatas: List[Dict[str, Any]] = []
        self._bm25_lock = threading.Lock()

    def _refresh_metadata_cache(self):
        """
        P1优化：刷新标题元数据和向量缓存（启动时加载一次，入库时增量更新）
        """
        try:
            results = self.full_doc_store.collection.get()
            if not results or not results.get('metadatas'):
                logger.warning("向量库中没有全文档，标题缓存为空")
                return

            self._title_metadata_cache = []
            self._title_vector_cache = {}
            titles_for_idf = []

            for i, metadata in enumerate(results['metadatas']):
                title = metadata.get('title', '')
                if not title:
                    continue

                self._title_metadata_cache.append({
                    'title': title,
                    'path': metadata.get('path', ''),
                    'title_vector_json': metadata.get('title_vector_json')
                })

                # 反序列化标题向量并缓存
                title_vector_json = metadata.get('title_vector_json')
                if title_vector_json:
                    try:
                        vec = json.loads(title_vector_json)
                        if isinstance(vec, list) and len(vec) > 0:
                            self._title_vector_cache[title] = np.array(vec)
                    except (json.JSONDecodeError, ValueError):
                        pass

                titles_for_idf.append(title)

            # 预计算 IDF 表
            self._compute_idf_table(titles_for_idf)

            logger.info(f"标题缓存已加载: {len(self._title_metadata_cache)} 条, 向量缓存 {len(self._title_vector_cache)} 条, IDF 词数 {len(self._idf_table)}")

        except Exception as e:
            logger.error(f"加载标题缓存失败: {str(e)}")

    def _compute_idf_table(self, titles: List[str]):
        """
        P1优化：预计算 IDF 表（用于 BM25 打分）
        IDF = log(N / df) 其中 N 是文档总数，df 是包含该词的文档数
        """
        if not titles:
            return

        N = len(titles)
        doc_freq: Dict[str, int] = {}  # word -> document frequency

        for title in titles:
            # 对标题分词，统计每个词出现在多少文档中
            words = set(jieba.cut(title))  # 使用 set 去重，同一文档中多次出现只计一次
            for word in words:
                if len(word) >= 2:  # 过滤短词
                    doc_freq[word] = doc_freq.get(word, 0) + 1

        # 计算 IDF
        for word, df in doc_freq.items():
            # 使用平滑 IDF 公式: log((N + 1) / (df + 0.5)) + 1
            self._idf_table[word] = np.log((N + 1) / (df + 0.5)) + 1

    def get_cached_title_vector(self, title: str) -> np.ndarray:
        """
        P1优化：从缓存获取标题向量，避免每次查询都解析 JSON
        """
        return self._title_vector_cache.get(title)

    def refresh_cache(self):
        """
        刷新所有缓存（入库后调用）
        """
        self._query_cache.clear()
        self._refresh_metadata_cache()
        self._bm25_service = None
        self._bm25_doc_contents = []
        self._bm25_doc_metadatas = []
        logger.info("所有缓存已刷新")

    def _get_cache_key(self, user_question: str) -> str:
        """
        生成缓存键（使用问题文本的 MD5 哈希）
        Args:
            user_question: 用户问题

        Returns:
            str: 缓存键
        """
        return hashlib.md5(user_question.encode()).hexdigest()

    def clear_cache(self):
        """
        清空查询缓存
        """
        self._query_cache.clear()
        logger.info("查询缓存已清空")

    def retrieval(self, user_question: str) -> List[Document]:
        """
        根据用户问题进行检索（带缓存）
        Args:
            user_question: 用户问题

        Returns:
            List[Document]: 检索结果，返回一个文档列表
        """
        cache_key = self._get_cache_key(user_question)

        # 使用 get() 安全访问缓存
        cached_result = self._query_cache.get(cache_key)
        if cached_result is not None:
            logger.info(f"命中缓存: {user_question[:20]}...")
            return cached_result

        # 执行检索
        result = self._do_retrieval(user_question)

        # 存入缓存
        self._query_cache[cache_key] = result
        logger.info(f"检索结果已缓存: {user_question[:20]}...")

        return result

    def retrieval_with_steps(
        self,
        user_question: str,
        on_step: StepCallback = None
    ) -> Tuple[List[Document], List[StepEvent]]:
        """
        带步骤回调的检索方法（用于 SSE 实时推送）

        Args:
            user_question: 用户问题
            on_step: 步骤回调函数，每个步骤开始/结束时调用

        Returns:
            Tuple[List[Document], List[StepEvent]]: 检索结果 + 所有步骤事件列表
        """
        events: List[StepEvent] = []

        def emit(step: str, status: str, **kwargs):
            """发射步骤事件"""
            event = StepEvent(step=step, status=status, **kwargs)
            events.append(event)
            if on_step:
                on_step(event)

        # ---- 步骤1: 查询理解 ----
        t0 = time.perf_counter()
        emit("query_understanding", "started")

        expanded_queries = self.query_expansion.expand(user_question)
        # 修复：expand()只返回扩展结果，queries_to_embed只需原问题+扩展查询
        queries_to_embed = [user_question] + expanded_queries[:settings.MAX_EXPANSION_QUERIES]
        all_query_vectors = self.chroma_vector.embedd_documents(queries_to_embed)
        question_vector = all_query_vectors[0]

        emit("query_understanding", "completed",
             duration_ms=int((time.perf_counter() - t0) * 1000),
             detail={"expanded_queries": expanded_queries[:3]})

        # ---- 步骤2: 知识检索 ----
        t1 = time.perf_counter()
        emit("knowledge_retrieval", "started")

        all_candidates = []
        # 修复：expand() 只返回扩展结果，需把原问题加入处理列表
        queries_to_process = [user_question] + expanded_queries[:settings.MAX_EXPANSION_QUERIES]

        def _search_one_query_step(idx_and_query):
            idx, query = idx_and_query
            qv = all_query_vectors[idx] if idx < len(all_query_vectors) else question_vector
            v_docs = self._search_base_vector(query, precomputed_vector=qv)
            t_docs = self._search_title(query, precomputed_question_vector=question_vector)
            bm25_docs = self._search_bm25(query)
            return self.rrf_service.fusion([v_docs, t_docs, bm25_docs])

        with ThreadPoolExecutor(max_workers=settings.PARALLEL_WORKERS) as executor:
            futures = [executor.submit(_search_one_query_step, (i, q))
                       for i, q in enumerate(queries_to_process)]
            for future in as_completed(futures):
                all_candidates.extend(future.result())

        # 关键词召回（已禁用：$contains子串匹配噪声高，边际收益低）
        # keyword_docs = self._keyword_search(user_question)
        # all_candidates.extend(keyword_docs)
        unique_candidates = self.remove_duplicates(all_candidates)

        emit("knowledge_retrieval", "completed",
             duration_ms=int((time.perf_counter() - t1) * 1000),
             detail={"candidate_count": len(unique_candidates)})

        # ---- 步骤3: 精排筛选 ----
        t2 = time.perf_counter()
        emit("reranking", "started")

        unique_candidates = self._sort_by_score(unique_candidates)
        if settings.ENABLE_RERANK and len(unique_candidates) > 0:
            final_docs = self.reranker.rerank(
                user_question,
                unique_candidates[:settings.TOP_RERANK],
                top_k=settings.TOP_FINAL
            )

            # 检查是否使用了 fallback 排序（没有实际调用 rerank API）
            # 当 rerank API 未配置时，fallback 文档的 rerank_score 是从已有分数复制的
            # 此时不应应用阈值过滤，因为分数含义不同
            rerank_api_available = self.reranker.api_url and len(self.reranker.api_url) > 0

            if rerank_api_available:
                # 分数阈值过滤 + 数量兜底
                filtered = [
                    doc for doc in final_docs
                    if doc.metadata.get('rerank_score', 0) >= settings.RERANK_SCORE_THRESHOLD
                ]
                if len(filtered) < settings.MIN_FINAL_DOCS and len(final_docs) >= settings.MIN_FINAL_DOCS:
                    logger.warning(
                        f"阈值过滤后仅 {len(filtered)} 个文档（阈值={settings.RERANK_SCORE_THRESHOLD}），"
                        f"启用数量兜底保留前 {settings.MIN_FINAL_DOCS} 个"
                    )
                    filtered = final_docs[:settings.MIN_FINAL_DOCS]
                final_docs = filtered
                logger.info(f"分数阈值过滤: 原始{len(final_docs)}个")

            # 如果 rerank API 未配置但 ENABLE_RERANK=True，rerank 会用 fallback sort
            # fallback sort 已经在内部设置了 rerank_score，无需额外过滤
        else:
            final_docs = unique_candidates[:settings.TOP_FINAL]

        # Web Search 兜底：检索结果为空时联网搜索
        if not final_docs and settings.ENABLE_WEB_SEARCH:
            if self._web_search is None:
                self._web_search = WebSearchService(
                    api_key=settings.WEB_SEARCH_API_KEY,
                    max_results=settings.WEB_SEARCH_MAX_RESULTS,
                )
            web_docs = self._web_search.search(user_question)
            if web_docs:
                final_docs = web_docs
                logger.info(f"Web Search 兜底生效: {len(web_docs)} 个结果")

        top_titles = [d.metadata.get('title', '未知') for d in final_docs[:3]]
        emit("reranking", "completed",
             duration_ms=int((time.perf_counter() - t2) * 1000),
             detail={"final_count": len(final_docs), "top_titles": top_titles})

        logger.info(f"检索完成: 扩展查询{len(expanded_queries)}个, 原始候选{len(all_candidates)}个, 唯一候选{len(unique_candidates)}个, 最终{len(final_docs)}个")

        return final_docs, events

    def _do_retrieval(self, user_question: str) -> List[Document]:
        """
        执行优化检索流程

        流程：
        1. 查询扩展 -> 多个查询变体
        2. 每个查询执行双路召回
        3. RRF 融合每路召回结果
        4. 关键词召回（补充）
        5. 合并所有查询的候选集
        6. 去重
        7. Cross-Encoder 精排（可选）
        8. 返回 Top K

        Args:
            user_question: 用户问题

        Returns:
            检索结果文档列表
        """
        try:
            # 1. 查询扩展
            expanded_queries = self.query_expansion.expand(user_question)

            # 2. 批量预计算所有查询向量（一次API调用，避免多次调用）
            # 修复：expand()只返回扩展结果，queries_to_embed只需原问题+扩展查询
            queries_to_embed = [user_question] + expanded_queries[:settings.MAX_EXPANSION_QUERIES]
            all_query_vectors = self.chroma_vector.embedd_documents(queries_to_embed)
            question_vector = all_query_vectors[0]  # 原始问题向量

            # 3. 对每个扩展查询执行检索
            all_candidates = []
            # 修复：expand() 只返回扩展结果，需把原问题加入处理列表
            queries_to_process = [user_question] + expanded_queries[:settings.MAX_EXPANSION_QUERIES]

            def _search_one_query(idx_and_query):
                idx, query = idx_and_query
                qv = all_query_vectors[idx] if idx < len(all_query_vectors) else question_vector
                v_docs = self._search_base_vector(query, precomputed_vector=qv)
                t_docs = self._search_title(query, precomputed_question_vector=question_vector)
                bm25_docs = self._search_bm25(query)
                return self.rrf_service.fusion([v_docs, t_docs, bm25_docs])

            with ThreadPoolExecutor(max_workers=settings.PARALLEL_WORKERS) as executor:
                futures = [executor.submit(_search_one_query, (i, q))
                           for i, q in enumerate(queries_to_process)]
                for future in as_completed(futures):
                    all_candidates.extend(future.result())

            # 4. 关键词召回（已禁用：$contains子串匹配噪声高，边际收益低）
            # keyword_docs = self._keyword_search(user_question)
            # all_candidates.extend(keyword_docs)

            # 5. 去重
            unique_candidates = self.remove_duplicates(all_candidates)

            # 6. 按分数排序（确保关键词召回的高分文档进入前列）
            unique_candidates = self._sort_by_score(unique_candidates)

            # 7. Cross-Encoder 精排（可选）
            if settings.ENABLE_RERANK and len(unique_candidates) > 0:
                # 使用原始问题进行精排
                reranked_docs = self.reranker.rerank(
                    user_question,
                    unique_candidates[:settings.TOP_RERANK],
                    top_k=settings.TOP_FINAL
                )

                # 修复：仅在真实调用rerank API时才应用阈值过滤
                # fallback分数范围0-2，与真实Reranker 0-1不同
                rerank_api_available = self.reranker.api_url and len(self.reranker.api_url) > 0

                if rerank_api_available:
                    # 分数阈值过滤 + 数量兜底
                    filtered = [
                        doc for doc in reranked_docs
                        if doc.metadata.get('rerank_score', 0) >= settings.RERANK_SCORE_THRESHOLD
                    ]
                    if len(filtered) < settings.MIN_FINAL_DOCS and len(reranked_docs) >= settings.MIN_FINAL_DOCS:
                        logger.warning(
                            f"阈值过滤后仅 {len(filtered)} 个文档（阈值={settings.RERANK_SCORE_THRESHOLD}），"
                            f"启用数量兜底保留前 {settings.MIN_FINAL_DOCS} 个"
                        )
                        filtered = reranked_docs[:settings.MIN_FINAL_DOCS]
                    final_docs = filtered
                    logger.info(f"分数阈值过滤: 原始{len(reranked_docs)}个, 过滤后{len(final_docs)}个")
                else:
                    # fallback排序时不过滤
                    final_docs = reranked_docs
            else:
                # 精排关闭或候选为空，直接截取
                final_docs = unique_candidates[:settings.TOP_FINAL]

            # Web Search 兜底：检索结果为空时联网搜索
            if not final_docs and settings.ENABLE_WEB_SEARCH:
                if self._web_search is None:
                    self._web_search = WebSearchService(
                        api_key=settings.WEB_SEARCH_API_KEY,
                        max_results=settings.WEB_SEARCH_MAX_RESULTS,
                    )
                web_docs = self._web_search.search(user_question)
                if web_docs:
                    final_docs = web_docs
                    logger.info(f"Web Search 兜底生效: {len(web_docs)} 个结果")

            logger.info(f"检索完成: 扩展查询{len(expanded_queries)}个, 原始候选{len(all_candidates)}个, 唯一候选{len(unique_candidates)}个, 最终{len(final_docs)}个")
            return final_docs

        except Exception as e:
            logger.warning(f"优化流程异常，降级为基础检索: {e}")
            return self._fallback_retrieval(user_question)

    def _sort_by_score(self, candidates: List[Document]) -> List[Document]:
        """
        按分数排序候选列表

        Args:
            candidates: 文档列表

        Returns:
            List[Document]: 按分数降序排列的文档列表
        """
        if not candidates:
            return []

        def get_score(doc: Document) -> float:
            # 修复：去掉标题匹配的2.0过度加权，RRF已能平衡多路召回
            # 直接使用统一排序分数
            sim_score = doc.metadata.get('similarity_score', 0)
            if sim_score > 0:
                # 标题匹配分数不加额外权重，让RRF和Reranker决定排序
                return sim_score

            # 其次使用向量检索分数
            return doc.metadata.get('normalized_score',
                   doc.metadata.get('rrf_score',
                   doc.metadata.get('rerank_score', 0)))

        return sorted(candidates, key=get_score, reverse=True)

    def _re_score_and_sort(self, unique_candidates: List[Document], user_question: str) -> List[Document]:
        """
        重新打分并排序（使用权重融合）
        Args:
            unique_candidates: 文档列表
            user_question: 用户问题

        Returns:
            List[Document]: 重新打分并排序后的文档列表
        """
        if not unique_candidates:
            return []

        scored_docs = []

        for doc in unique_candidates:
            # 向量检索分数（已归一化）
            vector_score = doc.metadata.get('normalized_score', 0)
            # 标题匹配分数
            title_score = doc.metadata.get('similarity_score', 0)
            # 融合分数
            final_score = settings.VECTOR_WEIGHT * vector_score + settings.TITLE_WEIGHT * title_score
            scored_docs.append((doc, final_score))

        sorted_docs = sorted(scored_docs, key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in sorted_docs[:settings.TOP_FINAL]]

    def _fallback_retrieval(self, user_question: str) -> List[Document]:
        """
        降级检索：原有双路召回 + 固定权重融合

        Args:
            user_question: 用户问题

        Returns:
            检索结果文档列表
        """
        base_vector_candidates = self._search_base_vector(user_question)
        title_candidates = self._search_title(user_question)
        bm25_candidates = self._search_bm25(user_question)
        total_candidates = base_vector_candidates + title_candidates + bm25_candidates
        unique_candidates = self.remove_duplicates(total_candidates)
        return self._re_score_and_sort(unique_candidates, user_question)

    def remove_duplicates(self,docs:List[Document])->List[Document]:
        """
        对文档列表去重
        Args:
            docs: 文档列表

        Returns:
            List[Document]: 去重后的文档列表
        """
        # 判断文档是否为空
        if not docs:
            return []
        # 2、使用集合来存储文档的元数据，确保元数据的唯一性
        seen_metadata = set()
        # 3、遍历合并后的每一个文档项
        unique_candidates = []
        for doc in docs:
            clean_content = re.sub(r'文档来源[：:].*?(?=(\n|#))', '', doc.page_content, flags=re.DOTALL).strip()
            # 使用 get 方法安全访问 title，如果没有则使用 source 或默认值
            title = doc.metadata.get('title', doc.metadata.get('source', '未知来源'))
            key = (title, clean_content[:100])
            if key not in seen_metadata:
                seen_metadata.add(key)
                unique_candidates.append(doc)
        return unique_candidates

    def _search_title(self, user_question: str, precomputed_question_vector: List[float] = None) -> List[Document]:
        """
        基于标题的检索（从向量库获取内容，支持预计算向量复用）
        Args:
            user_question: 用户问题
            precomputed_question_vector: 预计算的问题向量（可选，用于减少 API 调用）

        Returns:
            List[Document]: 检索结果，返回一个文档列表
        """
        # 1、优先从向量库获取全文档元数据
        mds_metadata = self._get_titles_from_full_doc_store()

        # 2、如果向量库为空，回退到磁盘读取
        if not mds_metadata:
            logger.warning("向量库中没有全文档，回退到磁盘读取")
            mds_metadata = MarkDownUtils.collect_md_metadata(settings.CRAWL_OUTPUT_DIR)

        # 3、根据用户问题，匹配标题，粗排
        md_title_matches = self.rank_documents_by_title(mds_metadata, user_question)

        # 4、获取精排后的结果（传入预计算向量）
        final_matches = self.find_ranking(md_title_matches, user_question, precomputed_question_vector=precomputed_question_vector)

        # 5、处理精排返回的数据，返回文档列表
        base_vector_candidates = []
        for find_md_metadata in final_matches:
            try:
                # 5.1、优先从向量库获取完整内容
                title = find_md_metadata['title']
                full_doc = self.full_doc_store.get_by_title(title)

                if full_doc:
                    # 从向量库获取到内容
                    content = full_doc.page_content
                    # 保留向量库中存储的 title_vector_json
                    if 'title_vector_json' in full_doc.metadata:
                        find_md_metadata['title_vector_json'] = full_doc.metadata['title_vector_json']
                else:
                    # 回退到磁盘读取
                    with open(find_md_metadata['path'], 'r', encoding='utf-8') as f:
                        content = f.read().strip()

                # 判断content的内容
                if len(content) < 3000:
                    # 不做切分
                    doc = Document(page_content=content, metadata={
                        "title": find_md_metadata['title'],
                        "path": find_md_metadata['path'],
                        "similarity_score": find_md_metadata.get('sim_score', 0)
                    })
                    base_vector_candidates.append(doc)
                else:
                    # 长文本，做切分（传入预计算向量）
                    doc_chunks = self._deal_long_title_content(content, find_md_metadata, user_question, precomputed_question_vector=precomputed_question_vector)
                    base_vector_candidates.extend(doc_chunks)
            except Exception as e:
                logger.error(f"获取标题出错,原因:{str(e)}")
        return base_vector_candidates

    def _get_titles_from_full_doc_store(self) -> List[Dict[str, Any]]:
        """
        P1优化：从缓存获取标题元数据（避免每次查询都调用 collection.get()）
        Returns:
            List[Dict[str, Any]]: 标题元数据列表
        """
        # 直接返回缓存，如果缓存为空则刷新
        if not self._title_metadata_cache:
            self._refresh_metadata_cache()
        return self._title_metadata_cache


    def _search_base_vector(self, user_question: str, precomputed_vector: List[float] = None) -> List[Document]:
        """
        基于嵌入模型的向量检索（返回归一化分数）
        Args:
            user_question: 用户问题
            precomputed_vector: 预计算的向量（可选，避免重复API调用）

        Returns:
            List[Document]: 检索结果，返回一个文档列表
        """
        documents_with_score = self.chroma_vector.search_similarity_with_score(
            user_question, k=settings.TOP_ROUGH, precomputed_vector=precomputed_vector
        )
        base_vector_candidates = []
        for document, distance in documents_with_score:
            # 将L2距离归一化为相似度分数
            normalized_score = normalize_vector_score(distance)
            document.metadata['normalized_score'] = normalized_score
            base_vector_candidates.append(document)

        return base_vector_candidates

    def _keyword_search(self, user_question: str) -> List[Document]:
        """
        关键词召回：直接在向量库文档内容中搜索关键词

        用于补充向量召回可能遗漏的内容（如标题不匹配但内容相关的文档）

        Args:
            user_question: 用户问题

        Returns:
            List[Document]: 包含关键词的文档列表
        """
        # 提取问题中的关键词（使用 jieba 分词，过滤短词）
        keywords = [word for word in jieba.cut(user_question) if len(word) >= 2]

        if not keywords:
            return []

        keyword_docs = []

        try:
            # 对每个关键词在向量库中搜索（减少数量，避免噪音）
            for keyword in keywords[:3]:  # 最多搜索3个关键词
                try:
                    results = self.chroma_vector.vector_database._collection.get(
                        where_document={"$contains": keyword},
                        include=["documents", "metadatas"],
                        limit=5  # 每个关键词最多5条（减少噪音）
                    )

                    for i, (doc_content, meta) in enumerate(zip(results.get("documents", []), results.get("metadatas", []))):
                        # 关键词匹配分数较低，仅作为补充召回
                        keyword_score = 0.5  # 较低的分数，不主导排序
                        doc = Document(
                            page_content=doc_content,
                            metadata={**meta, "keyword_match": keyword, "normalized_score": keyword_score}
                        )
                        keyword_docs.append(doc)

                except Exception as e:
                    logger.warning(f"关键词搜索失败: {keyword}, {e}")
                    continue

            logger.info(f"关键词召回: 关键词{keywords[:3]}, 结果{len(keyword_docs)}条")

        except Exception as e:
            logger.warning(f"关键词召回失败: {e}")

        return keyword_docs

    def _ensure_bm25_index(self):
        if self._bm25_service is not None and self._bm25_doc_contents:
            return

        with self._bm25_lock:
            if self._bm25_service is not None and self._bm25_doc_contents:
                return

            try:
                results = self.full_doc_store.collection.get(include=["documents", "metadatas"])
                if not results or not results.get('documents'):
                    logger.warning("BM25 索引构建失败：全文档库为空")
                    return

                self._bm25_doc_contents = results['documents']
                self._bm25_doc_metadatas = results.get('metadatas', [])
                self._bm25_service = Bm25Service()
                self._bm25_service.rebuild_index(self._bm25_doc_contents)
                logger.info(f"BM25 索引已构建: {len(self._bm25_doc_contents)} 篇文档")
            except Exception as e:
                logger.warning(f"BM25 索引构建异常: {e}")

    def _search_bm25(self, user_question: str) -> List[Document]:
        if not settings.BM25_ENABLED:
            return []

        self._ensure_bm25_index()
        if self._bm25_service is None or not self._bm25_doc_contents:
            return []

        results = self._bm25_service.search(user_question, top_k=settings.BM25_TOP_K)
        docs = []
        max_score = max(s[1] for s in results) if results else 1.0

        for idx, score in results:
            content = self._bm25_doc_contents[idx]
            meta = {}
            if idx < len(self._bm25_doc_metadatas):
                src = self._bm25_doc_metadatas[idx]
                meta["title"] = src.get("title", "")
                meta["path"] = src.get("path", "")
            meta["normalized_score"] = score / max_score if max_score > 0 else 0
            meta["bm25_raw_score"] = score
            doc = Document(page_content=content, metadata=meta)
            docs.append(doc)
        return docs

    def rank_documents_by_title(self, mds_metadata: List[Dict[str, Any]], user_question: str) -> List[Dict[str, Any]]:
        """
        根据标题匹配用户问题（Jaccard + BM25 混合粗排）
        Args:
            mds_metadata: markdown文档元数据
            user_question: 用户问题

        Returns:
            List[Dict[str,Any]]: 匹配结果，返回一个字典列表，包含标题和路径
        """
        # 1、用户输入是否存在
        if not user_question:
            return []

        # 计算平均标题长度（用于 BM25）
        titles = [md.get('title', '') for md in mds_metadata if md.get('title', '')]
        avg_title_length = sum(len(list(jieba.cut(t))) for t in titles) / len(titles) if titles else settings.BM25_AVG_TITLE_LENGTH

        # 2、遍历markdown文档元数据，匹配标题
        for md_metadata in mds_metadata:
            # 2.1、获取md的标题
            md_metadata_title = md_metadata.get('title', '')
            # 2.2、判断标题是否存在
            if not md_metadata_title or not md_metadata_title.strip():
                md_metadata['rank_score'] = 0
                md_metadata['bm25_score'] = 0
                continue

            # 2.3.1：字符级 Jaccard（权重 0.2）
            user_question_char = set(user_question)
            md_metadata_title_char = set(md_metadata_title)
            unique_char = user_question_char | md_metadata_title_char
            char_score = len(user_question_char & md_metadata_title_char) / len(unique_char) if len(unique_char) > 0 else 0

            # 2.3.2：词项级 Jaccard（权重 0.3）
            user_question_words = set(jieba.lcut(user_question))
            md_metadata_words = set(jieba.lcut(md_metadata_title))
            unique_word = user_question_words | md_metadata_words
            word_score = len(user_question_words & md_metadata_words) / len(unique_word) if len(unique_word) > 0 else 0

            # 2.3.3：BM25 TF-IDF 分数（权重 0.5）
            bm25_score = self._compute_bm25_title_score(
                user_question, md_metadata_title, avg_title_length
            )

            # 3、计算综合粗排分数：Jaccard (0.2+0.3) + BM25 (0.5)
            rank_score = char_score * 0.2 + word_score * 0.3 + bm25_score * 0.5
            md_metadata['rank_score'] = rank_score
            md_metadata['bm25_score'] = bm25_score  # 保存供后续分析

        # 4、按得分排序并过滤低分结果
        sorted_mds = sorted(mds_metadata, key=lambda x: x.get('rank_score', 0), reverse=True)
        # 过滤掉得分为0的结果
        return [md for md in sorted_mds if md.get('rank_score', 0) > 0]

    def _compute_bm25_title_score(
        self,
        user_question: str,
        title: str,
        avg_title_length: float,
        k1: float = None,
        b: float = None
    ) -> float:
        """
        P1优化：计算 BM25 标题匹配分数（加入 IDF 组件）

        BM25 公式:
        score = Σ IDF(w) * tf*(k1+1) / (tf + k1*(1-b+b*L/L_avg))

        Args:
            user_question: 用户问题
            title: 标题文本
            avg_title_length: 平均标题长度
            k1: BM25 参数，控制词频饱和（默认从 settings 获取）
            b: BM25 参数，控制长度惩罚（默认从 settings 获取）

        Returns:
            float: BM25 分数 (范围 0-1)
        """
        k1 = k1 or settings.BM25_K1
        b = b or settings.BM25_B

        question_words = list(jieba.cut(user_question))
        title_words = list(jieba.cut(title))
        title_length = len(title_words)

        # 计算标题词频
        title_word_freq = {}
        for word in title_words:
            title_word_freq[word] = title_word_freq.get(word, 0) + 1

        score = 0.0
        matched_terms = 0
        max_idf = max(self._idf_table.values()) if self._idf_table else 5.0  # 用于归一化

        for word in question_words:
            if word in title_word_freq:
                matched_terms += 1
                tf = title_word_freq[word]
                # P1优化：从预计算的 IDF 表获取权重
                idf = self._idf_table.get(word, 1.0)  # 默认 IDF 为 1（中等权重）
                # BM25 公式（加入 IDF）
                numerator = idf * tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * title_length / avg_title_length)
                score += numerator / denominator

        # 归一化到 0-1 范围
        if matched_terms == 0 or len(question_words) == 0:
            return 0.0

        # 使用最大可能的 IDF * TF 分数作为归一化因子
        max_possible_score = max_idf * len(question_words) * (k1 + 1)
        return min(score / max_possible_score, 1.0)

    def find_ranking(self, md_title_matches: List[Dict[str, Any]], user_question: str, precomputed_question_vector: List[float] = None) -> List[Dict[str, Any]]:
        """
        精排：使用 RRF 融合粗排和精排结果

        Args:
            md_title_matches: 粗排标题匹配结果
            user_question: 用户问题
            precomputed_question_vector: 预计算的问题向量（可选）

        Returns:
            精排后的元数据列表
        """
        if not md_title_matches:
            return []

        # 1. 对问题向量化
        if precomputed_question_vector:
            user_question_vector = precomputed_question_vector
        else:
            user_question_vector = self.chroma_vector.embedd_document(user_question)

        # 2. 获取标题向量（P1优化：优先使用缓存中的向量）
        title_vectors = [None] * len(md_title_matches)
        titles_to_embed = []
        titles_to_embed_indices = []

        for idx, md_metadata in enumerate(md_title_matches):
            title = md_metadata.get('title', '')
            # P1优化：优先从缓存获取向量（numpy 数组，无需解析 JSON）
            cached_vec = self._title_vector_cache.get(title)
            if cached_vec is not None and len(cached_vec) == len(user_question_vector):
                title_vectors[idx] = cached_vec.tolist()
            else:
                # 缓存中没有，尝试从 metadata 的 JSON 解析
                cached_json = md_metadata.get('title_vector_json')
                if cached_json:
                    try:
                        vec = json.loads(cached_json)
                        if isinstance(vec, list) and len(vec) == len(user_question_vector):
                            title_vectors[idx] = vec
                        else:
                            titles_to_embed.append(title)
                            titles_to_embed_indices.append(idx)
                    except json.JSONDecodeError:
                        titles_to_embed.append(title)
                        titles_to_embed_indices.append(idx)
                else:
                    titles_to_embed.append(title)
                    titles_to_embed_indices.append(idx)

        # 只对少数需要重新生成的标题调用API（通常很少）
        if titles_to_embed:
            try:
                new_vectors = self.chroma_vector.embedd_documents(titles_to_embed)
                for i, vec_idx in enumerate(titles_to_embed_indices):
                    title_vectors[vec_idx] = new_vectors[i]
            except Exception as e:
                logger.warning(f"批量生成标题向量失败: {e}")

        # 3. 计算向量相似度（过滤掉None值）
        valid_vectors = [(idx, v) for idx, v in enumerate(title_vectors) if v is not None]
        if valid_vectors:
            try:
                vector_indices = [item[0] for item in valid_vectors]
                vector_list = [item[1] for item in valid_vectors]
                similarity = cosine_similarity([user_question_vector], vector_list).flatten()

                # 将相似度映射回原始索引
                for sim_idx, orig_idx in enumerate(vector_indices):
                    md_title_matches[orig_idx]['sim_score'] = max(0, similarity[sim_idx])

                # 无效向量的文档使用粗排分数
                for idx, md_metadata in enumerate(md_title_matches):
                    if idx not in vector_indices:
                        md_metadata['sim_score'] = md_metadata.get('rank_score', 0)
            except Exception as e:
                logger.warning(f"向量相似度计算失败: {e}")
                for md_metadata in md_title_matches:
                    md_metadata['sim_score'] = md_metadata.get('rank_score', 0)
        else:
            # 无有效向量，使用粗排分数
            for md_metadata in md_title_matches:
                md_metadata['sim_score'] = md_metadata.get('rank_score', 0)

        # 4. 构建粗排结果（按 rank_score 排序）
        rough_ranked = sorted(md_title_matches, key=lambda x: x.get('rank_score', 0), reverse=True)

        # 5. 构建精排结果（按 sim_score 排序）
        precise_ranked = sorted(md_title_matches, key=lambda x: x.get('sim_score', 0), reverse=True)

        # 6. 使用 RRF 融合粗排和精排
        fused_result = self.rrf_service.fusion_metadata([rough_ranked, precise_ranked])

        return fused_result[:20]

    def _deal_long_title_content(self, content: str, find_md_metadata: Dict[str, Any], user_question: str, precomputed_question_vector: List[float] = None) -> List[Document]:
        """
        处理标题对应的长文本内容
        切分
        Args:
            content: 文本内容
            find_md_metadata: 匹配的元数据
            user_question: 用户问题
            precomputed_question_vector: 预计算的问题向量（可选，用于减少 API 调用）

        Returns:
            List[Document]: 文档列表
        """
        # 1、对长文本进行切分
        doc_chunks = self.spliter.text_splitter.split_text(content)
        # 2、获取对应的标题
        title = find_md_metadata['title']
        # 3、将标题注入到切分后的文档块中
        doc_chunks_inject_title = [f'文档来源：{title}'+ doc_chunk for doc_chunk in doc_chunks]

        # 4、对用户输入的问题向量化（复用预计算向量）
        if precomputed_question_vector:
            user_question_vector = precomputed_question_vector
        else:
            user_question_vector = self.chroma_vector.embedd_document(user_question)
        # 5、对切分后的文档向量化
        doc_chunks_vector = self.chroma_vector.embedd_documents(doc_chunks_inject_title)
        # 6、计算余弦相似度
        similarity = cosine_similarity([user_question_vector], doc_chunks_vector).flatten()
        # 7、获取三个相似性分数值高的索引经过argsort()排序 [1,2,0] --- [0,1,2]
        top_indices = similarity.argsort()[-3:][::-1]
        # 8、构建最终的文档对象（为每一个chunk）
        top_documents = []
        for index,chunk_index in enumerate(top_indices):
            doc = Document(
                page_content=doc_chunks_inject_title[chunk_index],
                metadata={
                    "title": find_md_metadata['title'],
                    "path": find_md_metadata['path'],
                    "chunk_index": int(chunk_index),
                    "similarity_score":float(similarity[chunk_index]),
                }
            )
            top_documents.append(doc)
        return top_documents


if __name__ == '__main__':
    retrieval_service = RetrievalService()
    # 先收集元数据，再进行标题匹配
    mds_metadata = MarkDownUtils.collect_md_metadata(settings.CRAWL_OUTPUT_DIR)
    results = retrieval_service.rank_documents_by_title(mds_metadata, '电脑黑屏了怎么办？')
    print(f"匹配结果数: {len(results)}")
    for r in results[:5]:
        print(f"标题: {r['title']}, 得分: {r['rank_score']:.4f}")