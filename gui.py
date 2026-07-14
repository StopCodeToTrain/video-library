#!/usr/bin/env python
"""视频库分类工具 GUI -- PyQt6 界面。

功能：
  1. 添加/管理本地视频目录
  2. 缩略图网格浏览
  3. 视频排序、筛选、搜索
  4. 后台 AI 分析（QThread 不阻塞 UI）
  5. 视频详情面板（人物、标签、关键帧）
  6. 设置对话框
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QCheckBox, QLineEdit,
    QScrollArea, QGridLayout, QFileDialog, QMessageBox,
    QSplitter, QSlider, QTabWidget, QDialog, QFormLayout,
    QSpinBox, QFrame, QGroupBox, QStatusBar, QListWidget,
    QListWidgetItem, QProgressBar, QPlainTextEdit, QSizePolicy,
    QAbstractItemView, QMenu,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QFont, QColor, QPixmap, QIcon, QAction, QDesktopServices

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    PROJECT_ROOT, THUMBNAIL_DIR, get_config, save_settings, load_settings,
    DEFAULT_SETTINGS, ALL_TAGS, TAG_CATEGORIES,
)
from storage.database import get_db, Database
from theme import get_theme_qss, get_current_theme_name


# ═══════════════════════════════════════════════════════════════
#  后台工作线程
# ═══════════════════════════════════════════════════════════════

class ScanWorker(QThread):
    """后台扫描目录"""
    progress = pyqtSignal(int, int, str)   # current, total, filepath
    finished = pyqtSignal(int)              # new_count
    log = pyqtSignal(str)

    def __init__(self, directories: list[str]):
        super().__init__()
        self.directories = directories

    def run(self):
        from video_io.scanner import scan_directory
        db = get_db()
        total_new = 0
        for d in self.directories:
            self.log.emit(f"正在扫描: {d}")
            scan_directory(Path(d), db, progress_callback=self._on_progress)
            total_new += 1  # 简化计数
        db.close()
        self.finished.emit(total_new)

    def _on_progress(self, current: int, total: int, filepath: str):
        self.progress.emit(current, total, filepath)


class AnalysisWorker(QThread):
    """后台 AI 分析（QThread 不阻塞 UI）"""
    progress = pyqtSignal(str, int, int, str)   # stage, current, total, message
    log = pyqtSignal(str)
    video_done = pyqtSignal(int)                 # video_id
    finished_all = pyqtSignal()
    new_characters_found = pyqtSignal(int)       # count
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._pipeline = None

    def run(self):
        from pipeline import AnalysisPipeline
        self._pipeline = AnalysisPipeline()
        self._pipeline.on_progress = self._on_progress
        self._pipeline.on_log = lambda msg: self.log.emit(msg)
        self._pipeline.on_error = lambda msg: self.error.emit(msg)
        self._pipeline.on_video_done = lambda vid: self.video_done.emit(vid)
        self._pipeline.on_new_characters = lambda cnt: self.new_characters_found.emit(cnt)
        self._pipeline.on_finished = lambda: self.finished_all.emit()
        self._pipeline.analyze_all_pending()

    def _on_progress(self, stage: str, current: int, total: int, message: str):
        self.progress.emit(stage, current, total, message)

    def cancel(self):
        if self._pipeline:
            self._pipeline.cancel()


class ThumbnailWorker(QThread):
    """后台生成缩略图"""
    progress = pyqtSignal(int, int)   # current, total
    log = pyqtSignal(str)
    thumbnail_ready = pyqtSignal(int, str)  # video_id, thumbnail_path
    finished_all = pyqtSignal()

    def __init__(self, video_ids: list[int]):
        super().__init__()
        self.video_ids = video_ids

    def run(self):
        from video_io.thumbnail import extract_thumbnail
        db = get_db()
        total = len(self.video_ids)

        for idx, vid in enumerate(self.video_ids):
            self.progress.emit(idx + 1, total)
            video = db.get_video_by_id(vid)
            if not video:
                continue

            path = extract_thumbnail(Path(video["file_path"]), vid)
            if path:
                db.update_video_thumbnail(vid, path)
                self.thumbnail_ready.emit(vid, path)
                self.log.emit(f"缩略图: {video['file_name']}")

        db.close()
        self.finished_all.emit()


class ClassifyWorker(QThread):
    """后台一键分类"""
    progress = pyqtSignal(int, int, str)    # current, total, message
    log = pyqtSignal(str)
    finished = pyqtSignal(dict)             # stats

    def __init__(self, target_dir: str, method: str):
        super().__init__()
        self.target_dir = target_dir
        self.method = method

    def run(self):
        from video_io.classifier import classify_videos
        stats = classify_videos(
            Path(self.target_dir),
            method=self.method,
            progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
            log_callback=lambda m: self.log.emit(m),
        )
        self.finished.emit(stats)


# ═══════════════════════════════════════════════════════════════
#  设置对话框
# ═══════════════════════════════════════════════════════════════

class SettingsDialog(QDialog):
    """设置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(450)
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 分析参数
        analysis_group = QGroupBox("分析参数")
        analysis_form = QFormLayout(analysis_group)

        self.frame_interval_spin = QSpinBox()
        self.frame_interval_spin.setRange(1, 60)
        self.frame_interval_spin.setSuffix(" 秒")
        analysis_form.addRow("关键帧间隔:", self.frame_interval_spin)

        self.max_frames_spin = QSpinBox()
        self.max_frames_spin.setRange(5, 200)
        self.max_frames_spin.setSuffix(" 帧")
        analysis_form.addRow("每视频最大帧数:", self.max_frames_spin)

        self.scene_threshold_spin = QSpinBox()
        self.scene_threshold_spin.setRange(10, 100)
        analysis_form.addRow("场景检测灵敏度:", self.scene_threshold_spin)

        layout.addWidget(analysis_group)

        # 人脸识别
        face_group = QGroupBox("人脸识别")
        face_form = QFormLayout(face_group)

        self.face_model_combo = QComboBox()
        self.face_model_combo.addItems(["hog (CPU 快速)", "cnn (GPU/高精度)"])
        face_form.addRow("识别模型:", self.face_model_combo)

        self.cluster_threshold_spin = QSpinBox()
        self.cluster_threshold_spin.setRange(3, 10)
        self.cluster_threshold_spin.setValue(5)
        self.cluster_threshold_spin.setPrefix("0.")
        self.cluster_threshold_spin.setSingleStep(1)
        face_form.addRow("聚类阈值:", self.cluster_threshold_spin)

        layout.addWidget(face_group)

        # 内容标签
        tag_group = QGroupBox("内容标签")
        tag_form = QFormLayout(tag_group)

        self.tag_enabled_check = QCheckBox("启用自动标签")
        self.tag_enabled_check.setChecked(True)
        tag_form.addRow(self.tag_enabled_check)

        self.tag_confidence_spin = QSpinBox()
        self.tag_confidence_spin.setRange(1, 9)
        self.tag_confidence_spin.setValue(3)
        self.tag_confidence_spin.setPrefix("0.")
        self.tag_confidence_spin.setSingleStep(1)
        tag_form.addRow("最低置信度:", self.tag_confidence_spin)

        layout.addWidget(tag_group)

        # 界面主题
        theme_group = QGroupBox("界面主题")
        theme_form = QFormLayout(theme_group)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("跟随系统", "auto")
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.addItem("浅色", "light")
        theme_form.addRow("主题模式:", self.theme_combo)

        layout.addWidget(theme_group)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save_settings)
        save_btn.setObjectName("settingsSaveBtn")
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _load_settings(self):
        settings = load_settings()
        config = DEFAULT_SETTINGS.copy()
        config.update(settings)

        self.frame_interval_spin.setValue(config.get("frame_interval", 5))
        self.max_frames_spin.setValue(config.get("max_frames_per_video", 50))
        self.scene_threshold_spin.setValue(config.get("scene_threshold", 30))

        face_model = config.get("face_recognition_model", "hog")
        self.face_model_combo.setCurrentIndex(0 if face_model == "hog" else 1)

        cluster_val = config.get("face_cluster_threshold", 0.5)
        self.cluster_threshold_spin.setValue(int(cluster_val * 10))

        self.tag_enabled_check.setChecked(config.get("tagging_enabled", True))
        tag_conf = config.get("tag_confidence_threshold", 0.3)
        self.tag_confidence_spin.setValue(int(tag_conf * 10))

        # 主题
        theme = config.get("theme_mode", "auto")
        idx = self.theme_combo.findData(theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)

    def _save_settings(self):
        settings = {
            "frame_interval": self.frame_interval_spin.value(),
            "max_frames_per_video": self.max_frames_spin.value(),
            "scene_threshold": self.scene_threshold_spin.value(),
            "face_recognition_model": "hog" if self.face_model_combo.currentIndex() == 0 else "cnn",
            "face_cluster_threshold": self.cluster_threshold_spin.value() / 10.0,
            "tagging_enabled": self.tag_enabled_check.isChecked(),
            "tag_confidence_threshold": self.tag_confidence_spin.value() / 10.0,
            "theme_mode": self.theme_combo.currentData(),
        }
        save_settings(settings)
        self.accept()


