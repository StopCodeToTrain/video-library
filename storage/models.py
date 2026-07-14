"""数据模型定义"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class VideoFile:
    """视频文件模型"""
    id: Optional[int] = None
    file_path: str = ""
    file_name: str = ""
    file_size: int = 0
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    thumbnail_path: str = ""
    analysis_status: str = "pending"  # pending | analyzing | done | error


@dataclass
class Frame:
    """关键帧模型"""
    id: Optional[int] = None
    video_id: int = 0
    timestamp: float = 0.0
    image_path: str = ""
    scene_change: bool = False


@dataclass
class Character:
    """人物模型"""
    id: Optional[int] = None
    name: Optional[str] = None
    cluster_id: int = 0
    face_count: int = 0
    representative_face_path: str = ""


@dataclass
class FaceEmbedding:
    """人脸 embedding 模型"""
    id: Optional[int] = None
    frame_id: int = 0
    character_id: Optional[int] = None
    embedding: bytes = b""
    face_location: str = ""  # JSON: [top, right, bottom, left]
    confidence: float = 0.0


@dataclass
class Tag:
    """标签模型"""
    id: Optional[int] = None
    name: str = ""
    category: str = ""


@dataclass
class VideoTag:
    """视频-标签关联"""
    video_id: int = 0
    tag_id: int = 0
    confidence: float = 0.0
    source: str = "clip"  # clip | manual


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg", ".ts"}
