# backend/its_knowledge/services/rrf_fusion_service.py
import hashlib
from typing import List, Dict, Any
from langchain_core.documents import Document

from backend.its_knowledge.config.settings import settings


class RRFFusionService:
    """
    RRF (Reciprocal Rank Fusion) 多路召回融合服务

    RRF 公式: score(d) = Σ 1/(k + rank_i(d))
    其中 k 为常数（默认60），rank_i(d) 为文档 d 在第 i 路召回中的排名位置
    """

    def __init__(self, k: int = None):
        self.k = k or settings.RRF_K

    def fusion(self, ranked_lists: List[List[Document]]) -> List[Document]:
        """
        RRF 融合多路召回结果

        Args:
            ranked_lists: 多路召回的文档列表（每路已按分数排序）

        Returns:
            融合后的文档列表（按 RRF 分数降序）
        """
        if not ranked_lists:
            return []

        # 合并所有列表并去重
        all_docs = []
        for lst in ranked_lists:
            all_docs.extend(lst)

        if not all_docs:
            return []

        # 计算每个文档的 RRF 分数
        rrf_scores: Dict[str, float] = {}
        doc_map: Dict[str, Document] = {}

        for ranked_list in ranked_lists:
            for rank, doc in enumerate(ranked_list, start=1):
                doc_key = self._get_doc_key(doc)

                if doc_key not in rrf_scores:
                    rrf_scores[doc_key] = 0.0
                    doc_map[doc_key] = doc

                # 累加 RRF 分数
                rrf_scores[doc_key] += 1.0 / (self.k + rank)

        # 按分数降序排序
        sorted_keys = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        from copy import deepcopy
        return [deepcopy(doc_map[key]) for key in sorted_keys]

    def fusion_metadata(self, ranked_lists: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        RRF 融合元数据列表（用于标题召回内部融合）

        Args:
            ranked_lists: 多路召回的元数据列表（每路已按分数排序）

        Returns:
            融合后的元数据列表（按 RRF 分数降序）
        """
        if not ranked_lists:
            return []

        # 合并所有列表
        all_mds = []
        for lst in ranked_lists:
            all_mds.extend(lst)

        if not all_mds:
            return []

        # 计算每个元数据的 RRF 分数
        rrf_scores: Dict[str, float] = {}
        md_map: Dict[str, Dict[str, Any]] = {}

        for ranked_list in ranked_lists:
            for rank, md in enumerate(ranked_list, start=1):
                md_key = self._get_metadata_key(md)

                if md_key not in rrf_scores:
                    rrf_scores[md_key] = 0.0
                    md_map[md_key] = md

                rrf_scores[md_key] += 1.0 / (self.k + rank)

        # 按分数降序排序
        sorted_keys = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        from copy import deepcopy
        return [deepcopy(md_map[key]) for key in sorted_keys]

    def _get_doc_key(self, doc: Document) -> str:
        """生成文档唯一标识（用于去重和分数累加）"""
        title = doc.metadata.get('title', '')
        content_hash = hashlib.md5(doc.page_content[:200].encode()).hexdigest()[:8]
        return f"{title}:{content_hash}"

    def _get_metadata_key(self, md: Dict[str, Any]) -> str:
        """生成元数据唯一标识"""
        title = md.get('title', '')
        path = md.get('path', '')
        return f"{title}:{path}"