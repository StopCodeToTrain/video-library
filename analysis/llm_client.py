"""(可选) LLM 多模态客户端 - Ollama 视觉模型接入"""

import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional
import base64

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config


class LLMVisionClient:
    """Ollama 视觉模型客户端（可选，高配机器使用）"""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or get_config()
        self._base_url = self.config.get("ollama_base_url", "http://localhost:11434")
        self._model = self.config.get("ollama_vision_model", "minicpm-v:8b")
        self._available = False
        self._check_available()

    def _check_available(self):
        """检查 Ollama 服务是否可用"""
        try:
            url = f"{self._base_url}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                self._available = resp.status == 200
        except Exception:
            self._available = False

    def is_available(self) -> bool:
        return self._available

    def describe_image(self, image_path: Path, prompt: str = "") -> str:
        """让视觉模型描述图像内容

        Args:
            image_path: 图像文件路径
            prompt: 可选的提示词

        Returns:
            模型生成的描述文本
        """
        if not self._available:
            return ""

        # 读取并编码图像
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        if not prompt:
            prompt = "请详细描述这张图片的内容，包括场景、人物、光线、色调等方面。"

        payload = {
            "model": self._model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
        }

        try:
            url = f"{self._base_url}/api/generate"
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")

            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("response", "").strip()
        except Exception:
            return ""
