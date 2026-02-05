# -*- coding: utf-8 -*-
"""Main menu designer dialog for title/background/BGM with live preview."""
from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any, Optional

from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabBar,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtCore import Qt, QRect, pyqtSignal

from .properties_panel import _CollapsibleSection


_DEFAULT_MENU_BUTTONS: list[dict[str, str]] = [
    {"label": "开始游戏", "action": "start"},
    {"label": "继续", "action": "continue"},
    {"label": "读取存档", "action": "load"},
    {"label": "设置", "action": "settings"},
    {"label": "退出", "action": "exit"},
]


def _normalize_menu_buttons(raw: Any) -> list[dict[str, Any]]:
    """Normalize menu button config into a fixed 5-item list.

    Each item contains: action, label, style('text'|'image'), image, image_scale.
    Unknown/missing actions are ignored.
    """

    by_action: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        for it in raw:
            if not isinstance(it, dict):
                continue
            action = str(it.get("action") or "").strip()
            if action not in {"start", "continue", "load", "settings", "exit"}:
                continue
            by_action[action] = dict(it)

    out: list[dict[str, Any]] = []
    for d in _DEFAULT_MENU_BUTTONS:
        action = d["action"]
        base_label = d["label"]
        it = by_action.get(action, {})
        label = str(it.get("label") or base_label)
        image = str(it.get("image") or it.get("image_path") or "")
        style_raw = it.get("style") or it.get("mode")
        if style_raw is None or str(style_raw).strip() == "":
            style = "image" if image else "text"
        else:
            style = str(style_raw).strip().lower()
        if style not in {"text", "image"}:
            style = "image" if image else "text"
        try:
            img_scale = float(it.get("image_scale", 1.0) or 1.0)
        except Exception:
            img_scale = 1.0
        img_scale = max(0.1, min(5.0, float(img_scale)))
        out.append({
            "action": action,
            "label": label,
            "style": style,
            "image": image,
            "image_scale": float(img_scale),
        })
    return out


class AspectRatioContainer(QWidget):
    """Keep a single child at a fixed aspect ratio (letterboxed)."""

    def __init__(self, child: QWidget, aspect_size: tuple[int, int], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._child = child
        self._child.setParent(self)
        self._aspect = (max(1, int(aspect_size[0])), max(1, int(aspect_size[1])))
        self.setMinimumSize(520, 320)

    def set_aspect_size(self, aspect_size: tuple[int, int]):
        self._aspect = (max(1, int(aspect_size[0])), max(1, int(aspect_size[1])))
        self._relayout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self):
        aw, ah = self._aspect
        if aw <= 0 or ah <= 0:
            self._child.setGeometry(self.rect())
            return
        w = self.width()
        h = self.height()
        scale = min(w / aw, h / ah)
        cw = int(aw * scale)
        ch = int(ah * scale)
        x = (w - cw) // 2
        y = (h - ch) // 2
        self._child.setGeometry(x, y, cw, ch)


