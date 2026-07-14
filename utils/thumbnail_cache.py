"""缩略图缓存管理"""

import shutil
from pathlib import Path

from config import THUMBNAIL_DIR


def clean_orphaned_thumbnails(active_video_ids: set[int]):
    """清理已删除视频的缩略图目录"""
    if not THUMBNAIL_DIR.exists():
        return

    for item in THUMBNAIL_DIR.iterdir():
        if item.is_dir():
            try:
                video_id = int(item.name)
                if video_id not in active_video_ids:
                    shutil.rmtree(item, ignore_errors=True)
            except ValueError:
                continue


def get_cache_size_mb() -> float:
    """获取缩略图缓存总大小 (MB)"""
    if not THUMBNAIL_DIR.exists():
        return 0.0

    total = 0
    for f in THUMBNAIL_DIR.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total / (1024 * 1024)


def clear_all_cache():
    """清空所有缩略图缓存"""
    if THUMBNAIL_DIR.exists():
        shutil.rmtree(THUMBNAIL_DIR, ignore_errors=True)
        THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
