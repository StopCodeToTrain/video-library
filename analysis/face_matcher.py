"""人脸自动匹配 - 将检测到的人脸与已知（已命名）人物进行比对

流程：
  1. 加载所有已命名人物及其 embedding
  2. 对新检测到的人脸 embedding 逐一比对
  3. 匹配成功（距离 < threshold）则自动归属到该人物
  4. 保存所有人脸缩略图到对应的 character 目录
"""

import json
import cv2
import numpy as np
from pathlib import Path
from typing import Optional

from config import THUMBNAIL_DIR, get_config
from storage.database import get_db


def match_against_known(
    face_embeddings: list[np.ndarray],
    face_ids: list[int],
    progress_callback=None,
) -> tuple[dict[int, int], list[int]]:
    """将人脸 embedding 与已知命名人物进行匹配

    Args:
        face_embeddings: 待匹配的人脸 embedding 列表 (每个 512 维)
        face_ids: 对应的人脸记录 ID 列表
        progress_callback: 进度回调

    Returns:
        ({face_id: character_id}, [unmatched_face_ids])
        - 已匹配的 face_id -> character_id 映射
        - 未匹配的 face_id 列表（将留给聚类处理）
    """
    db = get_db()
    config = get_config()
    match_threshold = config.get("face_cluster_threshold", 0.5)

    # 获取所有已命名人物
    named_chars = db.get_named_characters()
    if not named_chars:
        return {}, list(face_ids)

    if progress_callback:
        progress_callback("loading_known", f"加载 {len(named_chars)} 个已知人物...")

    # 为每个已命名人物加载代表性 embedding（取前 10 个）
    char_embeddings = {}  # char_id -> list[np.ndarray]
    for char in named_chars:
        char_id = char["id"]
        emb_rows = db.get_character_sample_embeddings(char_id, limit=10)
        embs = []
        for row in emb_rows:
            if row["embedding"]:
                try:
                    emb = np.frombuffer(row["embedding"], dtype=np.float32)
                    if len(emb) == 512:  # InsightFace ArcFace embedding
                        embs.append(emb)
                except Exception:
                    continue
        if embs:
            char_embeddings[char_id] = embs

    if not char_embeddings:
        return {}, list(face_ids)

    if progress_callback:
        progress_callback("matching", f"匹配 {len(face_embeddings)} 个人脸...")

    # 对每个人脸，找最匹配的已知人物
    matched = {}  # face_id -> character_id
    unmatched = []

    for face_idx, (emb, fid) in enumerate(zip(face_embeddings, face_ids)):
        best_char = None
        best_dist = float("inf")

        for char_id, known_embs in char_embeddings.items():
            # 计算与所有已知样本的最小距离
            distances = np.linalg.norm(np.array(known_embs) - emb, axis=1)
            min_dist = float(np.min(distances))

            if min_dist < best_dist and min_dist < match_threshold:
                best_dist = min_dist
                best_char = char_id

        if best_char is not None:
            matched[fid] = best_char
        else:
            unmatched.append(fid)

    return matched, unmatched


def save_all_face_thumbnails(face_rows: list[dict],
                             progress_callback=None) -> dict[int, str]:
    """为所有人脸记录保存裁剪的缩略图，按 character_id 组织

    Args:
        face_rows: 人脸记录列表 (含 id, frame_id, character_id, face_location)
        progress_callback: 进度回调

    Returns:
        {face_id: thumbnail_path, ...}
    """
    db = get_db()
    thumb_map = {}

    faces_dir = THUMBNAIL_DIR / "faces"
    faces_dir.mkdir(parents=True, exist_ok=True)

    total = len(face_rows)

    for idx, row in enumerate(face_rows):
        if progress_callback:
            progress_callback(idx + 1, total)

        face_id = row["id"]
        char_id = row.get("character_id") or 0
        loc_str = row.get("face_location", "")

        if not loc_str:
            continue

        try:
            loc = json.loads(loc_str)  # [top, right, bottom, left]
        except (json.JSONDecodeError, TypeError):
            continue

        # 按 character 分目录
        char_dir = faces_dir / f"char_{char_id}"
        char_dir.mkdir(parents=True, exist_ok=True)

        save_path = _crop_face_to_path(row["frame_id"], loc, char_dir, face_id)
        if save_path:
            thumb_map[face_id] = save_path

    return thumb_map


