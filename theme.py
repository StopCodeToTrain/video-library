"""主题管理 - 浅色/深色双主题 + 系统自动检测

支持三种模式:
  - "auto": 跟随系统亮暗模式自动切换
  - "dark": 始终深色 (Catppuccin Mocha)
  - "light": 始终浅色 (Catppuccin Latte)
"""

import sys
import subprocess
from PyQt6.QtCore import QSettings


# ═══════════════════════════════════════════════════════════════
#  深色主题 (Catppuccin Mocha)
# ═══════════════════════════════════════════════════════════════

DARK_QSS = """
/* 基础底色 - 仅作用于顶层窗口，不覆盖子控件 */
QMainWindow {
    background-color: #11111b;
}
QDockWidget {
    background-color: #1e1e2e;
}
QWidget#centralPanel {
    background-color: #11111b;
}

/* 通用文本 */
QLabel {
    color: #cdd6f4;
    background: transparent;
    border: none;
}

/* 分组框 - 带颜色标识条 */
QGroupBox {
    border: 2px solid #313244;
    border-top: 3px solid #89b4fa;
    border-radius: 8px;
    margin-top: 16px;
    padding: 18px 12px 12px 12px;
    background-color: #181825;
    font-weight: bold;
    color: #cdd6f4;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: #89b4fa;
    background-color: #181825;
}

/* 按钮 - 使用明显区别于背景的颜色 */
QPushButton {
    background-color: #45475a;
    color: #cdd6f4;
    border: 1px solid #585b70;
    border-radius: 6px;
    padding: 7px 18px;
    font-weight: 500;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #585b70;
    border-color: #74c7ec;
}
QPushButton:pressed {
    background-color: #6c7086;
}
QPushButton:disabled {
    background-color: #1e1e2e;
    color: #585b70;
    border-color: #313244;
}

/* 主要操作按钮 */
QPushButton#startBtn {
    background-color: #a6e3a1;
    color: #11111b;
    font-weight: bold;
    border: 1px solid #a6e3a1;
}
QPushButton#startBtn:hover {
    background-color: #94e2d5;
}

/* 危险/停止按钮 */
QPushButton#stopBtn {
    background-color: #f38ba8;
    color: #11111b;
    font-weight: bold;
    border: 1px solid #f38ba8;
}
QPushButton#stopBtn:hover {
    background-color: #eba0ac;
}

/* 下拉框 */
QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 5px;
    padding: 5px 10px;
    min-width: 100px;
}
QComboBox:hover {
    border-color: #74c7ec;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    selection-background-color: #45475a;
    border: 1px solid #585b70;
    border-radius: 4px;
    outline: none;
}

/* 输入框 */
QLineEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 5px;
    padding: 5px 10px;
}
QLineEdit:focus {
    border-color: #89b4fa;
    border-width: 2px;
}

/* 数值选择 */
QSpinBox, QDoubleSpinBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 5px;
    padding: 5px 8px;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #89b4fa;
}

/* 滚动区域 - 透明背景 */
QScrollArea {
    border: none;
    background: transparent;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}

/* 垂直滚动条 */
QScrollBar:vertical {
    background-color: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #585b70;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

/* 水平滚动条 */
QScrollBar:horizontal {
    background-color: transparent;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background-color: #45475a;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #585b70;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* 分割条 */
QSplitter::handle {
    background-color: #313244;
    width: 3px;
}

/* 进度条 */
QProgressBar {
    border: 1px solid #313244;
    border-radius: 5px;
    text-align: center;
    background-color: #11111b;
    color: #cdd6f4;
    height: 20px;
    font-size: 11px;
}
QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 4px;
}

/* 标签页 */
QTabWidget::pane {
    border: 1px solid #313244;
    background-color: #181825;
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    background-color: #1e1e2e;
    color: #6c7086;
    padding: 7px 18px;
    border: 1px solid #313244;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 3px;
}
QTabBar::tab:selected {
    background-color: #181825;
    color: #cdd6f4;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    color: #a6adc8;
}

/* 列表 */
QListWidget {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 6px;
    color: #cdd6f4;
    outline: none;
}
QListWidget::item {
    padding: 4px 8px;
    border-radius: 4px;
}
QListWidget::item:hover {
    background-color: #313244;
}
QListWidget::item:selected {
    background-color: #45475a;
    color: #cdd6f4;
}

/* 树形视图 */
QTreeWidget {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 6px;
    color: #cdd6f4;
    outline: none;
}
QTreeWidget::item {
    padding: 3px 6px;
    border-radius: 3px;
}
QTreeWidget::item:hover {
    background-color: #313244;
}
QTreeWidget::item:selected {
    background-color: #45475a;
}

/* 复选框 */
QCheckBox {
    color: #cdd6f4;
    spacing: 8px;
}
QCheckBox::indicator {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 3px;
    width: 17px;
    height: 17px;
}
QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}

/* 状态栏 */
QStatusBar {
    background-color: #181825;
    color: #a6adc8;
    border-top: 1px solid #313244;
    padding: 2px 8px;
}

/* 菜单 */
QMenuBar {
    background-color: #181825;
    color: #cdd6f4;
    border-bottom: 1px solid #313244;
    padding: 2px;
}
QMenuBar::item {
    padding: 4px 12px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #313244;
}
QMenu {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px;
}
QMenu::item {
    padding: 7px 28px 7px 16px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #45475a;
}
QMenu::separator {
    height: 1px;
    background-color: #45475a;
    margin: 5px 8px;
}

/* 对话框 */
QDialog {
    background-color: #1e1e2e;
    color: #cdd6f4;
}

/* 多行文本 */
QPlainTextEdit, QTextEdit {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 5px;
    font-family: "Cascadia Code", "Consolas", monospace;
    padding: 6px;
}

/* 卡片容器 */
QFrame#cardFrame {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 10px;
    padding: 6px;
}
QFrame#cardFrame:hover {
    border-color: #74c7ec;
    background-color: #1e1e2e;
}

/* 侧边栏 */
QFrame#sidebarPanel {
    background-color: #181825;
    border-right: 2px solid #313244;
}
QFrame#sidebarPanel QLabel {
    color: #a6adc8;
}
QFrame#sidebarPanel QGroupBox {
    background-color: #11111b;
    border-color: #313244;
    border-top-color: #cba6f7;
}

/* 详情面板 */
QFrame#detailPanel {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 8px;
    padding: 10px;
}
QFrame#detailPanel QLabel#sectionTitle {
    color: #89b4fa;
    font-weight: bold;
    font-size: 13px;
}

/* 缩略图网格容器 */
QWidget#thumbnailGrid {
    background: transparent;
}

/* 工具栏 */
QToolBar {
    background-color: #181825;
    border-bottom: 1px solid #313244;
    spacing: 6px;
    padding: 4px;
}
QToolButton {
    background-color: transparent;
    color: #cdd6f4;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 5px 10px;
}
QToolButton:hover {
    background-color: #313244;
    border-color: #45475a;
}

/* 搜索框 */
QLineEdit#searchBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 15px;
    padding: 6px 14px;
}
QLineEdit#searchBox:focus {
    border-color: #89b4fa;
}

/* 预览缩略图 */
QLabel#previewLabel {
    background-color: #11111b;
    border: 1px solid #313244;
    border-radius: 8px;
    color: #6c7086;
}

/* 次要提示文字 */
QLabel#secondaryHint {
    color: #a6adc8;
}

/* 缩略图背景 */
QLabel#thumbBg {
    background-color: #11111b;
    border: 1px solid #313244;
    border-radius: 6px;
    color: #6c7086;
}

/* 人脸缩略图 */
QLabel#faceThumb {
    border: 1px solid #45475a;
    border-radius: 4px;
    background-color: #11111b;
}

/* 未命名人物组 */
QGroupBox#unnamedGroup {
    border: 2px solid #f38ba8;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 18px;
    background-color: #181825;
    font-weight: bold;
}
QGroupBox#unnamedGroup::title {
    color: #f38ba8;
}

/* 设置保存按钮 */
QPushButton#settingsSaveBtn {
    border-color: #89b4fa;
}

/* 合并按钮 */
QPushButton#mergeBtn {
    border-color: #f9e2af;
    color: #f9e2af;
}
"""


