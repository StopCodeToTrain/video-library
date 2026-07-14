"""视频目录扫描器"""

import os
from pathlib import Path
from typing import Optional

import cv2

from storage.database import Database
from storage.models import VIDEO_EXTENSIONS


def is_video_file(filepath: Path) -> bool:
    """判断是否为视频文件"""
    return filepath.suffix.lower() in VIDEO_EXTENSIONS


def get_video_metadata(filepath: Path) -> dict:
    """提取视频元数据（时长、分辨率、fps）"""
    metadata = {
        "duration": 0.0,
        "width": 0,
        "height": 0,
        "fps": 0.0,
    }
    try:
        cap = cv2.VideoCapture(str(filepath))
        if cap.isOpened():
            metadata["fps"] = cap.get(cv2.CAP_PROP_FPS) or 0.0
            metadata["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            metadata["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if frame_count > 0 and metadata["fps"] > 0:
                metadata["duration"] = frame_count / metadata["fps"]
            cap.release()
    except Exception:
        pass
    return metadata


def scan_directory(directory: Path, db: Optional[Database] = None,
                   progress_callback=None) -> list[dict]:
    """扫描目录，发现视频文件并入库

    Args:
        directory: 要扫描的目录
        db: 数据库实例（可选）
        progress_callback: 进度回调 (current, total, filepath)

    Returns:
        新发现的视频记录列表
    """
    if db is None:
        from storage.database import get_db
        db = get_db()

    # 收集所有视频文件
    video_files = []
    for root, dirs, files in os.walk(directory):
        # 跳过隐藏目录
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            fp = Path(root) / f
            if is_video_file(fp):
                video_files.append(fp)

    total = len(video_files)
    existing_paths = set()
    new_videos = []

    for idx, fp in enumerate(video_files):
        if progress_callback:
            progress_callback(idx + 1, total, str(fp))

        existing_paths.add(str(fp))

        # 检查是否已存在
        existing = db.get_video_by_path(str(fp))
        if existing:
            continue

        # 提取元数据
        file_stat = fp.stat()
        meta = get_video_metadata(fp)

        video_id = db.insert_video(
            file_path=str(fp),
            file_name=fp.name,
            file_size=file_stat.st_size,
            duration=meta["duration"],
            width=meta["width"],
            height=meta["height"],
            fps=meta["fps"],
        )

        video = db.get_video_by_id(video_id)
        if video:
            new_videos.append(video)

    # 移除已不存在的视频
    removed = db.remove_missing_videos(existing_paths)

    return new_videos
