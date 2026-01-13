# -*- coding: utf-8 -*-
"""Simple UI layout designer for VNEngine text/name/portrait regions."""
import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QDoubleSpinBox,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QWidget,
)
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtCore import Qt


class LayoutPreview(QWidget):
    """Simple 2D preview for text/name/portrait positions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(520, 360)
        self._text_rect = [40, 380, 720, 160]
        self._name_rect = [40, 340, 200, 32]
        self._portrait = [0, 0]
        self._portrait_scale = 1.0

    def update_layout(self, data: dict):
        ta = data.get("text_area") or self._text_rect
        na = data.get("name_area") or self._name_rect
        pp = data.get("portrait_pos") or self._portrait
        ps = data.get("portrait_scale", 1.0)
        try:
            self._text_rect = [int(ta[0]), int(ta[1]), int(ta[2]), int(ta[3])]
            self._name_rect = [int(na[0]), int(na[1]), int(na[2]), int(na[3])]
            self._portrait = [int(pp[0]), int(pp[1])]
            self._portrait_scale = float(ps)
        except Exception:
            pass
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(24, 28, 36))

        base_w, base_h = 800, 600
        sx = self.width() / base_w
        sy = self.height() / base_h

        def draw_rect(rect_vals, color: QColor, border: QColor):
            x, y, w, h = rect_vals
            painter.setPen(QPen(border, 2))
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(int(x * sx), int(y * sy), int(w * sx), int(h * sy), 8, 8)

        draw_rect(self._text_rect, QColor(255, 255, 255, 28), QColor(255, 255, 255, 120))
        draw_rect(self._name_rect, QColor(255, 180, 120, 60), QColor(255, 180, 120, 180))

        # 立绘位置用矩形示意，大小跟随缩放
        painter.setPen(QPen(QColor(120, 200, 255, 200), 2))
        painter.setBrush(QBrush(QColor(120, 200, 255, 50)))
        px, py = self._portrait
        scale = max(0.2, min(3.0, self._portrait_scale))
        base_w, base_h = 120, 200
        pw = int(base_w * scale * sx)
        ph = int(base_h * scale * sy)
        cx = int(px * sx)
        cy = int(py * sy)
        painter.drawRect(cx - pw // 2, cy - ph // 2, pw, ph)


class UILayoutDesigner(QDialog):
    """Very lightweight UI layout editor saving to JSON under project ui/ folder."""

    def __init__(self, project_dir: Path, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
        self.setWindowTitle("UI 设计器")
        self.setMinimumWidth(720)
        self.layout_path: Path | None = None

        main = QVBoxLayout(self)
        top_row = QHBoxLayout()
        form = QFormLayout()

        # text area
        self.text_x = self._spin(0, 4000, 40)
        self.text_y = self._spin(0, 4000, 400)
        self.text_w = self._spin(100, 4000, 720)
        self.text_h = self._spin(60, 4000, 180)
        form.addRow("文本框 x", self.text_x)
        form.addRow("文本框 y", self.text_y)
        form.addRow("文本框 宽", self.text_w)
        form.addRow("文本框 高", self.text_h)

        # name box
        self.name_x = self._spin(0, 4000, 40)
        self.name_y = self._spin(0, 4000, 360)
        self.name_w = self._spin(60, 4000, 200)
        self.name_h = self._spin(24, 4000, 32)
        form.addRow("姓名框 x", self.name_x)
        form.addRow("姓名框 y", self.name_y)
        form.addRow("姓名框 宽", self.name_w)
        form.addRow("姓名框 高", self.name_h)

        # portrait position
        self.portrait_x = self._spin(-2000, 4000, 0)
        self.portrait_y = self._spin(-2000, 4000, 0)
        self.portrait_scale = self._dspin(0.1, 5.0, 1.0, 0.1)
        form.addRow("立绘位置 x", self.portrait_x)
        form.addRow("立绘位置 y", self.portrait_y)
        form.addRow("立绘缩放", self.portrait_scale)

        preview_wrap = QVBoxLayout()
        preview_label = QLabel("预览（基于 800x600，立绘点为中心）")
        self.preview = LayoutPreview()
        preview_wrap.addWidget(preview_label)
        preview_wrap.addWidget(self.preview)

        top_row.addLayout(form, 1)
        top_row.addLayout(preview_wrap, 2)
        main.addLayout(top_row)

        btn_row = QHBoxLayout()
        btn_load = QPushButton("打开布局")
        btn_save = QPushButton("保存布局")
        btn_close = QPushButton("关闭")
        btn_load.clicked.connect(self._load_file)
        btn_save.clicked.connect(self._save_file)
        btn_close.clicked.connect(self.reject)
        for b in (btn_load, btn_save, btn_close):
            btn_row.addWidget(b)
        main.addLayout(btn_row)

        for sp in [
            self.text_x,
            self.text_y,
            self.text_w,
            self.text_h,
            self.name_x,
            self.name_y,
            self.name_w,
            self.name_h,
            self.portrait_x,
            self.portrait_y,
            self.portrait_scale,
        ]:
            sp.valueChanged.connect(self._update_preview)
        self._update_preview()

    def _spin(self, mn: int, mx: int, val: int) -> QSpinBox:
        sp = QSpinBox()
        sp.setRange(mn, mx)
        sp.setValue(val)
        return sp

    def _dspin(self, mn: float, mx: float, val: float, step: float) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(mn, mx)
        sp.setDecimals(2)
        sp.setSingleStep(step)
        sp.setValue(val)
        return sp

    def _load_file(self):
        start = str(self.project_dir / "ui") if self.project_dir else ""
        path_str, _ = QFileDialog.getOpenFileName(self, "打开UI布局", start, "UI布局 (*.json)")
        if not path_str:
            return
        path = Path(path_str)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._apply_layout_data(data)
            self.layout_path = path
        except Exception as exc:
            QMessageBox.critical(self, "读取失败", f"无法读取布局：{exc}")

    def _save_file(self):
        start = str(self.project_dir / "ui") if self.project_dir else ""
        path_str, _ = QFileDialog.getSaveFileName(self, "保存UI布局", start, "UI布局 (*.json)")
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix != ".json":
            path = path.with_suffix(".json")
        data = self._collect_layout_data()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.layout_path = path
            QMessageBox.information(self, "保存成功", f"布局已保存到\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", f"无法保存布局：{exc}")

    def _update_preview(self):
        self.preview.update_layout(self._collect_layout_data())

    def _collect_layout_data(self) -> dict:
        return {
            "text_area": [self.text_x.value(), self.text_y.value(), self.text_w.value(), self.text_h.value()],
            "name_area": [self.name_x.value(), self.name_y.value(), self.name_w.value(), self.name_h.value()],
            "portrait_pos": [self.portrait_x.value(), self.portrait_y.value()],
            "portrait_scale": float(self.portrait_scale.value()),
        }

    def _apply_layout_data(self, data: dict):
        ta = data.get("text_area") or [40, 400, 720, 180]
        na = data.get("name_area") or [40, 360, 200, 32]
        pp = data.get("portrait_pos") or [0, 0]
        ps = data.get("portrait_scale", 1.0)
        try:
            self.text_x.setValue(int(ta[0]))
            self.text_y.setValue(int(ta[1]))
            self.text_w.setValue(int(ta[2]))
            self.text_h.setValue(int(ta[3]))
            self.name_x.setValue(int(na[0]))
            self.name_y.setValue(int(na[1]))
            self.name_w.setValue(int(na[2]))
            self.name_h.setValue(int(na[3]))
            self.portrait_x.setValue(int(pp[0]))
            self.portrait_y.setValue(int(pp[1]))
            self.portrait_scale.setValue(float(ps))
        except Exception:
            pass


__all__ = ["UILayoutDesigner"]