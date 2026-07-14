"""关键帧提取 - 基于 PySceneDetect 场景检测 + 等距采样"""

import cv2
from pathlib import Path
from typing import Optional

from config import THUMBNAIL_DIR, get_config


def extract_keyframes(video_path: Path, video_id: int,
                      progress_callback=None) -> list[dict]:
    """从视频中提取关键帧

    策略：
      1. PySceneDetect 检测场景切换 → 在切换点保存帧
      2. 每 N 秒补充一个等距帧（避免长场景无关键帧）
      3. 每视频最多 max_frames 帧

    Args:
        video_path: 视频文件路径
        video_id: 视频数据库 ID
        progress_callback: 进度回调 (frame_idx, total)

    Returns:
        [{"timestamp": float, "image_path": str, "scene_change": bool}, ...]
    """
    config = get_config()
    interval = config.get("frame_interval", 5)
    max_frames = config.get("max_frames_per_video", 50)
    thumb_width = config.get("thumbnail_width", 320)
    thumb_quality = config.get("thumbnail_quality", 75)

    # 帧输出目录
    frame_dir = THUMBNAIL_DIR / str(video_id) / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        cap.release()
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 1.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_count / fps if fps > 0 else 0

    if frame_count <= 0:
        cap.release()
        return []

    # ── 第一步: 场景检测 ──
    scene_timestamps = set()
    try:
        from scenedetect import open_video, SceneManager, ContentDetector
        video_scene = open_video(str(video_path))
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=config.get("scene_threshold", 30)))
        scene_manager.detect_scenes(video_scene)

        scene_list = scene_manager.get_scene_list()
        for scene in scene_list:
            start_timecode = scene[0]
            t_sec = start_timecode.get_seconds()
            scene_timestamps.add(t_sec)
    except Exception:
        pass  # PySceneDetect 不可用时跳过

    # ── 第二步: 等距采样 ──
    uniform_timestamps = set()
    t = 0.0
    while t < duration:
        uniform_timestamps.add(t)
        t += interval

    # ── 第三步: 合并去重 ──
    all_timestamps = sorted(scene_timestamps | uniform_timestamps)

    # 限制总量
    if len(all_timestamps) > max_frames:
        # 优先保留场景切换帧
        scene_sorted = sorted(scene_timestamps)
        remaining = max_frames - len(scene_sorted)
        if remaining > 0:
            uniform_sorted = sorted(uniform_timestamps - scene_timestamps)
            step = max(1, len(uniform_sorted) // remaining)
            selected = scene_sorted + uniform_sorted[::step][:remaining]
        else:
            selected = scene_sorted[:max_frames]
        all_timestamps = sorted(selected)

    # ── 第四步: 提取帧 ──
    frame_results = []
    for idx, t_sec in enumerate(all_timestamps):
        if progress_callback:
            progress_callback(idx + 1, len(all_timestamps))

        frame_no = int(t_sec * fps)
        if frame_no >= frame_count:
            continue

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        # 缩放
        h, w = frame.shape[:2]
        new_h = int(h * thumb_width / w)
        resized = cv2.resize(frame, (thumb_width, new_h))

        # 保存
        filename = f"frame_{frame_no:06d}.jpg"
        save_path = frame_dir / filename
        cv2.imwrite(str(save_path), resized, [cv2.IMWRITE_JPEG_QUALITY, thumb_quality])

        is_scene = t_sec in scene_timestamps
        frame_results.append({
            "timestamp": t_sec,
            "image_path": str(save_path),
            "scene_change": is_scene,
        })

    cap.release()
    return frame_results
