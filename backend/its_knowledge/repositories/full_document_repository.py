# backend/its_knowledge/repositories/full_document_repository.py
import json
import sqlite3
import threading
import os
from typing import List, Optional, Tuple, Dict, Any

from langchain_chroma import Chroma
from langchain_core.documents import Document

from backend.its_knowledge.config.settings import settings
from langchain_openai.embeddings import OpenAIEmbeddings
import logging

logger = logging.getLogger(__name__)


class FullDocumentRepository:
    """
    全文档集合仓储
    存储文档完整内容，用于标题检索时快速获取
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._init_db()

        self.embedding = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            openai_api_key=settings.API_KEY,
            openai_api_base=settings.BASE_URL,
        )
        self.collection = Chroma(
            persist_directory=settings.VECTOR_STORE_PATH,
            collection_name=settings.FULL_DOC_COLLECTION,
            embedding_function=self.embedding
        )

        # 存量迁移：将 Chroma 中已有的文档索引写入 SQLite（仅首次为空时执行）
        self._migrate_from_chroma()

    def _init_db(self):
        """初始化 SQLite 文档索引表"""
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(project_root, "data", "analytics.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS document_index (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    path TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_doc_title ON document_index(title)"
            )
        logger.info(f"SQLite 文档索引表已就绪: {self.db_path}")

    def _migrate_from_chroma(self):
        """将 Chroma 中已有的全文档元数据迁移到 SQLite 索引表（仅首次执行）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute("SELECT COUNT(*) FROM document_index").fetchone()
                if row[0] > 0:
                    return  # 已有索引数据，无需迁移

            results = self.collection.get(include=["metadatas"])
            if not results or not results.get('metadatas'):
                return

            docs_to_insert = []
            for i, meta in enumerate(results['metadatas']):
                doc_id = results['ids'][i] if results.get('ids') else f"legacy_{i}"
                title = meta.get('title', '') or ''
                path = meta.get('path', '') or ''
                docs_to_insert.append((doc_id, title, path))

            if docs_to_insert:
                with self._lock:
                    with sqlite3.connect(self.db_path) as conn:
                        conn.executemany(
                            "INSERT OR IGNORE INTO document_index (id, title, path) VALUES (?, ?, ?)",
                            docs_to_insert
                        )
                logger.info(f"已从 Chroma 迁移 {len(docs_to_insert)} 条文档索引到 SQLite")
        except Exception as e:
            logger.warning(f"Chroma -> SQLite 数据迁移跳过（不影响新文档入库）: {e}")

    def add_document(self, content: str, title: str, path: str, title_vector: List[float]) -> Optional[str]:
        doc = Document(
            page_content=content,
            metadata={
                "title": title,
                "path": path,
                "title_vector_json": json.dumps(title_vector)
            }
        )
        ids = self.collection.add_documents([doc])
        doc_id = ids[0] if ids else None

        # 同步写入 SQLite 索引
        if doc_id:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO document_index (id, title, path) VALUES (?, ?, ?)",
                        (doc_id, title, path)
                    )

        logger.info(f"全文档已存储: {title}")
        return doc_id

    def get_by_title(self, title: str) -> Optional[Document]:
        results = self.collection.get(where={"title": title})
        if results and results.get("documents"):
            return Document(
                page_content=results["documents"][0],
                metadata=results["metadatas"][0]
            )
        return None

    def get_by_titles(self, titles: List[str]) -> List[Document]:
        documents = []
        for title in titles:
            doc = self.get_by_title(title)
            if doc:
                documents.append(doc)
        return documents

    def delete_by_title(self, title: str) -> bool:
        doc = self.get_by_title(title)
        if not doc:
            return False
        try:
            results = self.collection.get(where={"title": title})
            if results and results.get("ids"):
                self.collection.delete(ids=results["ids"])
                # 同步从 SQLite 删除
                with self._lock:
                    with sqlite3.connect(self.db_path) as conn:
                        conn.execute(
                            "DELETE FROM document_index WHERE title = ?",
                            (title,)
                        )
                logger.info(f"全文档已删除: {title}")
                return True
        except Exception as e:
            logger.error(f"删除全文档失败: {title}, 原因: {e}")
        return False

    def count(self) -> int:
        """从 SQLite 索引获取文档总数，避免 Chroma 全量加载"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute("SELECT COUNT(*) FROM document_index").fetchone()
                return row[0]
        except Exception as e:
            logger.error(f"SQLite count 失败，回退到 Chroma: {e}")
            return self.collection._collection.count()

    def list_all(self, offset: int = 0, limit: int = 20, search: str = None) -> Tuple[List[Dict[str, Any]], int]:
        """从 SQLite 索引分页查询，支持标题模糊搜索，O(1) 内存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if search:
                    pattern = f"%{search}%"
                    count_row = conn.execute(
                        "SELECT COUNT(*) FROM document_index WHERE title LIKE ?",
                        (pattern,)
                    ).fetchone()
                    total = count_row[0]
                    rows = conn.execute(
                        "SELECT id, title, path FROM document_index "
                        "WHERE title LIKE ? ORDER BY title LIMIT ? OFFSET ?",
                        (pattern, limit, offset)
                    ).fetchall()
                else:
                    count_row = conn.execute(
                        "SELECT COUNT(*) FROM document_index"
                    ).fetchone()
                    total = count_row[0]
                    rows = conn.execute(
                        "SELECT id, title, path FROM document_index "
                        "ORDER BY title LIMIT ? OFFSET ?",
                        (limit, offset)
                    ).fetchall()
        except Exception as e:
            logger.error(f"SQLite list_all 失败，回退到 Chroma 全量查询: {e}")
            return self._list_all_fallback(offset, limit, search)

        docs = [
            {"id": r[0], "title": r[1], "path": r[2]}
            for r in rows
        ]
        return docs, total

    def _list_all_fallback(self, offset: int = 0, limit: int = 20, search: str = None) -> Tuple[List[Dict[str, Any]], int]:
        """回退方案：使用 Chroma 全量查询（原实现）"""
        results = self.collection.get(include=["metadatas"])
        if not results or not results.get('metadatas'):
            return [], 0

        docs = []
        for i, meta in enumerate(results['metadatas']):
            title = meta.get('title', '')
            if search and search.lower() not in title.lower():
                continue
            docs.append({
                'id': results['ids'][i] if results.get('ids') else str(i),
                'title': title,
                'path': meta.get('path', ''),
            })
        total = len(docs)
        return docs[offset:offset + limit], total

    def get_preview(self, title: str, max_chars: int = 1000) -> Optional[str]:
        """获取文档内容预览"""
        doc = self.get_by_title(title)
        if doc:
            return doc.page_content[:max_chars]
        return None