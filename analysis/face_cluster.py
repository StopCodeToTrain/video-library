"""人脸聚类 - 将检测到的人脸 embedding 按人物身份分组"""

import json
import cv2
from pathlib import Path
from typing import Optional

import numpy as np

from config import THUMBNAIL_DIR, get_config
from storage.database import get_db


def cluster_faces(video_id: Optional[int] = None,
                  exclude_face_ids: Optional[set[int]] = None,
                  progress_callback=None) -> list[dict]:
    """对未匹配的人脸 embedding 进行聚类，生成新人物身份

    使用 DBSCAN 聚类算法。已通过自动匹配归属的人脸通过
    exclude_face_ids 排除。

    Args:
        video_id: 可选，仅聚类某个视频的人脸
        exclude_face_ids: 已匹配/应排除的人脸 ID 集合
        progress_callback: 进度回调 (stage, info)

    Returns:
        [{"character_id": int, "face_count": int, "rep_face_path": str}, ...]
    """
    if exclude_face_ids is None:
        exclude_face_ids = set()

    config = get_config()
    eps = config.get("face_cluster_threshold", 0.5)

    db = get_db()

    # 获取所有 embedding
    if video_id:
        face_rows = db.get_embeddings_by_video(video_id)
    else:
        face_rows = db.get_all_embeddings()

    # 排除已匹配的
    face_rows = [r for r in face_rows if r["id"] not in exclude_face_ids]

    if not face_rows:
        return []

    if progress_callback:
        progress_callback("loading", f"加载 {len(face_rows)} 个待聚类人脸...")

    # 解析 embedding (InsightFace 512 维)
    embeddings = []
    face_ids = []
    for row in face_rows:
        if row["embedding"]:
            try:
                emb = np.frombuffer(row["embedding"], dtype=np.float32)
                if len(emb) == 512:  # InsightFace ArcFace embedding
                    embeddings.append(emb)
                    face_ids.append(row["id"])
            except Exception:
                continue

    if len(embeddings) < 2:
        # 单人脸：直接创建人物
        return _create_single_character(face_rows, progress_callback)

    if progress_callback:
        progress_callback("clustering", f"聚类 {len(embeddings)} 个人脸...")

    embeddings_arr = np.array(embeddings)

    # DBSCAN 聚类
    from sklearn.cluster import DBSCAN
    clustering = DBSCAN(eps=eps, min_samples=2, metric="euclidean")
    labels = clustering.fit_predict(embeddings_arr)

    # 统计每个簇 + 处理噪声点
    cluster_map = {}  # label -> [face_ids]
    noise_face_ids = []

    for face_id, label in zip(face_ids, labels):
        if label == -1:
            noise_face_ids.append(face_id)
        else:
            if label not in cluster_map:
                cluster_map[label] = []
            cluster_map[label].append(face_id)

    if progress_callback:
        progress_callback("saving", f"保存 {len(cluster_map)} 个新人物...")

    # 为每个簇创建人物记录 + 保存人脸缩略图
    results = []
    for label, fids in cluster_map.items():
        char_result = _create_character_from_cluster(fids, int(label))
        if char_result:
            results.append(char_result)

    # 噪声点单独创建单人人物
    for fid in noise_face_ids:
        row = next((r for r in face_rows if r["id"] == fid), None)
        if row:
            char_result = _create_character_from_cluster([fid], -1)
            if char_result:
                results.append(char_result)

    return results


def _create_character_from_cluster(face_ids: list[int], cluster_label: int) -> Optional[dict]:
    """为一个簇创建人物记录 + 保存所有人脸缩略图"""
    db = get_db()
    faces_dir = THUMBNAIL_DIR / "faces"

    if not face_ids:
        return None

    face_count = len(face_ids)
    rep_face_path = ""

    # 先创建人物（占位），再保存缩略图
    char_id = db.insert_character(
        cluster_id=cluster_label,
        face_count=face_count,
        face_path="",
    )

    # 为每个人脸裁剪缩略图并关联人物
    char_dir = faces_dir / f"char_{char_id}"
    char_dir.mkdir(parents=True, exist_ok=True)

    for idx, fid in enumerate(face_ids):
        # 更新 face_embedding 的 character_id
        db.update_face_character(fid, char_id)

        # 裁剪人脸缩略图
        face_row = db.get_face_embedding_by_id(fid)
        if face_row:
            loc_str = face_row.get("face_location", "")
            if loc_str:
                try:
                    loc = json.loads(loc_str)
                    path = _crop_face(face_row["frame_id"], loc, char_dir, fid)
                    if path:
                        if idx == 0:
                            rep_face_path = path
                except (json.JSONDecodeError, TypeError):
                    pass

    # 更新代表人物缩略图
    if rep_face_path:
        db.update_character(char_id, face_path=rep_face_path)

    return {
        "character_id": char_id,
        "face_count": face_count,
        "rep_face_path": rep_face_path,
    }


def _create_single_character(face_rows: list[dict],
                              progress_callback=None) -> list[dict]:
    """为单人脸创建人物"""
    results = []
    for row in face_rows:
        result = _create_character_from_cluster([row["id"]], -1)
        if result:
            results.append(result)
    return results


def _crop_face(frame_id: int, face_location: list,
               output_dir: Path, face_id: int) -> Optional[str]:
    """从帧图像中裁剪人脸并保存"""
    db = get_db()
    conn = db._get_conn()
    frame_row = conn.execute(
        "SELECT * FROM frames WHERE id=?", (frame_id,)
    ).fetchone()
    if not frame_row:
        return None

    frame_path = Path(frame_row["image_path"])
    if not frame_path.exists():
        return None

    img = cv2.imread(str(frame_path))
    if img is None:
        return None

    top, right, bottom, left = face_location
    h, w = img.shape[:2]
    top, right, bottom, left = max(0, top), min(w, right), min(h, bottom), max(0, left)

    if right <= left or bottom <= top:
        return None

    face_img = img[top:bottom, left:right]
    face_img = cv2.resize(face_img, (128, 128))

    save_path = output_dir / f"face_{face_id}.jpg"
    cv2.imwrite(str(save_path), face_img, [cv2.IMWRITE_JPEG_QUALITY, 85])

    return str(save_path)
