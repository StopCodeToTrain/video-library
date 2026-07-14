"""视频自动分类器 - 根据标签将视频整理到对应目录

策略:
  - 默认为每个标签创建子目录（如 动作/、对话场景/、夜景/）
  - 视频可能出现在多个标签目录（硬链接，同盘不占额外空间）
  - Fallback: 硬链接失败则复制，复制失败则跳过
"""

import os
import shutil
from pathlib import Path
from typing import Optional, Callable

from storage.database import get_db
from config import get_config


def classify_videos(
    target_dir: Path,
    method: str = "hardlink",
    progress_callback: Optional[Callable] = None,
    log_callback: Optional[Callable] = None,
) -> dict:
    """将视频按标签分类到目标目录

    Args:
        target_dir: 目标根目录（其下为各标签子目录）
        method: "hardlink" | "copy" | "move"
        progress_callback: (current, total, message)
        log_callback: (message)

    Returns:
        {"total_videos": int, "moved": int, "skipped": int, "errors": int, "folders": int}
    """
    db = get_db()

    # 收集所有有标签的视频
    all_videos = db.get_all_videos()
    tagged_videos = []

    for v in all_videos:
        tags = db.get_video_tags(v["id"])
        if tags:
            tagged_videos.append((v, tags))

    if not tagged_videos:
        if log_callback:
            log_callback("没有找到带标签的视频，请先分析视频。")
        return {"total_videos": 0, "moved": 0, "skipped": 0, "errors": 0, "folders": 0}

    if log_callback:
        log_callback(f"共 {len(tagged_videos)} 个视频有待分类标签")
        log_callback(f"分类方法: {method}")

    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    stats = {"total_videos": len(tagged_videos), "moved": 0, "skipped": 0, "errors": 0, "folders": 0}
    processed_set = set()  # (video_id, tag_name) 避免重复处理
    created_dirs = set()

    for idx, (video, tags) in enumerate(tagged_videos):
        video_path = Path(video["file_path"])
        video_name = video["file_name"]

        if not video_path.exists():
            if log_callback:
                log_callback(f"  [跳过] 文件不存在: {video_name}")
            stats["skipped"] += 1
            continue

        for tag in tags:
            tag_name = _sanitize_name(tag["name"])
            video_tag_key = (video["id"], tag_name)

            if video_tag_key in processed_set:
                continue
            processed_set.add(video_tag_key)

            # 标签子目录
            tag_subdir = target_dir / tag_name
            if tag_name not in created_dirs:
                tag_subdir.mkdir(parents=True, exist_ok=True)
                created_dirs.add(tag_name)
                stats["folders"] += 1

            dest_path = tag_subdir / video_name

            if progress_callback:
                progress_callback(
                    idx + 1, len(tagged_videos),
                    f"分类: {video_name} → {tag_name}/"
                )

            # 已存在则跳过
            if dest_path.exists():
                if log_callback:
                    log_callback(f"  [跳过] 已存在: {tag_name}/{video_name}")
                stats["skipped"] += 1
                continue

            # 执行操作
            success = False
            try:
                if method == "hardlink":
                    # 同盘硬链接（不占额外空间）
                    if _can_hardlink(video_path, dest_path):
                        os.link(str(video_path), str(dest_path))
                        success = True
                    else:
                        # Fallback to copy
                        if log_callback:
                            log_callback(f"  [降级复制] 跨盘无法硬链接: {video_name}")
                        shutil.copy2(str(video_path), str(dest_path))
                        success = True
                elif method == "copy":
                    shutil.copy2(str(video_path), str(dest_path))
                    success = True
                elif method == "move":
                    shutil.move(str(video_path), str(dest_path))
                    # 更新数据库路径
                    db._get_conn().execute(
                        "UPDATE videos SET file_path=? WHERE id=?",
                        (str(dest_path), video["id"])
                    )
                    db._get_conn().commit()
                    success = True
            except OSError as e:
                if log_callback:
                    log_callback(f"  [错误] {video_name}: {e}")

            if success:
                stats["moved"] += 1
            else:
                stats["errors"] += 1

    if log_callback:
        log_callback(
            f"分类完成: 移动 {stats['moved']}, "
            f"跳过 {stats['skipped']}, 错误 {stats['errors']}, "
            f"创建 {stats['folders']} 个标签目录"
        )

    return stats


def preview_classification() -> dict[str, list[str]]:
    """预览分类结果（不执行实际操作）

    Returns:
        {tag_name: [video_names, ...]}
    """
    db = get_db()
    all_videos = db.get_all_videos()

    tag_map = {}  # tag_name -> [video_names]
    for v in all_videos:
        tags = db.get_video_tags(v["id"])
        for tag in tags:
            tag_name = tag["name"]
            if tag_name not in tag_map:
                tag_map[tag_name] = []
            tag_map[tag_name].append(v["file_name"])

    return tag_map


def _sanitize_name(name: str) -> str:
    """清理文件夹名中的非法字符"""
    illegal = r'<>:"/\|?*'
    for ch in illegal:
        name = name.replace(ch, "_")
    # 去掉前后空格和点
    name = name.strip(". ")
    return name or "未命名"


def _can_hardlink(src: Path, dst: Path) -> bool:
    """检测是否可以使用硬链接（必须在同一磁盘分区）"""
    try:
        src_stat = src.stat()
        # 如果目标目录不存在父目录，先创建
        dst.parent.mkdir(parents=True, exist_ok=True)
        # 跨盘返回 False
        dst_drive = dst.resolve().drive
        src_drive = src.resolve().drive
        return dst_drive == src_drive
    except Exception:
        return False
