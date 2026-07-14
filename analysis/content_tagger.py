"""内容标签 - 基于 OpenCLIP 零样本图像分类生成视频内容标签"""

import sys
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config, ALL_TAGS, TAG_CATEGORIES

# 全局模型缓存
_clip_model = None
_clip_preprocess = None
_clip_device = None


def _get_clip_model():
    """懒加载 CLIP 模型"""
    global _clip_model, _clip_preprocess, _clip_device

    if _clip_model is not None:
        return _clip_model, _clip_preprocess, _clip_device

    import torch
    import open_clip

    _clip_device = "cuda" if torch.cuda.is_available() else "cpu"

    config = get_config()
    model_name = config.get("clip_model", "ViT-B-32")

    # 尝试加载模型
    try:
        _clip_model, _, _clip_preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained="openai"
        )
    except Exception:
        # fallback 到本地缓存的模型
        try:
            _clip_model, _, _clip_preprocess = open_clip.create_model_and_transforms(
                "ViT-B-32", pretrained="laion2b_s34b_b79k"
            )
        except Exception:
            # 最后尝试最小的模型
            _clip_model, _, _clip_preprocess = open_clip.create_model_and_transforms(
                "ViT-B-32", pretrained=None
            )

    _clip_model = _clip_model.to(_clip_device)
    _clip_model.eval()

    return _clip_model, _clip_preprocess, _clip_device


def tag_frame(image_path: Path,
              candidate_labels: Optional[list[str]] = None) -> list[tuple[str, float]]:
    """对单帧图像进行零样本标签分类

    Args:
        image_path: 图像路径
        candidate_labels: 候选标签列表，默认使用全部预定义标签

    Returns:
        [(label, confidence), ...] 按置信度降序排列
    """
    if candidate_labels is None:
        candidate_labels = ALL_TAGS

    model, preprocess, device = _get_clip_model()
    import torch
    import open_clip

    # 加载并预处理图像
    try:
        img = Image.open(image_path).convert("RGB")
        img_tensor = preprocess(img).unsqueeze(0).to(device)
    except Exception:
        return []

    # 编码文本标签（使用英文模板提高 CLIP 准确性）
    # CLIP 的零样本分类需要将标签包装为 prompt
    english_templates = [f"a photo of {label}" for label in candidate_labels]

    tokenizer = open_clip.get_tokenizer("ViT-B-32")
    text_tokens = tokenizer(english_templates).to(device)

    with torch.no_grad():
        image_features = model.encode_image(img_tensor)
        text_features = model.encode_text(text_tokens)

        # 归一化
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)
        text_features = text_features / text_features.norm(dim=-1, keepdim=True)

        # 余弦相似度
        similarity = (100.0 * image_features @ text_features.T).softmax(dim=-1)
        scores = similarity[0].cpu().numpy()

    # 按置信度排序
    config = get_config()
    threshold = config.get("tag_confidence_threshold", 0.3)

    results = []
    for label, opscore in zip(candidate_labels, scores):
        score = float(opscore)
        if score >= threshold:
            results.append((label, score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:10]  # 最多返回 10 个标签


def tag_video_frames(frame_paths: list[str],
                     progress_callback=None) -> dict[str, float]:
    """对视频的所有关键帧进行标签聚合

    Args:
        frame_paths: 关键帧路径列表
        progress_callback: 进度回调 (current, total)

    Returns:
        {tag_name: avg_confidence, ...} 视频级聚合标签
    """
    tag_scores = {}  # tag_name -> [scores]

    for idx, fpath in enumerate(frame_paths):
        if progress_callback:
            progress_callback(idx + 1, len(frame_paths))

        frame_results = tag_frame(Path(fpath))
        for label, score in frame_results:
            if label not in tag_scores:
                tag_scores[label] = []
            tag_scores[label].append(score)

    # 聚合：取平均置信度
    aggregated = {}
    for tag, scores in tag_scores.items():
        aggregated[tag] = sum(scores) / len(scores)

    # 排序
    sorted_tags = sorted(aggregated.items(), key=lambda x: x[1], reverse=True)
    return dict(sorted_tags[:10])