def _crop_face_to_path(frame_id: int, face_location: list,
                       output_dir: Path, face_id: int) -> str:
    """从帧图像中裁剪人脸并保存到指定目录"""
    db = get_db()
    conn = db._get_conn()
    frame_row = conn.execute(
        "SELECT * FROM frames WHERE id=?", (frame_id,)
    ).fetchone()
    if not frame_row:
        return ""

    frame_path = Path(frame_row["image_path"])
    if not frame_path.exists():
        return ""

    img = cv2.imread(str(frame_path))
    if img is None:
        return ""

    top, right, bottom, left = face_location
    h, w = img.shape[:2]
    top, right, bottom, left = max(0, top), min(w, right), min(h, bottom), max(0, left)

    if right <= left or bottom <= top:
        return ""

    face_img = img[top:bottom, left:right]

    # 统一缩放到 128x128 便于展示
    face_img = cv2.resize(face_img, (128, 128))

    save_path = output_dir / f"face_{face_id}.jpg"
    cv2.imwrite(str(save_path), face_img, [cv2.IMWRITE_JPEG_QUALITY, 85])

    return str(save_path)


def auto_match_all_videos(progress_callback=None) -> dict:
    """全局自动匹配：将所有人脸与已命名人物比对，跨视频匹配

    Returns:
        {"matched": int, "unmatched": int}
    """
    db = get_db()
    named_chars = db.get_named_characters()

    if not named_chars:
        return {"matched": 0, "unmatched": 0}

    # 获取所有未归属到已知人物的人脸
    all_faces = db.get_all_embeddings()
    unassigned = [f for f in all_faces if not f.get("character_id")]

    # 排除已有 character_id 但该 character 是未命名的
    unnamed_char_ids = {
        c["id"] for c in db.get_unnamed_characters()
    }
    unassigned += [
        f for f in all_faces
        if f.get("character_id") in unnamed_char_ids
    ]

    if not unassigned:
        return {"matched": 0, "unmatched": 0}

    if progress_callback:
        progress_callback("preparing", f"准备匹配 {len(unassigned)} 个人脸...")

    embeddings = []
    face_ids = []
    for f in unassigned:
        if f.get("embedding"):
            try:
                emb = np.frombuffer(f["embedding"], dtype=np.float32)
                if len(emb) == 512:  # InsightFace ArcFace embedding
                    embeddings.append(emb)
                    face_ids.append(f["id"])
            except Exception:
                continue

    matched_map, unmatched = match_against_known(embeddings, face_ids, progress_callback)

    # 更新数据库
    for face_id, char_id in matched_map.items():
        db.update_face_character(face_id, char_id)
        # 更新人物的出现计数
        char = db.get_character_by_id(char_id)
        if char:
            # 找 face_id 对应的 frame -> video
            for f in all_faces:
                if f["id"] == face_id:
                    frame_row = db._get_conn().execute(
                        "SELECT video_id FROM frames WHERE id=?",
                        (f["frame_id"],)
                    ).fetchone()
                    if frame_row:
                        db.link_character_video(frame_row["video_id"], char_id, 1)
                    break
            # 更新 face_count
            conn = db._get_conn()
            conn.execute(
                "UPDATE characters SET face_count=face_count+1 WHERE id=?",
                (char_id,)
            )
            conn.commit()

    if progress_callback:
        progress_callback("done", f"匹配: {len(matched_map)} 已归属, {len(unmatched)} 待聚类")

    return {"matched": len(matched_map), "unmatched": len(unmatched)}
