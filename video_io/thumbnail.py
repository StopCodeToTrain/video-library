"""缩略图生成"""

import cv2
from pathlib import Path
from typing import Optional

from config import THUMBNAIL_DIR, get_config


def extract_thumbnail(video_path: Path, video_id: int, time_ratio: float = 0.15) -> Optional[str]:
    """从视频中提取一张缩略图（默认取 15% 位置处的一帧）

    Args:
        video_path: 视频文件路径
        video_id: 视频数据库 ID
        time_ratio: 截取位置（0.0-1.0 比例）

    Returns:
        缩略图文件路径，失败返回 None
    """
    config = get_config()
    thumb_width = config.get("thumbnail_width", 320)
    thumb_quality = config.get("thumbnail_quality", 75)

    # 确保缩略图目录存在
    video_thumb_dir = THUMBNAIL_DIR / str(video_id)
    video_thumb_dir.mkdir(parents=True, exist_ok=True)

    thumb_path = video_thumb_dir / "thumbnail.jpg"

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        cap.release()
        return None

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if frame_count <= 0:
        cap.release()
        return None

    # 定位到目标帧
    target_frame = int(frame_count * time_ratio)
    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        return None

    # 缩放到目标宽度
    h, w = frame.shape[:2]
    new_h = int(h * thumb_width / w)
    resized = cv2.resize(frame, (thumb_width, new_h))

    # 保存为 JPEG
    cv2.imwrite(str(thumb_path), resized, [cv2.IMWRITE_JPEG_QUALITY, thumb_quality])

    return str(thumb_path)
