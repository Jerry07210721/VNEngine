# -*- coding: utf-8 -*-
"""Global text style configuration dialog (dialogue + name)."""

from __future__ import annotations

from dataclasses import dataclass
import shutil
from pathlib import Path

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QFontDatabase
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


def _hex_from_qcolor(c: QColor) -> str:
    return f"#{c.red():02X}{c.green():02X}{c.blue():02X}"


def _hex_from_color_cfg(val, default_hex: str) -> str:
    if isinstance(val, str) and val.strip():
        return val.strip()
    if isinstance(val, (list, tuple)) and len(val) >= 3:
        try:
            r, g, b = int(val[0]), int(val[1]), int(val[2])
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))
            return f"#{r:02X}{g:02X}{b:02X}"
        except Exception:
            return default_hex
    return default_hex


def _rgb_list_from_hex(s: str, default_hex: str) -> list[int]:
    text = (s or "").strip() or default_hex
    c = QColor(text)
    if not c.isValid():
        c = QColor(default_hex)
    return [int(c.red()), int(c.green()), int(c.blue())]


@dataclass
class TextStyle:
    font_family: str = "SimHei"
    font_path: str = ""
    size: int = 22
    color_hex: str = "#EBEBF0"
    bold: bool = False
    outline_color_hex: str = "#000000"
    outline_width: int = 0


