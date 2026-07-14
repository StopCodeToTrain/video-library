"""人脸检测 - 基于 InsightFace (ArcFace) 进行人脸检测和 embedding 提取

使用 InsightFace 的 buffalo_l 模型，支持：
  - 人脸检测 + 5 点关键点
  - 512 维 ArcFace embedding（比 dlib 128 维更精确）
  - 性别 + 年龄（可选附加信息）
  - CPU/GPU 自动切换
  - 无需 VS C++ 编译，pip install 即用
"""

import json
import cv2
import numpy as np
from pathlib import Path
from typing import Optional

# 全局模型单例（线程安全：InsightFace 内部已加锁）
_face_app = None
_face_app_cpu = None


def _get_face_app(use_gpu: bool = None):
    """懒加载 InsightFace 人脸分析模型"""
    global _face_app, _face_app_cpu

    import insightface

    if use_gpu is None:
        import torch
        use_gpu = torch.cuda.is_available()

    ctx_id = 0 if use_gpu else -1

    if use_gpu:
        if _face_app is None:
            _face_app = insightface.app.FaceAnalysis(name="buffalo_l")
            _face_app.prepare(ctx_id=0, det_size=(640, 640))
        return _face_app
    else:
        if _face_app_cpu is None:
            _face_app_cpu = insightface.app.FaceAnalysis(name="buffalo_l")
            _face_app_cpu.prepare(ctx_id=-1, det_size=(640, 640))
        return _face_app_cpu


def is_blurry(image_path: Path, threshold: float = 100.0) -> bool:
    """检测图像是否模糊（拉普拉斯方差）"""
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return True
    laplacian_var = cv2.Laplacian(img, cv2.CV_64F).var()
    return laplacian_var < threshold


def detect_faces(image_path: Path, model: str = "hog") -> list[dict]:
    """检测图像中的人脸并提取 512 维 embedding

    Args:
        image_path: 图像文件路径
        model: 保留参数兼容性，"hog"/"cnn" 均使用同一 InsightFace 模型

    Returns:
        [{"embedding": list[float], "location": "[top, right, bottom, left]", "confidence": float}, ...]
    """
    import torch
    use_gpu = torch.cuda.is_available()

    app = _get_face_app(use_gpu=use_gpu)

    # 检查模糊
    if is_blurry(image_path, threshold=50.0):
        return []

    # 加载图像
    img = cv2.imread(str(image_path))
    if img is None:
        return []

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # 检测
    faces = app.get(img_rgb)

    if not faces:
        return []

    # 限制最多 10 张人脸
    faces = faces[:10]

    results = []
    img_h, img_w = img.shape[:2]

    for face in faces:
        # bbox: [left, top, right, bottom] (InsightFace 格式)
        left, top, right, bottom = face.bbox.astype(int).tolist()

        # 转换到 face_recognition 兼容格式: [top, right, bottom, left]
        # 人脸大小置信度
        face_area = (bottom - top) * (right - left)
        img_area = img_h * img_w
        confidence = min(1.0, face_area / (img_area * 0.05))

        # embedding 是 512 维 numpy array
        embedding = face.embedding
        if embedding is None:
            continue

        results.append({
            "embedding": embedding.tolist(),
            "location": json.dumps([int(top), int(right), int(bottom), int(left)]),
            "confidence": round(confidence, 3),
        })

    return results
