# -*- coding: utf-8 -*-
"""Main menu designer dialog for title/background/BGM with live preview."""
from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any, Optional

from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QFileDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtCore import Qt, QRect


class MenuPreview(QWidget):
    """Lightweight rectangle-based preview for main menu layout."""

    def __init__(self, project_dir: Optional[Path], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project_dir = project_dir
        self.setMinimumSize(520, 320)
        self._state: dict[str, Any] = {}
        self._bg_pixmap: Optional[QPixmap] = None
        self._title_pixmap: Optional[QPixmap] = None

    # state management
    def update_state(self, cfg: dict[str, Any]):
        self._state = cfg or {}
        self._load_bg(cfg.get("menu_background", ""))
        self._load_title_img(cfg.get("menu_title_image", ""))
        self.update()

    def _resolve(self, path_str: str) -> Optional[Path]:
        if not path_str:
            return None
        p = Path(path_str)
        if p.is_absolute():
            return p if p.exists() else None
        if self.project_dir:
            candidate = (self.project_dir / p).resolve()
            return candidate if candidate.exists() else None
        return p if p.exists() else None

    def _load_bg(self, path_str: str):
        resolved = self._resolve(path_str)
        if resolved and resolved.exists():
            try:
                self._bg_pixmap = QPixmap(str(resolved))
                return
            except Exception:
                pass
        self._bg_pixmap = None

    def _load_title_img(self, path_str: str):
        resolved = self._resolve(path_str)
        if resolved and resolved.exists():
            try:
                self._title_pixmap = QPixmap(str(resolved))
                return
            except Exception:
                pass
        self._title_pixmap = None

    # painting
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # logical canvas 800x600 scaled to widget
        target_rect = self.rect()
        base_w, base_h = 800, 600
        scale = min(target_rect.width() / base_w, target_rect.height() / base_h)
        view_w, view_h = int(base_w * scale), int(base_h * scale)
        offset_x = (target_rect.width() - view_w) // 2
        offset_y = (target_rect.height() - view_h) // 2

        def to_view(x: float, y: float) -> tuple[int, int]:
            return int(offset_x + x * scale), int(offset_y + y * scale)

        def to_size(w: float, h: float) -> tuple[int, int]:
            return int(w * scale), int(h * scale)

        def pick_xy(val, default: tuple[float, float]):
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                try:
                    return float(val[0]), float(val[1])
                except Exception:
                    pass
            return default

        # background
        bg_rect = QRect(offset_x, offset_y, view_w, view_h)
        painter.fillRect(bg_rect, QColor(24, 24, 28))
        if self._bg_pixmap:
            scaled = self._bg_pixmap.scaled(view_w, view_h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(bg_rect, scaled, scaled.rect())

        overlay_alpha = int(self._state.get("menu_overlay_alpha", 0) or 0)
        if overlay_alpha > 0:
            painter.fillRect(bg_rect, QColor(0, 0, 0, max(0, min(255, overlay_alpha))))

        # title image or placeholder
        title_img_pos = self._state.get("menu_title_image_pos", [400, 80])
        title_img_scale = float(self._state.get("menu_title_image_scale", 1.0) or 1.0)
        tx, ty = pick_xy(title_img_pos, (400.0, 80.0))
        if self._title_pixmap:
            raw_w, raw_h = self._title_pixmap.width(), self._title_pixmap.height()
            draw_w, draw_h = to_size(raw_w * title_img_scale, raw_h * title_img_scale)
            cx, cy = to_view(tx, ty)
            painter.drawPixmap(cx - draw_w // 2, cy - draw_h // 2, draw_w, draw_h, self._title_pixmap)
        else:
            cx, cy = to_view(tx, ty)
            ph_w, ph_h = to_size(220 * title_img_scale, 100 * title_img_scale)
            painter.setPen(QColor(0, 160, 130, 200))
            painter.setBrush(QColor(0, 200, 160, 90))
            painter.drawRoundedRect(cx - ph_w // 2, cy - ph_h // 2, ph_w, ph_h, 10, 10)

        # title text
        title_text = self._state.get("menu_title", "标题")
        title_pos = self._state.get("menu_title_pos", [60, 60])
        title_scale = float(self._state.get("menu_title_scale", 1.0) or 1.0)
        title_color = self._state.get("menu_title_color", [240, 240, 255])
        px, py = pick_xy(title_pos, (60.0, 60.0))
        font = QFont("Arial", max(10, int(36 * title_scale)))
        painter.setFont(font)
        painter.setPen(QColor(*[int(min(255, max(0, c))) for c in (title_color if isinstance(title_color, (list, tuple)) else [240, 240, 255])]))
        txp, typ = to_view(px, py)
        painter.drawText(txp, typ, title_text)

        # options list
        opt_pos = self._state.get("menu_option_pos", [80, 140])
        opt_color = self._state.get("menu_option_color", [255, 255, 255])
        opt_scale = float(self._state.get("menu_option_scale", 1.0) or 1.0)
        ox, oy = pick_xy(opt_pos, (80.0, 140.0))
        font_opt = QFont("Arial", max(8, int(20 * opt_scale)))
        painter.setFont(font_opt)
        painter.setPen(QColor(*[int(min(255, max(0, c))) for c in (opt_color if isinstance(opt_color, (list, tuple)) else [255, 255, 255])]))
        rect_w, rect_h = to_size(300 * opt_scale, 70 * opt_scale)
        vx, vy = to_view(ox, oy)
        rect_y = vy - rect_h // 2
        painter.setBrush(QColor(255, 255, 255, 28))
        painter.setPen(QColor(255, 255, 255, 150))
        painter.drawRoundedRect(vx, rect_y, rect_w, rect_h, 10, 10)

        painter.end()


class MainMenuDesigner(QDialog):
    def __init__(self, project_dir: Optional[Path] = None, project_manager=None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project_manager = project_manager
        self.project_dir = Path(project_dir) if project_dir else (Path(project_manager.project_dir) if project_manager and project_manager.project_dir else None)
        data = (project_manager.project_data.get("game_config", {}) if project_manager else {}) or {}

        self.setWindowTitle("主菜单设计器")
        self.resize(980, 640)

        layout = QVBoxLayout(self)
        top_row = QHBoxLayout()

        # 左侧表单（参考 UI 设计器的布局）
        form = QFormLayout()
        form.addRow(self._section_label("标题"))

        self.title_edit = QLineEdit(data.get("menu_title", ""))
        form.addRow("标题文字", self.title_edit)

        pos_row = QHBoxLayout()
        self.title_x = QSpinBox(); self.title_x.setRange(0, 2000); self.title_x.setValue(int((data.get("menu_title_pos") or [60, 60])[0]))
        self.title_y = QSpinBox(); self.title_y.setRange(0, 2000); self.title_y.setValue(int((data.get("menu_title_pos") or [60, 60])[1]))
        pos_row.addWidget(QLabel("X")); pos_row.addWidget(self.title_x); pos_row.addWidget(QLabel("Y")); pos_row.addWidget(self.title_y)
        form.addRow("标题位置", pos_row)

        self.title_scale = QDoubleSpinBox(); self.title_scale.setRange(0.1, 5.0); self.title_scale.setSingleStep(0.1); self.title_scale.setDecimals(2); self.title_scale.setValue(float(data.get("menu_title_scale", 1.0) or 1.0))
        form.addRow("标题缩放", self.title_scale)

        self.title_color_edit = QLineEdit(self._color_to_hex(data.get("menu_title_color", [240, 240, 255])))
        color_row = QWidget(); color_layout = QHBoxLayout(color_row); color_layout.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton("选色"); btn.clicked.connect(lambda: self._pick_color(self.title_color_edit))
        color_layout.addWidget(self.title_color_edit); color_layout.addWidget(btn)
        form.addRow("标题颜色", color_row)

        self.title_img_edit = QLineEdit(data.get("menu_title_image", ""))
        form.addRow("标题图片", self._make_file_row(self.title_img_edit, self._pick_title_image, True))

        pos_img_row = QHBoxLayout()
        self.title_img_x = QSpinBox(); self.title_img_x.setRange(0, 2000); self.title_img_x.setValue(int((data.get("menu_title_image_pos") or [400, 80])[0]))
        self.title_img_y = QSpinBox(); self.title_img_y.setRange(0, 2000); self.title_img_y.setValue(int((data.get("menu_title_image_pos") or [400, 80])[1]))
        pos_img_row.addWidget(QLabel("X")); pos_img_row.addWidget(self.title_img_x); pos_img_row.addWidget(QLabel("Y")); pos_img_row.addWidget(self.title_img_y)
        form.addRow("标题图片中心", pos_img_row)

        self.title_img_scale = QDoubleSpinBox(); self.title_img_scale.setRange(0.1, 5.0); self.title_img_scale.setSingleStep(0.1); self.title_img_scale.setDecimals(2); self.title_img_scale.setValue(float(data.get("menu_title_image_scale", 1.0) or 1.0))
        form.addRow("标题图缩放", self.title_img_scale)

        form.addRow(self._section_label("选项"))

        pos_opt_row = QHBoxLayout()
        self.option_x = QSpinBox(); self.option_x.setRange(0, 2000); self.option_x.setValue(int((data.get("menu_option_pos") or [80, 140])[0]))
        self.option_y = QSpinBox(); self.option_y.setRange(0, 2000); self.option_y.setValue(int((data.get("menu_option_pos") or [80, 140])[1]))
        pos_opt_row.addWidget(QLabel("X")); pos_opt_row.addWidget(self.option_x); pos_opt_row.addWidget(QLabel("Y")); pos_opt_row.addWidget(self.option_y)
        form.addRow("选项起始位置", pos_opt_row)

        self.option_scale = QDoubleSpinBox(); self.option_scale.setRange(0.5, 5.0); self.option_scale.setSingleStep(0.1); self.option_scale.setDecimals(2); self.option_scale.setValue(float(data.get("menu_option_scale", 1.0) or 1.0))
        form.addRow("选项缩放", self.option_scale)

        self.option_color_edit = QLineEdit(self._color_to_hex(data.get("menu_option_color", [255, 255, 255])))
        opt_color_row = QWidget(); opt_color_layout = QHBoxLayout(opt_color_row); opt_color_layout.setContentsMargins(0, 0, 0, 0)
        btn_opt = QPushButton("选色"); btn_opt.clicked.connect(lambda: self._pick_color(self.option_color_edit))
        opt_color_layout.addWidget(self.option_color_edit); opt_color_layout.addWidget(btn_opt)
        form.addRow("选项颜色", opt_color_row)

        form.addRow(self._section_label("媒体"))

        self.bg_edit = QLineEdit(data.get("menu_background", ""))
        form.addRow("背景图", self._make_file_row(self.bg_edit, self._pick_bg, True))

        self.video_edit = QLineEdit(data.get("menu_video", ""))
        form.addRow("背景视频", self._make_file_row(self.video_edit, self._pick_video, True))

        self.video_loop_chk = QCheckBox("视频循环播放")
        self.video_loop_chk.setChecked(bool(data.get("menu_video_loop", False)))
        form.addRow("", self.video_loop_chk)

        self.bgm_edit = QLineEdit(data.get("menu_bgm", ""))
        form.addRow("BGM", self._make_file_row(self.bgm_edit, self._pick_bgm, True))

        self.bgm_loop_chk = QCheckBox("BGM循环播放")
        self.bgm_loop_chk.setChecked(bool(data.get("menu_bgm_loop", True)))
        form.addRow("", self.bgm_loop_chk)

        form.addRow(self._section_label("其他"))

        self.overlay_alpha = QSpinBox()
        self.overlay_alpha.setRange(0, 255)
        self.overlay_alpha.setValue(int(data.get("menu_overlay_alpha", 0)))
        form.addRow("遮罩透明度 (0-255)", self.overlay_alpha)

        # 预览
        self.preview = MenuPreview(self.project_dir, self)
        preview_wrap = QVBoxLayout()
        preview_wrap.addWidget(QLabel("主菜单预览 (矩形示意)", self))
        preview_wrap.addWidget(self.preview)

        top_row.addLayout(form, 1)
        top_row.addLayout(preview_wrap, 1)
        layout.addLayout(top_row)

        hint = QLabel("说明：背景/视频/BGM/标题图会复制到工程目录 (images/videos/audios)。遮罩透明度 0 不加深，255 全黑；颜色用 #RRGGBB。")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_cancel = QPushButton("取消")
        btn_save.clicked.connect(self._save)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self._wire_preview()
        self._update_preview()

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; padding-top: 6px;")
        return lbl

    # wiring
    def _wire_preview(self):
        for w in [
            self.title_edit,
            self.bg_edit,
            self.video_edit,
            self.title_img_edit,
            self.option_color_edit,
            self.title_color_edit,
            self.bgm_edit,
        ]:
            w.editingFinished.connect(self._update_preview)
        for sp in [
            self.title_x,
            self.title_y,
            self.title_scale,
            self.option_x,
            self.option_y,
            self.option_scale,
            self.overlay_alpha,
            self.title_img_x,
            self.title_img_y,
            self.title_img_scale,
        ]:
            sp.valueChanged.connect(self._update_preview)
        self.video_loop_chk.stateChanged.connect(self._update_preview)
        self.bgm_loop_chk.stateChanged.connect(self._update_preview)

    # helpers
    def _make_file_row(self, edit: QLineEdit, handler, with_clear: bool = False) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit)
        btn = QPushButton("选择"); btn.clicked.connect(handler)
        layout.addWidget(btn)
        if with_clear:
            btn_clear = QPushButton("清除")
            btn_clear.clicked.connect(lambda: edit.setText(""))
            layout.addWidget(btn_clear)
        return row

    def _pick_bg(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择背景图", str(self.project_dir or ""), "图片 (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        self.bg_edit.setText(self._store_into_project(path, "resources/images"))
        self._update_preview()

    def _pick_bgm(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择BGM", str(self.project_dir or ""), "音频 (*.mp3 *.ogg *.wav)")
        if not path:
            return
        self.bgm_edit.setText(self._store_into_project(path, "resources/audios"))
        self._update_preview()

    def _pick_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择视频", str(self.project_dir or ""), "视频 (*.mp4 *.mov *.mkv *.avi)")
        if not path:
            return
        self.video_edit.setText(self._store_into_project(path, "resources/videos"))
        self._update_preview()

    def _pick_title_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择标题图片", str(self.project_dir or ""), "图片 (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        self.title_img_edit.setText(self._store_into_project(path, "resources/images"))
        self._update_preview()

    def _store_into_project(self, src_path: str, subfolder: str) -> str:
        if not src_path:
            return ""
        if not self.project_dir:
            return src_path
        src = Path(src_path)
        target_dir = (self.project_dir / subfolder).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            if src.resolve().is_relative_to(self.project_dir.resolve()):
                return str(src.relative_to(self.project_dir))
        except Exception:
            pass
        target = target_dir / src.name
        try:
            shutil.copy2(src, target)
            return str(target.relative_to(self.project_dir))
        except Exception:
            return str(src)

    def _save(self):
        cfg = self.project_manager.project_data.setdefault("game_config", {}) if self.project_manager else {}
        cfg.update(self._collect_cfg())
        cfg["menu_bgm"] = self.bgm_edit.text()
        cfg["menu_bgm_loop"] = self.bgm_loop_chk.isChecked()
        QMessageBox.information(self, "已保存", "主菜单配置已写入工程，保存工程文件后生效。")
        self.accept()

    def _collect_cfg(self) -> dict[str, Any]:
        return {
            "menu_title": self.title_edit.text(),
            "menu_title_pos": [int(self.title_x.value()), int(self.title_y.value())],
            "menu_title_color": self._hex_to_rgb(self.title_color_edit.text()),
            "menu_title_scale": float(self.title_scale.value()),
            "menu_background": self.bg_edit.text(),
            "menu_video": self.video_edit.text(),
            "menu_video_loop": self.video_loop_chk.isChecked(),
            "menu_overlay_alpha": int(self.overlay_alpha.value()),
            "menu_option_pos": [int(self.option_x.value()), int(self.option_y.value())],
            "menu_option_color": self._hex_to_rgb(self.option_color_edit.text()),
            "menu_title_image": self.title_img_edit.text(),
            "menu_title_image_pos": [int(self.title_img_x.value()), int(self.title_img_y.value())],
            "menu_title_image_scale": float(self.title_img_scale.value()),
            "menu_option_scale": float(self.option_scale.value()),
        }

    def _update_preview(self):
        cfg = self._collect_cfg()
        self.preview.update_state(cfg)

    def _pick_color(self, edit: QLineEdit):
        chosen = QColorDialog.getColor()
        if chosen.isValid():
            edit.setText(chosen.name(QColor.NameFormat.HexRgb))

    def _color_to_hex(self, val) -> str:
        if isinstance(val, (list, tuple)) and len(val) >= 3:
            try:
                r, g, b = int(val[0]), int(val[1]), int(val[2])
                return f"#{r:02X}{g:02X}{b:02X}"
            except Exception:
                return "#FFFFFF"
        return "#FFFFFF"

    def _hex_to_rgb(self, text: str) -> list[int]:
        s = text.strip().lstrip("#")
        if len(s) == 6:
            try:
                return [int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)]
            except Exception:
                return [255, 255, 255]
        return [255, 255, 255]


__all__ = ["MainMenuDesigner"]
