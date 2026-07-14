"""SQLite 数据库操作"""

import sqlite3
import threading
from pathlib import Path
from typing import Optional

from config import DATABASE_FILE

# 线程本地存储，每个线程独立的数据库连接
_local = threading.local()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_name TEXT NOT NULL,
    file_size INTEGER DEFAULT 0,
    duration REAL DEFAULT 0,
    width INTEGER DEFAULT 0,
    height INTEGER DEFAULT 0,
    fps REAL DEFAULT 0,
    thumbnail_path TEXT DEFAULT '',
    scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    analysis_status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    timestamp REAL DEFAULT 0,
    image_path TEXT DEFAULT '',
    scene_change INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    cluster_id INTEGER DEFAULT 0,
    face_count INTEGER DEFAULT 0,
    representative_face_path TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS face_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER REFERENCES frames(id) ON DELETE CASCADE,
    character_id INTEGER REFERENCES characters(id),
    embedding BLOB,
    face_location TEXT DEFAULT '',
    confidence REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    category TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS video_tags (
    video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    confidence REAL DEFAULT 0.0,
    source TEXT DEFAULT 'clip',
    PRIMARY KEY (video_id, tag_id)
);

CREATE TABLE IF NOT EXISTS video_characters (
    video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    appear_count INTEGER DEFAULT 0,
    PRIMARY KEY (video_id, character_id)
);

CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(analysis_status);
CREATE INDEX IF NOT EXISTS idx_videos_filepath ON videos(file_path);
CREATE INDEX IF NOT EXISTS idx_frames_video ON frames(video_id);
CREATE INDEX IF NOT EXISTS idx_faces_char ON face_embeddings(character_id);
CREATE INDEX IF NOT EXISTS idx_video_tags_video ON video_tags(video_id);
CREATE INDEX IF NOT EXISTS idx_video_tags_tag ON video_tags(tag_id);
"""


class Database:
    """SQLite 数据库管理器（线程安全）"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or DATABASE_FILE)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接"""
        if not hasattr(_local, "conn") or _local.conn is None:
            _local.conn = sqlite3.connect(self.db_path)
            _local.conn.row_factory = sqlite3.Row
            _local.conn.execute("PRAGMA journal_mode=WAL")
            _local.conn.execute("PRAGMA foreign_keys=ON")
        return _local.conn

    def _init_schema(self):
        """初始化数据库表结构"""
        conn = self._get_conn()
        conn.executescript(SCHEMA_SQL)
        conn.commit()

    def close(self):
        """关闭当前线程的数据库连接"""
        if hasattr(_local, "conn") and _local.conn:
            _local.conn.close()
            _local.conn = None

    # ============ 视频操作 ============

    def insert_video(self, file_path: str, file_name: str, file_size: int = 0,
                     duration: float = 0, width: int = 0, height: int = 0,
                     fps: float = 0) -> int:
        """插入或更新视频记录，返回 id"""
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO videos (file_path, file_name, file_size, duration, width, height, fps)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                file_name=excluded.file_name,
                file_size=excluded.file_size,
                duration=excluded.duration,
                width=excluded.width,
                height=excluded.height,
                fps=excluded.fps,
                updated_at=CURRENT_TIMESTAMP
        """, (file_path, file_name, file_size, duration, width, height, fps))
        conn.commit()
        row = conn.execute("SELECT id FROM videos WHERE file_path=?", (file_path,)).fetchone()
        return row["id"] if row else 0

    def get_video_by_path(self, file_path: str) -> Optional[dict]:
        """根据路径获取视频"""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM videos WHERE file_path=?", (file_path,)).fetchone()
        return dict(row) if row else None

    def get_video_by_id(self, video_id: int) -> Optional[dict]:
        """根据 ID 获取视频"""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        return dict(row) if row else None

    def get_all_videos(self, status: Optional[str] = None) -> list[dict]:
        """获取所有视频，可按状态筛选"""
        conn = self._get_conn()
        if status:
            rows = conn.execute(
                "SELECT * FROM videos WHERE analysis_status=? ORDER BY file_name", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM videos ORDER BY file_name").fetchall()
        return [dict(r) for r in rows]

    def get_videos_by_status(self, status: str) -> list[dict]:
        """按分析状态获取视频列表"""
        return self.get_all_videos(status=status)

    def update_video_status(self, video_id: int, status: str):
        """更新视频分析状态"""
        conn = self._get_conn()
        conn.execute(
            "UPDATE videos SET analysis_status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, video_id)
        )
        conn.commit()

    def update_video_thumbnail(self, video_id: int, thumbnail_path: str):
        """更新视频缩略图路径"""
        conn = self._get_conn()
        conn.execute(
            "UPDATE videos SET thumbnail_path=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (thumbnail_path, video_id)
        )
        conn.commit()

    def delete_video(self, video_id: int):
        """删除视频及其关联数据（级联删除）"""
        conn = self._get_conn()
        conn.execute("DELETE FROM videos WHERE id=?", (video_id,))
        conn.commit()

    def remove_missing_videos(self, existing_paths: set) -> int:
        """删除数据库中已不存在的视频记录，返回删除数"""
        conn = self._get_conn()
        all_rows = conn.execute("SELECT id, file_path FROM videos").fetchall()
        deleted = 0
        for row in all_rows:
            if row["file_path"] not in existing_paths:
                conn.execute("DELETE FROM videos WHERE id=?", (row["id"],))
                deleted += 1
        conn.commit()
        return deleted

    # ============ 关键帧操作 ============

    def insert_frame(self, video_id: int, timestamp: float, image_path: str,
                     scene_change: bool = False) -> int:
        """插入关键帧，返回 id"""
        conn = self._get_conn()
        cur = conn.execute(
            "INSERT INTO frames (video_id, timestamp, image_path, scene_change) VALUES (?,?,?,?)",
            (video_id, timestamp, image_path, int(scene_change))
        )
        conn.commit()
        return cur.lastrowid

    def get_frames_by_video(self, video_id: int) -> list[dict]:
        """获取某个视频的所有关键帧"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM frames WHERE video_id=? ORDER BY timestamp", (video_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_frames_by_video(self, video_id: int):
        """删除某个视频的所有关键帧"""
        conn = self._get_conn()
        conn.execute("DELETE FROM frames WHERE video_id=?", (video_id,))
        conn.commit()

    # ============ 人物操作 ============

    def insert_character(self, name: Optional[str] = None, cluster_id: int = 0,
                         face_count: int = 0, face_path: str = "") -> int:
        """插入人物，返回 id"""
        conn = self._get_conn()
        cur = conn.execute(
            "INSERT INTO characters (name, cluster_id, face_count, representative_face_path) VALUES (?,?,?,?)",
            (name, cluster_id, face_count, face_path)
        )
        conn.commit()
        return cur.lastrowid

    def update_character(self, char_id: int, name: Optional[str] = None,
                         face_path: Optional[str] = None):
        """更新人物信息"""
        conn = self._get_conn()
        if name is not None and face_path is not None:
            conn.execute(
                "UPDATE characters SET name=?, representative_face_path=? WHERE id=?",
                (name, face_path, char_id)
            )
        elif name is not None:
            conn.execute("UPDATE characters SET name=? WHERE id=?", (name, char_id))
        elif face_path is not None:
            conn.execute("UPDATE characters SET representative_face_path=? WHERE id=?", (face_path, char_id))
        conn.commit()

    def get_all_characters(self) -> list[dict]:
        """获取所有人物"""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM characters ORDER BY face_count DESC").fetchall()
        return [dict(r) for r in rows]

    def get_character_by_id(self, char_id: int) -> Optional[dict]:
        """根据 ID 获取人物"""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
        return dict(row) if row else None

    def get_characters_by_video(self, video_id: int) -> list[dict]:
        """获取某个视频中出现的人物"""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT c.*, vc.appear_count FROM characters c
            JOIN video_characters vc ON c.id = vc.character_id
            WHERE vc.video_id = ?
            ORDER BY vc.appear_count DESC
        """, (video_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_named_characters(self) -> list[dict]:
        """获取所有已命名的已知人物"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM characters WHERE name IS NOT NULL AND name != '' ORDER BY face_count DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_unnamed_characters(self) -> list[dict]:
        """获取所有未命名的人物（新聚类出的）"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM characters WHERE name IS NULL OR name = '' ORDER BY face_count DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_character_sample_embeddings(self, char_id: int, limit: int = 10) -> list[dict]:
        """获取某个人物的代表性 embedding（高质量样本）"""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT * FROM face_embeddings
            WHERE character_id = ?
            ORDER BY confidence DESC
            LIMIT ?
        """, (char_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_faces_by_character(self, char_id: int) -> list[dict]:
        """获取某个人物的所有人脸记录（含帧路径）"""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT fe.*, f.image_path as frame_image_path, f.video_id
            FROM face_embeddings fe
            JOIN frames f ON fe.frame_id = f.id
            WHERE fe.character_id = ?
            ORDER BY fe.confidence DESC
            LIMIT 50
        """, (char_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_video_faces(self, video_id: int) -> list[dict]:
        """获取某个视频的所有人脸记录（含帧路径和人物名）"""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT fe.*, f.image_path as frame_image_path, f.timestamp,
                   c.name as character_name
            FROM face_embeddings fe
            JOIN frames f ON fe.frame_id = f.id
            LEFT JOIN characters c ON fe.character_id = c.id
            WHERE f.video_id = ?
            ORDER BY f.timestamp, fe.confidence DESC
        """, (video_id,)).fetchall()
        return [dict(r) for r in rows]

    def merge_characters(self, from_char_id: int, to_char_id: int):
        """合并人物：将 from_char 的所有人脸移到 to_char"""
        conn = self._get_conn()
        # 更新所有人脸
        conn.execute(
            "UPDATE face_embeddings SET character_id=? WHERE character_id=?",
            (to_char_id, from_char_id)
        )
        # 更新 video_characters
        from_vcs = conn.execute(
            "SELECT * FROM video_characters WHERE character_id=?", (from_char_id,)
        ).fetchall()
        for vc in from_vcs:
            conn.execute("""
                INSERT INTO video_characters (video_id, character_id, appear_count)
                VALUES (?, ?, ?)
                ON CONFLICT(video_id, character_id) DO UPDATE
                SET appear_count=appear_count+excluded.appear_count
            """, (vc["video_id"], to_char_id, vc["appear_count"]))
        conn.execute("DELETE FROM video_characters WHERE character_id=?", (from_char_id,))
        # 更新 face_count
        from_count = conn.execute(
            "SELECT face_count FROM characters WHERE id=?", (from_char_id,)
        ).fetchone()
        if from_count:
            conn.execute(
                "UPDATE characters SET face_count=face_count+? WHERE id=?",
                (from_count["face_count"], to_char_id)
            )
        # 删除旧人物
        conn.execute("DELETE FROM characters WHERE id=?", (from_char_id,))
        conn.commit()

    def get_face_embedding_by_id(self, face_id: int) -> Optional[dict]:
        """根据 ID 获取单个人脸记录"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM face_embeddings WHERE id=?", (face_id,)
        ).fetchone()
        return dict(row) if row else None

    def link_character_video(self, video_id: int, character_id: int, count: int = 1):
        """关联人物到视频"""
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO video_characters (video_id, character_id, appear_count)
            VALUES (?, ?, ?)
            ON CONFLICT(video_id, character_id) DO UPDATE SET appear_count=appear_count+excluded.appear_count
        """, (video_id, character_id, count))
        conn.commit()

    # ============ 人脸 embedding 操作 ============

    def insert_face_embedding(self, frame_id: int, character_id: Optional[int],
                              embedding: bytes, face_location: str, confidence: float = 0.0) -> int:
        """插入人脸 embedding"""
        conn = self._get_conn()
        cur = conn.execute(
            "INSERT INTO face_embeddings (frame_id, character_id, embedding, face_location, confidence) VALUES (?,?,?,?,?)",
            (frame_id, character_id, embedding, face_location, confidence)
        )
        conn.commit()
        return cur.lastrowid

    def get_all_embeddings(self) -> list[dict]:
        """获取所有人脸 embedding"""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM face_embeddings").fetchall()
        return [dict(r) for r in rows]

    def get_embeddings_by_video(self, video_id: int) -> list[dict]:
        """获取某个视频的所有人脸 embedding"""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT fe.* FROM face_embeddings fe
            JOIN frames f ON fe.frame_id = f.id
            WHERE f.video_id = ?
        """, (video_id,)).fetchall()
        return [dict(r) for r in rows]

    def update_face_character(self, face_id: int, character_id: int):
        """更新人脸的归属人物"""
        conn = self._get_conn()
        conn.execute("UPDATE face_embeddings SET character_id=? WHERE id=?", (character_id, face_id))
        conn.commit()

    # ============ 标签操作 ============

    def ensure_tags(self, tag_names: list[str], category: str = "") -> dict[str, int]:
        """确保标签存在，返回 {tag_name: tag_id}"""
        conn = self._get_conn()
        result = {}
        for name in tag_names:
            row = conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
            if row:
                result[name] = row["id"]
            else:
                cur = conn.execute("INSERT INTO tags (name, category) VALUES (?,?)", (name, category))
                result[name] = cur.lastrowid
        conn.commit()
        return result

    def set_video_tags(self, video_id: int, tag_scores: list[tuple[int, float]],
                       source: str = "clip"):
        """设置视频标签（先删后插）"""
        conn = self._get_conn()
        conn.execute("DELETE FROM video_tags WHERE video_id=?", (video_id,))
        for tag_id, confidence in tag_scores:
            conn.execute(
                "INSERT INTO video_tags (video_id, tag_id, confidence, source) VALUES (?,?,?,?)",
                (video_id, tag_id, confidence, source)
            )
        conn.commit()

    def get_video_tags(self, video_id: int) -> list[dict]:
        """获取视频标签"""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT t.*, vt.confidence, vt.source FROM tags t
            JOIN video_tags vt ON t.id = vt.tag_id
            WHERE vt.video_id = ?
            ORDER BY vt.confidence DESC
        """, (video_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_all_tags(self) -> list[dict]:
        """获取所有标签"""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM tags ORDER BY category, name").fetchall()
        return [dict(r) for r in rows]


# 全局数据库单例（按线程）
_db_instance: Optional[Database] = None
_db_lock = threading.Lock()


def get_db() -> Database:
    """获取数据库单例"""
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                _db_instance = Database()
    return _db_instance