class _TextStylePreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._style = TextStyle()
        self._text = "示例文本：你好，VNEngine!"
        self.setMinimumHeight(90)

    def set_style(self, style: TextStyle):
        self._style = style
        self.update()

    def set_text(self, text: str):
        self._text = text
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        rect = self.rect().adjusted(10, 10, -10, -10)
        p.setPen(QColor("#2A2E39"))
        p.drawRect(rect.adjusted(0, 0, -1, -1))

        font = QFont(self._style.font_family)
        font.setPointSize(int(self._style.size))
        font.setBold(bool(self._style.bold))
        p.setFont(font)

        text = self._text
        if not text:
            return

        # center text
        fm = p.fontMetrics()
        text_rect = fm.boundingRect(text)
        x = rect.x() + max(0, (rect.width() - text_rect.width()) // 2)
        y = rect.y() + max(0, (rect.height() + fm.ascent() - fm.descent()) // 2)

        path = QPainterPath()
        path.addText(x, y, font, text)

        outline_w = max(0, int(self._style.outline_width))
        if outline_w > 0:
            pen = QPen(QColor(self._style.outline_color_hex))
            pen.setWidth(outline_w * 2)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.strokePath(path, pen)

        p.fillPath(path, QColor(self._style.color_hex))


class _TextStyleTab(QWidget):
    def __init__(self, title: str, defaults: TextStyle, project_dir: Path | None, parent=None):
        super().__init__(parent)
        self._title = title
        self._project_dir = project_dir

        self.font_box = QFontComboBox()
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 120)

        self.bold_chk = QCheckBox("加粗")

        self.font_path_edit = QLineEdit("")
        self.font_path_edit.setPlaceholderText("可选：选择 .ttf/.otf（会拷贝到工程 resources/fonts）")

        self.color_edit = QLineEdit(defaults.color_hex)
        self.color_btn = QLabel("")
        self.color_pick = QLabel("")

        self.outline_color_edit = QLineEdit(defaults.outline_color_hex)
        self.outline_width_spin = QSpinBox()
        self.outline_width_spin.setRange(0, 20)

        self.preview = _TextStylePreview()
        self.preview.set_text(f"{title}示例：你好，VNEngine!\n这是第二行预览")

        form = QFormLayout()

        form.addRow("字体", self.font_box)
        form.addRow("字体文件(可选)", self._font_file_row())
        form.addRow("字号", self.size_spin)
        form.addRow("颜色", self._color_row("选择颜色", self.color_edit))
        form.addRow("加粗", self.bold_chk)
        form.addRow("描边颜色", self._color_row("选择描边颜色", self.outline_color_edit))
        form.addRow("描边粗细", self.outline_width_spin)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(QLabel("预览"))
        lay.addWidget(self.preview)
        lay.addStretch(1)

        # init
        self.set_style(defaults)

        # hooks
        self.font_box.currentFontChanged.connect(self._sync_preview)
        self.font_path_edit.textChanged.connect(self._sync_preview)
        self.size_spin.valueChanged.connect(self._sync_preview)
        self.bold_chk.toggled.connect(self._sync_preview)
        self.color_edit.textChanged.connect(self._sync_preview)
        self.outline_color_edit.textChanged.connect(self._sync_preview)
        self.outline_width_spin.valueChanged.connect(self._sync_preview)

    def _font_file_row(self) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        btn_pick = QPushButton("选择...")
        btn_clear = QPushButton("清空")
        try:
            btn_pick.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        except Exception:
            pass

        def pick_font():
            start_dir = str(self._project_dir) if self._project_dir else ""
            path_str, _ = QFileDialog.getOpenFileName(
                self,
                f"选择{self._title}字体文件",
                start_dir,
                "字体文件 (*.ttf *.otf)",
            )
            if not path_str:
                return
            stored = self._store_font_into_project(Path(path_str))
            if not stored:
                return
            self.font_path_edit.setText(stored)
            self._try_load_font_for_preview(stored)

        def clear_font():
            self.font_path_edit.setText("")

        btn_pick.clicked.connect(pick_font)
        btn_clear.clicked.connect(clear_font)

        def _sync_clear_enabled():
            btn_clear.setEnabled(bool((self.font_path_edit.text() or "").strip()))

        self.font_path_edit.textChanged.connect(_sync_clear_enabled)
        _sync_clear_enabled()

        h.addWidget(self.font_path_edit, 1)
        h.addWidget(btn_pick)
        h.addWidget(btn_clear)
        return row

    def _store_font_into_project(self, src: Path) -> str:
        if not self._project_dir:
            QMessageBox.warning(self, "提示", "请先新建或加载工程后再选择字体文件。")
            return ""
        try:
            if not src.exists():
                return ""
            dst_dir = self._project_dir / "resources" / "fonts"
            dst_dir.mkdir(parents=True, exist_ok=True)
            base = src.stem
            ext = src.suffix
            dst = dst_dir / (base + ext)
            i = 1
            while dst.exists():
                dst = dst_dir / f"{base}_{i}{ext}"
                i += 1
            shutil.copy2(src, dst)
            rel = Path("resources") / "fonts" / dst.name
            return rel.as_posix()
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"拷贝字体文件失败：{str(exc)}")
            return ""

    def _try_load_font_for_preview(self, rel_path: str):
        if not self._project_dir:
            return
        try:
            abs_path = (self._project_dir / Path(rel_path)).resolve()
            if not abs_path.exists():
                return
            font_id = QFontDatabase.addApplicationFont(str(abs_path))
            if font_id < 0:
                return
            fams = QFontDatabase.applicationFontFamilies(font_id)
            if fams:
                self.font_box.setCurrentFont(QFont(fams[0]))
        except Exception:
            return

    def _color_row(self, title: str, edit: QLineEdit) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        pick = QLabel("选色")
        pick.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pick.setFixedWidth(56)
        pick.setStyleSheet("QLabel{border:1px solid #3A3F4B; padding:4px;} QLabel:hover{background:#2A2E39;}")
        pick.setCursor(Qt.CursorShape.PointingHandCursor)

        def on_pick():
            s = (edit.text() or "").strip()
            initial = QColor(s) if s else QColor("#FFFFFF")
            chosen = QColorDialog.getColor(initial, self, title)
            if not chosen.isValid():
                return
            edit.setText(_hex_from_qcolor(chosen))

        pick.mousePressEvent = lambda e: on_pick()  # type: ignore[assignment]

        h.addWidget(edit, 1)
        h.addWidget(pick)
        return row

    def set_style(self, style: TextStyle):
        try:
            self.font_box.setCurrentFont(QFont(style.font_family))
        except Exception:
            pass
        self.font_path_edit.setText(str(style.font_path or ""))
        if style.font_path:
            self._try_load_font_for_preview(style.font_path)
        self.size_spin.setValue(int(style.size))
        self.bold_chk.setChecked(bool(style.bold))
        self.color_edit.setText(style.color_hex)
        self.outline_color_edit.setText(style.outline_color_hex)
        self.outline_width_spin.setValue(int(style.outline_width))
        self._sync_preview()

    def get_style_cfg(self) -> dict:
        family = self.font_box.currentFont().family()
        return {
            "font_family": str(family or "SimHei"),
            "font_path": (self.font_path_edit.text() or "").strip(),
            "size": int(self.size_spin.value()),
            "color": _rgb_list_from_hex(self.color_edit.text(), "#EBEBF0"),
            "bold": bool(self.bold_chk.isChecked()),
            "outline_color": _rgb_list_from_hex(self.outline_color_edit.text(), "#000000"),
            "outline_width": int(self.outline_width_spin.value()),
        }

    def _sync_preview(self):
        family = self.font_box.currentFont().family() or "SimHei"
        style = TextStyle(
            font_family=str(family),
            font_path=(self.font_path_edit.text() or "").strip(),
            size=int(self.size_spin.value()),
            color_hex=(self.color_edit.text() or "#EBEBF0").strip() or "#EBEBF0",
            bold=bool(self.bold_chk.isChecked()),
            outline_color_hex=(self.outline_color_edit.text() or "#000000").strip() or "#000000",
            outline_width=int(self.outline_width_spin.value()),
        )
        # validate colors
        if not QColor(style.color_hex).isValid():
            style.color_hex = "#EBEBF0"
        if not QColor(style.outline_color_hex).isValid():
            style.outline_color_hex = "#000000"
        self.preview.set_style(style)