# ═══════════════════════════════════════════════════════════════
#  浅色主题 (Catppuccin Latte)
# ═══════════════════════════════════════════════════════════════

LIGHT_QSS = """
/* 基础底色 - 仅作用于顶层窗口 */
QMainWindow {
    background-color: #e6e9ef;
}
QDockWidget {
    background-color: #eff1f5;
}
QWidget#centralPanel {
    background-color: #e6e9ef;
}

/* 通用文本 */
QLabel {
    color: #4c4f69;
    background: transparent;
    border: none;
}

/* 分组框 - 带颜色标识条 */
QGroupBox {
    border: 2px solid #ccd0da;
    border-top: 3px solid #1e66f5;
    border-radius: 8px;
    margin-top: 16px;
    padding: 18px 12px 12px 12px;
    background-color: #ffffff;
    font-weight: bold;
    color: #4c4f69;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: #1e66f5;
    background-color: #ffffff;
}

/* 按钮 - 高对比度，与面板背景明显区分 */
QPushButton {
    background-color: #dce0e8;
    color: #4c4f69;
    border: 1px solid #bcc0cc;
    border-radius: 6px;
    padding: 7px 18px;
    font-weight: 500;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #ccd0da;
    border-color: #1e66f5;
}
QPushButton:pressed {
    background-color: #bcc0cc;
}
QPushButton:disabled {
    background-color: #eff1f5;
    color: #9ca0b0;
    border-color: #ccd0da;
}

/* 主要操作按钮 */
QPushButton#startBtn {
    background-color: #40a02b;
    color: #ffffff;
    font-weight: bold;
    border: 1px solid #40a02b;
}
QPushButton#startBtn:hover {
    background-color: #179299;
    border-color: #179299;
}

/* 危险/停止按钮 */
QPushButton#stopBtn {
    background-color: #d20f39;
    color: #ffffff;
    font-weight: bold;
    border: 1px solid #d20f39;
}
QPushButton#stopBtn:hover {
    background-color: #e64553;
    border-color: #e64553;
}

/* 下拉框 - 白色背景加灰色边框 */
QComboBox {
    background-color: #ffffff;
    color: #4c4f69;
    border: 1px solid #bcc0cc;
    border-radius: 5px;
    padding: 5px 10px;
    min-width: 100px;
}
QComboBox:hover {
    border-color: #1e66f5;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #4c4f69;
    selection-background-color: #dce0e8;
    border: 1px solid #ccd0da;
    border-radius: 4px;
    outline: none;
}

/* 输入框 */
QLineEdit {
    background-color: #ffffff;
    color: #4c4f69;
    border: 1px solid #bcc0cc;
    border-radius: 5px;
    padding: 5px 10px;
}
QLineEdit:focus {
    border-color: #1e66f5;
    border-width: 2px;
}

/* 数值选择 */
QSpinBox, QDoubleSpinBox {
    background-color: #ffffff;
    color: #4c4f69;
    border: 1px solid #bcc0cc;
    border-radius: 5px;
    padding: 5px 8px;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #1e66f5;
}

/* 滚动区域 - 透明 */
QScrollArea {
    border: none;
    background: transparent;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}

/* 垂直滚动条 */
QScrollBar:vertical {
    background-color: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #acb0be;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #8c8fa1;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

/* 水平滚动条 */
QScrollBar:horizontal {
    background-color: transparent;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background-color: #acb0be;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #8c8fa1;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* 分割条 */
QSplitter::handle {
    background-color: #ccd0da;
    width: 3px;
}

/* 进度条 */
QProgressBar {
    border: 1px solid #ccd0da;
    border-radius: 5px;
    text-align: center;
    background-color: #ffffff;
    color: #4c4f69;
    height: 20px;
    font-size: 11px;
}
QProgressBar::chunk {
    background-color: #1e66f5;
    border-radius: 4px;
}

/* 标签页 */
QTabWidget::pane {
    border: 1px solid #ccd0da;
    background-color: #ffffff;
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    background-color: #eff1f5;
    color: #9ca0b0;
    padding: 7px 18px;
    border: 1px solid #ccd0da;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 3px;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    color: #4c4f69;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    color: #5c5f77;
}

/* 列表 */
QListWidget {
    background-color: #ffffff;
    border: 1px solid #ccd0da;
    border-radius: 6px;
    color: #4c4f69;
    outline: none;
}
QListWidget::item {
    padding: 4px 8px;
    border-radius: 4px;
}
QListWidget::item:hover {
    background-color: #dce0e8;
}
QListWidget::item:selected {
    background-color: #ccd0da;
    color: #4c4f69;
}

/* 树形视图 */
QTreeWidget {
    background-color: #ffffff;
    border: 1px solid #ccd0da;
    border-radius: 6px;
    color: #4c4f69;
    outline: none;
}
QTreeWidget::item {
    padding: 3px 6px;
    border-radius: 3px;
}
QTreeWidget::item:hover {
    background-color: #dce0e8;
}
QTreeWidget::item:selected {
    background-color: #ccd0da;
}

/* 复选框 */
QCheckBox {
    color: #4c4f69;
    spacing: 8px;
}
QCheckBox::indicator {
    background-color: #ffffff;
    border: 1px solid #bcc0cc;
    border-radius: 3px;
    width: 17px;
    height: 17px;
}
QCheckBox::indicator:checked {
    background-color: #1e66f5;
    border-color: #1e66f5;
}

/* 状态栏 */
QStatusBar {
    background-color: #dce0e8;
    color: #5c5f77;
    border-top: 1px solid #ccd0da;
    padding: 2px 8px;
}

/* 菜单栏 */
QMenuBar {
    background-color: #ffffff;
    color: #4c4f69;
    border-bottom: 1px solid #ccd0da;
    padding: 2px;
}
QMenuBar::item {
    padding: 4px 12px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #dce0e8;
}
QMenu {
    background-color: #ffffff;
    color: #4c4f69;
    border: 1px solid #ccd0da;
    border-radius: 6px;
    padding: 6px;
}
QMenu::item {
    padding: 7px 28px 7px 16px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #dce0e8;
}
QMenu::separator {
    height: 1px;
    background-color: #ccd0da;
    margin: 5px 8px;
}

/* 对话框 */
QDialog {
    background-color: #eff1f5;
    color: #4c4f69;
}

/* 多行文本 */
QPlainTextEdit, QTextEdit {
    background-color: #ffffff;
    color: #4c4f69;
    border: 1px solid #ccd0da;
    border-radius: 5px;
    font-family: "Cascadia Code", "Consolas", monospace;
    padding: 6px;
}

/* 卡片容器 - 缩略图项 */
QFrame#cardFrame {
    background-color: #ffffff;
    border: 1px solid #ccd0da;
    border-radius: 10px;
    padding: 6px;
}
QFrame#cardFrame:hover {
    border-color: #1e66f5;
    background-color: #f4f4fa;
}

/* 侧边栏 */
QFrame#sidebarPanel {
    background-color: #ffffff;
    border-right: 2px solid #ccd0da;
}
QFrame#sidebarPanel QLabel {
    color: #5c5f77;
}
QFrame#sidebarPanel QGroupBox {
    background-color: #f4f4f9;
    border-color: #dce0e8;
    border-top-color: #8839ef;
}

/* 详情面板 */
QFrame#detailPanel {
    background-color: #ffffff;
    border: 1px solid #ccd0da;
    border-radius: 8px;
    padding: 10px;
}
QFrame#detailPanel QLabel#sectionTitle {
    color: #1e66f5;
    font-weight: bold;
    font-size: 13px;
}

/* 缩略图网格容器 */
QWidget#thumbnailGrid {
    background: transparent;
}

/* 工具栏 */
QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #ccd0da;
    spacing: 6px;
    padding: 4px;
}
QToolButton {
    background-color: transparent;
    color: #4c4f69;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 5px 10px;
}
QToolButton:hover {
    background-color: #dce0e8;
    border-color: #bcc0cc;
}

/* 搜索框 */
QLineEdit#searchBox {
    background-color: #ffffff;
    border: 1px solid #bcc0cc;
    border-radius: 15px;
    padding: 6px 14px;
}
QLineEdit#searchBox:focus {
    border-color: #1e66f5;
}

/* 预览缩略图 */
QLabel#previewLabel {
    background-color: #e6e9ef;
    border: 1px solid #ccd0da;
    border-radius: 8px;
    color: #9ca0b0;
}

/* 次要提示文字 */
QLabel#secondaryHint {
    color: #6c6f85;
}

/* 缩略图背景 */
QLabel#thumbBg {
    background-color: #e6e9ef;
    border: 1px solid #ccd0da;
    border-radius: 6px;
    color: #9ca0b0;
}

/* 人脸缩略图 */
QLabel#faceThumb {
    border: 1px solid #ccd0da;
    border-radius: 4px;
    background-color: #e6e9ef;
}

/* 未命名人物组 */
QGroupBox#unnamedGroup {
    border: 2px solid #d20f39;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 18px;
    background-color: #ffffff;
    font-weight: bold;
}
QGroupBox#unnamedGroup::title {
    color: #d20f39;
}

/* 设置保存按钮 */
QPushButton#settingsSaveBtn {
    border-color: #1e66f5;
}

/* 合并按钮 */
QPushButton#mergeBtn {
    border-color: #df8e1d;
    color: #df8e1d;
}
"""


# ═══════════════════════════════════════════════════════════════
#  主题工具函数
# ═══════════════════════════════════════════════════════════════

def _detect_windows_theme() -> str:
    """检测 Windows 系统主题（light/dark）"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return "light" if value == 1 else "dark"
    except Exception:
        return "dark"


def _detect_system_theme() -> str:
    """跨平台检测系统亮暗模式"""
    if sys.platform == "win32":
        return _detect_windows_theme()
    elif sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True, timeout=3
            )
            return "dark" if result.returncode == 0 and "Dark" in result.stdout else "light"
        except Exception:
            return "light"
    else:
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True, text=True, timeout=3
            )
            return "dark" if "dark" in result.stdout.lower() else "light"
        except Exception:
            return "dark"


def get_theme_qss(theme_mode: str = "auto") -> str:
    """获取当前应该使用的 QSS 样式表"""
    if theme_mode == "auto":
        actual = _detect_system_theme()
    else:
        actual = theme_mode
    return DARK_QSS if actual == "dark" else LIGHT_QSS


def get_current_theme_name(theme_mode: str = "auto") -> str:
    """获取当前生效的主题名称"""
    if theme_mode == "auto":
        actual = _detect_system_theme()
        return f"自动 ({actual})"
    return theme_mode