# ═══════════════════════════════════════════════════════════════
#  人物命名对话框 - 查看人脸缩略图 + 自定义命名 + 合并
# ═══════════════════════════════════════════════════════════════

class CharacterNamingDialog(QDialog):
    """人物管理对话框：展示人脸缩略图、命名、合并"""

    character_saved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("人物管理")
        self.setMinimumSize(800, 600)
        self.resize(900, 650)
        self.db = get_db()
        self._char_data = []  # [(char_dict, [face_rows])]
        self._selected_indices = set()
        self._build_ui()
        self._load_characters()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 顶部提示
        hint = QLabel("对未命名的人物（红框）输入名称后点击「保存命名」。可多选后点击「合并选中」将人物合并。")
        hint.setStyleSheet("font-size: 12px; border: none; background: transparent;")
        hint.setObjectName("secondaryHint")
        layout.addWidget(hint)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.char_container = QWidget()
        self.char_layout = QVBoxLayout(self.char_container)
        self.char_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.char_layout.setSpacing(10)
        scroll.setWidget(self.char_container)

        layout.addWidget(scroll)

        # 底部按钮
        btn_layout = QHBoxLayout()

        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.clicked.connect(self._on_select_all)
        btn_layout.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("取消全选")
        self.btn_deselect_all.clicked.connect(self._on_deselect_all)
        btn_layout.addWidget(self.btn_deselect_all)

        self.btn_merge = QPushButton("合并选中")
        self.btn_merge.setObjectName("mergeBtn")
        self.btn_merge.clicked.connect(self._on_merge_selected)
        btn_layout.addWidget(self.btn_merge)

        btn_layout.addStretch()

        self.btn_save_names = QPushButton("保存命名")
        self.btn_save_names.setObjectName("startBtn")
        self.btn_save_names.clicked.connect(self._on_save_names)
        btn_layout.addWidget(self.btn_save_names)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _load_characters(self):
        """加载所有人物及其人脸缩略图"""
        # 清空
        for i in reversed(range(self.char_layout.count())):
            w = self.char_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        self._char_data = []
        self._selected_indices.clear()

        characters = self.db.get_all_characters()

        if not characters:
            no_char = QLabel("还没有检测到人物。请先分析视频。")
            no_char.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_char.setStyleSheet("font-size: 14px; border: none; background: transparent;")
            no_char.setObjectName("secondaryHint")
            self.char_layout.addWidget(no_char)
            return

        for idx, char in enumerate(characters):
            group = self._build_character_row(idx, char)
            self.char_layout.addWidget(group)

    def _build_character_row(self, idx: int, char: dict) -> QGroupBox:
        """构建一个人物行：checkbox + 名称输入 + 人脸缩略图"""
        is_named = char.get("name") and char["name"].strip()
        display_name = char["name"] if is_named else f"未命名人物 #{char['id']}"
        face_count = char.get("face_count", 0)

        title = f"{display_name} ({face_count} 张人脸)"
        group = QGroupBox(title)
        if not is_named:
            group.setObjectName("unnamedGroup")

        row_layout = QHBoxLayout(group)
        row_layout.setSpacing(8)

        # 复选框
        cb = QCheckBox()
        cb.stateChanged.connect(lambda state, i=idx: self._on_check_toggled(i, state))
        row_layout.addWidget(cb)

        # 名称输入
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("输入人物姓名...")
        if is_named:
            name_edit.setText(char["name"])
        name_edit.setMaximumWidth(200)
        name_edit.setObjectName(f"name_{char['id']}")
        row_layout.addWidget(name_edit)

        # 人脸缩略图
        face_rows = self.db.get_faces_by_character(char["id"])
        faces_layout = QHBoxLayout()
        faces_layout.setSpacing(4)

        for fr in face_rows[:12]:  # 最多显示 12 张
            face_lbl = QLabel()
            face_lbl.setFixedSize(64, 64)
            face_lbl.setObjectName("faceThumb")

            # 读取已裁剪的人脸缩略图
            faces_dir = THUMBNAIL_DIR / "faces" / f"char_{char['id']}"
            crop_path = faces_dir / f"face_{fr['id']}.jpg"
            img_path = crop_path if crop_path.exists() else fr.get("frame_image_path", "")

            if img_path and Path(img_path).exists():
                pixmap = QPixmap(str(img_path))
                if not pixmap.isNull():
                    pixmap = pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
                    face_lbl.setPixmap(pixmap)

                # 如果用的是原始帧图（不是裁剪的），尝试从 frame 中裁脸
                if crop_path == img_path or not crop_path.exists():
                    if fr.get("face_location"):
                        try:
                            import json, cv2
                            loc = json.loads(fr["face_location"])
                            frame_img = cv2.imread(str(img_path))
                            if frame_img is not None:
                                top, right, bottom, left = loc
                                h, w = frame_img.shape[:2]
                                top, right, bottom, left = max(0, top), min(w, right), min(h, bottom), max(0, left)
                                if right > left and bottom > top:
                                    face_crop = frame_img[top:bottom, left:right]
                                    face_crop = cv2.resize(face_crop, (64, 64))
                                    import numpy as np
                                    h2, w2, ch = face_crop.shape
                                    qimg = QPixmap.fromImage(
                                        QApplication.instance().style().standardIcon.__class__.__module__  # dummy
                                    )
                                    # Use QImage via bytes
                                    from PyQt6.QtGui import QImage
                                    rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
                                    qi = QImage(rgb.data, w2, h2, w2 * 3, QImage.Format.Format_RGB888)
                                    face_lbl.setPixmap(QPixmap.fromImage(qi).scaled(
                                        64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))
                        except Exception:
                            pass
            else:
                face_lbl.setText("#")

            face_lbl.setToolTip(f"人脸 #{fr['id']}")
            faces_layout.addWidget(face_lbl)

        faces_layout.addStretch()
        row_layout.addLayout(faces_layout)
        row_layout.addStretch()

        self._char_data.append((char, face_rows))

        return group

    def _on_check_toggled(self, idx: int, state: int):
        if state == Qt.CheckState.Checked.value:
            self._selected_indices.add(idx)
        else:
            self._selected_indices.discard(idx)

    def _on_select_all(self):
        for i in range(self.char_layout.count()):
            w = self.char_layout.itemAt(i).widget()
            if isinstance(w, QGroupBox):
                cb = w.findChild(QCheckBox)
                if cb:
                    cb.setChecked(True)

    def _on_deselect_all(self):
        for i in range(self.char_layout.count()):
            w = self.char_layout.itemAt(i).widget()
            if isinstance(w, QGroupBox):
                cb = w.findChild(QCheckBox)
                if cb:
                    cb.setChecked(False)

    def _on_save_names(self):
        """保存所有命名"""
        renamed = 0
        for i in range(self.char_layout.count()):
            w = self.char_layout.itemAt(i).widget()
            if isinstance(w, QGroupBox):
                name_edit = w.findChild(QLineEdit)
                if name_edit:
                    new_name = name_edit.text().strip()
                    if new_name and i < len(self._char_data):
                        char = self._char_data[i][0]
                        old_name = char.get("name") or ""
                        if new_name != old_name:
                            self.db.update_character(char["id"], name=new_name)
                            renamed += 1

        if renamed > 0:
            QMessageBox.information(self, "保存成功", f"已更新 {renamed} 个人物名称。")
            self.character_saved.emit()
        self._load_characters()

    def _on_merge_selected(self):
        """合并选中的人物"""
        if len(self._selected_indices) < 2:
            QMessageBox.warning(self, "提示", "请至少选择 2 个人物进行合并。")
            return

        indices = sorted(self._selected_indices)
        if indices[0] >= len(self._char_data):
            return

        to_char = self._char_data[indices[0]][0]
        from_chars = [self._char_data[i][0] for i in indices[1:] if i < len(self._char_data)]

        to_name = to_char.get("name") or f"未命名人物 #{to_char['id']}"
        reply = QMessageBox.question(
            self, "确认合并",
            f"将 {len(from_chars)} 个人物合并到「{to_name}」？\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        for fc in from_chars:
            self.db.merge_characters(fc["id"], to_char["id"])

        self.character_saved.emit()
        self._load_characters()
        self._selected_indices.clear()


# ═══════════════════════════════════════════════════════════════
#  一键分类对话框
# ═══════════════════════════════════════════════════════════════

class ClassificationDialog(QDialog):
    """一键分类对话框：预览标签分布 + 选择目标目录 + 执行"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("一键分类")
        self.setMinimumWidth(500)
        self.resize(550, 450)
        self.db = get_db()
        self._worker: Optional[ClassifyWorker] = None
        self._build_ui()
        self._load_preview()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 说明
        hint = QLabel("根据视频的 AI 标签自动创建文件夹，将视频归类到对应目录。\n"
                       "硬链接：不占额外磁盘空间（同盘）；复制：保留原文件。")
        hint.setStyleSheet("font-size: 12px; border: none; background: transparent;")
        hint.setObjectName("secondaryHint")
        layout.addWidget(hint)

        # 目标目录
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("目标目录:"))
        self.dir_edit = QLineEdit()
        self.dir_edit.setReadOnly(True)
        dir_layout.addWidget(self.dir_edit)
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_dir)
        dir_layout.addWidget(browse_btn)
        layout.addLayout(dir_layout)

        # 分类方式
        method_layout = QHBoxLayout()
        method_layout.addWidget(QLabel("方式:"))
        self.method_combo = QComboBox()
        self.method_combo.addItem("硬链接 (推荐，不占额外空间)", "hardlink")
        self.method_combo.addItem("复制 (保留原文件)", "copy")
        self.method_combo.addItem("移动 (移走原文件)", "move")
        method_layout.addWidget(self.method_combo)
        method_layout.addStretch()
        layout.addLayout(method_layout)

        # 标签预览
        layout.addWidget(QLabel("标签分布预览:"))
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(200)
        self.preview_text.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.preview_text)

        # 进度
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 12px; border: none; background: transparent;")
        self.status_label.setObjectName("secondaryHint")
        layout.addWidget(self.status_label)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        refresh_btn = QPushButton("刷新预览")
        refresh_btn.clicked.connect(self._load_preview)
        btn_layout.addWidget(refresh_btn)

        cancel_btn = QPushButton("关闭")
        cancel_btn.clicked.connect(self._on_close)
        btn_layout.addWidget(cancel_btn)

        self.start_btn = QPushButton("开始分类")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self._on_start)
        btn_layout.addWidget(self.start_btn)

        layout.addLayout(btn_layout)

    def _load_preview(self):
        from video_io.classifier import preview_classification
        try:
            tag_map = preview_classification()
        except Exception as e:
            self.preview_text.setPlainText(f"预览失败: {e}")
            return

        if not tag_map:
            self.preview_text.setPlainText("没有带标签的视频。请先分析视频。")
            self.start_btn.setEnabled(False)
            return

        self.start_btn.setEnabled(True)
        lines = []
        total = 0
        for tag_name in sorted(tag_map.keys(), key=lambda t: -len(tag_map[t])):
            videos = tag_map[tag_name]
            total += len(videos)
            lines.append(f"  [{tag_name}]  {len(videos)} 个视频")
            for v in videos[:3]:
                lines.append(f"      - {v}")
            if len(videos) > 3:
                lines.append(f"      ... 还有 {len(videos) - 3} 个")

        lines.insert(0, f"共 {len(tag_map)} 个标签, {total} 个视频项\n")
        self.preview_text.setPlainText("\n".join(lines))

    def _browse_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "选择目标目录")
        if directory:
            self.dir_edit.setText(directory)

    def _on_start(self):
        target = self.dir_edit.text().strip()
        if not target:
            QMessageBox.warning(self, "提示", "请先选择目标目录。")
            return

        reply = QMessageBox.question(
            self, "确认分类",
            f"将在「{target}」下按标签创建文件夹并归类视频，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.start_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        method = self.method_combo.currentData()

        self._worker = ClassifyWorker(target, method)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._on_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, current, total, message):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(message)

    def _on_log(self, message):
        self.status_label.setText(message)

    def _on_finished(self, stats):
        self.progress_bar.setVisible(False)
        self.status_label.setText(
            f"完成: 处理 {stats['moved']}, 跳过 {stats['skipped']}, "
            f"错误 {stats['errors']}, 创建 {stats['folders']} 个分类目录"
        )
        QMessageBox.information(self, "分类完成",
            f"移动: {stats['moved']}\n"
            f"跳过: {stats['skipped']}\n"
            f"错误: {stats['errors']}\n"
            f"目录: {stats['folders']}\n\n"
            f"共 {stats['total_videos']} 个视频参与分类。")
        self.start_btn.setEnabled(True)

    def _on_close(self):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait()
        self.accept()


# ═══════════════════════════════════════════════════════════════
#  缩略图卡片组件
# ═══════════════════════════════════════════════════════════════

class ThumbnailCard(QFrame):
    """视频缩略图卡片"""
    clicked = pyqtSignal(int)  # video_id

    def __init__(self, video: dict, parent=None):
        super().__init__(parent)
        self.video_id = video["id"]
        self.video = video
        self.setFixedSize(220, 200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("cardFrame")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 缩略图
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(204, 115)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setObjectName("thumbBg")

        thumb_path = self.video.get("thumbnail_path", "")
        if thumb_path and Path(thumb_path).exists():
            pixmap = QPixmap(thumb_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(204, 115, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                self.thumb_label.setPixmap(pixmap)
        else:
            self.thumb_label.setText("No\nPreview")

        layout.addWidget(self.thumb_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # 文件名
        name = self.video.get("file_name", "")
        if len(name) > 28:
            name = name[:26] + "..."
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("font-weight: bold; border: none; background: transparent;")
        self.name_label.setToolTip(self.video.get("file_name", ""))
        layout.addWidget(self.name_label)

        # 信息行
        duration = self.video.get("duration", 0)
        mins = int(duration // 60)
        secs = int(duration % 60)
        size_mb = (self.video.get("file_size", 0) or 0) / (1024 * 1024)
        info = f"{mins}:{secs:02d}  |  {size_mb:.0f} MB"

        status = self.video.get("analysis_status", "pending")
        if status == "done":
            info += "  [已分析]"
        elif status == "analyzing":
            info += "  [分析中...]"

        self.info_label = QLabel(info)
        self.info_label.setStyleSheet("font-size: 11px; border: none; background: transparent;")
        self.info_label.setObjectName("secondaryHint")
        layout.addWidget(self.info_label)

    def mousePressEvent(self, event):
        self.clicked.emit(self.video_id)
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════
#  主窗口
# ═══════════════════════════════════════════════════════════════

class VideoLibraryWindow(QMainWindow):
    """视频库主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("视频库分类工具")
        self.setMinimumSize(1024, 680)
        self.resize(1280, 800)

        self.db = get_db()
        self._scan_worker: Optional[ScanWorker] = None
        self._thumb_worker: Optional[ThumbnailWorker] = None
        self._analysis_worker: Optional[AnalysisWorker] = None
        self._all_videos: list[dict] = []
        self._cards: list[ThumbnailCard] = []

        self._build_menu()
        self._build_ui()
        self._load_videos()

    def _build_menu(self):
        menubar = self.menuBar()

        # 文件
        file_menu = menubar.addMenu("文件")
        add_dir_action = QAction("添加视频目录...", self)
        add_dir_action.triggered.connect(self._on_add_directory)
        file_menu.addAction(add_dir_action)

        refresh_action = QAction("刷新", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._on_refresh)
        file_menu.addAction(refresh_action)

        file_menu.addSeparator()
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 工具
        tools_menu = menubar.addMenu("工具")
        gen_thumb_action = QAction("生成所有缩略图", self)
        gen_thumb_action.triggered.connect(self._on_generate_thumbnails)
        tools_menu.addAction(gen_thumb_action)

        tools_menu.addSeparator()
        char_mgr_action = QAction("人物管理...", self)
        char_mgr_action.triggered.connect(self._on_character_manager)
        tools_menu.addAction(char_mgr_action)

        tools_menu.addSeparator()
        classify_action = QAction("一键分类...", self)
        classify_action.triggered.connect(self._on_classify)
        tools_menu.addAction(classify_action)

        tools_menu.addSeparator()
        settings_action = QAction("设置...", self)
        settings_action.triggered.connect(self._on_open_settings)
        tools_menu.addAction(settings_action)

        # 帮助
        help_menu = menubar.addMenu("帮助")
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(8)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.btn_add_dir = QPushButton("+ 添加目录")
        self.btn_add_dir.clicked.connect(self._on_add_directory)
        toolbar.addWidget(self.btn_add_dir)

        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self._on_refresh)
        toolbar.addWidget(self.btn_refresh)

        self.btn_analyze = QPushButton("开始分析")
        self.btn_analyze.setObjectName("startBtn")
        self.btn_analyze.clicked.connect(self._on_start_analysis)
        self.btn_analyze.setEnabled(False)
        toolbar.addWidget(self.btn_analyze)

        toolbar.addStretch()

        toolbar.addWidget(QLabel("排序:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["名称", "时长", "大小", "添加时间"])
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        toolbar.addWidget(self.sort_combo)

        toolbar.addWidget(QLabel("状态:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["全部", "待分析", "已分析", "有标签", "有人物"])
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.filter_combo)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索视频名称...")
        self.search_edit.setMaximumWidth(200)
        self.search_edit.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_edit)

        main_layout.addLayout(toolbar)

        # ── 主分割器 ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧: 缩略图网格
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.grid_widget = QWidget()
        self.grid_widget.setObjectName("thumbnailGrid")
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid_layout.setSpacing(10)
        self.scroll_area.setWidget(self.grid_widget)

        left_layout.addWidget(self.scroll_area)
        splitter.addWidget(left_panel)

        # 右侧: 详情面板
        self.right_panel = QFrame()
        self.right_panel.setObjectName("detailPanel")
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(8)

        # 视频预览缩略图
        self.preview_label = QLabel()
        self.preview_label.setFixedHeight(180)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setObjectName("previewLabel")
        self.preview_label.setText("选择视频查看详情")
        right_layout.addWidget(self.preview_label)

        # 文件信息
        info_group = QGroupBox("文件信息")
        info_layout = QVBoxLayout(info_group)
        self.info_text = QLabel("未选择视频")
        self.info_text.setWordWrap(True)
        info_layout.addWidget(self.info_text)
        right_layout.addWidget(info_group)

        # 标签页
        self.detail_tabs = QTabWidget()

        # 人物标签页
        self.char_list = QListWidget()
        self.detail_tabs.addTab(self.char_list, "人物")

        # 标签页
        self.tag_list = QListWidget()
        self.detail_tabs.addTab(self.tag_list, "标签")

        right_layout.addWidget(self.detail_tabs)

        splitter.addWidget(self.right_panel)
        splitter.setSizes([700, 300])
        main_layout.addWidget(splitter)

        # ── 状态栏 ──
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

        self._update_status_bar()

    # ═══════════════════════════════════════════════════
    #  视频列表操作
    # ═══════════════════════════════════════════════════

    def _load_videos(self):
        """加载视频列表到网格"""
        # 清空网格
        for i in reversed(range(self.grid_layout.count())):
            w = self.grid_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        videos = self.db.get_all_videos()
        self._all_videos = videos
        self._apply_sort_and_filter()

    def _apply_sort_and_filter(self):
        """应用排序和筛选"""
        videos = list(self._all_videos)

        # 筛选
        filter_text = self.filter_combo.currentText()
        if filter_text == "待分析":
            videos = [v for v in videos if v.get("analysis_status") == "pending"]
        elif filter_text == "已分析":
            videos = [v for v in videos if v.get("analysis_status") == "done"]
        elif filter_text == "有标签":
            tagged_ids = {t["video_id"] for t in self._get_all_video_tags()}
            videos = [v for v in videos if v["id"] in tagged_ids]
        elif filter_text == "有人物":
            from collections import defaultdict
            char_videos = defaultdict(set)
            for vc in self._get_all_video_characters():
                char_videos[vc["video_id"]] = set()
            videos = [v for v in videos if v["id"] in char_videos]

        # 搜索
        search_text = self.search_edit.text().strip().lower()
        if search_text:
            videos = [v for v in videos if search_text in v.get("file_name", "").lower()]

        # 排序
        sort_text = self.sort_combo.currentText()
        if sort_text == "名称":
            videos.sort(key=lambda v: v.get("file_name", "").lower())
        elif sort_text == "时长":
            videos.sort(key=lambda v: v.get("duration", 0), reverse=True)
        elif sort_text == "大小":
            videos.sort(key=lambda v: v.get("file_size", 0) or 0, reverse=True)
        elif sort_text == "添加时间":
            videos.sort(key=lambda v: v.get("created_at", ""), reverse=True)

        # 渲染网格
        for i in reversed(range(self.grid_layout.count())):
            w = self.grid_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        self._cards = []
        cols = max(1, self.scroll_area.width() // 240)
        for idx, video in enumerate(videos):
            card = ThumbnailCard(video)
            card.clicked.connect(self._on_video_selected)
            row = idx // cols
            col = idx % cols
            self.grid_layout.addWidget(card, row, col)
            self._cards.append(card)

        # 允许分析
        pending = [v for v in videos if v.get("analysis_status") != "analyzing"]
        self.btn_analyze.setEnabled(len(pending) > 0)

        self._update_status_bar()

    def _update_status_bar(self):
        all_v = self._all_videos
        total = len(all_v)
        done = sum(1 for v in all_v if v.get("analysis_status") == "done")
        chars = len(self.db.get_all_characters())
        self.status_label.setText(f"共 {total} 个视频  |  已分析 {done} 个  |  识别 {chars} 个角色")

    def _get_all_video_tags(self):
        result = []
        for v in self._all_videos or []:
            tags = self.db.get_video_tags(v["id"])
            for t in tags:
                result.append({"video_id": v["id"], "tag_id": t["id"]})
        return result

    def _get_all_video_characters(self):
        result = []
        for v in self._all_videos or []:
            chars = self.db.get_characters_by_video(v["id"])
            for c in chars:
                result.append({"video_id": v["id"], "character_id": c["id"]})
        return result

    # ═══════════════════════════════════════════════════
    #  事件处理
    # ═══════════════════════════════════════════════════

    def _on_add_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "选择视频目录")
        if not directory:
            return

        self.status_label.setText(f"正在扫描: {directory}...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self._scan_worker = ScanWorker([directory])
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.log.connect(self._on_log)
        self._scan_worker.start()

        self.btn_add_dir.setEnabled(False)
        self.btn_refresh.setEnabled(False)

    def _on_scan_progress(self, current, total, filepath):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"扫描中 ({current}/{total}): {Path(filepath).name}")

    def _on_scan_finished(self, new_count):
        self.progress_bar.setVisible(False)
        self.btn_add_dir.setEnabled(True)
        self.btn_refresh.setEnabled(True)
        self.status_label.setText(f"扫描完成")
        # 重新加载视频列表
        self._all_videos = self.db.get_all_videos()
        self._apply_sort_and_filter()
        # 生成缩略图
        self._on_generate_thumbnails()

    def _on_refresh(self):
        config = get_config()
        dirs = config.get("library_directories", [])
        if not dirs:
            QMessageBox.information(self, "提示", "请先添加视频目录。")
            return

        self.status_label.setText("正在刷新...")
        self._all_videos = self.db.get_all_videos()
        self._apply_sort_and_filter()
        self.status_label.setText("刷新完成")

    def _on_generate_thumbnails(self):
        videos = self._all_videos or self.db.get_all_videos()
        need_thumb = [v["id"] for v in videos if not v.get("thumbnail_path") or
                      not Path(v.get("thumbnail_path", "")).exists()]

        if not need_thumb:
            return

        self.status_label.setText(f"正在生成缩略图 (0/{len(need_thumb)})...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(need_thumb))

        self._thumb_worker = ThumbnailWorker(need_thumb)
        self._thumb_worker.progress.connect(self._on_thumb_progress)
        self._thumb_worker.thumbnail_ready.connect(self._on_thumb_ready)
        self._thumb_worker.log.connect(self._on_log)
        self._thumb_worker.finished_all.connect(self._on_thumb_finished)
        self._thumb_worker.start()

    def _on_thumb_progress(self, current, total):
        self.progress_bar.setValue(current)
        self.status_label.setText(f"正在生成缩略图 ({current}/{total})...")

    def _on_thumb_ready(self, video_id, path):
        # 更新对应卡片
        for card in self._cards:
            if card.video_id == video_id:
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    pixmap = pixmap.scaled(204, 115, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
                    card.thumb_label.setPixmap(pixmap)
                break

    def _on_thumb_finished(self):
        self.progress_bar.setVisible(False)
        self.status_label.setText("缩略图生成完成")
        # 重新加载数据
        self._all_videos = self.db.get_all_videos()

    def _on_start_analysis(self):
        """开始分析所有待分析的视频"""
        pending = [v for v in self._all_videos
                   if v.get("analysis_status") not in ("analyzing",)]

        if not pending:
            QMessageBox.information(self, "提示", "没有需要分析的视频。")
            return

        # 禁用按钮
        self.btn_analyze.setEnabled(False)
        self.btn_add_dir.setEnabled(False)
        self.btn_refresh.setEnabled(False)

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("开始 AI 分析...")

        self._analysis_worker = AnalysisWorker()
        self._analysis_worker.progress.connect(self._on_analysis_progress)
        self._analysis_worker.log.connect(self._on_log)
        self._analysis_worker.video_done.connect(self._on_analysis_video_done)
        self._analysis_worker.new_characters_found.connect(self._on_new_characters_found)
        self._analysis_worker.finished_all.connect(self._on_analysis_finished)
        self._analysis_worker.error.connect(self._on_analysis_error)
        self._analysis_worker.start()

    def _on_analysis_progress(self, stage, current, total, message):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"[{stage}] {message}")

    def _on_analysis_video_done(self, video_id):
        # 重新从数据库加载视频数据
        video = self.db.get_video_by_id(video_id)
        if video:
            for i, v in enumerate(self._all_videos):
                if v["id"] == video_id:
                    self._all_videos[i] = video
                    break
        self._apply_sort_and_filter()

    def _on_new_characters_found(self, count):
        """分析过程中发现新人物时记录"""
        if not hasattr(self, '_pending_new_chars'):
            self._pending_new_chars = 0
        self._pending_new_chars += count

    def _on_analysis_finished(self):
        self.progress_bar.setVisible(False)
        self.btn_analyze.setEnabled(True)
        self.btn_add_dir.setEnabled(True)
        self.btn_refresh.setEnabled(True)
        self.status_label.setText("AI 分析完成")

        # 重新加载全部
        self._all_videos = self.db.get_all_videos()
        self._apply_sort_and_filter()

        # 如果发现了新人物，自动弹出人物管理对话框
        pending = getattr(self, '_pending_new_chars', 0)
        self._pending_new_chars = 0
        if pending > 0:
            reply = QMessageBox.question(
                self, "发现新人物",
                f"本次分析发现了 {pending} 个新人物。\n是否立即打开人物管理进行命名？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._on_character_manager()

    def _on_character_manager(self):
        """打开人物管理对话框"""
        dialog = CharacterNamingDialog(self)
        dialog.character_saved.connect(self._load_videos)
        dialog.exec()
        self._load_videos()

    def _on_char_item_double_clicked(self, item: QListWidgetItem):
        """双击人物列表项时快速打开人物管理"""
        self._on_character_manager()

    def _on_classify(self):
        """打开一键分类对话框"""
        dialog = ClassificationDialog(self)
        dialog.exec()
        self._load_videos()

    def _on_analysis_error(self, message):
        self._on_log(f"错误: {message}")

    def _on_video_selected(self, video_id: int):
        """视频卡片被选中"""
        video = self.db.get_video_by_id(video_id)
        if not video:
            return

        # 预览图
        thumb_path = video.get("thumbnail_path", "")
        if thumb_path and Path(thumb_path).exists():
            pixmap = QPixmap(thumb_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(320, 180, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                self.preview_label.setPixmap(pixmap)
        else:
            self.preview_label.setText("无预览图")

        # 文件信息
        duration = video.get("duration", 0)
        mins = int(duration // 60)
        secs = int(duration % 60)
        size_mb = (video.get("file_size", 0) or 0) / (1024 * 1024)
        w, h = video.get("width", 0), video.get("height", 0)
        fps = video.get("fps", 0)

        info_lines = [
            f"文件名: {video.get('file_name', '')}",
            f"路径: {video.get('file_path', '')}",
            f"时长: {mins}:{secs:02d}",
            f"大小: {size_mb:.1f} MB",
            f"分辨率: {w} x {h}",
            f"帧率: {fps:.1f} fps" if fps else "",
            f"状态: {video.get('analysis_status', '')}",
        ]
        self.info_text.setText("\n".join(line for line in info_lines if line))

        # 人物列表（含人脸缩略图）
        self.char_list.clear()
        characters = self.db.get_characters_by_video(video_id)
        if characters:
            for c in characters:
                name = c.get("name") or f"未命名人物 #{c['id']}"
                item_text = f"{name}  (出现 {c.get('appear_count', 0)} 次)"
                item = QListWidgetItem(item_text)

                # 设置人物缩略图为图标
                face_path = c.get("representative_face_path", "")
                if face_path and Path(face_path).exists():
                    pixmap = QPixmap(face_path)
                    if not pixmap.isNull():
                        icon = QPixmap(face_path).scaled(48, 48,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
                        item.setIcon(QPixmap(icon))
                self.char_list.addItem(item)

            # 双击人物编辑名称
            self.char_list.itemDoubleClicked.connect(self._on_char_item_double_clicked)
        else:
            self.char_list.addItem("(暂无人物数据)")

        # 标签列表
        self.tag_list.clear()
        tags = self.db.get_video_tags(video_id)
        if tags:
            for t in tags:
                conf = t.get("confidence", 0)
                item = QListWidgetItem(f"{t['name']}  ({conf:.0%})")
                self.tag_list.addItem(item)
        else:
            self.tag_list.addItem("(暂无标签数据)")

    def _on_sort_changed(self):
        self._apply_sort_and_filter()

    def _on_filter_changed(self):
        self._apply_sort_and_filter()

    def _on_search_changed(self):
        self._apply_sort_and_filter()

    def _on_open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_theme()
            self._load_videos()

    def _apply_theme(self):
        """根据当前设置重新应用主题 QSS"""
        config = load_settings()
        theme_mode = config.get("theme_mode", "auto")
        qss = get_theme_qss(theme_mode)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(qss)
            self.status_label.setText(f"主题: {get_current_theme_name(theme_mode)}")

    def _on_about(self):
        QMessageBox.about(self, "关于",
                         "视频库分类工具 v0.1\n\n"
                         "本地视频资源管理 + AI 自动分类\n"
                         "支持人脸识别、场景标签、人物标记")

    def _on_log(self, message: str):
        self.status_label.setText(message)

    def closeEvent(self, event):
        if self._scan_worker and self._scan_worker.isRunning():
            self._scan_worker.quit()
            self._scan_worker.wait()
        if self._thumb_worker and self._thumb_worker.isRunning():
            self._thumb_worker.quit()
            self._thumb_worker.wait()
        if self._analysis_worker and self._analysis_worker.isRunning():
            self._analysis_worker.cancel()
            self._analysis_worker.quit()
            self._analysis_worker.wait()
        self.db.close()
        super().closeEvent(event)


def main():
    """启动 GUI"""
    app = QApplication(sys.argv)

    # 加载用户主题设置
    config = load_settings()
    theme_mode = config.get("theme_mode", "auto")
    qss = get_theme_qss(theme_mode)
    app.setStyleSheet(qss)

    # 设置字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    window = VideoLibraryWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