class GlobalTextStyleDialog(QDialog):
    def __init__(self, project_manager, project_dir: Path | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("全局文本样式")
        self.setMinimumWidth(520)
        self._pm = project_manager
        self._project_dir = project_dir

        cfg = {}
        try:
            cfg = (self._pm.project_data or {}).get("game_config", {}) if self._pm else {}
        except Exception:
            cfg = {}

        text_styles = cfg.get("text_styles", {}) if isinstance(cfg, dict) else {}
        dialogue_cfg = text_styles.get("dialogue", {}) if isinstance(text_styles, dict) else {}
        name_cfg = text_styles.get("name", {}) if isinstance(text_styles, dict) else {}

        dlg_defaults = TextStyle(
            font_family=str(dialogue_cfg.get("font_family") or "SimHei"),
            font_path=str(dialogue_cfg.get("font_path") or ""),
            size=int(dialogue_cfg.get("size") or 22),
            color_hex=_hex_from_color_cfg(dialogue_cfg.get("color"), "#EBEBF0"),
            bold=bool(dialogue_cfg.get("bold", False)),
            outline_color_hex=_hex_from_color_cfg(dialogue_cfg.get("outline_color"), "#000000"),
            outline_width=int(dialogue_cfg.get("outline_width") or 0),
        )
        name_defaults = TextStyle(
            font_family=str(name_cfg.get("font_family") or "SimHei"),
            font_path=str(name_cfg.get("font_path") or ""),
            size=int(name_cfg.get("size") or 24),
            color_hex=_hex_from_color_cfg(name_cfg.get("color"), "#DCDCDC"),
            bold=bool(name_cfg.get("bold", True)),
            outline_color_hex=_hex_from_color_cfg(name_cfg.get("outline_color"), "#000000"),
            outline_width=int(name_cfg.get("outline_width") or 0),
        )

        self.tabs = QTabWidget()
        self.tab_dialogue = _TextStyleTab("对白", dlg_defaults, self._project_dir)
        self.tab_name = _TextStyleTab("姓名", name_defaults, self._project_dir)
        self.tabs.addTab(self.tab_dialogue, "对白")
        self.tabs.addTab(self.tab_name, "姓名")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)
        lay.addWidget(buttons)

    def apply_to_project(self):
        if not self._pm:
            return
        data = getattr(self._pm, "project_data", None)
        if not isinstance(data, dict):
            return
        cfg = data.setdefault("game_config", {})
        if not isinstance(cfg, dict):
            return
        text_styles = cfg.setdefault("text_styles", {})
        if not isinstance(text_styles, dict):
            cfg["text_styles"] = {}
            text_styles = cfg["text_styles"]

        text_styles["dialogue"] = self.tab_dialogue.get_style_cfg()
        text_styles["name"] = self.tab_name.get_style_cfg()

    def accept(self):
        self.apply_to_project()
        super().accept()


class EntryTextStyleDialog(QDialog):
    """Per-entry text style override dialog (dialogue + name).

    This dialog edits and returns a `text_styles` dict:
    {
      "dialogue": {...},
      "name": {...}
    }
    """

    def __init__(self, initial_text_styles: dict | None, project_dir: Path | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("对白样式覆盖")
        self.setMinimumWidth(520)
        self._project_dir = project_dir

        styles = initial_text_styles if isinstance(initial_text_styles, dict) else {}
        dialogue_cfg = styles.get("dialogue", {}) if isinstance(styles.get("dialogue"), dict) else {}
        name_cfg = styles.get("name", {}) if isinstance(styles.get("name"), dict) else {}

        dlg_defaults = TextStyle(
            font_family=str(dialogue_cfg.get("font_family") or "SimHei"),
            font_path=str(dialogue_cfg.get("font_path") or ""),
            size=int(dialogue_cfg.get("size") or 22),
            color_hex=_hex_from_color_cfg(dialogue_cfg.get("color"), "#EBEBF0"),
            bold=bool(dialogue_cfg.get("bold", False)),
            outline_color_hex=_hex_from_color_cfg(dialogue_cfg.get("outline_color"), "#000000"),
            outline_width=int(dialogue_cfg.get("outline_width") or 0),
        )
        name_defaults = TextStyle(
            font_family=str(name_cfg.get("font_family") or "SimHei"),
            font_path=str(name_cfg.get("font_path") or ""),
            size=int(name_cfg.get("size") or 24),
            color_hex=_hex_from_color_cfg(name_cfg.get("color"), "#DCDCDC"),
            bold=bool(name_cfg.get("bold", True)),
            outline_color_hex=_hex_from_color_cfg(name_cfg.get("outline_color"), "#000000"),
            outline_width=int(name_cfg.get("outline_width") or 0),
        )

        self.tabs = QTabWidget()
        self.tab_dialogue = _TextStyleTab("对白", dlg_defaults, self._project_dir)
        self.tab_name = _TextStyleTab("姓名", name_defaults, self._project_dir)
        self.tabs.addTab(self.tab_dialogue, "对白")
        self.tabs.addTab(self.tab_name, "姓名")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)
        lay.addWidget(buttons)

    def get_text_styles(self) -> dict:
        return {
            "dialogue": self.tab_dialogue.get_style_cfg(),
            "name": self.tab_name.get_style_cfg(),
        }
