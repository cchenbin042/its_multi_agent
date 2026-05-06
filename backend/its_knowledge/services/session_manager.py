import time
import sqlite3
import os
import json
from typing import Dict, List, Any
import threading


class SessionManager:
    """
    对话Session管理器
    支持 TTL 自动过期清理 + SQLite 持久化
    """

    def __init__(self, ttl_seconds: int = 1800, db_path: str = None):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

        if db_path is None:
            project_root = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
            db_path = os.path.join(project_root, "data", "analytics.db")

        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id, id)"
            )

    def _save_message_db(self, session_id: str, role: str, content: str):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO conversations (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )

    def _load_messages_db(self, session_id: str) -> List[Dict[str, str]]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT role, content FROM conversations WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [{"role": r, "content": c} for r, c in rows]

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        """获取对话历史（内存优先，回退 DB）"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                if time.time() - session['last_active'] > self._ttl:
                    del self._sessions[session_id]
                else:
                    return list(session['messages'])

        # 回退到 DB
        messages = self._load_messages_db(session_id)
        if messages:
            with self._lock:
                self._sessions[session_id] = {
                    'messages': list(messages),
                    'last_active': time.time(),
                }
        return messages

    def add_message(self, session_id: str, role: str, content: str):
        """添加消息到历史（内存 + DB 双写）"""
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = {
                    'messages': [],
                    'last_active': time.time(),
                }
            self._sessions[session_id]['messages'].append({
                'role': role,
                'content': content,
            })
            self._sessions[session_id]['last_active'] = time.time()

        # 持久化到 DB
        self._save_message_db(session_id, role, content)

    def clear_session(self, session_id: str):
        """清理指定 Session（内存 + DB）"""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """列出最近的会话（用于历史对话侧边栏）"""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute("""
                SELECT session_id,
                       MIN(created_at) as started_at,
                       COUNT(*) as msg_count
                FROM conversations
                WHERE role = 'user'
                GROUP BY session_id
                ORDER BY MIN(id) DESC
                LIMIT ?
            """, (limit,)).fetchall()

        sessions = []
        for row in rows:
            # 取第一条用户消息作为预览
            first_msg = conn.execute(
                "SELECT content FROM conversations WHERE session_id = ? AND role = 'user' ORDER BY id LIMIT 1",
                (row[0],),
            ).fetchone()
            preview = first_msg[0] if first_msg else ""
            sessions.append({
                "session_id": row[0],
                "started_at": row[1],
                "msg_count": row[2],
                "preview": preview,
            })
        return sessions

    def get_session_messages(self, session_id: str) -> List[Dict[str, str]]:
        """获取指定会话的所有消息（用于继续对话）"""
        return self._load_messages_db(session_id)
