"""查询统计分析服务 — SQLite 存储"""

import sqlite3
import time
import threading
import os
from typing import Dict, Any


class AnalyticsService:
    def __init__(self, db_path: str = None):
        if db_path is None:
            project_root = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
            db_path = os.path.join(project_root, "data", "analytics.db")

        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS query_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT,
                    question TEXT NOT NULL,
                    answer_length INTEGER DEFAULT 0,
                    num_sources INTEGER DEFAULT 0,
                    duration_ms INTEGER DEFAULT 0,
                    candidate_count INTEGER DEFAULT 0,
                    final_count INTEGER DEFAULT 0,
                    web_search_used INTEGER DEFAULT 0,
                    cache_hit INTEGER DEFAULT 0
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ts ON query_events(timestamp)"
            )
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    message_id TEXT,
                    session_id TEXT,
                    question TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    comment TEXT DEFAULT '',
                    sources TEXT DEFAULT '',
                    source_titles TEXT DEFAULT '',
                    review_status TEXT DEFAULT 'pending'
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fb_ts ON feedback_events(timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fb_rating ON feedback_events(rating)"
            )

    def record_query(
        self, question: str, session_id: str = None,
        answer_length: int = 0, num_sources: int = 0,
        duration_ms: int = 0, candidate_count: int = 0,
        final_count: int = 0, web_search_used: bool = False,
        cache_hit: bool = False,
    ):
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO query_events
                    (timestamp, session_id, question, answer_length,
                     num_sources, duration_ms, candidate_count,
                     final_count, web_search_used, cache_hit)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    time.strftime("%Y-%m-%d %H:%M:%S"), session_id,
                    question, answer_length, num_sources, duration_ms,
                    candidate_count, final_count,
                    1 if web_search_used else 0, 1 if cache_hit else 0,
                ))

    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM query_events "
                "WHERE timestamp >= date('now', ?)",
                (f'-{days} days',)
            ).fetchone()[0]

            avg_dur = conn.execute(
                "SELECT AVG(duration_ms) FROM query_events "
                "WHERE timestamp >= date('now', ?)",
                (f'-{days} days',)
            ).fetchone()[0] or 0

            avg_src = conn.execute(
                "SELECT AVG(final_count) FROM query_events "
                "WHERE timestamp >= date('now', ?)",
                (f'-{days} days',)
            ).fetchone()[0] or 0

            daily = conn.execute("""
                SELECT date(timestamp) as day, COUNT(*) as cnt,
                       AVG(duration_ms) as avg_dur
                FROM query_events
                WHERE timestamp >= date('now', ?)
                GROUP BY day ORDER BY day
            """, (f'-{days} days',)).fetchall()

            ws_rate = conn.execute(
                "SELECT COUNT(*) FROM query_events "
                "WHERE web_search_used=1 AND timestamp >= date('now', ?)",
                (f'-{days} days',)
            ).fetchone()[0]

            cache_hits = conn.execute(
                "SELECT COUNT(*) FROM query_events "
                "WHERE cache_hit=1 AND timestamp >= date('now', ?)",
                (f'-{days} days',)
            ).fetchone()[0]

            return {
                "total_queries": total,
                "avg_duration_ms": round(avg_dur, 1),
                "avg_sources": round(avg_src, 1),
                "web_search_rate_pct": round(
                    ws_rate / max(total, 1) * 100, 1
                ),
                "cache_hit_rate_pct": round(
                    cache_hits / max(total, 1) * 100, 1
                ),
                "daily_counts": [
                    {"date": d, "count": c, "avg_duration_ms": round(a, 1)}
                    for d, c, a in daily
                ],
            }

    def record_feedback(
        self, message_id: str = "", session_id: str = "",
        question: str = "", rating: str = "",
        comment: str = "", sources: str = "",
    ):
        """记录用户反馈到 feedback_events 表"""
        # 解析 sources JSON 数组，提取标题列表
        source_titles = ""
        if sources:
            try:
                src_list = json.loads(sources) if isinstance(sources, str) else sources
                if isinstance(src_list, list):
                    source_titles = ",".join(src_list)
            except (json.JSONDecodeError, TypeError):
                source_titles = str(sources)

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO feedback_events
                    (timestamp, message_id, session_id, question, rating, comment, sources, source_titles)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    time.strftime("%Y-%m-%d %H:%M:%S"), message_id,
                    session_id, question, rating, comment,
                    str(sources), source_titles,
                ))

    def get_feedback_stats(self, days: int = 7) -> Dict[str, Any]:
        """获取反馈统计（正面/负面比例、高负反馈文档、低分查询示例）"""
        with sqlite3.connect(self.db_path) as conn:
            # 反馈总数和比例
            total_fb = conn.execute(
                "SELECT COUNT(*) FROM feedback_events "
                "WHERE timestamp >= date('now', ?)",
                (f'-{days} days',)
            ).fetchone()[0]

            positive = conn.execute(
                "SELECT COUNT(*) FROM feedback_events "
                "WHERE rating = 'positive' AND timestamp >= date('now', ?)",
                (f'-{days} days',)
            ).fetchone()[0]

            negative = conn.execute(
                "SELECT COUNT(*) FROM feedback_events "
                "WHERE rating = 'negative' AND timestamp >= date('now', ?)",
                (f'-{days} days',)
            ).fetchone()[0]

            # 高负反馈文档 Top 10（按 source_titles 分组统计负面反馈次数）
            negative_docs = conn.execute("""
                SELECT source_titles, COUNT(*) as neg_count
                FROM feedback_events
                WHERE rating = 'negative'
                  AND source_titles != ''
                  AND timestamp >= date('now', ?)
                GROUP BY source_titles
                ORDER BY neg_count DESC
                LIMIT 10
            """, (f'-{days} days',)).fetchall()

            # 低分查询示例（最近10条负面反馈）
            negative_queries = conn.execute("""
                SELECT question, comment, source_titles, timestamp
                FROM feedback_events
                WHERE rating = 'negative'
                  AND timestamp >= date('now', ?)
                ORDER BY timestamp DESC
                LIMIT 10
            """, (f'-{days} days',)).fetchall()

            # 待审核文档：累计 5 次以上负面反馈的文档
            pending_review = conn.execute("""
                SELECT source_titles, COUNT(*) as neg_count
                FROM feedback_events
                WHERE rating = 'negative' AND source_titles != ''
                GROUP BY source_titles
                HAVING COUNT(*) >= 5
                ORDER BY neg_count DESC
            """).fetchall()

            # 每日反馈趋势
            daily_fb = conn.execute("""
                SELECT date(timestamp) as day,
                       COUNT(*) as total,
                       SUM(CASE WHEN rating='positive' THEN 1 ELSE 0 END) as pos,
                       SUM(CASE WHEN rating='negative' THEN 1 ELSE 0 END) as neg
                FROM feedback_events
                WHERE timestamp >= date('now', ?)
                GROUP BY day ORDER BY day
            """, (f'-{days} days',)).fetchall()

            return {
                "total_feedback": total_fb,
                "positive_count": positive,
                "negative_count": negative,
                "positive_rate_pct": round(
                    positive / max(total_fb, 1) * 100, 1
                ),
                "top_negative_docs": [
                    {"title": row[0], "negative_count": row[1]}
                    for row in negative_docs
                ],
                "recent_negative_queries": [
                    {
                        "question": row[0],
                        "comment": row[1],
                        "sources": row[2],
                        "timestamp": row[3],
                    }
                    for row in negative_queries
                ],
                "pending_review": [
                    {"title": row[0], "negative_count": row[1]}
                    for row in pending_review
                ],
                "daily_feedback": [
                    {"date": d, "total": t, "positive": p, "negative": n}
                    for d, t, p, n in daily_fb
                ],
            }
