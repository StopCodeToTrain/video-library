"""全局配置"""

import json
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent

# 缩略图目录
THUMBNAIL_DIR = PROJECT_ROOT / "thumbnails"
THUMBNAIL_DIR.mkdir(exist_ok=True)

# 数据库文件
DATABASE_FILE = PROJECT_ROOT / "video_library.db"

# 配置文件
SETTINGS_FILE = PROJECT_ROOT / "settings.json"


# ============ 配置持久化 ============

def load_settings() -> dict:
    """从 settings.json 加载用户配置"""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_settings(settings: dict) -> None:
    """保存配置到 settings.json"""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def get_setting(key: str, default=None):
    """获取单个配置项"""
    return load_settings().get(key, default)


def set_setting(key: str, value) -> None:
    """设置单个配置项"""
    settings = load_settings()
    settings[key] = value
    save_settings(settings)


# ============ 默认配置 ============

DEFAULT_SETTINGS = {
    # 目录管理
    "library_directories": [],         # 监控的视频目录列表

    # 分析参数
    "frame_interval": 5,               # 关键帧间隔(秒)
    "max_frames_per_video": 50,        # 每视频最大关键帧数
    "scene_threshold": 30,             # PySceneDetect 灵敏度

    # 人脸识别
    "face_recognition_model": "hog",   # hog(CPU快) | cnn
    "face_cluster_threshold": 0.5,     # DBSCAN eps

    # 内容标签
    "tagging_enabled": True,
    "clip_model": "ViT-B-32",
    "tag_confidence_threshold": 0.3,

    # LLM 后端（可选）
    "llm_backend": "none",             # none | ollama | api
    "ollama_base_url": "http://localhost:11434",
    "ollama_vision_model": "minicpm-v:8b",

    # 界面
    "theme_mode": "auto",              # auto | dark | light

    # 缩略图
    "thumbnail_width": 320,
    "thumbnail_quality": 75,
}


def get_config() -> dict:
    """获取完整配置（合并默认值和用户设置）"""
    settings = load_settings()
    config = DEFAULT_SETTINGS.copy()
    config.update({k: v for k, v in settings.items() if k in DEFAULT_SETTINGS})
    return config


# ============ 预定义标签体系 ============

SCENE_TAGS = [
    "室内", "室外", "白天", "夜晚", "街道", "办公室", "家中",
    "餐厅", "校园", "医院", "车站", "野外",
]

CHARACTER_TAGS = [
    "单人", "双人", "多人", "特写", "全身", "背影",
]

STYLE_TAGS = [
    "明亮", "昏暗", "暖色调", "冷色调", "高对比度",
]

TYPE_TAGS = [
    "对话场景", "动作场景", "风景", "城市", "文字/字幕", "空镜",
]

ALL_TAGS = SCENE_TAGS + CHARACTER_TAGS + STYLE_TAGS + TYPE_TAGS
TAG_CATEGORIES = {
    "场景": SCENE_TAGS,
    "人物": CHARACTER_TAGS,
    "风格": STYLE_TAGS,
    "类型": TYPE_TAGS,
}
