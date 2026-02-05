"""Function menu designer for VNEngine.

Edits project-level `game_config.function_menus` (global design), not UI layout JSON.

This config controls mouse-enabled overlays:
- save / load / settings / history / help
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QBrush, QPen, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QGroupBox,
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


def _set_spin_value(sp: QSpinBox, v: int):
    try:
        sp.blockSignals(True)
        sp.setValue(int(v))
    finally:
        sp.blockSignals(False)


class _DraggableRect(QGraphicsRectItem):
    def __init__(
        self,
        name: str,
        rect,
        *,
        preview,
        on_changed,
        label: str | None = None,
        pen: QPen | None = None,
        brush: QBrush | None = None,
        movable: bool = True,
        resizable: bool = False,
        min_w: int = 10,
        min_h: int = 10,
    ):
        super().__init__(rect)
        self.name = name
        self._preview = preview
        self._on_changed = on_changed
        self._movable = bool(movable)
        self._resizable = bool(resizable)
        self._min_w = int(min_w)
        self._min_h = int(min_h)
        self._drag_mode: str | None = None  # 'move' | 'resize'
        self._drag_handle: str | None = None  # tl/tr/bl/br
        self._press_scene_pos = None
        self._press_rect = None
        self._handle_px = 10

        self._label = QGraphicsSimpleTextItem(label or name, self)
        self._label.setBrush(QBrush(QColor(255, 255, 255)))
        self._label.setPos(rect.x() + 6, rect.y() + 4)
        self._label.setZValue(30)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setPen(pen or QPen(QColor(255, 255, 255, 220), 2))
        self.setBrush(brush or QBrush(QColor(255, 255, 255, 60)))

    def _handle_at(self, pos) -> str | None:
        if not self._resizable:
            return None
        r = self.rect()
        s = float(self._handle_px)
        x, y = float(pos.x()), float(pos.y())
        corners = {
            "tl": (r.x(), r.y()),
            "tr": (r.x() + r.width(), r.y()),
            "bl": (r.x(), r.y() + r.height()),
            "br": (r.x() + r.width(), r.y() + r.height()),
        }
        for name, (cx, cy) in corners.items():
            if abs(x - cx) <= s and abs(y - cy) <= s:
                return name
        return None

    def hoverMoveEvent(self, event):
        h = self._handle_at(event.pos())
        if h:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif self._movable:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        return super().hoverMoveEvent(event)

    def paint(self, painter: QPainter, option, widget=None):
        # Custom paint to avoid Qt's default dashed selection outline.
        r = self.rect()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawRect(r)

        if self.isSelected():
            sel_pen = QPen(QColor(255, 255, 255, 240), 2)
            sel_pen.setStyle(Qt.PenStyle.SolidLine)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(r)

            if self._resizable:
                s = float(self._handle_px)
                hs = max(4.0, min(8.0, s * 0.6))
                handle_brush = QBrush(QColor(255, 255, 255, 240))
                painter.setBrush(handle_brush)
                painter.setPen(QPen(QColor(0, 0, 0, 180), 1))

                corners = [
                    (r.x(), r.y()),
                    (r.x() + r.width(), r.y()),
                    (r.x(), r.y() + r.height()),
                    (r.x() + r.width(), r.y() + r.height()),
                ]
                for cx, cy in corners:
                    painter.drawRect(QRectF(cx - hs / 2.0, cy - hs / 2.0, hs, hs))

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._press_scene_pos = event.scenePos()
        self._press_rect = self.rect()
        self._drag_handle = self._handle_at(event.pos())
        if self._drag_handle:
            self._drag_mode = "resize"
        elif self._movable:
            self._drag_mode = "move"
        else:
            self._drag_mode = None
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._drag_mode or self._press_scene_pos is None or self._press_rect is None:
            return super().mouseMoveEvent(event)
        delta = event.scenePos() - self._press_scene_pos
        nr = self._press_rect
        if self._drag_mode == "move":
            nr = nr.translated(delta.x(), delta.y())
        elif self._drag_mode == "resize" and self._drag_handle:
            x0, y0, w0, h0 = float(nr.x()), float(nr.y()), float(nr.width()), float(nr.height())
            x1, y1 = x0, y0
            x2, y2 = x0 + w0, y0 + h0
            dx, dy = float(delta.x()), float(delta.y())
            if self._drag_handle in {"tl", "bl"}:
                x1 = x0 + dx
            if self._drag_handle in {"tr", "br"}:
                x2 = x0 + w0 + dx
            if self._drag_handle in {"tl", "tr"}:
                y1 = y0 + dy
            if self._drag_handle in {"bl", "br"}:
                y2 = y0 + h0 + dy
            nw = max(float(self._min_w), abs(x2 - x1))
            nh = max(float(self._min_h), abs(y2 - y1))
            nx = min(x1, x2)
            ny = min(y1, y2)
            nr = QRectF(nx, ny, nw, nh)

        # snapping (grid + align)
        if self._preview is not None and hasattr(self._preview, "apply_snap"):
            nr = self._preview.apply_snap(self.name, nr, mode=self._drag_mode, handle=self._drag_handle)

        self.setRect(nr)
        self._label.setPos(nr.x() + 6, nr.y() + 4)
        try:
            if callable(self._on_changed):
                self._on_changed(self)
        except Exception:
            pass
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_mode = None
        self._drag_handle = None
        self._press_scene_pos = None
        self._press_rect = None
        try:
            if self._preview is not None and hasattr(self._preview, "_clear_guides"):
                self._preview._clear_guides()
        except Exception:
            pass
        return super().mouseReleaseEvent(event)


class _LayoutPreview(QGraphicsView):
    def __init__(self, resolution: tuple[int, int], parent=None):
        super().__init__(parent)
        w, h = int(resolution[0]), int(resolution[1])
        self._resolution = (max(1, w), max(1, h))
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(0, 0, self._resolution[0], self._resolution[1])
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.setBackgroundBrush(QBrush(QColor(30, 34, 42)))
        self.setMinimumSize(340, 260)

        self._bg_item = QGraphicsPixmapItem()
        self._bg_item.setZValue(-50)
        self._scene.addItem(self._bg_item)
        self._bg_item.setVisible(False)
        self._bg_path = ""
        self._bg_alpha = 255

        self._grid_snap_enabled = True
        self._grid_size = 10
        self._align_snap_enabled = True
        self._align_threshold = 6

        self._show_grid = False
        self._show_guides = True
        self._guide_items: list[QGraphicsLineItem] = []

        # a light grid
        grid_pen = QPen(QColor(70, 80, 95, 140))
        grid_pen.setWidth(1)
        step = 40
        for x in range(0, self._resolution[0] + 1, step):
            self._scene.addLine(x, 0, x, self._resolution[1], grid_pen)
        for y in range(0, self._resolution[1] + 1, step):
            self._scene.addLine(0, y, self._resolution[0], y, grid_pen)

        border = QGraphicsRectItem(0, 0, self._resolution[0], self._resolution[1])
        border.setPen(QPen(QColor(220, 220, 220, 180), 2))
        border.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        border.setZValue(10)
        border.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._scene.addItem(border)

        self._items: dict[str, _DraggableRect] = {}
        self._updating_from_controls = False

    def set_background(self, rel_or_abs: str, alpha: int, project_dir: Path | None):
        s = (rel_or_abs or "").strip()
        self._bg_path = s
        try:
            self._bg_alpha = int(alpha)
        except Exception:
            self._bg_alpha = 255
        self._bg_alpha = max(0, min(255, self._bg_alpha))

        if not s:
            self._bg_item.setVisible(False)
            return

        p = Path(s)
        if not p.is_absolute() and project_dir:
            p = (Path(project_dir) / p).resolve()
        if not p.exists():
            self._bg_item.setVisible(False)
            return
        try:
            px = QPixmap(str(p))
            if px.isNull():
                self._bg_item.setVisible(False)
                return
            scaled = px.scaled(self._resolution[0], self._resolution[1], Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self._bg_item.setPixmap(scaled)
            self._bg_item.setOpacity(float(self._bg_alpha) / 255.0)
            self._bg_item.setPos(0, 0)
            self._bg_item.setVisible(True)
        except Exception:
            self._bg_item.setVisible(False)

    def set_grid_snap(self, enabled: bool, grid_size: int | None = None):
        self._grid_snap_enabled = bool(enabled)
        if grid_size is not None:
            try:
                self._grid_size = max(1, int(grid_size))
            except Exception:
                self._grid_size = 10
        self.viewport().update()

    def set_align_snap(self, enabled: bool, threshold: int | None = None):
        self._align_snap_enabled = bool(enabled)
        if threshold is not None:
            try:
                self._align_threshold = max(1, int(threshold))
            except Exception:
                self._align_threshold = 6

    def set_show_grid(self, enabled: bool):
        self._show_grid = bool(enabled)
        self.viewport().update()

    def set_show_guides(self, enabled: bool):
        self._show_guides = bool(enabled)
        if not self._show_guides:
            self._clear_guides()

    def _clear_guides(self):
        if not self._guide_items:
            return
        try:
            for it in list(self._guide_items):
                try:
                    self._scene.removeItem(it)
                except Exception:
                    pass
        finally:
            self._guide_items.clear()

    def _set_guides(self, x_line: float | None, y_line: float | None):
        if not self._show_guides:
            return
        self._clear_guides()
        pen = QPen(QColor(255, 240, 120, 200), 1, Qt.PenStyle.DashLine)
        w, h = self._resolution
        if x_line is not None:
            li = QGraphicsLineItem(float(x_line), 0.0, float(x_line), float(h))
            li.setPen(pen)
            li.setZValue(100)
            self._scene.addItem(li)
            self._guide_items.append(li)
        if y_line is not None:
            li = QGraphicsLineItem(0.0, float(y_line), float(w), float(y_line))
            li.setPen(pen)
            li.setZValue(100)
            self._scene.addItem(li)
            self._guide_items.append(li)

    def apply_snap(self, name: str, rect: QRectF, *, mode: str | None, handle: str | None) -> QRectF:
        x = float(rect.x())
        y = float(rect.y())
        w = float(rect.width())
        h = float(rect.height())

        guide_x: float | None = None
        guide_y: float | None = None

        # align snap to other items
        if self._align_snap_enabled and self._items:
            thresh = float(self._align_threshold)
            others: list[QRectF] = []
            for k, it in self._items.items():
                if k == name:
                    continue
                try:
                    others.append(it.rect())
                except Exception:
                    continue

            def pts_for(r: QRectF):
                return [r.x(), r.x() + r.width() / 2.0, r.x() + r.width()], [r.y(), r.y() + r.height() / 2.0, r.y() + r.height()]

            txs: list[float] = []
            tys: list[float] = []
            for o in others:
                oxs, oys = pts_for(o)
                txs.extend([float(v) for v in oxs])
                tys.extend([float(v) for v in oys])

            # candidate points for current rect
            cand_xs = [x, x + w / 2.0, x + w]
            cand_ys = [y, y + h / 2.0, y + h]

            best_dx = None
            best_dy = None
            best_tx = None
            best_ty = None
            for cx in cand_xs:
                for tx0 in txs:
                    d = tx0 - cx
                    if abs(d) <= thresh and (best_dx is None or abs(d) < abs(best_dx)):
                        best_dx = d
                        best_tx = tx0
            for cy in cand_ys:
                for ty0 in tys:
                    d = ty0 - cy
                    if abs(d) <= thresh and (best_dy is None or abs(d) < abs(best_dy)):
                        best_dy = d
                        best_ty = ty0

            if mode == "move":
                if best_dx is not None:
                    x += float(best_dx)
                    guide_x = float(best_tx) if best_tx is not None else None
                if best_dy is not None:
                    y += float(best_dy)
                    guide_y = float(best_ty) if best_ty is not None else None
            elif mode == "resize" and handle:
                # snap moving edges only
                left = x
                right = x + w
                top = y
                bottom = y + h
                if handle in {"tl", "bl"} and best_dx is not None:
                    left += float(best_dx)
                    guide_x = float(best_tx) if best_tx is not None else None
                if handle in {"tr", "br"} and best_dx is not None:
                    right += float(best_dx)
                    guide_x = float(best_tx) if best_tx is not None else None
                if handle in {"tl", "tr"} and best_dy is not None:
                    top += float(best_dy)
                    guide_y = float(best_ty) if best_ty is not None else None
                if handle in {"bl", "br"} and best_dy is not None:
                    bottom += float(best_dy)
                    guide_y = float(best_ty) if best_ty is not None else None
                x = min(left, right)
                y = min(top, bottom)
                w = max(1.0, abs(right - left))
                h = max(1.0, abs(bottom - top))

        self._set_guides(guide_x, guide_y)

        # grid snap
        if self._grid_snap_enabled and self._grid_size > 0:
            g = float(max(1, int(self._grid_size)))
            def snap(v: float) -> float:
                return round(v / g) * g
            x = snap(x)
            y = snap(y)
            w = max(1.0, snap(w))
            h = max(1.0, snap(h))

        # clamp to canvas
        x = max(0.0, min(float(self._resolution[0] - 1), x))
        y = max(0.0, min(float(self._resolution[1] - 1), y))
        w = max(1.0, min(float(self._resolution[0]) - x, w))
        h = max(1.0, min(float(self._resolution[1]) - y, h))
        return QRectF(x, y, w, h)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        super().drawBackground(painter, rect)
        if not (self._show_grid or self._grid_snap_enabled):
            return
        try:
            g = int(self._grid_size)
        except Exception:
            g = 10
        g = max(4, g)

        w, h = self._resolution
        pen = QPen(QColor(255, 255, 255, 14), 1)
        painter.save()
        painter.setPen(pen)
        # vertical
        x = 0
        while x <= w:
            painter.drawLine(x, 0, x, h)
            x += g
        # horizontal
        y = 0
        while y <= h:
            painter.drawLine(0, y, w, y)
            y += g
        painter.restore()

    def add_rect(
        self,
        name: str,
        x: int,
        y: int,
        w: int,
        h: int,
        *,
        on_changed,
        resizable: bool = False,
        min_w: int = 10,
        min_h: int = 10,
    ) -> _DraggableRect:
        it = _DraggableRect(
            name,
            QRectF(float(x), float(y), float(w), float(h)),
            preview=self,
            on_changed=on_changed,
            label=name,
            movable=True,
            resizable=resizable,
            min_w=min_w,
            min_h=min_h,
        )
        it.setZValue(20)
        self._scene.addItem(it)
        self._items[name] = it
        return it

    def style_rect(self, name: str, *, label: str | None = None, pen: QPen | None = None, brush: QBrush | None = None):
        it = self._items.get(name)
        if not it:
            return
        if label is not None:
            it._label.setText(label)
        if pen is not None:
            it.setPen(pen)
        if brush is not None:
            it.setBrush(brush)

    def set_rect(self, name: str, x: int, y: int, w: int, h: int):
        it = self._items.get(name)
        if not it:
            return
        try:
            it.blockSignals(True)
        except Exception:
            pass
        it.setRect(float(x), float(y), float(w), float(h))
        try:
            it._label.setPos(float(x) + 6, float(y) + 4)
        except Exception:
            pass

    def showEvent(self, event):
        try:
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        except Exception:
            pass
        return super().showEvent(event)

    def resizeEvent(self, event):
        try:
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        except Exception:
            pass
        return super().resizeEvent(event)


class FunctionMenuDesigner(QDialog):
    def __init__(self, project_dir: Path, project_manager, project_resolution: tuple[int, int] | None = None, parent=None):
        super().__init__(parent)
        self.project_dir = Path(project_dir) if project_dir else None
        self.project_manager = project_manager
        self.project_resolution = project_resolution or (800, 600)

        self.setWindowTitle("功能菜单设计器")
        self.resize(760, 620)

        root = QVBoxLayout(self)

        hint = QLabel("配置写入工程全局 game_config.function_menus（保存工程文件后生效）")
        hint.setWordWrap(True)
        root.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_reload = QPushButton("从工程重载")
        btn_save = QPushButton("写入工程")
        btn_close = QPushButton("关闭")
        try:
            btn_reload.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        except Exception:
            pass
        btn_reload.clicked.connect(self._reload_from_project)
        btn_save.clicked.connect(self._write_to_project)
        btn_close.clicked.connect(self.close)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_reload)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        self.chk_enabled = QCheckBox("启用功能菜单自定义（启用后覆盖默认旧 overlay）")
        self.chk_enabled.stateChanged.connect(self._mark_dirty)
        root.addWidget(self.chk_enabled)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self._dirty = False
        self._previews: dict[str, _LayoutPreview] = {}

        self._build_tabs()
        self._apply_defaults()
        self._reload_from_project()

    def closeEvent(self, event):
        if getattr(self, "_dirty", False):
            btn = QMessageBox.question(
                self,
                "未保存的更改",
                "当前有未写入工程的更改，确定要关闭吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if btn != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        super().closeEvent(event)

    # --- UI helpers

    def _spin(self, mn: int, mx: int, val: int) -> QSpinBox:
        sp = QSpinBox()
        sp.setRange(mn, mx)
        sp.setValue(val)
        sp.valueChanged.connect(self._mark_dirty)
        return sp

    def _color_row(self, label: str, default_hex: str) -> tuple[QLineEdit, QWidget]:
        edit = QLineEdit(default_hex)
        edit.textChanged.connect(self._mark_dirty)
        btn = QPushButton("选色")
        try:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        except Exception:
            pass

        def pick():
            s = (edit.text() or "").strip()
            initial = QColor(s) if s else QColor(default_hex)
            c = QColorDialog.getColor(initial, self, f"选择{label}")
            if not c.isValid():
                return
            edit.setText(_hex_from_qcolor(c))

        btn.clicked.connect(pick)
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(edit, 1)
        lay.addWidget(btn)
        return edit, row

    def _image_row(self, title: str) -> tuple[QLineEdit, QWidget]:
        edit = QLineEdit("")
        edit.textChanged.connect(self._mark_dirty)
        btn_pick = QPushButton("选择图片")
        btn_clear = QPushButton("清空")
        try:
            btn_pick.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        except Exception:
            pass

        def pick():
            start = str(self.project_dir / "resources" / "images") if self.project_dir else ""
            path_str, _ = QFileDialog.getOpenFileName(self, title, start, "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)")
            if not path_str:
                return
            stored = self._store_into_project(Path(path_str), "resources/images")
            edit.setText(stored)

        def clear():
            edit.setText("")

        btn_pick.clicked.connect(pick)
        btn_clear.clicked.connect(clear)
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(edit, 1)
        lay.addWidget(btn_pick)
        lay.addWidget(btn_clear)

        def _sync_clear_enabled():
            btn_clear.setEnabled(bool((edit.text() or "").strip()))

        edit.textChanged.connect(_sync_clear_enabled)
        _sync_clear_enabled()
        return edit, row

    def _attach_preview_toggles(self, pv_lay: QVBoxLayout, preview: _LayoutPreview):
        bar = QWidget()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)

        chk_grid_snap = QCheckBox("网格吸附")
        chk_grid_snap.setChecked(True)
        chk_show_grid = QCheckBox("显示网格")
        chk_show_grid.setChecked(False)
        sp_grid = self._spin(4, 80, 10)
        sp_grid.setFixedWidth(70)

        chk_align = QCheckBox("对齐吸附")
        chk_align.setChecked(True)
        chk_guides = QCheckBox("参考线")
        chk_guides.setChecked(True)

        for w in (chk_grid_snap, chk_show_grid, chk_align, chk_guides):
            try:
                w.setCursor(Qt.CursorShape.PointingHandCursor)
            except Exception:
                pass

        def sync():
            preview.set_grid_snap(bool(chk_grid_snap.isChecked()), int(sp_grid.value()))
            preview.set_show_grid(bool(chk_show_grid.isChecked()))
            preview.set_align_snap(bool(chk_align.isChecked()))
            preview.set_show_guides(bool(chk_guides.isChecked()))

        chk_grid_snap.stateChanged.connect(lambda _s: sync())
        chk_show_grid.stateChanged.connect(lambda _s: sync())
        chk_align.stateChanged.connect(lambda _s: sync())
        chk_guides.stateChanged.connect(lambda _s: sync())
        sp_grid.valueChanged.connect(lambda _v: sync())
        sync()

        lay.addWidget(chk_grid_snap)
        lay.addWidget(QLabel("格距"))
        lay.addWidget(sp_grid)
        lay.addSpacing(10)
        lay.addWidget(chk_show_grid)
        lay.addSpacing(14)
        lay.addWidget(chk_align)
        lay.addWidget(chk_guides)
        lay.addStretch(1)

        pv_lay.addWidget(bar)

    def _store_into_project(self, file_path: Path, dest_subfolder: str) -> str:
        if not self.project_dir:
            return str(file_path).replace("\\", "/")
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                return ""
            proj = Path(self.project_dir)
            try:
                rel = file_path.resolve().relative_to(proj.resolve())
                return str(rel).replace("\\", "/")
            except Exception:
                pass

            dest_dir = proj / dest_subfolder
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / file_path.name
            if dest_path.exists():
                stem = dest_path.stem
                suffix = dest_path.suffix
                i = 2
                while (dest_dir / f"{stem}_{i}{suffix}").exists():
                    i += 1
                dest_path = dest_dir / f"{stem}_{i}{suffix}"
            shutil.copy2(str(file_path), str(dest_path))
            rel2 = dest_path.resolve().relative_to(proj.resolve())
            return str(rel2).replace("\\", "/")
        except Exception:
            return str(file_path).replace("\\", "/")

    def _mark_dirty(self, *args):
        self._dirty = True

    def _refresh_preview_backgrounds(self):
        # common
        pv = self._previews.get("common")
        if pv is not None and hasattr(pv, "set_background"):
            pv.set_background(str(self.common_bg_edit.text() or "").strip(), int(self.common_bg_alpha.value()), self.project_dir)

        for key in ("save", "load", "settings", "history", "help"):
            pv = self._previews.get(key)
            if pv is None or not hasattr(pv, "set_background"):
                continue
            chk = getattr(self, f"{key}_bg_override", None)
            edit = getattr(self, f"{key}_bg_edit", None)
            alp = getattr(self, f"{key}_bg_alpha", None)
            eff_bg = str(self.common_bg_edit.text() or "").strip()
            eff_alpha = int(self.common_bg_alpha.value())
            if chk is not None and bool(chk.isChecked()):
                if edit is not None:
                    eff_bg = str(edit.text() or "").strip()
                if alp is not None:
                    eff_alpha = int(alp.value())
            pv.set_background(eff_bg, eff_alpha, self.project_dir)

    # --- tabs

    def _build_tabs(self):
        self.tab_common = QWidget()
        self.tab_save = QWidget()
        self.tab_load = QWidget()
        self.tab_settings = QWidget()
        self.tab_history = QWidget()
        self.tab_help = QWidget()

        self.tabs.addTab(self.tab_common, "通用")
        self.tabs.addTab(self.tab_save, "存档")
        self.tabs.addTab(self.tab_load, "读档")
        self.tabs.addTab(self.tab_settings, "设置")
        self.tabs.addTab(self.tab_history, "历史")
        self.tabs.addTab(self.tab_help, "帮助")

        self._build_common_tab()
        self._build_simple_tab(self.tab_save, key="save")
        self._build_simple_tab(self.tab_load, key="load")
        self._build_simple_tab(self.tab_settings, key="settings")
        self._build_scroll_tab(self.tab_history, key="history")
        self._build_scroll_tab(self.tab_help, key="help")

    def _build_common_tab(self):
        outer = QHBoxLayout(self.tab_common)

        left = QWidget()
        lay = QVBoxLayout(left)

        box = QGroupBox("通用样式")
        form = QFormLayout(box)

        self.common_overlay_alpha = self._spin(0, 255, 160)
        form.addRow("遮罩透明度(0-255)", self.common_overlay_alpha)

        self.common_bg_edit, bg_row = self._image_row("选择通用背景图")
        form.addRow("背景图(可选)", bg_row)

        self.common_bg_alpha = self._spin(0, 255, 255)
        form.addRow("背景图透明度(0-255)", self.common_bg_alpha)

        self.common_font_size = self._spin(8, 72, 18)
        self.common_title_font_size = self._spin(8, 96, 22)
        form.addRow("正文字号", self.common_font_size)
        form.addRow("标题字号", self.common_title_font_size)

        self.common_title_color_edit, row = self._color_row("标题颜色", "#FFFFFF")
        form.addRow("标题颜色", row)
        self.common_text_color_edit, row = self._color_row("文字颜色", "#E6E6E6")
        form.addRow("文字颜色", row)
        self.common_hint_color_edit, row = self._color_row("提示颜色", "#C8C8C8")
        form.addRow("提示颜色", row)
        self.common_hover_color_edit, row = self._color_row("悬停颜色", "#FFFFFF")
        form.addRow("悬停颜色", row)

        # positions
        pos_row = QWidget()
        pos_lay = QHBoxLayout(pos_row)
        pos_lay.setContentsMargins(0, 0, 0, 0)
        self.common_title_x = self._spin(0, 9999, 40)
        self.common_title_y = self._spin(0, 9999, 40)
        pos_lay.addWidget(QLabel("x"))
        pos_lay.addWidget(self.common_title_x)
        pos_lay.addSpacing(8)
        pos_lay.addWidget(QLabel("y"))
        pos_lay.addWidget(self.common_title_y)
        pos_lay.addStretch(1)
        form.addRow("标题位置", pos_row)

        close_box = QGroupBox("关闭按钮(×)")
        close_form = QFormLayout(close_box)
        close_pos = QWidget()
        close_lay = QHBoxLayout(close_pos)
        close_lay.setContentsMargins(0, 0, 0, 0)
        self.common_close_x = self._spin(0, 9999, 740)
        self.common_close_y = self._spin(0, 9999, 40)
        close_lay.addWidget(QLabel("x"))
        close_lay.addWidget(self.common_close_x)
        close_lay.addSpacing(8)
        close_lay.addWidget(QLabel("y"))
        close_lay.addWidget(self.common_close_y)
        close_lay.addStretch(1)
        close_form.addRow("位置", close_pos)

        close_size = QWidget()
        size_lay = QHBoxLayout(close_size)
        size_lay.setContentsMargins(0, 0, 0, 0)
        self.common_close_w = self._spin(18, 200, 32)
        self.common_close_h = self._spin(18, 200, 32)
        size_lay.addWidget(QLabel("w"))
        size_lay.addWidget(self.common_close_w)
        size_lay.addSpacing(8)
        size_lay.addWidget(QLabel("h"))
        size_lay.addWidget(self.common_close_h)
        size_lay.addStretch(1)
        close_form.addRow("大小", close_size)

        lay.addWidget(box)
        lay.addWidget(close_box)
        lay.addStretch(1)

        preview_box = QGroupBox("预览（拖拽移动；四角拖拽缩放；支持吸附）")
        pv_lay = QVBoxLayout(preview_box)
        preview = _LayoutPreview(self.project_resolution, self)
        self._attach_preview_toggles(pv_lay, preview)
        pv_lay.addWidget(preview, 1)
        self._previews["common"] = preview

        def _on_controls_changed():
            if getattr(preview, "_updating_from_controls", False):
                return
            preview._updating_from_controls = True
            try:
                preview.set_background(str(self.common_bg_edit.text() or "").strip(), int(self.common_bg_alpha.value()), self.project_dir)

                tx = int(self.common_title_x.value())
                ty = int(self.common_title_y.value())
                preview.set_rect("title", tx, ty, 220, 40)

                cx = int(self.common_close_x.value())
                cy = int(self.common_close_y.value())
                cw = int(self.common_close_w.value())
                ch = int(self.common_close_h.value())
                preview.set_rect("close", cx, cy, max(18, cw), max(18, ch))
            finally:
                preview._updating_from_controls = False

        def on_title_changed(item: _DraggableRect):
            if preview._updating_from_controls:
                return
            r = item.rect()
            preview._updating_from_controls = True
            try:
                _set_spin_value(self.common_title_x, int(r.x()))
                _set_spin_value(self.common_title_y, int(r.y()))
            finally:
                preview._updating_from_controls = False
            self._mark_dirty()

        def on_close_changed(item: _DraggableRect):
            if preview._updating_from_controls:
                return
            r = item.rect()
            preview._updating_from_controls = True
            try:
                _set_spin_value(self.common_close_x, int(r.x()))
                _set_spin_value(self.common_close_y, int(r.y()))
                _set_spin_value(self.common_close_w, int(r.width()))
                _set_spin_value(self.common_close_h, int(r.height()))
            finally:
                preview._updating_from_controls = False
            self._mark_dirty()

        preview.add_rect("title", 40, 40, 220, 40, on_changed=on_title_changed, resizable=False)
        preview.style_rect(
            "title",
            label="title",
            pen=QPen(QColor(120, 180, 255, 220), 2),
            brush=QBrush(QColor(120, 180, 255, 80)),
        )
        preview.add_rect("close", self.project_resolution[0] - 60, 40, 32, 32, on_changed=on_close_changed, resizable=True, min_w=18, min_h=18)
        preview.style_rect(
            "close",
            label="close",
            pen=QPen(QColor(255, 120, 120, 220), 2),
            brush=QBrush(QColor(255, 120, 120, 90)),
        )

        for spn in (
            self.common_bg_alpha,
            self.common_title_x,
            self.common_title_y,
            self.common_close_x,
            self.common_close_y,
            self.common_close_w,
            self.common_close_h,
        ):
            spn.valueChanged.connect(lambda _v, _fn=_on_controls_changed: _fn())
        self.common_bg_edit.textChanged.connect(lambda _t, _fn=_on_controls_changed: (_fn(), self._refresh_preview_backgrounds()))
        self.common_bg_alpha.valueChanged.connect(lambda _v: self._refresh_preview_backgrounds())
        _on_controls_changed()

        outer.addWidget(left, 2)
        outer.addWidget(preview_box, 3)

    def _build_simple_tab(self, tab: QWidget, *, key: str):
        outer = QHBoxLayout(tab)
        left = QWidget()
        lay = QVBoxLayout(left)
        gb = QGroupBox("覆盖(可选)")
        form = QFormLayout(gb)

        chk_bg = QCheckBox("覆盖背景图")
        chk_bg.stateChanged.connect(self._mark_dirty)
        edit_bg, bg_row = self._image_row(f"选择{key}背景图")
        edit_bg.setEnabled(False)
        bg_row.setEnabled(False)

        bg_alpha = self._spin(0, 255, 255)
        bg_alpha.setEnabled(False)

        def on_chk_bg(state: int):
            enabled = chk_bg.isChecked()
            edit_bg.setEnabled(enabled)
            bg_row.setEnabled(enabled)
            bg_alpha.setEnabled(enabled)
            self._mark_dirty()

        chk_bg.stateChanged.connect(on_chk_bg)

        form.addRow(chk_bg)
        form.addRow("背景图", bg_row)
        form.addRow("背景图透明度(0-255)", bg_alpha)

        # layout (always available)
        layout_box = QGroupBox("布局")
        layout_form = QFormLayout(layout_box)

        if key in {"save", "load"}:
            # page size (slots per page)
            page_size = self._spin(1, 10, 10)
            page_size.setToolTip("每页显示的槽位数量（1-10）。影响翻页和数字键选择范围。")
            layout_form.addRow("每页槽位数(1-10)", page_size)

            # slot list
            slot_pos = QWidget()
            slot_lay = QHBoxLayout(slot_pos)
            slot_lay.setContentsMargins(0, 0, 0, 0)
            spx = self._spin(0, 9999, 40)
            spy = self._spin(0, 9999, 120)
            slot_lay.addWidget(QLabel("x"))
            slot_lay.addWidget(spx)
            slot_lay.addSpacing(8)
            slot_lay.addWidget(QLabel("y"))
            slot_lay.addWidget(spy)
            slot_lay.addStretch(1)
            layout_form.addRow("槽位列表位置", slot_pos)

            slw = self._spin(100, 9999, max(100, int(self.project_resolution[0] - 80)))
            layout_form.addRow("槽位列表宽度", slw)
            srh = self._spin(20, 200, 34)
            layout_form.addRow("槽位行高度", srh)
            ssp = self._spin(0, 100, 8)
            layout_form.addRow("槽位行间距", ssp)

            # page buttons/text
            prev_pos = QWidget()
            prev_lay = QHBoxLayout(prev_pos)
            prev_lay.setContentsMargins(0, 0, 0, 0)
            ppx = self._spin(0, 9999, 40)
            ppy = self._spin(0, 9999, max(0, int(self.project_resolution[1] - 60)))
            prev_lay.addWidget(QLabel("x"))
            prev_lay.addWidget(ppx)
            prev_lay.addSpacing(8)
            prev_lay.addWidget(QLabel("y"))
            prev_lay.addWidget(ppy)
            prev_lay.addStretch(1)
            layout_form.addRow("上一页按钮位置", prev_pos)

            next_pos = QWidget()
            next_lay = QHBoxLayout(next_pos)
            next_lay.setContentsMargins(0, 0, 0, 0)
            npx = self._spin(0, 9999, 140)
            npy = self._spin(0, 9999, max(0, int(self.project_resolution[1] - 60)))
            next_lay.addWidget(QLabel("x"))
            next_lay.addWidget(npx)
            next_lay.addSpacing(8)
            next_lay.addWidget(QLabel("y"))
            next_lay.addWidget(npy)
            next_lay.addStretch(1)
            layout_form.addRow("下一页按钮位置", next_pos)

            text_pos = QWidget()
            text_lay = QHBoxLayout(text_pos)
            text_lay.setContentsMargins(0, 0, 0, 0)
            tpx = self._spin(0, 9999, 240)
            tpy = self._spin(0, 9999, max(0, int(self.project_resolution[1] - 60)))
            text_lay.addWidget(QLabel("x"))
            text_lay.addWidget(tpx)
            text_lay.addSpacing(8)
            text_lay.addWidget(QLabel("y"))
            text_lay.addWidget(tpy)
            text_lay.addStretch(1)
            layout_form.addRow("页码文字位置", text_pos)

            setattr(self, f"{key}_slot_list_x", spx)
            setattr(self, f"{key}_slot_list_y", spy)
            setattr(self, f"{key}_slot_list_width", slw)
            setattr(self, f"{key}_slot_row_height", srh)
            setattr(self, f"{key}_slot_row_spacing", ssp)
            setattr(self, f"{key}_page_prev_x", ppx)
            setattr(self, f"{key}_page_prev_y", ppy)
            setattr(self, f"{key}_page_next_x", npx)
            setattr(self, f"{key}_page_next_y", npy)
            setattr(self, f"{key}_page_text_x", tpx)
            setattr(self, f"{key}_page_text_y", tpy)
            setattr(self, f"{key}_page_size", page_size)

        elif key == "settings":
            spos = QWidget()
            spos_lay = QHBoxLayout(spos)
            spos_lay.setContentsMargins(0, 0, 0, 0)
            sx = self._spin(0, 9999, 80)
            sy = self._spin(0, 9999, 140)
            spos_lay.addWidget(QLabel("x"))
            spos_lay.addWidget(sx)
            spos_lay.addSpacing(8)
            spos_lay.addWidget(QLabel("y"))
            spos_lay.addWidget(sy)
            spos_lay.addStretch(1)
            layout_form.addRow("滑块起点", spos)
            sw = self._spin(80, 9999, max(80, int(self.project_resolution[0] - 160)))
            layout_form.addRow("滑块宽度", sw)
            sh = self._spin(6, 80, 10)
            layout_form.addRow("滑块高度", sh)
            sg = self._spin(10, 300, 70)
            layout_form.addRow("滑块间距", sg)

            bpos = QWidget()
            bpos_lay = QHBoxLayout(bpos)
            bpos_lay.setContentsMargins(0, 0, 0, 0)
            bx = self._spin(0, 9999, 80)
            by = self._spin(0, 9999, max(0, int(self.project_resolution[1] - 90)))
            bpos_lay.addWidget(QLabel("x"))
            bpos_lay.addWidget(bx)
            bpos_lay.addSpacing(8)
            bpos_lay.addWidget(QLabel("y"))
            bpos_lay.addWidget(by)
            bpos_lay.addStretch(1)
            layout_form.addRow("按钮行位置", bpos)

            bsize = QWidget()
            bsize_lay = QHBoxLayout(bsize)
            bsize_lay.setContentsMargins(0, 0, 0, 0)
            bw = self._spin(60, 9999, 120)
            bh = self._spin(26, 9999, 36)
            bsize_lay.addWidget(QLabel("w"))
            bsize_lay.addWidget(bw)
            bsize_lay.addSpacing(8)
            bsize_lay.addWidget(QLabel("h"))
            bsize_lay.addWidget(bh)
            bsize_lay.addStretch(1)
            layout_form.addRow("按钮大小", bsize)

            setattr(self, f"{key}_slider_x", sx)
            setattr(self, f"{key}_slider_y", sy)
            setattr(self, f"{key}_slider_width", sw)
            setattr(self, f"{key}_slider_height", sh)
            setattr(self, f"{key}_slider_gap", sg)
            setattr(self, f"{key}_button_row_x", bx)
            setattr(self, f"{key}_button_row_y", by)
            setattr(self, f"{key}_button_w", bw)
            setattr(self, f"{key}_button_h", bh)

        preview_box = None
        if layout_form.rowCount() > 0:
            lay.addWidget(layout_box)

            preview_box = QGroupBox("预览（拖拽移动；四角拖拽缩放；支持吸附）")
            pv_lay = QVBoxLayout(preview_box)
            preview = _LayoutPreview(self.project_resolution, self)
            self._attach_preview_toggles(pv_lay, preview)
            pv_lay.addWidget(preview, 1)
            self._previews[key] = preview

        # store controls
        setattr(self, f"{key}_bg_override", chk_bg)
        setattr(self, f"{key}_bg_edit", edit_bg)
        setattr(self, f"{key}_bg_alpha", bg_alpha)

        lay.addWidget(gb)
        lay.addStretch(1)

        outer.addWidget(left, 2)
        if preview_box is not None:
            outer.addWidget(preview_box, 3)

            def _on_controls_changed():
                if getattr(preview, "_updating_from_controls", False):
                    return
                preview._updating_from_controls = True
                try:
                    eff_bg = str(self.common_bg_edit.text() or "").strip()
                    eff_alpha = int(self.common_bg_alpha.value())
                    if chk_bg.isChecked():
                        eff_bg = str(edit_bg.text() or "").strip()
                        eff_alpha = int(bg_alpha.value())
                    preview.set_background(eff_bg, eff_alpha, self.project_dir)

                    if key in {"save", "load"}:
                        lx = int(getattr(self, f"{key}_slot_list_x").value())
                        ly = int(getattr(self, f"{key}_slot_list_y").value())
                        lw = int(getattr(self, f"{key}_slot_list_width").value())
                        rh = int(getattr(self, f"{key}_slot_row_height").value())
                        sp = int(getattr(self, f"{key}_slot_row_spacing").value())
                        try:
                            ps = int(getattr(self, f"{key}_page_size").value())
                        except Exception:
                            ps = 10
                        ps = max(1, min(10, int(ps)))
                        approx_h = (rh + sp) * ps - sp
                        preview.set_rect("slot_list", lx, ly, max(80, lw), max(40, approx_h))

                        if "row_height_handle" in preview._items:
                            preview.set_rect("row_height_handle", lx + 10, ly + rh - 3, 120, 6)
                        if "row_spacing_handle" in preview._items:
                            preview.set_rect("row_spacing_handle", lx + 10, ly + rh + sp - 3, 120, 6)

                        px = int(getattr(self, f"{key}_page_prev_x").value())
                        py = int(getattr(self, f"{key}_page_prev_y").value())
                        nx = int(getattr(self, f"{key}_page_next_x").value())
                        ny = int(getattr(self, f"{key}_page_next_y").value())
                        tx = int(getattr(self, f"{key}_page_text_x").value())
                        ty = int(getattr(self, f"{key}_page_text_y").value())
                        preview.set_rect("page_prev", px, py, 80, 34)
                        preview.set_rect("page_next", nx, ny, 80, 34)
                        preview.set_rect("page_text", tx, ty, 90, 26)

                    if key == "settings":
                        sx = int(getattr(self, f"{key}_slider_x").value())
                        sy = int(getattr(self, f"{key}_slider_y").value())
                        sw = int(getattr(self, f"{key}_slider_width").value())
                        sh = int(getattr(self, f"{key}_slider_height").value())
                        gap = int(getattr(self, f"{key}_slider_gap").value())
                        preview.set_rect("slider0", sx, sy, max(80, sw), max(6, sh))
                        preview.set_rect("slider1", sx, sy + gap, max(80, sw), max(6, sh))
                        preview.set_rect("slider2", sx, sy + gap * 2, max(80, sw), max(6, sh))
                        preview.set_rect("slider3", sx, sy + gap * 3, max(80, sw), max(6, sh))
                        preview.set_rect("slider4", sx, sy + gap * 4, max(80, sw), max(6, sh))
                        # gap handle at second slider
                        preview.set_rect("gap_handle", sx - 18, sy + gap - 8, 16, 16)

                        bx = int(getattr(self, f"{key}_button_row_x").value())
                        by = int(getattr(self, f"{key}_button_row_y").value())
                        bw = int(getattr(self, f"{key}_button_w").value())
                        bh = int(getattr(self, f"{key}_button_h").value())
                        preview.set_rect("btn_save", bx, by, max(60, bw), max(26, bh))
                        preview.set_rect("btn_cancel", bx + max(60, bw) + 20, by, max(60, bw), max(26, bh))
                finally:
                    preview._updating_from_controls = False

            edit_bg.textChanged.connect(lambda _t, _fn=_on_controls_changed: _fn())
            bg_alpha.valueChanged.connect(lambda _v, _fn=_on_controls_changed: _fn())

            # create preview items + callbacks
            if key in {"save", "load"}:
                def on_slot_list_changed(item: _DraggableRect):
                    if preview._updating_from_controls:
                        return
                    r = item.rect()
                    preview._updating_from_controls = True
                    try:
                        _set_spin_value(getattr(self, f"{key}_slot_list_x"), int(r.x()))
                        _set_spin_value(getattr(self, f"{key}_slot_list_y"), int(r.y()))
                        _set_spin_value(getattr(self, f"{key}_slot_list_width"), int(r.width()))
                    finally:
                        preview._updating_from_controls = False
                    self._mark_dirty()

                def _on_btn_pos(namex: str, namey: str):
                    def _cb(item: _DraggableRect):
                        if preview._updating_from_controls:
                            return
                        r = item.rect()
                        preview._updating_from_controls = True
                        try:
                            _set_spin_value(getattr(self, namex), int(r.x()))
                            _set_spin_value(getattr(self, namey), int(r.y()))
                        finally:
                            preview._updating_from_controls = False
                        self._mark_dirty()
                    return _cb

                preview.add_rect("slot_list", 40, 120, 720, 420, on_changed=on_slot_list_changed, resizable=True, min_w=80, min_h=40)
                preview.add_rect("page_prev", 40, self.project_resolution[1] - 60, 80, 34, on_changed=_on_btn_pos(f"{key}_page_prev_x", f"{key}_page_prev_y"))
                preview.add_rect("page_next", 140, self.project_resolution[1] - 60, 80, 34, on_changed=_on_btn_pos(f"{key}_page_next_x", f"{key}_page_next_y"))
                preview.add_rect("page_text", 240, self.project_resolution[1] - 60, 90, 26, on_changed=_on_btn_pos(f"{key}_page_text_x", f"{key}_page_text_y"))

                preview.style_rect(
                    "slot_list",
                    label="slot_list",
                    pen=QPen(QColor(255, 255, 255, 200), 2),
                    brush=QBrush(QColor(255, 255, 255, 35)),
                )
                for n in ("page_prev", "page_next", "page_text"):
                    preview.style_rect(
                        n,
                        label=n,
                        pen=QPen(QColor(255, 255, 255, 200), 2),
                        brush=QBrush(QColor(255, 255, 255, 45)),
                    )

                def on_row_height_handle_changed(item: _DraggableRect):
                    if preview._updating_from_controls:
                        return
                    r = item.rect()
                    base_y = int(getattr(self, f"{key}_slot_list_y").value())
                    new_rh = max(20, int(r.y() + 3 - base_y))
                    preview._updating_from_controls = True
                    try:
                        _set_spin_value(getattr(self, f"{key}_slot_row_height"), new_rh)
                    finally:
                        preview._updating_from_controls = False
                    self._mark_dirty()

                def on_row_spacing_handle_changed(item: _DraggableRect):
                    if preview._updating_from_controls:
                        return
                    r = item.rect()
                    base_y = int(getattr(self, f"{key}_slot_list_y").value())
                    rh0 = int(getattr(self, f"{key}_slot_row_height").value())
                    new_sp = max(0, int(r.y() + 3 - (base_y + rh0)))
                    preview._updating_from_controls = True
                    try:
                        _set_spin_value(getattr(self, f"{key}_slot_row_spacing"), new_sp)
                    finally:
                        preview._updating_from_controls = False
                    self._mark_dirty()

                preview.add_rect("row_height_handle", 50, 120 + 34 - 3, 120, 6, on_changed=on_row_height_handle_changed, resizable=False)
                preview.add_rect("row_spacing_handle", 50, 120 + 34 + 8 - 3, 120, 6, on_changed=on_row_spacing_handle_changed, resizable=False)
                preview.style_rect(
                    "row_height_handle",
                    label="row_height",
                    pen=QPen(QColor(255, 200, 0, 255), 2),
                    brush=QBrush(QColor(255, 200, 0, 140)),
                )
                preview.style_rect(
                    "row_spacing_handle",
                    label="row_spacing",
                    pen=QPen(QColor(255, 160, 0, 255), 2),
                    brush=QBrush(QColor(255, 160, 0, 140)),
                )

                for spn in (
                    getattr(self, f"{key}_page_size"),
                    getattr(self, f"{key}_slot_list_x"),
                    getattr(self, f"{key}_slot_list_y"),
                    getattr(self, f"{key}_slot_list_width"),
                    getattr(self, f"{key}_slot_row_height"),
                    getattr(self, f"{key}_slot_row_spacing"),
                    getattr(self, f"{key}_page_prev_x"),
                    getattr(self, f"{key}_page_prev_y"),
                    getattr(self, f"{key}_page_next_x"),
                    getattr(self, f"{key}_page_next_y"),
                    getattr(self, f"{key}_page_text_x"),
                    getattr(self, f"{key}_page_text_y"),
                ):
                    spn.valueChanged.connect(lambda _v, _fn=_on_controls_changed: _fn())

                _on_controls_changed()

            if key == "settings":
                def on_slider0_changed(item: _DraggableRect):
                    if preview._updating_from_controls:
                        return
                    r = item.rect()
                    preview._updating_from_controls = True
                    try:
                        _set_spin_value(getattr(self, f"{key}_slider_x"), int(r.x()))
                        _set_spin_value(getattr(self, f"{key}_slider_y"), int(r.y()))
                        _set_spin_value(getattr(self, f"{key}_slider_width"), int(r.width()))
                        _set_spin_value(getattr(self, f"{key}_slider_height"), int(r.height()))
                    finally:
                        preview._updating_from_controls = False
                    self._mark_dirty()

                def on_gap_handle_changed(item: _DraggableRect):
                    if preview._updating_from_controls:
                        return
                    r = item.rect()
                    # gap = slider1_y - slider0_y
                    base_y = int(getattr(self, f"{key}_slider_y").value())
                    new_gap = max(10, int(r.y() + 8 - base_y))
                    preview._updating_from_controls = True
                    try:
                        _set_spin_value(getattr(self, f"{key}_slider_gap"), new_gap)
                    finally:
                        preview._updating_from_controls = False
                    self._mark_dirty()

                def on_button_row_changed(item: _DraggableRect):
                    if preview._updating_from_controls:
                        return
                    r = item.rect()
                    preview._updating_from_controls = True
                    try:
                        _set_spin_value(getattr(self, f"{key}_button_row_x"), int(r.x()))
                        _set_spin_value(getattr(self, f"{key}_button_row_y"), int(r.y()))
                        _set_spin_value(getattr(self, f"{key}_button_w"), int(r.width()))
                        _set_spin_value(getattr(self, f"{key}_button_h"), int(r.height()))
                    finally:
                        preview._updating_from_controls = False
                    self._mark_dirty()

                preview.add_rect("slider0", 80, 140, max(80, self.project_resolution[0] - 160), 10, on_changed=on_slider0_changed, resizable=True, min_w=80, min_h=6)
                preview.add_rect("slider1", 80, 210, max(80, self.project_resolution[0] - 160), 10, on_changed=lambda _i: None)
                preview.add_rect("slider2", 80, 280, max(80, self.project_resolution[0] - 160), 10, on_changed=lambda _i: None)
                preview.add_rect("slider3", 80, 350, max(80, self.project_resolution[0] - 160), 10, on_changed=lambda _i: None)
                preview.add_rect("slider4", 80, 420, max(80, self.project_resolution[0] - 160), 10, on_changed=lambda _i: None)
                # only slider0 is directly movable/resizable; other sliders follow
                for sn in ("slider0", "slider1", "slider2", "slider3", "slider4"):
                    preview.style_rect(
                        sn,
                        label=sn,
                        pen=QPen(QColor(255, 255, 255, 200), 2),
                        brush=QBrush(QColor(255, 255, 255, 35 if sn != "slider0" else 55)),
                    )
                preview._items["slider1"]._movable = False
                preview._items["slider2"]._movable = False
                preview._items["slider3"]._movable = False
                preview._items["slider4"]._movable = False

                preview.add_rect("gap_handle", 62, 210 - 8, 16, 16, on_changed=on_gap_handle_changed, resizable=False, min_w=10, min_h=10)
                preview.style_rect(
                    "gap_handle",
                    label="gap",
                    pen=QPen(QColor(255, 200, 0, 255), 2),
                    brush=QBrush(QColor(255, 200, 0, 150)),
                )

                preview.add_rect("btn_save", 80, self.project_resolution[1] - 90, 120, 36, on_changed=on_button_row_changed, resizable=True, min_w=60, min_h=26)
                preview.add_rect("btn_cancel", 220, self.project_resolution[1] - 90, 120, 36, on_changed=lambda _i: None)
                for bn in ("btn_save", "btn_cancel"):
                    preview.style_rect(
                        bn,
                        label=bn,
                        pen=QPen(QColor(255, 255, 255, 200), 2),
                        brush=QBrush(QColor(255, 255, 255, 45 if bn == "btn_save" else 25)),
                    )
                preview._items["btn_cancel"]._movable = False

                for spn in (
                    getattr(self, f"{key}_slider_x"),
                    getattr(self, f"{key}_slider_y"),
                    getattr(self, f"{key}_slider_width"),
                    getattr(self, f"{key}_slider_height"),
                    getattr(self, f"{key}_slider_gap"),
                    getattr(self, f"{key}_button_row_x"),
                    getattr(self, f"{key}_button_row_y"),
                    getattr(self, f"{key}_button_w"),
                    getattr(self, f"{key}_button_h"),
                ):
                    spn.valueChanged.connect(lambda _v, _fn=_on_controls_changed: _fn())

                _on_controls_changed()

    def _build_scroll_tab(self, tab: QWidget, *, key: str):
        outer = QHBoxLayout(tab)
        left = QWidget()
        lay = QVBoxLayout(left)
        gb = QGroupBox("覆盖(可选)")
        form = QFormLayout(gb)

        chk_bg = QCheckBox("覆盖背景图")
        chk_bg.stateChanged.connect(self._mark_dirty)
        edit_bg, bg_row = self._image_row(f"选择{key}背景图")
        edit_bg.setEnabled(False)
        bg_row.setEnabled(False)

        bg_alpha = self._spin(0, 255, 255)
        bg_alpha.setEnabled(False)

        def on_chk_bg(state: int):
            enabled = chk_bg.isChecked()
            edit_bg.setEnabled(enabled)
            bg_row.setEnabled(enabled)
            bg_alpha.setEnabled(enabled)
            self._mark_dirty()

        chk_bg.stateChanged.connect(on_chk_bg)
        form.addRow(chk_bg)
        form.addRow("背景图", bg_row)
        form.addRow("背景图透明度(0-255)", bg_alpha)

        chk_area = QCheckBox("覆盖文本区域")
        chk_area.stateChanged.connect(self._mark_dirty)
        area_row = QWidget()
        a_lay = QHBoxLayout(area_row)
        a_lay.setContentsMargins(0, 0, 0, 0)
        ax = self._spin(0, 9999, 40)
        ay = self._spin(0, 9999, 100)
        aw = self._spin(20, 9999, 720)
        ah = self._spin(20, 9999, 440)
        for wdg, lbl in ((ax, "x"), (ay, "y"), (aw, "w"), (ah, "h")):
            a_lay.addWidget(QLabel(lbl))
            a_lay.addWidget(wdg)
            a_lay.addSpacing(6)
        a_lay.addStretch(1)
        area_row.setEnabled(False)

        def on_chk_area(state: int):
            enabled = chk_area.isChecked()
            area_row.setEnabled(enabled)
            self._mark_dirty()

        chk_area.stateChanged.connect(on_chk_area)

        form.addRow(chk_area)
        form.addRow("区域", area_row)

        preview_box = QGroupBox("预览（拖拽移动；四角拖拽缩放；支持吸附）")
        pv_lay = QVBoxLayout(preview_box)
        preview = _LayoutPreview(self.project_resolution, self)
        self._attach_preview_toggles(pv_lay, preview)
        pv_lay.addWidget(preview, 1)
        self._previews[key] = preview

        def _sync_visibility():
            # only show text area when override is enabled
            it = preview._items.get("text_area")
            if not it:
                return
            it.setVisible(bool(chk_area.isChecked()))

        def _on_controls_changed():
            if getattr(preview, "_updating_from_controls", False):
                return
            preview._updating_from_controls = True
            try:
                eff_bg = str(self.common_bg_edit.text() or "").strip()
                eff_alpha = int(self.common_bg_alpha.value())
                if chk_bg.isChecked():
                    eff_bg = str(edit_bg.text() or "").strip()
                    eff_alpha = int(bg_alpha.value())
                preview.set_background(eff_bg, eff_alpha, self.project_dir)

                axv = int(ax.value())
                ayv = int(ay.value())
                awv = int(aw.value())
                ahv = int(ah.value())
                preview.set_rect("text_area", axv, ayv, max(20, awv), max(20, ahv))
                _sync_visibility()
            finally:
                preview._updating_from_controls = False

        def on_area_changed(item: _DraggableRect):
            if preview._updating_from_controls:
                return
            r = item.rect()
            preview._updating_from_controls = True
            try:
                _set_spin_value(ax, int(r.x()))
                _set_spin_value(ay, int(r.y()))
                _set_spin_value(aw, int(r.width()))
                _set_spin_value(ah, int(r.height()))
            finally:
                preview._updating_from_controls = False
            self._mark_dirty()

        preview.add_rect("text_area", 40, 100, self.project_resolution[0] - 80, self.project_resolution[1] - 160, on_changed=on_area_changed, resizable=True, min_w=20, min_h=20)
        preview.style_rect(
            "text_area",
            label="text_area",
            pen=QPen(QColor(160, 255, 160, 220), 2),
            brush=QBrush(QColor(160, 255, 160, 60)),
        )

        chk_area.stateChanged.connect(lambda _s: (_sync_visibility(), self._mark_dirty()))
        edit_bg.textChanged.connect(lambda _t, _fn=_on_controls_changed: _fn())
        bg_alpha.valueChanged.connect(lambda _v, _fn=_on_controls_changed: _fn())
        for spn in (ax, ay, aw, ah):
            spn.valueChanged.connect(lambda _v, _fn=_on_controls_changed: _fn())
        _on_controls_changed()

        setattr(self, f"{key}_bg_override", chk_bg)
        setattr(self, f"{key}_bg_edit", edit_bg)
        setattr(self, f"{key}_bg_alpha", bg_alpha)
        setattr(self, f"{key}_area_override", chk_area)
        setattr(self, f"{key}_area_x", ax)
        setattr(self, f"{key}_area_y", ay)
        setattr(self, f"{key}_area_w", aw)
        setattr(self, f"{key}_area_h", ah)
        setattr(self, f"{key}_area_row", area_row)

        lay.addWidget(gb)
        lay.addStretch(1)

        outer.addWidget(left, 2)
        outer.addWidget(preview_box, 3)

    # --- data

    def _apply_defaults(self):
        self.chk_enabled.setChecked(False)
        self._dirty = False

    def _reload_from_project(self):
        if not self.project_manager:
            QMessageBox.warning(self, "无法读取", "当前没有工程管理器，无法读取工程配置。")
            return
        cfg = (self.project_manager.project_data.get("game_config", {}) if self.project_manager.project_data else {}) or {}
        fm = cfg.get("function_menus") if isinstance(cfg, dict) else None
        self._apply_from_function_menus(fm if isinstance(fm, dict) else {})
        self._dirty = False

    def _write_to_project(self):
        if not self.project_manager:
            QMessageBox.warning(self, "无法保存", "当前没有工程管理器，无法写入工程配置。")
            return
        cfg = self.project_manager.project_data.setdefault("game_config", {})
        cfg["function_menus"] = self._collect_function_menus()
        self._dirty = False
        QMessageBox.information(self, "已保存", "功能菜单配置已写入工程，保存工程文件后生效。")

    def _apply_from_function_menus(self, fm: dict):
        self.chk_enabled.setChecked(bool(fm.get("enabled", False)))
        common = fm.get("common") if isinstance(fm.get("common"), dict) else {}

        def g(key: str, default):
            v = common.get(key)
            return v if v is not None else default

        self.common_overlay_alpha.setValue(int(g("overlay_alpha", 160)))
        self.common_bg_edit.setText(str(g("background_image", "")))
        self.common_bg_alpha.setValue(int(g("background_alpha", 255)))
        self.common_font_size.setValue(int(g("font_size", 18)))
        self.common_title_font_size.setValue(int(g("title_font_size", 22)))
        self.common_title_color_edit.setText(_hex_from_color_cfg(g("title_color", [255, 255, 255]), "#FFFFFF"))
        self.common_text_color_edit.setText(_hex_from_color_cfg(g("text_color", [230, 230, 230]), "#E6E6E6"))
        self.common_hint_color_edit.setText(_hex_from_color_cfg(g("hint_color", [200, 200, 200]), "#C8C8C8"))
        self.common_hover_color_edit.setText(_hex_from_color_cfg(g("hover_color", [255, 255, 255]), "#FFFFFF"))

        tp = g("title_pos", [40, 40])
        if isinstance(tp, (list, tuple)) and len(tp) >= 2:
            self.common_title_x.setValue(int(tp[0]))
            self.common_title_y.setValue(int(tp[1]))

        cb = g("close_button", {})
        if isinstance(cb, dict):
            pos = cb.get("pos", [740, 40])
            size = cb.get("size", [32, 32])
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                self.common_close_x.setValue(int(pos[0]))
                self.common_close_y.setValue(int(pos[1]))
            if isinstance(size, (list, tuple)) and len(size) >= 2:
                self.common_close_w.setValue(int(size[0]))
                self.common_close_h.setValue(int(size[1]))

        for key in ("save", "load", "settings"):
            spec = fm.get(key) if isinstance(fm.get(key), dict) else {}
            chk = getattr(self, f"{key}_bg_override")
            edit = getattr(self, f"{key}_bg_edit")
            alp = getattr(self, f"{key}_bg_alpha")
            if "background_image" in spec:
                chk.setChecked(True)
                edit.setText(str(spec.get("background_image") or ""))
                alp.setValue(int(spec.get("background_alpha", 255)))
            else:
                chk.setChecked(False)
                edit.setText("")
                alp.setValue(255)

            # layout fields
            if key in {"save", "load"}:
                try:
                    ps = int(spec.get("page_size", 10) or 10)
                    ps = max(1, min(10, ps))
                    getattr(self, f"{key}_page_size").setValue(int(ps))
                except Exception:
                    pass
                try:
                    pos = spec.get("slot_list_pos", [40, 120])
                    getattr(self, f"{key}_slot_list_x").setValue(int(pos[0]))
                    getattr(self, f"{key}_slot_list_y").setValue(int(pos[1]))
                except Exception:
                    pass
                try:
                    getattr(self, f"{key}_slot_list_width").setValue(int(spec.get("slot_list_width", self.project_resolution[0] - 80)))
                except Exception:
                    pass
                try:
                    getattr(self, f"{key}_slot_row_height").setValue(int(spec.get("slot_row_height", 34)))
                except Exception:
                    pass
                try:
                    getattr(self, f"{key}_slot_row_spacing").setValue(int(spec.get("slot_row_spacing", 8)))
                except Exception:
                    pass

                for name, default in (
                    ("page_prev_pos", [40, self.project_resolution[1] - 60]),
                    ("page_next_pos", [140, self.project_resolution[1] - 60]),
                    ("page_text_pos", [240, self.project_resolution[1] - 60]),
                ):
                    try:
                        p = spec.get(name, default)
                        if name == "page_prev_pos":
                            getattr(self, f"{key}_page_prev_x").setValue(int(p[0]))
                            getattr(self, f"{key}_page_prev_y").setValue(int(p[1]))
                        elif name == "page_next_pos":
                            getattr(self, f"{key}_page_next_x").setValue(int(p[0]))
                            getattr(self, f"{key}_page_next_y").setValue(int(p[1]))
                        else:
                            getattr(self, f"{key}_page_text_x").setValue(int(p[0]))
                            getattr(self, f"{key}_page_text_y").setValue(int(p[1]))
                    except Exception:
                        continue

            if key == "settings":
                try:
                    p = spec.get("slider_pos", [80, 140])
                    getattr(self, f"{key}_slider_x").setValue(int(p[0]))
                    getattr(self, f"{key}_slider_y").setValue(int(p[1]))
                except Exception:
                    pass
                for name, attr, default in (
                    ("slider_width", f"{key}_slider_width", self.project_resolution[0] - 160),
                    ("slider_height", f"{key}_slider_height", 10),
                    ("slider_gap", f"{key}_slider_gap", 70),
                ):
                    try:
                        getattr(self, attr).setValue(int(spec.get(name, default)))
                    except Exception:
                        continue
                try:
                    p = spec.get("button_row_pos", [80, self.project_resolution[1] - 90])
                    getattr(self, f"{key}_button_row_x").setValue(int(p[0]))
                    getattr(self, f"{key}_button_row_y").setValue(int(p[1]))
                except Exception:
                    pass
                try:
                    s = spec.get("button_size", [120, 36])
                    getattr(self, f"{key}_button_w").setValue(int(s[0]))
                    getattr(self, f"{key}_button_h").setValue(int(s[1]))
                except Exception:
                    pass

        for key in ("history", "help"):
            spec = fm.get(key) if isinstance(fm.get(key), dict) else {}
            chk = getattr(self, f"{key}_bg_override")
            edit = getattr(self, f"{key}_bg_edit")
            alp = getattr(self, f"{key}_bg_alpha")
            if "background_image" in spec:
                chk.setChecked(True)
                edit.setText(str(spec.get("background_image") or ""))
                alp.setValue(int(spec.get("background_alpha", 255)))
            else:
                chk.setChecked(False)
                edit.setText("")
                alp.setValue(255)

            chk_area = getattr(self, f"{key}_area_override")
            row = getattr(self, f"{key}_area_row")
            if "text_area" in spec and isinstance(spec.get("text_area"), (list, tuple)) and len(spec.get("text_area")) == 4:
                chk_area.setChecked(True)
                row.setEnabled(True)
                ta = spec.get("text_area")
                getattr(self, f"{key}_area_x").setValue(int(ta[0]))
                getattr(self, f"{key}_area_y").setValue(int(ta[1]))
                getattr(self, f"{key}_area_w").setValue(int(ta[2]))
                getattr(self, f"{key}_area_h").setValue(int(ta[3]))
            else:
                chk_area.setChecked(False)
                row.setEnabled(False)

        self._refresh_preview_backgrounds()

    def _collect_function_menus(self) -> dict:
        common = {
            "overlay_alpha": int(self.common_overlay_alpha.value()),
            "background_image": str(self.common_bg_edit.text() or "").strip(),
            "background_alpha": int(self.common_bg_alpha.value()),
            "font_size": int(self.common_font_size.value()),
            "title_font_size": int(self.common_title_font_size.value()),
            "title_color": _rgb_list_from_hex(str(self.common_title_color_edit.text() or "").strip(), "#FFFFFF"),
            "text_color": _rgb_list_from_hex(str(self.common_text_color_edit.text() or "").strip(), "#E6E6E6"),
            "hint_color": _rgb_list_from_hex(str(self.common_hint_color_edit.text() or "").strip(), "#C8C8C8"),
            "hover_color": _rgb_list_from_hex(str(self.common_hover_color_edit.text() or "").strip(), "#FFFFFF"),
            "title_pos": [int(self.common_title_x.value()), int(self.common_title_y.value())],
            "close_button": {
                "pos": [int(self.common_close_x.value()), int(self.common_close_y.value())],
                "size": [int(self.common_close_w.value()), int(self.common_close_h.value())],
                "text": "×",
            },
        }

        def collect_simple(key: str) -> dict:
            d: dict = {}
            if getattr(self, f"{key}_bg_override").isChecked():
                # when override is enabled, empty means "explicitly clear"
                d["background_image"] = str(getattr(self, f"{key}_bg_edit").text() or "").strip()
                d["background_alpha"] = int(getattr(self, f"{key}_bg_alpha").value())

            if key in {"save", "load"}:
                try:
                    ps = int(getattr(self, f"{key}_page_size").value())
                except Exception:
                    ps = 10
                d["page_size"] = max(1, min(10, int(ps)))
                d["slot_list_pos"] = [
                    int(getattr(self, f"{key}_slot_list_x").value()),
                    int(getattr(self, f"{key}_slot_list_y").value()),
                ]
                d["slot_list_width"] = int(getattr(self, f"{key}_slot_list_width").value())
                d["slot_row_height"] = int(getattr(self, f"{key}_slot_row_height").value())
                d["slot_row_spacing"] = int(getattr(self, f"{key}_slot_row_spacing").value())
                d["page_prev_pos"] = [
                    int(getattr(self, f"{key}_page_prev_x").value()),
                    int(getattr(self, f"{key}_page_prev_y").value()),
                ]
                d["page_next_pos"] = [
                    int(getattr(self, f"{key}_page_next_x").value()),
                    int(getattr(self, f"{key}_page_next_y").value()),
                ]
                d["page_text_pos"] = [
                    int(getattr(self, f"{key}_page_text_x").value()),
                    int(getattr(self, f"{key}_page_text_y").value()),
                ]

            if key == "settings":
                d["slider_pos"] = [
                    int(getattr(self, f"{key}_slider_x").value()),
                    int(getattr(self, f"{key}_slider_y").value()),
                ]
                d["slider_width"] = int(getattr(self, f"{key}_slider_width").value())
                d["slider_height"] = int(getattr(self, f"{key}_slider_height").value())
                d["slider_gap"] = int(getattr(self, f"{key}_slider_gap").value())
                d["button_row_pos"] = [
                    int(getattr(self, f"{key}_button_row_x").value()),
                    int(getattr(self, f"{key}_button_row_y").value()),
                ]
                d["button_size"] = [
                    int(getattr(self, f"{key}_button_w").value()),
                    int(getattr(self, f"{key}_button_h").value()),
                ]
            return d

        def collect_scroll(key: str) -> dict:
            d = collect_simple(key)
            if getattr(self, f"{key}_area_override").isChecked():
                d["text_area"] = [
                    int(getattr(self, f"{key}_area_x").value()),
                    int(getattr(self, f"{key}_area_y").value()),
                    int(getattr(self, f"{key}_area_w").value()),
                    int(getattr(self, f"{key}_area_h").value()),
                ]
            return d

        return {
            "enabled": bool(self.chk_enabled.isChecked()),
            "common": common,
            "save": collect_simple("save"),
            "load": collect_simple("load"),
            "settings": collect_simple("settings"),
            "history": collect_scroll("history"),
            "help": collect_scroll("help"),
        }
