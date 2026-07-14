"""视频分析流水线编排 - 串联帧提取、人脸检测、人脸聚类、内容标签"""

import sys
import time
from pathlib import Path
from typing import Optional, Callable

sys.path.insert(0, str(Path(__file__).parent))

from config import get_config, TAG_CATEGORIES
from storage.database import get_db


class AnalysisPipeline:
    """视频分析流水线

    回调签名:
        on_progress(stage: str, current: int, total: int, message: str)
        on_log(message: str)
        on_error(message: str)
        on_video_done(video_id: int)
        on_finished()
    """

    def __init__(self):
        self.db = get_db()
        self.config = get_config()

        # 回调
        self.on_progress: Optional[Callable] = None
        self.on_log: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_video_done: Optional[Callable] = None
        self.on_finished: Optional[Callable] = None
        self.on_new_characters: Optional[Callable] = None  # (count: int)

        self._cancelled = False

    def cancel(self):
        """取消处理"""
        self._cancelled = True

    def _log(self, msg: str):
        if self.on_log:
            self.on_log(msg)

    def _progress(self, stage: str, current: int, total: int, message: str = ""):
        if self.on_progress:
            self.on_progress(stage, current, total, message)

    def analyze_video(self, video: dict) -> bool:
        """分析单个视频（帧提取 + 人脸检测 + 标签）

        返回 True 表示成功
        """
        video_id = video["id"]
        file_path = video["file_path"]

        self._log(f"开始分析: {video['file_name']}")

        # 更新状态
        self.db.update_video_status(video_id, "analyzing")
        self.db.delete_frames_by_video(video_id)

        # ── Stage 1: 关键帧提取 ──
        self._progress("extract_frames", 0, 4, "提取关键帧...")

        from video_io.frame_extractor import extract_keyframes
        frames = extract_keyframes(
            Path(file_path), video_id,
            progress_callback=lambda c, t: self._progress(
                "extract_frames", c, t, f"提取关键帧 ({c}/{t})"
            )
        )

        if self._cancelled:
            return False

        if not frames:
            self._log(f"  无有效帧: {video['file_name']}")
            self.db.update_video_status(video_id, "done")
            if self.on_video_done:
                self.on_video_done(video_id)
            return True

        # 入库关键帧
        frame_records = []
        for f in frames:
            fid = self.db.insert_frame(
                video_id, f["timestamp"], f["image_path"], f["scene_change"]
            )
            frame_records.append({"id": fid, **f})

        self._log(f"  提取 {len(frame_records)} 个关键帧")

        # ── Stage 2: 人脸检测 ──
        self._progress("detect_faces", 1, 5, "检测人脸...")

        tagging_enabled = self.config.get("tagging_enabled", True)
        all_new_face_ids = []

        if tagging_enabled:
            from analysis.face_detector import detect_faces

            total_faces = 0
            for idx, fr in enumerate(frame_records):
                if self._cancelled:
                    return False

                self._progress("detect_faces", idx + 1, len(frame_records),
                              f"检测人脸 ({idx + 1}/{len(frame_records)})")

                faces = detect_faces(
                    Path(fr["image_path"]),
                    model=self.config.get("face_recognition_model", "hog")
                )

                for face in faces:
                    embedding_bytes = np.array(face["embedding"], dtype=np.float32).tobytes()
                    fid = self.db.insert_face_embedding(
                        fr["id"], None, embedding_bytes,
                        face["location"], face["confidence"]
                    )
                    all_new_face_ids.append(fid)
                    total_faces += 1

            self._log(f"  检测到 {total_faces} 个人脸")

        # ── Stage 3: 自动匹配已知人物 ──
        self._progress("auto_match", 2, 5, "自动匹配已知人物...")

        matched_ids = set()
        new_char_count = 0

        if tagging_enabled and all_new_face_ids:
            import numpy as np
            from analysis.face_matcher import match_against_known

            # 收集所有新人脸的 embedding
            new_embs = []
            new_ids = []
            for fid in all_new_face_ids:
                row = self.db.get_face_embedding_by_id(fid)
                if row and row["embedding"]:
                    try:
                        emb = np.frombuffer(row["embedding"], dtype=np.float32)
                        if len(emb) == 512:  # InsightFace embedding
                            new_embs.append(emb)
                            new_ids.append(fid)
                    except Exception:
                        continue

            if new_embs:
                matched_map, unmatched_ids = match_against_known(
                    new_embs, new_ids,
                    progress_callback=lambda stage, info: self._log(f"  匹配: {info}")
                )

                # 更新已匹配的人脸
                for face_id, char_id in matched_map.items():
                    self.db.update_face_character(face_id, char_id)
                    matched_ids.add(face_id)
                    # 关联人物到视频
                    self.db.link_character_video(video_id, char_id, 1)
                    # 更新人物 face_count
                    conn = self.db._get_conn()
                    conn.execute(
                        "UPDATE characters SET face_count=face_count+1 WHERE id=?",
                        (char_id,)
                    )
                    conn.commit()

                self._log(f"  自动匹配: {len(matched_map)} 个, 待聚类: {len(unmatched_ids)} 个")

        # ── Stage 4: 聚类未匹配人脸 ──
        self._progress("cluster_faces", 3, 5, "聚类新人脸...")

        if tagging_enabled:
            import numpy as np
            from analysis.face_cluster import cluster_faces

            clusters = cluster_faces(
                video_id=video_id,
                exclude_face_ids=matched_ids,
                progress_callback=lambda stage, info: self._log(f"  聚类: {info}")
            )

            new_char_count = len(clusters)

            # 关联新人物到视频
            for c in clusters:
                self.db.link_character_video(video_id, c["character_id"], c["face_count"])

            self._log(f"  新建 {new_char_count} 个人物")

            if self.on_new_characters and new_char_count > 0:
                self.on_new_characters(new_char_count)

        # ── Stage 5: 内容标签 ──
        self._progress("tag_frames", 4, 5, "生成内容标签...")

        if tagging_enabled:
            from analysis.content_tagger import tag_video_frames

            frame_paths = [fr["image_path"] for fr in frame_records]
            tag_aggregated = tag_video_frames(
                frame_paths,
                progress_callback=lambda c, t: self._progress(
                    "tag_frames", c, t, f"标签分析 ({c}/{t})"
                )
            )

            if tag_aggregated:
                # 确保标签在数据库中存在并获取 ID
                all_tag_names = list(tag_aggregated.keys())
                tag_name_to_id = self.db.ensure_tags(all_tag_names)

                tag_scores = []
                for tag_name, confidence in tag_aggregated.items():
                    tid = tag_name_to_id.get(tag_name)
                    if tid:
                        tag_scores.append((tid, confidence))

                if tag_scores:
                    self.db.set_video_tags(video_id, tag_scores, source="clip")
                    self._log(f"  生成 {len(tag_scores)} 个标签")

        # 完成
        self.db.update_video_status(video_id, "done")
        self._log(f"分析完成: {video['file_name']}")

        if self.on_video_done:
            self.on_video_done(video_id)

        return True

    def analyze_all_pending(self) -> int:
        """分析所有待处理的视频，返回成功数量"""
        pending = self.db.get_videos_by_status("pending")

        if not pending:
            self._log("没有待分析的视频")
            if self.on_finished:
                self.on_finished()
            return 0

        total = len(pending)
        self._log(f"共 {total} 个视频待分析")

        success = 0
        for idx, video in enumerate(pending):
            if self._cancelled:
                self._log(f"已取消 (完成 {success}/{total})")
                break

            self._progress("overall", idx, total, f"分析视频 ({idx + 1}/{total})")

            try:
                if self.analyze_video(video):
                    success += 1
            except Exception as e:
                self._log(f"分析失败: {video['file_name']} - {e}")
                if self.on_error:
                    self.on_error(f"{video['file_name']}: {e}")
                self.db.update_video_status(video["id"], "error")

        self._log(f"分析完成: {success}/{total} 成功")

        if self.on_finished:
            self.on_finished()

        return success


# 确保 numpy 可用
try:
    import numpy as np
except ImportError:
    pass