class _AspectRatioMenuCanvas(QWidget):
    """Letterboxed drawing surface keeping base resolution aspect ratio."""

    def __init__(self, base_size: tuple[int, int], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._base_size = (max(1, int(base_size[0])), max(1, int(base_size[1])))

    def set_base_size(self, base_size: tuple[int, int]):
        self._base_size = (max(1, int(base_size[0])), max(1, int(base_size[1])))
        self.update()

    def _transform(self) -> tuple[float, int, int, int, int]:
        base_w, base_h = self._base_size
        r = self.rect()
        scale = min(r.width() / base_w, r.height() / base_h)
        view_w, view_h = int(base_w * scale), int(base_h * scale)
        ox = (r.width() - view_w) // 2
        oy = (r.height() - view_h) // 2
        return scale, ox, oy, view_w, view_h

    def base_to_widget(self, x: float, y: float) -> tuple[int, int]:
        scale, ox, oy, _, _ = self._transform()
        return int(ox + x * scale), int(oy + y * scale)

    def widget_to_base(self, x: float, y: float) -> tuple[float, float]:
        scale, ox, oy, _, _ = self._transform()
        if scale <= 0:
            return 0.0, 0.0
        return (x - ox) / scale, (y - oy) / scale

    def base_rect_to_widget(self, rect_vals: list[float]) -> tuple[int, int, int, int]:
        x, y, w, h = rect_vals
        x1, y1 = self.base_to_widget(x, y)
        x2, y2 = self.base_to_widget(x + w, y + h)
        return x1, y1, max(1, x2 - x1), max(1, y2 - y1)


class InteractiveMenuPreview(_AspectRatioMenuCanvas):
    """Interactive preview with drag+corner-resize for title text, title image, and option list area."""

    layoutEdited = pyqtSignal(dict)

    def __init__(self, project_dir: Optional[Path], base_size: tuple[int, int] = (800, 600), parent: Optional[QWidget] = None):
        super().__init__(base_size, parent)
        self.project_dir = project_dir
        self.setMouseTracking(True)
        self.setMinimumSize(520, 320)

        self._state: dict[str, Any] = {}
        self._bg_pixmap: Optional[QPixmap] = None
        self._title_pixmap: Optional[QPixmap] = None
        self._button_pixmaps: dict[str, Optional[QPixmap]] = {}
        self._indicator_pixmap: Optional[QPixmap] = None

        self._selected: str | None = None
        self._hovered: str | None = None
        self._drag_mode: str | None = None  # 'move' | 'resize'
        self._drag_handle: str | None = None
        self._drag_start_pos = None
        self._drag_start_rect = None
        self._handle_px = 10
        self._min_w = 20
        self._min_h = 20

        self._grid_snap_enabled = False
        self._grid_size = 10
        self._align_guides_enabled = True
        self._align_snap_enabled = True
        self._align_threshold = 6
        self._active_guides: list[tuple[str, float]] = []

    def set_grid_snap(self, enabled: bool, grid_size: int | None = None):
        self._grid_snap_enabled = bool(enabled)
        if grid_size is not None:
            try:
                self._grid_size = max(1, int(grid_size))
            except Exception:
                self._grid_size = 10
        self.update()

    def set_align_guides(self, enabled: bool, snap: bool | None = None):
        self._align_guides_enabled = bool(enabled)
        if snap is not None:
            self._align_snap_enabled = bool(snap)
        self.update()

    def update_state(self, cfg: dict[str, Any]):
        self._state = cfg or {}
        self._load_bg(cfg.get("menu_background", ""))
        self._load_title_img(cfg.get("menu_title_image", ""))
        self._load_indicator_img(cfg.get("menu_option_indicator_image", ""))
        self._preload_button_pixmaps()
        self.update()

    def _preload_button_pixmaps(self):
        self._button_pixmaps = {}
        buttons = _normalize_menu_buttons(self._state.get("menu_buttons"))
        for it in buttons:
            if it.get("style") != "image":
                continue
            key = it.get("action")
            img = str(it.get("image") or "")
            if not key:
                continue
            resolved = self._resolve(img)
            if resolved and resolved.exists():
                try:
                    px = QPixmap(str(resolved))
                    self._button_pixmaps[str(key)] = px if not px.isNull() else None
                except Exception:
                    self._button_pixmaps[str(key)] = None
            else:
                self._button_pixmaps[str(key)] = None

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

    def _load_indicator_img(self, path_str: str):
        resolved = self._resolve(path_str)
        if resolved and resolved.exists():
            try:
                px = QPixmap(str(resolved))
                self._indicator_pixmap = px if not px.isNull() else None
                return
            except Exception:
                pass
        self._indicator_pixmap = None

    def _handles_for_rect(self, wx: int, wy: int, ww: int, wh: int) -> dict[str, tuple[int, int, int, int]]:
        s = self._handle_px
        return {
            "tl": (wx - s // 2, wy - s // 2, s, s),
            "tr": (wx + ww - s // 2, wy - s // 2, s, s),
            "bl": (wx - s // 2, wy + wh - s // 2, s, s),
            "br": (wx + ww - s // 2, wy + wh - s // 2, s, s),
        }

    def _title_image_rect(self) -> list[float]:
        pos = self._state.get("menu_title_image_pos") or [400, 80]
        scale = float(self._state.get("menu_title_image_scale", 1.0) or 1.0)
        cx, cy = float(pos[0]), float(pos[1])
        if self._title_pixmap and not self._title_pixmap.isNull():
            rw, rh = float(self._title_pixmap.width()), float(self._title_pixmap.height())
        else:
            rw, rh = 220.0, 100.0
        w = max(1.0, rw * scale)
        h = max(1.0, rh * scale)
        return [cx - w / 2.0, cy - h / 2.0, w, h]

    def _title_text_rect(self) -> list[float]:
        title_text = str(self._state.get("menu_title") or "标题")
        pos = self._state.get("menu_title_pos") or [60, 60]
        scale = float(self._state.get("menu_title_scale", 1.0) or 1.0)
        x, y = float(pos[0]), float(pos[1])
        font = QFont("Arial")
        font.setPixelSize(max(10, int(36 * scale)))
        metrics = QFontMetrics(font)
        w = float(max(40, metrics.horizontalAdvance(title_text)))
        h = float(max(18, metrics.height()))
        return [x, y, w, h]

    def _option_rect(self) -> list[float]:
        pos = self._state.get("menu_option_pos") or [80, 140]
        scale = float(self._state.get("menu_option_scale", 1.0) or 1.0)
        x, y = float(pos[0]), float(pos[1])
        w = float(300.0 * scale)
        # approximate list height
        try:
            spacing = int(self._state.get("menu_option_spacing", 10) or 10)
        except Exception:
            spacing = 10
        line = float(max(8.0, 20.0 * scale) + max(0, float(spacing)))
        count = 5
        h = float(max(40.0, line * count))
        return [x, y, w, h]

    def _components(self) -> list[tuple[str, list[float]]]:
        # priority (topmost first)
        return [
            ("title_text", self._title_text_rect()),
            ("title_image", self._title_image_rect()),
            ("options", self._option_rect()),
        ]

    def _hit_test(self, mx: int, my: int):
        for name, base_rect in self._components():
            wx, wy, ww, wh = self.base_rect_to_widget(base_rect)
            handles = self._handles_for_rect(wx, wy, ww, wh)
            for hname, (hx, hy, hw, hh) in handles.items():
                if hx <= mx <= hx + hw and hy <= my <= hy + hh:
                    return name, "resize", hname, base_rect
            if wx <= mx <= wx + ww and wy <= my <= wy + wh:
                return name, "move", None, base_rect
        return None, None, None, None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        name, mode, handle, base_rect = self._hit_test(int(event.position().x()), int(event.position().y()))
        if not name:
            self._selected = None
            self._active_guides = []
            self.update()
            return
        self._selected = name
        self._drag_mode = mode
        self._drag_handle = handle
        self._drag_start_pos = (event.position().x(), event.position().y())
        self._drag_start_rect = list(base_rect)
        self._active_guides = []
        self.update()

    def mouseMoveEvent(self, event):
        mx = int(event.position().x())
        my = int(event.position().y())

        if not self._drag_mode:
            name, _, _, _ = self._hit_test(mx, my)
            if name != self._hovered:
                self._hovered = name
                self.update()
            return

        if not self._selected or not self._drag_start_pos or not self._drag_start_rect:
            return

        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)

        dx_base, dy_base = self.widget_to_base(mx, my)
        sx0, sy0 = self.widget_to_base(self._drag_start_pos[0], self._drag_start_pos[1])
        dx = dx_base - sx0
        dy = dy_base - sy0

        x0, y0, w0, h0 = self._drag_start_rect
        x, y, w, h = float(x0), float(y0), float(w0), float(h0)
        self._active_guides = []

        if self._drag_mode == "move":
            x = x0 + dx
            y = y0 + dy
            if self._align_guides_enabled:
                x, y = self._apply_align_snap_move(self._selected, x, y, w0, h0)
        elif self._drag_mode == "resize" and self._drag_handle:
            sign_x = 1 if self._drag_handle in {"tr", "br"} else -1
            sign_y = 1 if self._drag_handle in {"bl", "br"} else -1
            factor = 2.0 if alt else 1.0
            w = w0 + factor * sign_x * dx
            h = h0 + factor * sign_y * dy
            if shift and w0 > 0 and h0 > 0:
                ratio = float(w0) / float(h0)
                if abs(dx) >= abs(dy):
                    h = w / ratio
                else:
                    w = h * ratio
            w = max(float(self._min_w), float(w))
            h = max(float(self._min_h), float(h))

            if alt:
                cx0 = x0 + w0 / 2.0
                cy0 = y0 + h0 / 2.0
                x = cx0 - w / 2.0
                y = cy0 - h / 2.0
            else:
                if self._drag_handle == "tl":
                    ax, ay = x0 + w0, y0 + h0
                    x, y = ax - w, ay - h
                elif self._drag_handle == "tr":
                    ax, ay = x0, y0 + h0
                    x, y = ax, ay - h
                elif self._drag_handle == "bl":
                    ax, ay = x0 + w0, y0
                    x, y = ax - w, ay
                else:
                    x, y = x0, y0

                if self._align_guides_enabled:
                    x, y, w, h = self._apply_align_snap_resize(self._selected, self._drag_handle, x, y, w, h)

        if self._grid_snap_enabled and self._grid_size > 0:
            x, y, w, h = self._apply_grid_snap(x, y, w, h)

        w = max(float(self._min_w), float(w))
        h = max(float(self._min_h), float(h))
        self._apply_rect_to_state(self._selected, [float(x), float(y), float(w), float(h)], w0, h0)
        self.update()
        self.layoutEdited.emit(self._state)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_mode = None
        self._drag_handle = None
        self._drag_start_pos = None
        self._drag_start_rect = None
        self._active_guides = []
        self.update()

    def _apply_grid_snap(self, x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
        g = max(1, int(self._grid_size))
        def snap(v: float) -> float:
            return round(v / g) * g
        return snap(x), snap(y), max(float(self._min_w), snap(w)), max(float(self._min_h), snap(h))

    def _collect_align_points(self, exclude_name: str) -> dict[str, list[float]]:
        xs: list[float] = []
        ys: list[float] = []
        for name, rect in self._components():
            if name == exclude_name:
                continue
            rx, ry, rw, rh = rect
            xs.extend([float(rx), float(rx + rw / 2.0), float(rx + rw)])
            ys.extend([float(ry), float(ry + rh / 2.0), float(ry + rh)])
        return {"x": xs, "y": ys}

    def _apply_align_snap_move(self, name: str, x: float, y: float, w: float, h: float) -> tuple[float, float]:
        pts = self._collect_align_points(name)
        best_dx = None
        best_dy = None
        best_v = None
        best_h = None
        thresh = float(self._align_threshold)

        cand_xs = [float(x), float(x + w / 2.0), float(x + w)]
        cand_ys = [float(y), float(y + h / 2.0), float(y + h)]

        for cx in cand_xs:
            for tx in pts["x"]:
                d = tx - cx
                if abs(d) <= thresh and (best_dx is None or abs(d) < abs(best_dx)):
                    best_dx = d
                    best_v = tx

        for cy in cand_ys:
            for ty in pts["y"]:
                d = ty - cy
                if abs(d) <= thresh and (best_dy is None or abs(d) < abs(best_dy)):
                    best_dy = d
                    best_h = ty

        self._active_guides = []
        if best_v is not None:
            self._active_guides.append(("v", float(best_v)))
        if best_h is not None:
            self._active_guides.append(("h", float(best_h)))

        if self._align_snap_enabled:
            if best_dx is not None:
                x += best_dx
            if best_dy is not None:
                y += best_dy
        return x, y

    def _apply_align_snap_resize(self, name: str, handle: str, x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
        pts = self._collect_align_points(name)
        thresh = float(self._align_threshold)
        left = float(x)
        right = float(x + w)
        top = float(y)
        bottom = float(y + h)
        cx = float(x + w / 2.0)
        cy = float(y + h / 2.0)

        move_left = handle in {"tl", "bl"}
        move_right = handle in {"tr", "br"}
        move_top = handle in {"tl", "tr"}
        move_bottom = handle in {"bl", "br"}

        guides: list[tuple[str, float]] = []

        best_dx = None
        best_target_x = None
        candidates = []
        if move_left:
            candidates.append(left)
        if move_right:
            candidates.append(right)
        candidates.append(cx)
        for cval in candidates:
            for tx in pts["x"]:
                d = tx - cval
                if abs(d) <= thresh and (best_dx is None or abs(d) < abs(best_dx)):
                    best_dx = d
                    best_target_x = tx
        if best_target_x is not None:
            guides.append(("v", float(best_target_x)))
            if self._align_snap_enabled and best_dx is not None:
                if move_left and abs(best_target_x - left) <= thresh:
                    x += best_dx
                    w -= best_dx
                elif move_right and abs(best_target_x - right) <= thresh:
                    w += best_dx
                else:
                    x += best_dx

        best_dy = None
        best_target_y = None
        candidates_y = []
        if move_top:
            candidates_y.append(top)
        if move_bottom:
            candidates_y.append(bottom)
        candidates_y.append(cy)
        for cval in candidates_y:
            for ty in pts["y"]:
                d = ty - cval
                if abs(d) <= thresh and (best_dy is None or abs(d) < abs(best_dy)):
                    best_dy = d
                    best_target_y = ty
        if best_target_y is not None:
            guides.append(("h", float(best_target_y)))
            if self._align_snap_enabled and best_dy is not None:
                if move_top and abs(best_target_y - top) <= thresh:
                    y += best_dy
                    h -= best_dy
                elif move_bottom and abs(best_target_y - bottom) <= thresh:
                    h += best_dy
                else:
                    y += best_dy

        self._active_guides = guides
        w = max(float(self._min_w), float(w))
        h = max(float(self._min_h), float(h))
        return x, y, w, h

    def _apply_rect_to_state(self, name: str, rect: list[float], w0: float, h0: float):
        x, y, w, h = rect
        if name == "title_image":
            cx = x + w / 2.0
            cy = y + h / 2.0
            if self._title_pixmap and not self._title_pixmap.isNull():
                rw, rh = float(self._title_pixmap.width()), float(self._title_pixmap.height())
            else:
                rw, rh = 220.0, 100.0
            new_scale = max(0.1, min(5.0, float(w) / max(1.0, rw)))
            self._state["menu_title_image_pos"] = [int(round(cx)), int(round(cy))]
            self._state["menu_title_image_scale"] = float(new_scale)
            return

        if name == "title_text":
            old_scale = float(self._state.get("menu_title_scale", 1.0) or 1.0)
            # scale by height ratio (more stable for fonts)
            ratio = float(h) / max(1.0, float(h0))
            new_scale = max(0.1, min(5.0, old_scale * ratio))
            self._state["menu_title_pos"] = [int(round(x)), int(round(y))]
            self._state["menu_title_scale"] = float(new_scale)
            return

        if name == "options":
            old_scale = float(self._state.get("menu_option_scale", 1.0) or 1.0)
            ratio = float(h) / max(1.0, float(h0))
            new_scale = max(0.5, min(5.0, old_scale * ratio))
            self._state["menu_option_pos"] = [int(round(x)), int(round(y))]
            self._state["menu_option_scale"] = float(new_scale)
            return

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        scale, ox, oy, view_w, view_h = self._transform()
        bg_rect = QRect(ox, oy, view_w, view_h)
        painter.fillRect(self.rect(), QColor(18, 20, 24))
        painter.fillRect(bg_rect, QColor(24, 24, 28))
        if self._bg_pixmap:
            scaled = self._bg_pixmap.scaled(view_w, view_h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(bg_rect, scaled, scaled.rect())

        overlay_alpha = int(self._state.get("menu_overlay_alpha", 0) or 0)
        if overlay_alpha > 0:
            painter.fillRect(bg_rect, QColor(0, 0, 0, max(0, min(255, overlay_alpha))))

        # helpers
        def draw_rect_outline(name: str, rect_vals: list[float], color: QColor):
            wx, wy, ww, wh = self.base_rect_to_widget(rect_vals)
            painter.setPen(QPen(color, 2 if name == self._selected else 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(wx, wy, ww, wh)
            if name == self._selected:
                painter.setBrush(QColor(255, 255, 255, 220))
                painter.setPen(Qt.PenStyle.NoPen)
                for _, (hx, hy, hw, hh) in self._handles_for_rect(wx, wy, ww, wh).items():
                    painter.drawRect(hx, hy, hw, hh)

        # draw option area preview
        opt_rect = self._option_rect()
        wx, wy, ww, wh = self.base_rect_to_widget(opt_rect)
        painter.setBrush(QColor(255, 255, 255, 18))
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1))
        painter.drawRoundedRect(wx, wy, ww, wh, 10, 10)

        # title image
        img_rect = self._title_image_rect()
        if self._title_pixmap:
            wx, wy, ww, wh = self.base_rect_to_widget(img_rect)
            painter.drawPixmap(wx, wy, ww, wh, self._title_pixmap)
        else:
            wx, wy, ww, wh = self.base_rect_to_widget(img_rect)
            painter.setPen(QPen(QColor(0, 160, 130, 200), 2))
            painter.setBrush(QColor(0, 200, 160, 90))
            painter.drawRoundedRect(wx, wy, ww, wh, 10, 10)

        # title text
        title_text = str(self._state.get("menu_title") or "标题")
        title_color = self._state.get("menu_title_color", [240, 240, 255])
        title_scale = float(self._state.get("menu_title_scale", 1.0) or 1.0)
        trect = self._title_text_rect()
        tx, ty, _, _ = trect
        twx, twy = self.base_to_widget(tx, ty)
        font = QFont("Arial")
        font.setPixelSize(max(10, int(36 * title_scale * scale)))
        painter.setFont(font)
        try:
            r, g, b = (title_color if isinstance(title_color, (list, tuple)) else [240, 240, 255])
            painter.setPen(QColor(int(r), int(g), int(b)))
        except Exception:
            painter.setPen(QColor(240, 240, 255))
        painter.drawText(twx, twy + max(12, int(36 * title_scale * scale * 0.8)), title_text)

        # menu buttons (WYSIWYG)
        buttons = _normalize_menu_buttons(self._state.get("menu_buttons"))
        start_x, start_y = self._state.get("menu_option_pos") or [80, 140]
        try:
            spacing = int(self._state.get("menu_option_spacing", 10) or 10)
        except Exception:
            spacing = 10
        try:
            zoom = float(self._state.get("menu_option_selected_zoom", 1.08) or 1.08)
        except Exception:
            zoom = 1.08
        zoom = max(1.0, min(1.5, float(zoom)))
        try:
            selected_idx = int(self._state.get("menu_preview_selected", 0) or 0)
        except Exception:
            selected_idx = 0
        selected_idx = max(0, min(len(buttons) - 1, selected_idx)) if buttons else 0
        option_color = self._state.get("menu_option_color", [255, 255, 255])
        option_hover_color = self._state.get("menu_option_hover_color", option_color)
        try:
            or_, og_, ob_ = (option_color if isinstance(option_color, (list, tuple)) else [255, 255, 255])
            base_col = QColor(int(or_), int(og_), int(ob_))
        except Exception:
            base_col = QColor(255, 255, 255)

        try:
            hr, hg, hb = (option_hover_color if isinstance(option_hover_color, (list, tuple)) else option_color)
            hover_col = QColor(int(hr), int(hg), int(hb))
        except Exception:
            hover_col = base_col

        option_scale = float(self._state.get("menu_option_scale", 1.0) or 1.0)

        # Precompute stable layout using UNZOOMED sizes so selection zoom doesn't move others.
        layout_items: list[dict[str, Any]] = []
        cur_y = float(start_y)
        for idx, it in enumerate(buttons):
            sel = idx == selected_idx
            style = str(it.get("style") or "text")
            label = str(it.get("label") or "")
            action = str(it.get("action") or "")
            if style == "image":
                px = self._button_pixmaps.get(action)
                if px is not None and not px.isNull():
                    try:
                        item_scale = float(it.get("image_scale", 1.0) or 1.0)
                    except Exception:
                        item_scale = 1.0
                    item_scale = max(0.1, min(5.0, float(item_scale)))
                    base_scale = option_scale * item_scale
                    base_w = max(1, int(px.width() * base_scale))
                    base_h = max(1, int(px.height() * base_scale))
                    layout_items.append({
                        "idx": idx,
                        "style": "image",
                        "label": label,
                        "action": action,
                        "px": px,
                        "x": float(start_x),
                        "y": float(cur_y),
                        "w": float(base_w),
                        "h": float(base_h),
                    })
                    cur_y += float(base_h) + float(spacing)
                else:
                    # fallback placeholder
                    ph_base = max(10, int(22 * option_scale))
                    pw_base = max(60, int(140 * option_scale))
                    layout_items.append({
                        "idx": idx,
                        "style": "placeholder",
                        "label": label,
                        "action": action,
                        "x": float(start_x),
                        "y": float(cur_y),
                        "w": float(pw_base),
                        "h": float(ph_base + 10),
                    })
                    cur_y += float(ph_base + 10) + float(spacing)
            else:
                # text slot height based on base pixels
                font = QFont("Arial")
                font.setPixelSize(max(8, int(20 * option_scale)))
                fm = QFontMetrics(font)
                line_h = max(10, int(fm.height()))
                layout_items.append({
                    "idx": idx,
                    "style": "text",
                    "label": label,
                    "action": action,
                    "x": float(start_x),
                    "y": float(cur_y),
                    "w": 0.0,
                    "h": float(line_h),
                })
                cur_y += float(line_h) + float(spacing)

        # draw layout items
        if bool(self._state.get("menu_option_indicator", False)) and layout_items:
            sel_item = None
            for it in layout_items:
                if int(it.get("idx", -1)) == int(selected_idx):
                    sel_item = it
                    break
            if sel_item is not None:
                bx = float(sel_item.get("x", float(start_x)))
                by = float(sel_item.get("y", float(start_y)))
                bh = float(sel_item.get("h", 0.0))
                cy = by + bh / 2.0
                gap = 12.0 * max(0.5, option_scale)

                # If user provided an indicator image, render it; else fallback triangle.
                ind_px = self._indicator_pixmap
                ind_scale = 1.0
                try:
                    ind_scale = float(self._state.get("menu_option_indicator_image_scale", 1.0) or 1.0)
                except Exception:
                    ind_scale = 1.0
                ind_scale = max(0.1, min(5.0, float(ind_scale)))

                if ind_px is not None and not ind_px.isNull() and ind_px.height() > 0 and ind_px.width() > 0:
                    final_scale = max(0.1, float(option_scale) * float(ind_scale))
                    w0 = float(ind_px.width()) * final_scale
                    h0 = float(ind_px.height()) * final_scale
                    dx = bx - gap - w0
                    dy = cy - h0 / 2.0
                    wx, wy = self.base_to_widget(dx, dy)
                    painter.drawPixmap(wx, wy, int(w0 * scale), int(h0 * scale), ind_px)
                else:
                    aw = 14.0 * max(0.5, option_scale)
                    ah = 18.0 * max(0.5, option_scale)
                    tip_x = bx - gap
                    base_x = tip_x - aw
                    p1 = self.base_to_widget(tip_x, cy)
                    p2 = self.base_to_widget(base_x, cy - ah / 2.0)
                    p3 = self.base_to_widget(base_x, cy + ah / 2.0)
                    path = QPainterPath()
                    path.moveTo(p1[0], p1[1])
                    path.lineTo(p2[0], p2[1])
                    path.lineTo(p3[0], p3[1])
                    path.closeSubpath()
                    painter.setBrush(QColor(255, 255, 255, 220))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawPath(path)

        for it in layout_items:
            idx = int(it.get("idx", 0))
            sel = idx == selected_idx
            st = str(it.get("style") or "text")
            bx = float(it.get("x", 0.0))
            by = float(it.get("y", 0.0))
            bw = float(it.get("w", 0.0))
            bh = float(it.get("h", 0.0))

            if st == "image":
                px = it.get("px")
                if px is not None and not px.isNull():
                    z = zoom if sel else 1.0
                    w2 = max(1.0, bw * float(z))
                    h2 = max(1.0, bh * float(z))
                    dx = bx - (w2 - bw) / 2.0
                    dy = by - (h2 - bh) / 2.0
                    wx, wy = self.base_to_widget(dx, dy)
                    painter.drawPixmap(wx, wy, int(w2 * scale), int(h2 * scale), px)
                continue

            if st == "placeholder":
                wx, wy = self.base_to_widget(bx, by)
                painter.setBrush(QColor(0, 180, 255, 50 if sel else 30))
                painter.setPen(QPen(QColor(0, 180, 255, 120), 1))
                painter.drawRoundedRect(wx, wy, int(bw * scale), int(bh * scale), 8, 8)
                continue

            # text
            font = QFont("Arial")
            font.setPixelSize(max(8, int(20 * option_scale * scale)))
            painter.setFont(font)
            active = hover_col if sel else base_col
            col = active if sel else QColor(int(active.red() * 0.75), int(active.green() * 0.75), int(active.blue() * 0.75))
            painter.setPen(col)
            wx, wy = self.base_to_widget(bx, by)
            painter.drawText(wx, wy + max(10, int(18 * option_scale * scale)), str(it.get("label") or ""))

        # outlines
        draw_rect_outline("options", opt_rect, QColor(255, 255, 255, 80) if self._hovered == "options" else QColor(255, 255, 255, 60))
        draw_rect_outline("title_image", img_rect, QColor(140, 255, 170, 140) if self._hovered == "title_image" else QColor(140, 255, 170, 90))
        draw_rect_outline("title_text", trect, QColor(255, 200, 120, 140) if self._hovered == "title_text" else QColor(255, 200, 120, 90))

        # alignment guides
        if self._align_guides_enabled and self._active_guides:
            painter.setPen(QPen(QColor(255, 120, 220, 200), 1))
            for kind, pos in self._active_guides:
                if kind == "v":
                    vx, _ = self.base_to_widget(pos, 0)
                    painter.drawLine(vx, 0, vx, self.height())
                elif kind == "h":
                    _, vy = self.base_to_widget(0, pos)
                    painter.drawLine(0, vy, self.width(), vy)


class MainMenuDesigner(QDialog):
    def __init__(self, project_dir: Optional[Path] = None, project_manager=None, base_resolution: tuple[int, int] | None = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project_manager = project_manager
        self.project_dir = Path(project_dir) if project_dir else (Path(project_manager.project_dir) if project_manager and project_manager.project_dir else None)
        game_cfg = (project_manager.project_data.get("game_config", {}) if project_manager else {}) or {}
        self._menus: list[dict[str, Any]] = self._load_main_menus(game_cfg)
        self._active_menu_tab: int = 0
        data = self._menus[self._active_menu_tab]
        self.base_resolution = base_resolution or (int(game_cfg.get("window_width", 800)), int(game_cfg.get("window_height", 600)))

        self.setWindowTitle("主菜单设计器")
        self.resize(980, 720)
        self.setMinimumWidth(760)
        self.setMaximumSize(1200, 900)

        self._updating = False
        self._suppress_dirty = False
        self._dirty = False
        self._initialized = False

        self._button_image_to_index: dict[QLineEdit, int] = {}
        self._last_button_image_paths: list[str] = [""] * 5

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # main menu tabs: 主菜单1/2/3
        self.menu_tabs = QTabBar(self)
        self.menu_tabs.addTab("主菜单1")
        self.menu_tabs.addTab("主菜单2")
        self.menu_tabs.addTab("主菜单3")
        self.menu_tabs.setExpanding(False)
        self.menu_tabs.setMovable(False)
        self.menu_tabs.setCurrentIndex(self._active_menu_tab)
        self.menu_tabs.currentChanged.connect(self._on_menu_tab_changed)
        layout.addWidget(self.menu_tabs)

        top_row = QHBoxLayout()

        # Left pane (scrollable + collapsible)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # interaction toggles (same as UI designer)
        self.chk_grid_snap = QCheckBox("网格吸附")
        self.chk_align_guides = QCheckBox("对齐线")
        self.chk_align_snap = QCheckBox("对齐吸附")
        self.chk_grid_snap.setChecked(False)
        self.chk_align_guides.setChecked(True)
        self.chk_align_snap.setChecked(True)
        self.grid_size = QSpinBox()
        self.grid_size.setRange(1, 200)
        self.grid_size.setValue(10)

        # --- Section: 辅助 ---
        sec_help = _CollapsibleSection("辅助（吸附/对齐）")
        help_form = QFormLayout()
        help_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        opt_row = QWidget()
        opt_layout = QHBoxLayout(opt_row)
        opt_layout.setContentsMargins(0, 0, 0, 0)
        opt_layout.addWidget(self.chk_grid_snap)
        opt_layout.addWidget(QLabel("网格大小"))
        opt_layout.addWidget(self.grid_size)
        opt_layout.addSpacing(12)
        opt_layout.addWidget(self.chk_align_guides)
        opt_layout.addWidget(self.chk_align_snap)
        opt_layout.addStretch(1)
        help_form.addRow(opt_row)

        self.preview_selected = QSpinBox()
        self.preview_selected.setRange(1, 5)
        self.preview_selected.setValue(1)
        self.preview_selected.setToolTip("仅影响设计器预览的“当前选中按钮”效果")
        help_form.addRow("预览选中(1-5)", self.preview_selected)
        sec_help.setContentLayout(help_form)
        left_layout.addWidget(sec_help)

        # --- Section: 标题 ---
        sec_title = _CollapsibleSection("标题")
        title_form = QFormLayout()
        title_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.title_edit = QLineEdit(data.get("menu_title", ""))
        title_form.addRow("标题文字", self.title_edit)

        pos_row = QHBoxLayout()
        self.title_x = QSpinBox(); self.title_x.setRange(0, 2000); self.title_x.setValue(int((data.get("menu_title_pos") or [60, 60])[0]))
        self.title_y = QSpinBox(); self.title_y.setRange(0, 2000); self.title_y.setValue(int((data.get("menu_title_pos") or [60, 60])[1]))
        pos_row.addWidget(QLabel("X")); pos_row.addWidget(self.title_x); pos_row.addWidget(QLabel("Y")); pos_row.addWidget(self.title_y)
        title_form.addRow("标题位置", pos_row)

        self.title_scale = QDoubleSpinBox(); self.title_scale.setRange(0.1, 5.0); self.title_scale.setSingleStep(0.1); self.title_scale.setDecimals(2); self.title_scale.setValue(float(data.get("menu_title_scale", 1.0) or 1.0))
        title_form.addRow("标题缩放", self.title_scale)

        self.title_color_edit = QLineEdit(self._color_to_hex(data.get("menu_title_color", [240, 240, 255])))
        color_row = QWidget(); color_layout = QHBoxLayout(color_row); color_layout.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton("选色"); btn.clicked.connect(lambda: self._pick_color(self.title_color_edit))
        color_layout.addWidget(self.title_color_edit); color_layout.addWidget(btn)
        title_form.addRow("标题颜色", color_row)

        self.title_img_edit = QLineEdit(data.get("menu_title_image", ""))
        title_form.addRow("标题图片", self._make_file_row(self.title_img_edit, self._pick_title_image, True))

        pos_img_row = QHBoxLayout()
        self.title_img_x = QSpinBox(); self.title_img_x.setRange(0, 2000); self.title_img_x.setValue(int((data.get("menu_title_image_pos") or [400, 80])[0]))
        self.title_img_y = QSpinBox(); self.title_img_y.setRange(0, 2000); self.title_img_y.setValue(int((data.get("menu_title_image_pos") or [400, 80])[1]))
        pos_img_row.addWidget(QLabel("X")); pos_img_row.addWidget(self.title_img_x); pos_img_row.addWidget(QLabel("Y")); pos_img_row.addWidget(self.title_img_y)
        title_form.addRow("标题图片中心", pos_img_row)

        self.title_img_scale = QDoubleSpinBox(); self.title_img_scale.setRange(0.1, 5.0); self.title_img_scale.setSingleStep(0.1); self.title_img_scale.setDecimals(2); self.title_img_scale.setValue(float(data.get("menu_title_image_scale", 1.0) or 1.0))
        title_form.addRow("标题图缩放", self.title_img_scale)

        sec_title.setContentLayout(title_form)
        left_layout.addWidget(sec_title)

        # --- Section: 按钮组布局 ---
        sec_btn_group = _CollapsibleSection("按钮组")
        btn_form = QFormLayout()
        btn_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        pos_opt_row = QHBoxLayout()
        self.option_x = QSpinBox(); self.option_x.setRange(0, 2000); self.option_x.setValue(int((data.get("menu_option_pos") or [80, 140])[0]))
        self.option_y = QSpinBox(); self.option_y.setRange(0, 2000); self.option_y.setValue(int((data.get("menu_option_pos") or [80, 140])[1]))
        pos_opt_row.addWidget(QLabel("X")); pos_opt_row.addWidget(self.option_x); pos_opt_row.addWidget(QLabel("Y")); pos_opt_row.addWidget(self.option_y)
        btn_form.addRow("起始位置", pos_opt_row)

        self.option_scale = QDoubleSpinBox(); self.option_scale.setRange(0.5, 5.0); self.option_scale.setSingleStep(0.1); self.option_scale.setDecimals(2); self.option_scale.setValue(float(data.get("menu_option_scale", 1.0) or 1.0))
        self.option_scale.setToolTip("拖拽预览中“选项区域”可缩放；Shift 等比缩放")
        btn_form.addRow("整体缩放", self.option_scale)

        self.option_spacing = QSpinBox(); self.option_spacing.setRange(0, 200); self.option_spacing.setValue(int(data.get("menu_option_spacing", 10) or 10))
        btn_form.addRow("按钮间距", self.option_spacing)

        self.option_selected_zoom = QDoubleSpinBox(); self.option_selected_zoom.setRange(1.0, 1.5); self.option_selected_zoom.setSingleStep(0.02); self.option_selected_zoom.setDecimals(2)
        self.option_selected_zoom.setValue(float(data.get("menu_option_selected_zoom", 1.08) or 1.08))
        self.option_selected_zoom.setToolTip("仅对图片按钮生效：选中时轻微放大")
        btn_form.addRow("图片选中放大", self.option_selected_zoom)

        self.option_indicator_chk = QCheckBox("选中箭头指示")
        self.option_indicator_chk.setChecked(bool(data.get("menu_option_indicator", False)))
        self.option_indicator_chk.setToolTip("启用后：选中按钮左侧显示小箭头指示")
        btn_form.addRow("", self.option_indicator_chk)

        self.option_indicator_img_edit = QLineEdit(str(data.get("menu_option_indicator_image", "")))
        btn_form.addRow("箭头图片", self._make_file_row(self.option_indicator_img_edit, self._pick_indicator_image, True))

        self.option_indicator_img_scale = QDoubleSpinBox(); self.option_indicator_img_scale.setRange(0.1, 5.0); self.option_indicator_img_scale.setSingleStep(0.05); self.option_indicator_img_scale.setDecimals(2)
        self.option_indicator_img_scale.setValue(float(data.get("menu_option_indicator_image_scale", 1.0) or 1.0))
        self.option_indicator_img_scale.setToolTip("箭头图片缩放（最终尺寸=图片尺寸×整体缩放×该缩放）")
        btn_form.addRow("箭头缩放", self.option_indicator_img_scale)

        self.option_color_edit = QLineEdit(self._color_to_hex(data.get("menu_option_color", [255, 255, 255])))
        opt_color_row = QWidget(); opt_color_layout = QHBoxLayout(opt_color_row); opt_color_layout.setContentsMargins(0, 0, 0, 0)
        btn_opt = QPushButton("选色"); btn_opt.clicked.connect(lambda: self._pick_color(self.option_color_edit))
        try:
            btn_opt.setCursor(Qt.CursorShape.PointingHandCursor)
        except Exception:
            pass
        opt_color_layout.addWidget(self.option_color_edit); opt_color_layout.addWidget(btn_opt)
        btn_form.addRow("文字颜色", opt_color_row)

        self.option_hover_color_edit = QLineEdit(
            self._color_to_hex(data.get("menu_option_hover_color", data.get("menu_option_color", [255, 255, 255])))
        )
        opt_hover_row = QWidget(); opt_hover_layout = QHBoxLayout(opt_hover_row); opt_hover_layout.setContentsMargins(0, 0, 0, 0)
        btn_opt_hover = QPushButton("选色"); btn_opt_hover.clicked.connect(lambda: self._pick_color(self.option_hover_color_edit))
        try:
            btn_opt_hover.setCursor(Qt.CursorShape.PointingHandCursor)
        except Exception:
            pass
        opt_hover_layout.addWidget(self.option_hover_color_edit); opt_hover_layout.addWidget(btn_opt_hover)
        btn_form.addRow("悬停颜色", opt_hover_row)

        sec_btn_group.setContentLayout(btn_form)
        left_layout.addWidget(sec_btn_group)

        # --- Section: 五个按钮样式 ---
        self._button_mode: list[QComboBox] = []
        self._button_text: list[QLineEdit] = []
        self._button_image: list[QLineEdit] = []
        self._button_image_scale: list[QDoubleSpinBox] = []

        buttons_cfg = _normalize_menu_buttons(data.get("menu_buttons"))
        for idx, it in enumerate(buttons_cfg):
            title = f"按钮 {idx + 1}：{it.get('label') or ''}"
            sec = _CollapsibleSection(title)
            f = QFormLayout()
            f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

            mode = QComboBox()
            mode.addItems(["文字", "图片"])
            mode.setCurrentIndex(1 if it.get("style") == "image" else 0)
            f.addRow("样式", mode)

            text = QLineEdit(str(it.get("label") or ""))
            f.addRow("文字", text)

            img = QLineEdit(str(it.get("image") or ""))
            # QPushButton.clicked emits a bool; swallow it so we always pass the QLineEdit.
            f.addRow("图片", self._make_file_row(img, lambda _checked=False, e=img: self._pick_button_image(e), True))

            img_scale = QDoubleSpinBox(); img_scale.setRange(0.1, 5.0); img_scale.setSingleStep(0.05); img_scale.setDecimals(2)
            img_scale.setValue(float(it.get("image_scale", 1.0) or 1.0))
            f.addRow("图片缩放", img_scale)

            sec.setContentLayout(f)
            left_layout.addWidget(sec)

            self._button_mode.append(mode)
            self._button_text.append(text)
            self._button_image.append(img)
            self._button_image_scale.append(img_scale)
            self._button_image_to_index[img] = idx
            self._last_button_image_paths[idx] = img.text().strip()

            def _apply_enabled(m: QComboBox, t: QLineEdit, i: QLineEdit, s: QDoubleSpinBox):
                is_img = m.currentIndex() == 1
                t.setEnabled(not is_img)
                i.setEnabled(is_img)
                s.setEnabled(is_img)

            _apply_enabled(mode, text, img, img_scale)
            mode.currentIndexChanged.connect(lambda _=0, m=mode, t=text, i=img, s=img_scale: (_apply_enabled(m, t, i, s), self._update_preview()))

            # If user directly edits image path: auto toggle mode and set a sensible default scale once.
            img.editingFinished.connect(lambda e=img: self._on_button_image_edited(e))

        # --- Section: 媒体 ---
        sec_media = _CollapsibleSection("媒体")
        media_form = QFormLayout()
        media_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.bg_edit = QLineEdit(data.get("menu_background", ""))
        media_form.addRow("背景图", self._make_file_row(self.bg_edit, self._pick_bg, True))

        self.video_edit = QLineEdit(data.get("menu_video", ""))
        media_form.addRow("背景视频", self._make_file_row(self.video_edit, self._pick_video, True))

        self.video_loop_chk = QCheckBox("视频循环播放")
        self.video_loop_chk.setChecked(bool(data.get("menu_video_loop", False)))
        media_form.addRow("", self.video_loop_chk)

        self.bgm_edit = QLineEdit(data.get("menu_bgm", ""))
        media_form.addRow("BGM", self._make_file_row(self.bgm_edit, self._pick_bgm, True))

        self.bgm_loop_chk = QCheckBox("BGM循环播放")
        self.bgm_loop_chk.setChecked(bool(data.get("menu_bgm_loop", True)))
        media_form.addRow("", self.bgm_loop_chk)

        sec_media.setContentLayout(media_form)
        left_layout.addWidget(sec_media)

        # --- Section: 其他 ---
        sec_other = _CollapsibleSection("其他")
        other_form = QFormLayout()
        other_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.overlay_alpha = QSpinBox()
        self.overlay_alpha.setRange(0, 255)
        self.overlay_alpha.setValue(int(data.get("menu_overlay_alpha", 0)))
        other_form.addRow("遮罩透明度 (0-255)", self.overlay_alpha)

        self.trigger_condition_edit = QLineEdit(str(data.get("trigger_condition", "") or ""))
        self.trigger_condition_edit.setPlaceholderText("留空=默认主菜单；示例：flag==1 and love>=10")
        self.trigger_condition_edit.setToolTip("触发条件：参考条件节点的变量表达式；成立则应用该主菜单样式。多个满足时按主菜单1→2→3优先级。")
        other_form.addRow("触发条件", self.trigger_condition_edit)

        self.reset_globals_chk = QCheckBox("开始游戏时重置全局变量")
        self.reset_globals_chk.setChecked(bool(data.get("reset_globals_on_start", True)))
        self.reset_globals_chk.setToolTip("关闭后：从主菜单点击【开始游戏】将保留当前全局变量值。")
        other_form.addRow("", self.reset_globals_chk)

        self.save_slots_spin = QSpinBox()
        self.save_slots_spin.setRange(1, 200)
        self.save_slots_spin.setValue(int(data.get("save_slots", 5) or 5))
        self.save_slots_spin.setToolTip("游戏存档栏数量；超过10个时将按10个/页分页，数字键0-9选择")
        other_form.addRow("存档栏数量", self.save_slots_spin)

        self.enable_autosave_chk = QCheckBox("ESC 返回主菜单时自动存档到【自动存档】")
        self.enable_autosave_chk.setChecked(bool(data.get("enable_autosave_on_menu", True)))
        other_form.addRow("", self.enable_autosave_chk)

        self.help_hotkey_edit = QLineEdit(str(data.get("help_hotkey", "F1") or "F1"))
        self.help_hotkey_edit.setToolTip("帮助菜单快捷键，如：F1 / F2 / H 等")
        other_form.addRow("帮助菜单快捷键", self.help_hotkey_edit)

        self.help_right_click_chk = QCheckBox("右键调出帮助菜单")
        self.help_right_click_chk.setChecked(bool(data.get("help_right_click", True)))
        other_form.addRow("", self.help_right_click_chk)

        sec_other.setContentLayout(other_form)
        left_layout.addWidget(sec_other)

        left_layout.addStretch(1)

        left_scroll = QScrollArea(self)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setWidget(left_widget)

        # Right preview (fixed aspect, not stretched)
        self.preview = InteractiveMenuPreview(self.project_dir, self.base_resolution, self)
        self.preview.layoutEdited.connect(self._on_preview_edited)
        self.preview.set_align_guides(self.chk_align_guides.isChecked(), snap=self.chk_align_snap.isChecked())
        self.preview.set_grid_snap(self.chk_grid_snap.isChecked(), self.grid_size.value())
        preview_wrap = QVBoxLayout()
        preview_wrap.addWidget(QLabel("主菜单预览（比例固定；拖拽/四角缩放）", self))
        self.preview_container = AspectRatioContainer(self.preview, self.base_resolution, self)
        preview_wrap.addWidget(self.preview_container)

        top_row.addWidget(left_scroll, 1)
        top_row.addLayout(preview_wrap, 2)
        layout.addLayout(top_row, 1)

        hint = QLabel("说明：背景/视频/BGM/标题图会复制到工程目录 (images/videos/audios)。遮罩透明度 0 不加深，255 全黑；颜色用 #RRGGBB。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_cancel = QPushButton("取消")
        btn_save.clicked.connect(self._save)
        btn_cancel.clicked.connect(self.reject)
        try:
            btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        except Exception:
            pass
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self._wire_preview()
        self._update_preview()
        self._initialized = True

    def _load_main_menus(self, game_cfg: dict[str, Any]) -> list[dict[str, Any]]:
        """Load 3 independent main menu configs.

        Backward compatible:
        - If game_cfg.main_menus exists: use it.
        - Else: build 主菜单1 from legacy flat keys (menu_*/save/help), and 主菜单2/3 as empty defaults.
        """

        game_cfg = game_cfg or {}
        raw = game_cfg.get("main_menus")
        if isinstance(raw, list) and raw:
            menus: list[dict[str, Any]] = []
            for it in raw[:3]:
                menus.append(it if isinstance(it, dict) else {})
            while len(menus) < 3:
                menus.append({})
            return menus

        menu0: dict[str, Any] = {}
        for k, v in (game_cfg or {}).items():
            if isinstance(k, str) and (k.startswith("menu_") or k in {"save_slots", "enable_autosave_on_menu", "help_hotkey", "help_right_click", "reset_globals_on_start"}):
                menu0[k] = v
        menu0.setdefault("trigger_condition", "")
        menu0.setdefault("reset_globals_on_start", True)
        return [menu0, {"trigger_condition": "", "reset_globals_on_start": True}, {"trigger_condition": "", "reset_globals_on_start": True}]

    def _on_menu_tab_changed(self, new_index: int):
        if not self._initialized:
            self._active_menu_tab = max(0, min(2, int(new_index)))
            return
        if self._updating:
            return

        old = self._active_menu_tab
        try:
            old = int(old)
        except Exception:
            old = 0
        old = max(0, min(2, old))

        try:
            new_index = int(new_index)
        except Exception:
            new_index = 0
        new_index = max(0, min(2, new_index))
        if new_index == old:
            return

        # save current tab state
        self._menus[old] = self._collect_cfg()
        self._active_menu_tab = new_index

        # load new tab state
        self._apply_cfg_to_widgets(self._menus[new_index] or {})

    def _apply_cfg_to_widgets(self, data: dict[str, Any]):
        data = data or {}
        self._updating = True
        self._suppress_dirty = True
        try:
            # title
            self.title_edit.setText(str(data.get("menu_title", "") or ""))
            tp = data.get("menu_title_pos") or [60, 60]
            try:
                self.title_x.setValue(int(tp[0] if isinstance(tp, (list, tuple)) and len(tp) >= 2 else 60))
                self.title_y.setValue(int(tp[1] if isinstance(tp, (list, tuple)) and len(tp) >= 2 else 60))
            except Exception:
                self.title_x.setValue(60)
                self.title_y.setValue(60)
            try:
                self.title_scale.setValue(float(data.get("menu_title_scale", 1.0) or 1.0))
            except Exception:
                self.title_scale.setValue(1.0)
            self.title_color_edit.setText(self._color_to_hex(data.get("menu_title_color", [240, 240, 255])))
            self.title_img_edit.setText(str(data.get("menu_title_image", "") or ""))
            ip = data.get("menu_title_image_pos") or [400, 80]
            try:
                self.title_img_x.setValue(int(ip[0] if isinstance(ip, (list, tuple)) and len(ip) >= 2 else 400))
                self.title_img_y.setValue(int(ip[1] if isinstance(ip, (list, tuple)) and len(ip) >= 2 else 80))
            except Exception:
                self.title_img_x.setValue(400)
                self.title_img_y.setValue(80)
            try:
                self.title_img_scale.setValue(float(data.get("menu_title_image_scale", 1.0) or 1.0))
            except Exception:
                self.title_img_scale.setValue(1.0)

            # options/buttons layout
            op = data.get("menu_option_pos") or [80, 140]
            try:
                self.option_x.setValue(int(op[0] if isinstance(op, (list, tuple)) and len(op) >= 2 else 80))
                self.option_y.setValue(int(op[1] if isinstance(op, (list, tuple)) and len(op) >= 2 else 140))
            except Exception:
                self.option_x.setValue(80)
                self.option_y.setValue(140)
            try:
                self.option_scale.setValue(float(data.get("menu_option_scale", 1.0) or 1.0))
            except Exception:
                self.option_scale.setValue(1.0)
            try:
                self.option_spacing.setValue(int(data.get("menu_option_spacing", 10) or 10))
            except Exception:
                self.option_spacing.setValue(10)
            try:
                self.option_selected_zoom.setValue(float(data.get("menu_option_selected_zoom", 1.08) or 1.08))
            except Exception:
                self.option_selected_zoom.setValue(1.08)
            self.option_indicator_chk.setChecked(bool(data.get("menu_option_indicator", False)))
            self.option_indicator_img_edit.setText(str(data.get("menu_option_indicator_image", "") or ""))
            try:
                self.option_indicator_img_scale.setValue(float(data.get("menu_option_indicator_image_scale", 1.0) or 1.0))
            except Exception:
                self.option_indicator_img_scale.setValue(1.0)

            self.option_color_edit.setText(self._color_to_hex(data.get("menu_option_color", [255, 255, 255])))
            self.option_hover_color_edit.setText(self._color_to_hex(data.get("menu_option_hover_color", data.get("menu_option_color", [255, 255, 255]))))

            # per-button style
            buttons_cfg = _normalize_menu_buttons(data.get("menu_buttons"))
            for idx, it in enumerate(buttons_cfg):
                is_img = (it.get("style") == "image")
                self._button_mode[idx].setCurrentIndex(1 if is_img else 0)
                self._button_text[idx].setText(str(it.get("label") or ""))
                self._button_image[idx].setText(str(it.get("image") or ""))
                try:
                    self._button_image_scale[idx].setValue(float(it.get("image_scale", 1.0) or 1.0))
                except Exception:
                    self._button_image_scale[idx].setValue(1.0)
                self._button_text[idx].setEnabled(not is_img)
                self._button_image[idx].setEnabled(is_img)
                self._button_image_scale[idx].setEnabled(is_img)
                self._last_button_image_paths[idx] = self._button_image[idx].text().strip()

            # media
            self.bg_edit.setText(str(data.get("menu_background", "") or ""))
            self.video_edit.setText(str(data.get("menu_video", "") or ""))
            self.video_loop_chk.setChecked(bool(data.get("menu_video_loop", False)))
            self.bgm_edit.setText(str(data.get("menu_bgm", "") or ""))
            self.bgm_loop_chk.setChecked(bool(data.get("menu_bgm_loop", True)))

            # other
            try:
                self.overlay_alpha.setValue(int(data.get("menu_overlay_alpha", 0) or 0))
            except Exception:
                self.overlay_alpha.setValue(0)
            try:
                self.save_slots_spin.setValue(int(data.get("save_slots", 5) or 5))
            except Exception:
                self.save_slots_spin.setValue(5)
            self.enable_autosave_chk.setChecked(bool(data.get("enable_autosave_on_menu", True)))
            self.help_hotkey_edit.setText(str(data.get("help_hotkey", "F1") or "F1"))
            self.help_right_click_chk.setChecked(bool(data.get("help_right_click", True)))
            self.trigger_condition_edit.setText(str(data.get("trigger_condition", "") or ""))
            self.reset_globals_chk.setChecked(bool(data.get("reset_globals_on_start", True)))
            try:
                self.preview_selected.setValue(int((data.get("menu_preview_selected", 0) or 0)) + 1)
            except Exception:
                self.preview_selected.setValue(1)

        finally:
            self._updating = False
            # refresh preview without marking dirty
            self._update_preview()
            self._suppress_dirty = False

    def _mark_dirty(self):
        if not self._initialized or self._suppress_dirty:
            return
        self._dirty = True

    # wiring
    def _wire_preview(self):
        for w in [
            self.title_edit,
            self.bg_edit,
            self.video_edit,
            self.title_img_edit,
            self.option_color_edit,
            self.option_hover_color_edit,
            self.title_color_edit,
            self.bgm_edit,
            self.trigger_condition_edit,
            self.help_hotkey_edit,
            self.option_indicator_img_edit,
        ]:
            w.editingFinished.connect(self._update_preview)
        for sp in [
            self.title_x,
            self.title_y,
            self.title_scale,
            self.option_x,
            self.option_y,
            self.option_scale,
            self.option_spacing,
            self.option_selected_zoom,
            self.preview_selected,
            self.overlay_alpha,
            self.title_img_x,
            self.title_img_y,
            self.title_img_scale,
            self.save_slots_spin,
            self.option_indicator_img_scale,
        ]:
            sp.valueChanged.connect(self._update_preview)
        self.video_loop_chk.stateChanged.connect(self._update_preview)
        self.bgm_loop_chk.stateChanged.connect(self._update_preview)
        self.option_indicator_chk.stateChanged.connect(self._update_preview)
        self.reset_globals_chk.stateChanged.connect(self._update_preview)
        self.enable_autosave_chk.stateChanged.connect(self._update_preview)
        self.help_right_click_chk.stateChanged.connect(self._update_preview)
        self.chk_grid_snap.toggled.connect(self._update_preview)
        self.chk_align_guides.toggled.connect(self._update_preview)
        self.chk_align_snap.toggled.connect(self._update_preview)
        self.grid_size.valueChanged.connect(self._update_preview)

        # per-button fields
        for ed in self._button_text + self._button_image:
            ed.editingFinished.connect(self._update_preview)
        for sp in self._button_image_scale:
            sp.valueChanged.connect(self._update_preview)

        self.option_indicator_img_edit.editingFinished.connect(lambda: self._on_indicator_image_edited())

    # helpers
    def _make_file_row(self, edit: QLineEdit, handler, with_clear: bool = False) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit)
        btn = QPushButton("选择"); btn.clicked.connect(handler)
        try:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        except Exception:
            pass
        layout.addWidget(btn)
        if with_clear:
            btn_clear = QPushButton("清除")
            btn_clear.clicked.connect(lambda: edit.setText(""))
            try:
                btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
            except Exception:
                pass
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
        ok = self._write_to_project(show_message=True)
        if ok:
            self.accept()

    def _write_to_project(self, show_message: bool) -> bool:
        if not self.project_manager:
            if show_message:
                QMessageBox.warning(self, "无法保存", "当前没有工程管理器，无法写入工程配置。")
            return False
        # persist current tab first
        try:
            idx = int(self.menu_tabs.currentIndex())
        except Exception:
            idx = 0
        idx = max(0, min(2, idx))
        self._menus[idx] = self._collect_cfg()

        cfg = self.project_manager.project_data.setdefault("game_config", {})
        cfg["main_menus"] = list(self._menus[:3])

        # backward compatibility: mirror 主菜单1 到旧的扁平字段（供旧版本或其他模块读取）
        menu0 = dict(self._menus[0] or {})
        menu0.pop("trigger_condition", None)
        cfg.update(menu0)

        self._dirty = False
        if show_message:
            QMessageBox.information(self, "已保存", "主菜单配置已写入工程，保存工程文件后生效。")
        return True

    def _collect_cfg(self) -> dict[str, Any]:
        buttons: list[dict[str, Any]] = []
        for idx, base in enumerate(_DEFAULT_MENU_BUTTONS):
            action = base["action"]
            mode = self._button_mode[idx].currentIndex()  # 0 text / 1 image
            style = "image" if mode == 1 else "text"
            label = self._button_text[idx].text().strip() or base["label"]
            image = self._button_image[idx].text().strip()
            try:
                img_scale = float(self._button_image_scale[idx].value())
            except Exception:
                img_scale = 1.0
            buttons.append({
                "action": action,
                "label": label,
                "style": style,
                "image": image,
                "image_scale": float(img_scale),
            })

        return {
            "trigger_condition": self.trigger_condition_edit.text().strip(),
            "reset_globals_on_start": bool(self.reset_globals_chk.isChecked()),
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
            "menu_option_hover_color": self._hex_to_rgb(self.option_hover_color_edit.text()),
            "menu_title_image": self.title_img_edit.text(),
            "menu_title_image_pos": [int(self.title_img_x.value()), int(self.title_img_y.value())],
            "menu_title_image_scale": float(self.title_img_scale.value()),
            "menu_option_scale": float(self.option_scale.value()),
            "menu_option_spacing": int(self.option_spacing.value()),
            "menu_option_selected_zoom": float(self.option_selected_zoom.value()),
            "menu_option_indicator": bool(self.option_indicator_chk.isChecked()),
            "menu_option_indicator_image": self.option_indicator_img_edit.text().strip(),
            "menu_option_indicator_image_scale": float(self.option_indicator_img_scale.value()),
            "menu_preview_selected": int(self.preview_selected.value() - 1),
            "menu_buttons": buttons,
            "save_slots": int(self.save_slots_spin.value()),
            "enable_autosave_on_menu": bool(self.enable_autosave_chk.isChecked()),
            "help_hotkey": self.help_hotkey_edit.text().strip() or "F1",
            "help_right_click": bool(self.help_right_click_chk.isChecked()),
        }

    def _update_preview(self):
        self._mark_dirty()
        cfg = self._collect_cfg()
        self.preview.set_grid_snap(self.chk_grid_snap.isChecked(), self.grid_size.value())
        self.preview.set_align_guides(self.chk_align_guides.isChecked(), snap=self.chk_align_snap.isChecked())
        self.preview.update_state(cfg)

    def _on_preview_edited(self, changed: dict):
        # Sync back interactive edits to the controls.
        if self._updating:
            return
        self._updating = True
        self._suppress_dirty = True
        try:
            tp = changed.get("menu_title_pos")
            if isinstance(tp, (list, tuple)) and len(tp) >= 2:
                self.title_x.setValue(int(tp[0]))
                self.title_y.setValue(int(tp[1]))
            ts = changed.get("menu_title_scale")
            if ts is not None:
                try:
                    self.title_scale.setValue(float(ts))
                except Exception:
                    pass

            ip = changed.get("menu_title_image_pos")
            if isinstance(ip, (list, tuple)) and len(ip) >= 2:
                self.title_img_x.setValue(int(ip[0]))
                self.title_img_y.setValue(int(ip[1]))
            iscale = changed.get("menu_title_image_scale")
            if iscale is not None:
                try:
                    self.title_img_scale.setValue(float(iscale))
                except Exception:
                    pass

            op = changed.get("menu_option_pos")
            if isinstance(op, (list, tuple)) and len(op) >= 2:
                self.option_x.setValue(int(op[0]))
                self.option_y.setValue(int(op[1]))
            oscale = changed.get("menu_option_scale")
            if oscale is not None:
                try:
                    self.option_scale.setValue(float(oscale))
                except Exception:
                    pass
        finally:
            self._suppress_dirty = False
            self._updating = False
        self._dirty = True
        self._update_preview()

    def _pick_indicator_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择箭头图片", str(self.project_dir or ""), "图片 (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        prev = self.option_indicator_img_edit.text().strip()
        self.option_indicator_img_edit.setText(self._store_into_project(path, "resources/images"))
        if not prev:
            self._auto_set_indicator_image_scale()
        self._update_preview()

    def _pick_button_image(self, edit: QLineEdit):
        idx = self._button_image_to_index.get(edit)
        path, _ = QFileDialog.getOpenFileName(self, "选择按钮图片", str(self.project_dir or ""), "图片 (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        prev = edit.text().strip()
        edit.setText(self._store_into_project(path, "resources/images"))
        if idx is not None:
            # Switching to image mode makes the binding effective immediately.
            self._button_mode[idx].setCurrentIndex(1)
            # Default scale: make image height ~= one-line text height (20px @ option_scale=1).
            if not prev:
                self._auto_set_button_image_scale(idx)
        self._update_preview()

    def _on_button_image_edited(self, edit: QLineEdit):
        idx = self._button_image_to_index.get(edit)
        if idx is None:
            return
        new_path = edit.text().strip()
        old_path = (self._last_button_image_paths[idx] or "").strip()

        if new_path:
            self._button_mode[idx].setCurrentIndex(1)
            if new_path != old_path:
                self._auto_set_button_image_scale(idx)
        else:
            # If image cleared, fall back to text for safety.
            self._button_mode[idx].setCurrentIndex(0)

        self._last_button_image_paths[idx] = new_path

    def _auto_set_button_image_scale(self, idx: int):
        if idx < 0 or idx >= len(self._button_image):
            return
        rel = self._button_image[idx].text().strip()
        if not rel:
            return
        try:
            p = Path(rel)
            if not p.is_absolute() and self.project_dir:
                p = (self.project_dir / p).resolve()
        except Exception:
            return
        if not p.exists():
            return
        try:
            px = QPixmap(str(p))
        except Exception:
            return
        if px.isNull() or px.height() <= 0:
            return

        target_text_h = 20.0  # matches runtime base font size for menu options
        scale = target_text_h / float(px.height())
        scale = max(0.1, min(5.0, float(scale)))
        # Only set if still at default-ish value (avoid overriding user adjustments).
        try:
            cur = float(self._button_image_scale[idx].value())
        except Exception:
            cur = 1.0
        if abs(cur - 1.0) <= 1e-6:
            self._button_image_scale[idx].setValue(scale)

    def _on_indicator_image_edited(self):
        new_path = self.option_indicator_img_edit.text().strip()
        if new_path:
            self._auto_set_indicator_image_scale()

    def _auto_set_indicator_image_scale(self):
        rel = self.option_indicator_img_edit.text().strip()
        if not rel:
            return
        try:
            p = Path(rel)
            if not p.is_absolute() and self.project_dir:
                p = (self.project_dir / p).resolve()
        except Exception:
            return
        if not p.exists():
            return
        try:
            px = QPixmap(str(p))
        except Exception:
            return
        if px.isNull() or px.height() <= 0:
            return

        target_h = 18.0  # matches runtime default arrow height (@ option_scale=1)
        scale = target_h / float(px.height())
        scale = max(0.1, min(5.0, float(scale)))
        try:
            cur = float(self.option_indicator_img_scale.value())
        except Exception:
            cur = 1.0
        if abs(cur - 1.0) <= 1e-6:
            self.option_indicator_img_scale.setValue(scale)

    def closeEvent(self, event):
        if self._confirm_close():
            event.accept()
        else:
            event.ignore()

    def reject(self):
        if self._confirm_close():
            super().reject()

    def _confirm_close(self) -> bool:
        if not self._dirty:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("未保存")
        box.setText("主菜单配置尚未保存，是否保存后退出？")
        btn_save = box.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
        btn_discard = box.addButton("不保存", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_save)
        box.exec()
        clicked = box.clickedButton()
        if clicked == btn_cancel:
            return False
        if clicked == btn_discard:
            return True
        # save
        ok = self._write_to_project(show_message=False)
        return bool(ok)

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
