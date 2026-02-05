"""Simple UI layout designer for VNEngine text/name/portrait regions.

Enhancements:
- Custom textbox/namebox frame images with alpha.
- Preview sample images for bg/portrait/portrait2.
- Drag to move, corner drag to resize for textbox/namebox/portrait/portrait2.
"""

import json
import shutil
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QRect
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QColorDialog,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .properties_panel import _CollapsibleSection


class AspectRatioContainer(QWidget):
    """Keep a single child at a fixed aspect ratio (letterboxed)."""

    def __init__(self, child: QWidget, aspect_size: tuple[int, int], parent=None):
        super().__init__(parent)
        self._child = child
        self._child.setParent(self)
        self._aspect = (max(1, int(aspect_size[0])), max(1, int(aspect_size[1])))
        self.setMinimumSize(520, 360)

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


class LayoutPreview(QWidget):
    """2D preview for text/name/portrait positions with drag+resize."""

    layoutEdited = pyqtSignal(dict)

    def __init__(self, base_size: tuple[int, int] = (800, 600), path_base: Path | None = None, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(420, 300)
        self._base_size = (max(1, int(base_size[0])), max(1, int(base_size[1])))
        self._path_base = path_base

        self._text_rect = [40, 380, 720, 160]
        self._name_rect = [40, 340, 200, 32]

        self._portrait_rect = [0, 0, 120, 200]
        self._portrait_scale = 1.0

        self._portrait2_rect = [0, 0, 120, 200]
        self._portrait2_scale = 1.0

        self._text_frame_path = ""
        self._text_frame_alpha = 255
        self._name_frame_path = ""
        self._name_frame_alpha = 255
        self._preview_bg_path = ""
        self._preview_portrait_path = ""
        self._preview_portrait2_path = ""

        # in-game HUD button group preview
        self._hud_enabled = False
        self._hud_pos = [20, 20]
        self._hud_spacing = 10
        self._hud_scale = 1.0
        self._hud_selected_zoom = 1.08
        self._hud_orientation = "vertical"  # 'vertical' | 'horizontal'
        self._hud_color = [255, 255, 255]
        self._hud_hover_color = [255, 255, 255]
        self._hud_buttons: list[dict] = []
        self._hud_rect = [20, 20, 120, 60]  # computed bounding box (base coords)

        # choice button group preview (for choice nodes)
        self._choice_enabled = False
        self._choice_pos = [120, 140]
        self._choice_spacing = 12
        self._choice_scale = 1.0
        self._choice_hover_zoom = 1.08
        self._choice_orientation = "vertical"  # 'vertical' | 'horizontal'
        self._choice_font_size = 20
        self._choice_color = [230, 230, 230]
        self._choice_hover_color = [255, 255, 255]
        self._choice_overlay_alpha = 180
        self._choice_bg_image = ""
        self._choice_bg_alpha = 255
        self._choice_padding = [18, 10]
        self._choice_min_size = [0, 0]
        self._choice_sample_options = ["选项 1", "选项 2", "选项 3"]
        self._choice_rect = [120, 140, 220, 120]  # computed bounding box (base coords)

        self._pix_cache: dict[str, QPixmap] = {}
        self._selected: str | None = None
        self._hovered: str | None = None
        self._drag_mode: str | None = None  # 'move' | 'resize'
        self._drag_handle: str | None = None  # 'tl'|'tr'|'bl'|'br'
        self._drag_start_pos = None
        self._drag_start_rect = None
        self._min_w = 20
        self._min_h = 20
        self._handle_px = 10

        # interaction options
        self._grid_snap_enabled = False
        self._grid_size = 10
        self._align_guides_enabled = False
        self._align_snap_enabled = False
        self._align_threshold = 6
        self._active_guides: list[tuple[str, float]] = []  # ('v'|'h', base_coord)

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

    def update_layout(self, data: dict):
        ta = data.get("text_area") or self._text_rect
        na = data.get("name_area") or self._name_rect
        pp = data.get("portrait_pos") or [0, 0]
        psz = data.get("portrait_size") or [0, 0]
        ps = data.get("portrait_scale", 1.0)
        pp2 = data.get("portrait2_pos") or [0, 0]
        psz2 = data.get("portrait2_size") or [0, 0]
        ps2 = data.get("portrait2_scale", 1.0)
        try:
            self._text_rect = [int(ta[0]), int(ta[1]), int(ta[2]), int(ta[3])]
            self._name_rect = [int(na[0]), int(na[1]), int(na[2]), int(na[3])]

            self._portrait_scale = float(ps)
            self._portrait2_scale = float(ps2)
            self._portrait_scale = max(0.1, min(5.0, self._portrait_scale))
            self._portrait2_scale = max(0.1, min(5.0, self._portrait2_scale))

            base_pw, base_ph = 120, 200
            if isinstance(psz, (list, tuple)) and len(psz) == 2:
                base_pw = max(0, int(psz[0])) or 120
                base_ph = max(0, int(psz[1])) or 200
            pw = base_pw * self._portrait_scale
            ph = base_ph * self._portrait_scale
            cx, cy = int(pp[0]), int(pp[1])
            self._portrait_rect = [int(cx - pw / 2), int(cy - ph / 2), int(pw), int(ph)]

            base_pw2, base_ph2 = 120, 200
            if isinstance(psz2, (list, tuple)) and len(psz2) == 2:
                base_pw2 = max(0, int(psz2[0])) or 120
                base_ph2 = max(0, int(psz2[1])) or 200
            pw2 = base_pw2 * self._portrait2_scale
            ph2 = base_ph2 * self._portrait2_scale
            cx2, cy2 = int(pp2[0]), int(pp2[1])
            self._portrait2_rect = [int(cx2 - pw2 / 2), int(cy2 - ph2 / 2), int(pw2), int(ph2)]
        except Exception:
            pass

        self._text_frame_path = str(data.get("text_frame_image") or "")
        self._name_frame_path = str(data.get("name_frame_image") or "")
        try:
            self._text_frame_alpha = int(data.get("text_frame_alpha", 255))
        except Exception:
            self._text_frame_alpha = 255
        try:
            self._name_frame_alpha = int(data.get("name_frame_alpha", 255))
        except Exception:
            self._name_frame_alpha = 255

        self._preview_bg_path = str(data.get("preview_background") or "")
        self._preview_portrait_path = str(data.get("preview_portrait") or "")
        self._preview_portrait2_path = str(data.get("preview_portrait2") or "")

        # HUD button group
        self._hud_enabled = bool(data.get("hud_buttons_enabled", False))
        hp = data.get("hud_button_pos")
        if isinstance(hp, (list, tuple)) and len(hp) >= 2:
            try:
                self._hud_pos = [int(hp[0]), int(hp[1])]
            except Exception:
                self._hud_pos = [20, 20]
        else:
            self._hud_pos = [20, 20]
        try:
            self._hud_spacing = int(data.get("hud_button_spacing", 10) or 10)
        except Exception:
            self._hud_spacing = 10
        self._hud_spacing = max(0, min(200, int(self._hud_spacing)))
        try:
            self._hud_scale = float(data.get("hud_button_scale", 1.0) or 1.0)
        except Exception:
            self._hud_scale = 1.0
        self._hud_scale = max(0.5, min(5.0, float(self._hud_scale)))
        try:
            self._hud_selected_zoom = float(data.get("hud_button_selected_zoom", 1.08) or 1.08)
        except Exception:
            self._hud_selected_zoom = 1.08
        self._hud_selected_zoom = max(1.0, min(1.5, float(self._hud_selected_zoom)))
        orient = str(data.get("hud_button_orientation") or "vertical").strip().lower()
        self._hud_orientation = "horizontal" if orient in {"horizontal", "h", "row", "x"} else "vertical"
        col = data.get("hud_button_color")
        if isinstance(col, (list, tuple)) and len(col) >= 3:
            try:
                self._hud_color = [int(col[0]), int(col[1]), int(col[2])]
            except Exception:
                self._hud_color = [255, 255, 255]
        else:
            self._hud_color = [255, 255, 255]

        col2 = data.get("hud_button_hover_color")
        if isinstance(col2, (list, tuple)) and len(col2) >= 3:
            try:
                self._hud_hover_color = [int(col2[0]), int(col2[1]), int(col2[2])]
            except Exception:
                self._hud_hover_color = list(self._hud_color)
        else:
            self._hud_hover_color = list(self._hud_color)
        btns = data.get("hud_buttons")
        self._hud_buttons = btns if isinstance(btns, list) else []
        self._hud_rect = self._compute_hud_rect()

        # choice button group
        self._choice_enabled = bool(data.get("choice_buttons_enabled", False))
        cp = data.get("choice_button_pos")
        if isinstance(cp, (list, tuple)) and len(cp) >= 2:
            try:
                self._choice_pos = [int(cp[0]), int(cp[1])]
            except Exception:
                self._choice_pos = [120, 140]
        else:
            self._choice_pos = [120, 140]

        try:
            self._choice_spacing = int(data.get("choice_button_spacing", 12) or 12)
        except Exception:
            self._choice_spacing = 12
        self._choice_spacing = max(0, min(300, int(self._choice_spacing)))

        try:
            self._choice_scale = float(data.get("choice_button_scale", 1.0) or 1.0)
        except Exception:
            self._choice_scale = 1.0
        self._choice_scale = max(0.5, min(5.0, float(self._choice_scale)))

        try:
            self._choice_hover_zoom = float(data.get("choice_button_hover_zoom", 1.08) or 1.08)
        except Exception:
            self._choice_hover_zoom = 1.08
        self._choice_hover_zoom = max(1.0, min(1.8, float(self._choice_hover_zoom)))

        orient = str(data.get("choice_button_orientation") or "vertical").strip().lower()
        self._choice_orientation = "horizontal" if orient in {"horizontal", "h", "row", "x"} else "vertical"

        try:
            self._choice_font_size = int(data.get("choice_button_font_size", 20) or 20)
        except Exception:
            self._choice_font_size = 20
        self._choice_font_size = max(8, min(72, int(self._choice_font_size)))

        col = data.get("choice_button_text_color")
        if isinstance(col, (list, tuple)) and len(col) >= 3:
            try:
                self._choice_color = [int(col[0]), int(col[1]), int(col[2])]
            except Exception:
                self._choice_color = [230, 230, 230]
        else:
            self._choice_color = [230, 230, 230]

        col2 = data.get("choice_button_text_hover_color")
        if isinstance(col2, (list, tuple)) and len(col2) >= 3:
            try:
                self._choice_hover_color = [int(col2[0]), int(col2[1]), int(col2[2])]
            except Exception:
                self._choice_hover_color = list(self._choice_color)
        else:
            self._choice_hover_color = list(self._choice_color)

        try:
            self._choice_overlay_alpha = int(data.get("choice_overlay_alpha", 180))
        except Exception:
            self._choice_overlay_alpha = 180
        self._choice_overlay_alpha = max(0, min(255, int(self._choice_overlay_alpha)))

        self._choice_bg_image = str(data.get("choice_button_bg_image") or "")
        try:
            self._choice_bg_alpha = int(data.get("choice_button_bg_alpha", 255))
        except Exception:
            self._choice_bg_alpha = 255
        self._choice_bg_alpha = max(0, min(255, int(self._choice_bg_alpha)))

        pad = data.get("choice_button_padding")
        if isinstance(pad, (list, tuple)) and len(pad) >= 2:
            try:
                self._choice_padding = [max(0, int(pad[0])), max(0, int(pad[1]))]
            except Exception:
                self._choice_padding = [18, 10]
        else:
            self._choice_padding = [18, 10]

        ms = data.get("choice_button_min_size")
        if isinstance(ms, (list, tuple)) and len(ms) >= 2:
            try:
                self._choice_min_size = [max(0, int(ms[0])), max(0, int(ms[1]))]
            except Exception:
                self._choice_min_size = [0, 0]
        else:
            self._choice_min_size = [0, 0]

        self._choice_rect = self._compute_choice_rect()

        self._text_frame_alpha = max(0, min(255, self._text_frame_alpha))
        self._name_frame_alpha = max(0, min(255, self._name_frame_alpha))

        self.update()

    def set_base_size(self, size: tuple[int, int]):
        try:
            self._base_size = (max(1, int(size[0])), max(1, int(size[1])))
        except Exception:
            return
        self.update()

    def _sx_sy(self) -> tuple[float, float]:
        base_w, base_h = self._base_size
        return self.width() / base_w, self.height() / base_h

    def _base_to_widget_rect(self, rect_vals: list[int]) -> tuple[int, int, int, int]:
        sx, sy = self._sx_sy()
        x, y, w, h = rect_vals
        return int(x * sx), int(y * sy), int(w * sx), int(h * sy)

    def _widget_to_base_point(self, x: int, y: int) -> tuple[float, float]:
        sx, sy = self._sx_sy()
        if sx <= 0 or sy <= 0:
            return 0.0, 0.0
        return x / sx, y / sy

    def _pix(self, path: str) -> QPixmap | None:
        raw = (path or "").strip()
        if not raw:
            return None
        try:
            pp = Path(raw)
            if not pp.is_absolute() and self._path_base is not None:
                pp = (Path(self._path_base) / pp).resolve()
            key = str(pp)
        except Exception:
            key = raw
        if key in self._pix_cache:
            px = self._pix_cache[key]
            return px if not px.isNull() else None
        px = QPixmap(key)
        self._pix_cache[key] = px
        return px if not px.isNull() else None

    def _components(self) -> list[tuple[str, list[int]]]:
        # selection priority: name/text on top, then portraits
        items: list[tuple[str, list[int]]] = []
        if self._choice_enabled:
            items.append(("choice", self._choice_rect))
        if self._hud_enabled:
            items.append(("hud", self._hud_rect))
        items.extend(
            [
                ("name", self._name_rect),
                ("text", self._text_rect),
                ("portrait2", self._portrait2_rect),
                ("portrait", self._portrait_rect),
            ]
        )
        return items

    def _resolve_size_for_hud_button(self, item: dict) -> tuple[int, int]:
        style = str(item.get("style") or "text").strip().lower()
        label = str(item.get("label") or "")

        if style == "image":
            img_path = str(item.get("image") or item.get("image_path") or "")
            pix = self._pix(img_path)
            if pix is not None:
                try:
                    img_scale = float(item.get("image_scale", 1.0) or 1.0)
                except Exception:
                    img_scale = 1.0
                img_scale = max(0.1, min(5.0, float(img_scale)))
                s = max(0.5, min(5.0, float(self._hud_scale)))
                w = max(1, int(pix.width() * s * img_scale))
                h = max(1, int(pix.height() * s * img_scale))
                return w, h

        # text fallback
        s = max(0.5, min(5.0, float(self._hud_scale)))
        font = QFont("Arial")
        font.setPixelSize(max(8, int(18 * s)))
        fm = QFontMetrics(font)
        w = max(1, int(fm.horizontalAdvance(label)))
        h = max(1, int(fm.height()))
        return w, h

    def _hud_item_rects(self) -> list[list[int]]:
        if not self._hud_enabled or not self._hud_buttons:
            return []
        x0, y0 = int(self._hud_pos[0]), int(self._hud_pos[1])
        spacing = int(self._hud_spacing)
        rects: list[list[int]] = []
        cur_x, cur_y = x0, y0
        for it in self._hud_buttons:
            if not isinstance(it, dict):
                continue
            w, h = self._resolve_size_for_hud_button(it)
            rects.append([int(cur_x), int(cur_y), int(w), int(h)])
            if self._hud_orientation == "horizontal":
                cur_x += int(w) + spacing
            else:
                cur_y += int(h) + spacing
        return rects

    def _compute_hud_rect(self) -> list[int]:
        x0, y0 = int(self._hud_pos[0]), int(self._hud_pos[1])
        rects = self._hud_item_rects()
        if not rects:
            return [x0, y0, 120, 60]
        left = min(r[0] for r in rects)
        top = min(r[1] for r in rects)
        right = max(r[0] + r[2] for r in rects)
        bottom = max(r[1] + r[3] for r in rects)
        w = max(20, int(right - left))
        h = max(20, int(bottom - top))
        return [int(left), int(top), int(w), int(h)]

    def _resolve_size_for_choice_item(self, label: str) -> tuple[int, int]:
        # approximate text box size; background image is stretched to box
        s = max(0.5, min(5.0, float(self._choice_scale)))
        font = QFont("Arial")
        font.setPixelSize(max(8, int(float(self._choice_font_size) * s)))
        fm = QFontMetrics(font)
        tw = int(fm.horizontalAdvance(str(label)))
        th = int(fm.height())
        pad = self._choice_padding if isinstance(self._choice_padding, (list, tuple)) else [18, 10]
        try:
            px, py = int(pad[0]), int(pad[1])
        except Exception:
            px, py = 18, 10
        w = tw + px * 2
        h = th + py * 2
        ms = self._choice_min_size if isinstance(self._choice_min_size, (list, tuple)) else [0, 0]
        try:
            mw, mh = int(ms[0]), int(ms[1])
        except Exception:
            mw, mh = 0, 0
        w = max(mw, w)
        h = max(mh, h)
        return max(1, int(w)), max(1, int(h))

    def _choice_item_rects(self) -> list[list[int]]:
        if not self._choice_enabled:
            return []
        cx, cy = int(self._choice_pos[0]), int(self._choice_pos[1])
        spacing = int(self._choice_spacing)
        rects: list[list[int]] = []
        labels = self._choice_sample_options if isinstance(self._choice_sample_options, list) else ["选项 1", "选项 2", "选项 3"]
        sizes: list[tuple[int, int]] = []
        for label in labels:
            sizes.append(self._resolve_size_for_choice_item(str(label)))

        if self._choice_orientation == "horizontal":
            total_w = sum(w for w, _ in sizes) + spacing * max(0, len(sizes) - 1)
            cur_x = int(cx - total_w / 2)
            for (w, h) in sizes:
                rects.append([int(cur_x), int(cy - h / 2), int(w), int(h)])
                cur_x += int(w) + spacing
        else:
            total_h = sum(h for _, h in sizes) + spacing * max(0, len(sizes) - 1)
            cur_y = int(cy - total_h / 2)
            for (w, h) in sizes:
                rects.append([int(cx - w / 2), int(cur_y), int(w), int(h)])
                cur_y += int(h) + spacing
        return rects

    def _compute_choice_rect(self) -> list[int]:
        cx, cy = int(self._choice_pos[0]), int(self._choice_pos[1])
        rects = self._choice_item_rects()
        if not rects:
            return [int(cx - 110), int(cy - 60), 220, 120]
        left = min(r[0] for r in rects)
        top = min(r[1] for r in rects)
        right = max(r[0] + r[2] for r in rects)
        bottom = max(r[1] + r[3] for r in rects)
        w = max(20, int(right - left))
        h = max(20, int(bottom - top))
        return [int(left), int(top), int(w), int(h)]

    def _handles_for_rect(self, wx: int, wy: int, ww: int, wh: int) -> dict[str, tuple[int, int, int, int]]:
        s = self._handle_px
        return {
            "tl": (wx - s // 2, wy - s // 2, s, s),
            "tr": (wx + ww - s // 2, wy - s // 2, s, s),
            "bl": (wx - s // 2, wy + wh - s // 2, s, s),
            "br": (wx + ww - s // 2, wy + wh - s // 2, s, s),
        }

    def _hit_test(self, mx: int, my: int):
        # returns (component, mode, handle)
        for name, rect_vals in self._components():
            wx, wy, ww, wh = self._base_to_widget_rect(rect_vals)
            handles = self._handles_for_rect(wx, wy, ww, wh)
            for hname, (hx, hy, hw, hh) in handles.items():
                if hx <= mx <= hx + hw and hy <= my <= hy + hh:
                    return name, "resize", hname
            if wx <= mx <= wx + ww and wy <= my <= wy + wh:
                return name, "move", None
        return None, None, None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        name, mode, handle = self._hit_test(event.position().x(), event.position().y())
        if not name:
            self._selected = None
            self.update()
            return
        self._selected = name
        self._drag_mode = mode
        self._drag_handle = handle
        self._drag_start_pos = (event.position().x(), event.position().y())
        self._drag_start_rect = list(self._get_rect_by_name(name))
        self._active_guides = []
        self.update()

    def mouseMoveEvent(self, event):
        mx = int(event.position().x())
        my = int(event.position().y())

        if not self._drag_mode:
            name, _, _ = self._hit_test(mx, my)
            if name != self._hovered:
                self._hovered = name
                self.update()
            return

        if not self._selected or not self._drag_start_pos or not self._drag_start_rect:
            return

        sx, sy = self._sx_sy()
        if sx <= 0 or sy <= 0:
            return

        dx_base = (mx - self._drag_start_pos[0]) / sx
        dy_base = (my - self._drag_start_pos[1]) / sy

        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)

        x0, y0, w0, h0 = self._drag_start_rect
        x, y, w, h = float(x0), float(y0), float(w0), float(h0)
        self._active_guides = []

        if self._drag_mode == "move":
            x = x0 + dx_base
            y = y0 + dy_base

            if self._align_guides_enabled:
                x, y = self._apply_align_snap_move(self._selected, x, y, w0, h0)
        elif self._drag_mode == "resize" and self._drag_handle:
            # handle signs
            sign_x = 1 if self._drag_handle in {"tr", "br"} else -1
            sign_y = 1 if self._drag_handle in {"bl", "br"} else -1
            factor = 2.0 if alt else 1.0

            # compute size deltas
            w = w0 + factor * sign_x * dx_base
            h = h0 + factor * sign_y * dy_base

            # keep aspect ratio when Shift is pressed
            if shift and h0 > 0 and w0 > 0:
                ratio = float(w0) / float(h0)
                dw = abs(factor * sign_x * dx_base)
                dh = abs(factor * sign_y * dy_base)
                if dw >= dh:
                    h = w / ratio
                else:
                    w = h * ratio

            # enforce minimum
            w = max(float(self._min_w), float(w))
            h = max(float(self._min_h), float(h))

            if alt:
                cx0 = x0 + w0 / 2.0
                cy0 = y0 + h0 / 2.0
                x = cx0 - w / 2.0
                y = cy0 - h / 2.0
            else:
                # anchor opposite corner
                if self._drag_handle == "tl":
                    ax, ay = x0 + w0, y0 + h0
                    x, y = ax - w, ay - h
                elif self._drag_handle == "tr":
                    ax, ay = x0, y0 + h0
                    x, y = ax, ay - h
                elif self._drag_handle == "bl":
                    ax, ay = x0 + w0, y0
                    x, y = ax - w, ay
                else:  # br
                    ax, ay = x0, y0
                    x, y = ax, ay

                if self._align_guides_enabled:
                    x, y, w, h = self._apply_align_snap_resize(self._selected, self._drag_handle, x, y, w, h)

        # grid snap (applied last)
        if self._grid_snap_enabled and self._grid_size > 0:
            x, y, w, h = self._apply_grid_snap(x, y, w, h)

        w = max(float(self._min_w), float(w))
        h = max(float(self._min_h), float(h))

        # Special mapping for HUD/choice group: resize updates scale, move updates pos.
        if self._selected == "hud":
            if self._drag_mode == "move":
                self._hud_pos = [int(round(x)), int(round(y))]
            elif self._drag_mode == "resize":
                try:
                    ratio = float(h) / max(1.0, float(h0))
                except Exception:
                    ratio = 1.0
                self._hud_scale = max(0.5, min(5.0, float(self._hud_scale) * float(ratio)))
                self._hud_pos = [int(round(x)), int(round(y))]
            self._hud_rect = self._compute_hud_rect()
        elif self._selected == "choice":
            if self._drag_mode == "move":
                self._choice_pos = [int(round(x + w / 2.0)), int(round(y + h / 2.0))]
            elif self._drag_mode == "resize":
                try:
                    ratio = float(h) / max(1.0, float(h0))
                except Exception:
                    ratio = 1.0
                self._choice_scale = max(0.5, min(5.0, float(self._choice_scale) * float(ratio)))
                self._choice_pos = [int(round(x + w / 2.0)), int(round(y + h / 2.0))]
            self._choice_rect = self._compute_choice_rect()
        else:
            self._set_rect_by_name(self._selected, [int(round(x)), int(round(y)), int(round(w)), int(round(h))])
        self.update()
        self.layoutEdited.emit(self._layout_from_state())

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

    def _apply_align_snap_move(self, name: str, x: float, y: float, w: int, h: int) -> tuple[float, float]:
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

        if self._align_guides_enabled:
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
        # Only snap the moving edges for non-alt resize.
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

        best = []
        guides: list[tuple[str, float]] = []

        # horizontal snap
        best_dx = None
        best_target_x = None
        candidates = []
        if move_left:
            candidates.append(("left", left))
        if move_right:
            candidates.append(("right", right))
        # allow center snap when shift keeps ratio or general
        candidates.append(("center", cx))

        for cname, cval in candidates:
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

        # vertical snap
        best_dy = None
        best_target_y = None
        candidates_y = []
        if move_top:
            candidates_y.append(("top", top))
        if move_bottom:
            candidates_y.append(("bottom", bottom))
        candidates_y.append(("center", cy))

        for cname, cval in candidates_y:
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

    def _get_rect_by_name(self, name: str) -> list[int]:
        if name == "choice":
            return self._choice_rect
        if name == "hud":
            return self._hud_rect
        if name == "text":
            return self._text_rect
        if name == "name":
            return self._name_rect
        if name == "portrait":
            return self._portrait_rect
        if name == "portrait2":
            return self._portrait2_rect
        return self._text_rect

    def _set_rect_by_name(self, name: str, rect_vals: list[int]):
        if name == "choice":
            self._choice_rect = rect_vals
        elif name == "hud":
            self._hud_rect = rect_vals
        elif name == "text":
            self._text_rect = rect_vals
        elif name == "name":
            self._name_rect = rect_vals
        elif name == "portrait":
            self._portrait_rect = rect_vals
        elif name == "portrait2":
            self._portrait2_rect = rect_vals

    def _layout_from_state(self) -> dict:
        # portrait layout uses center + base size + scale
        px, py, pw, ph = self._portrait_rect
        cx = int(px + pw / 2)
        cy = int(py + ph / 2)
        s = max(0.1, min(5.0, float(self._portrait_scale)))
        base_pw = int(max(0, round(pw / s)))
        base_ph = int(max(0, round(ph / s)))
        if base_pw <= 0:
            base_pw = 0
        if base_ph <= 0:
            base_ph = 0

        px2, py2, pw2, ph2 = self._portrait2_rect
        cx2 = int(px2 + pw2 / 2)
        cy2 = int(py2 + ph2 / 2)
        s2 = max(0.1, min(5.0, float(self._portrait2_scale)))
        base_pw2 = int(max(0, round(pw2 / s2)))
        base_ph2 = int(max(0, round(ph2 / s2)))
        if base_pw2 <= 0:
            base_pw2 = 0
        if base_ph2 <= 0:
            base_ph2 = 0

        out = {
            "text_area": [int(v) for v in self._text_rect],
            "name_area": [int(v) for v in self._name_rect],
            "portrait_pos": [cx, cy],
            "portrait_size": [base_pw, base_ph],
            "portrait_scale": float(self._portrait_scale),
            "portrait2_pos": [cx2, cy2],
            "portrait2_size": [base_pw2, base_ph2],
            "portrait2_scale": float(self._portrait2_scale),
        }
        if self._choice_enabled:
            out["choice_button_pos"] = [int(self._choice_pos[0]), int(self._choice_pos[1])]
            out["choice_button_scale"] = float(self._choice_scale)
        if self._hud_enabled:
            out["hud_button_pos"] = [int(self._hud_pos[0]), int(self._hud_pos[1])]
            out["hud_button_scale"] = float(self._hud_scale)
        return out

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # background
        bg = self._pix(self._preview_bg_path)
        if bg is not None:
            painter.drawPixmap(self.rect(), bg)
        else:
            painter.fillRect(self.rect(), QColor(24, 28, 36))

        # grid (visual helper, tied to grid snap)
        if self._grid_snap_enabled and self._grid_size > 0:
            base_w, base_h = self._base_size
            g = max(1, int(self._grid_size))
            sx, sy = self._sx_sy()
            # avoid drawing too many lines
            max_lines = 220
            step = g
            if base_w / step > max_lines:
                step = int(max(1, round(base_w / max_lines)))
            if base_h / step > max_lines:
                step = int(max(step, round(base_h / max_lines)))
            painter.setPen(QPen(QColor(255, 255, 255, 18), 1))
            x = 0
            while x <= base_w:
                wx = int(x * sx)
                painter.drawLine(wx, 0, wx, self.height())
                x += step
            y = 0
            while y <= base_h:
                wy = int(y * sy)
                painter.drawLine(0, wy, self.width(), wy)
                y += step

        def draw_image_in_rect(img_path: str, rect_vals: list[int], alpha: int = 255, fallback_color: QColor | None = None, border: QColor | None = None):
            wx, wy, ww, wh = self._base_to_widget_rect(rect_vals)
            if ww <= 0 or wh <= 0:
                return
            pix = self._pix(img_path)
            if pix is not None:
                painter.save()
                painter.setOpacity(max(0.0, min(1.0, alpha / 255.0)))
                painter.drawPixmap(wx, wy, ww, wh, pix)
                painter.restore()
            else:
                if fallback_color is not None:
                    painter.setBrush(QBrush(fallback_color))
                else:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                if border is not None:
                    painter.setPen(QPen(border, 2))
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(wx, wy, ww, wh)

        # portraits (behind)
        draw_image_in_rect(
            self._preview_portrait2_path,
            self._portrait2_rect,
            255,
            fallback_color=QColor(140, 255, 170, 50),
            border=QColor(140, 255, 170, 200),
        )
        draw_image_in_rect(
            self._preview_portrait_path,
            self._portrait_rect,
            255,
            fallback_color=QColor(120, 200, 255, 50),
            border=QColor(120, 200, 255, 200),
        )

        # textbox/namebox frames (above)
        if (self._text_frame_path or "").strip():
            draw_image_in_rect(self._text_frame_path, self._text_rect, alpha=self._text_frame_alpha)
        else:
            draw_image_in_rect(
                "",
                self._text_rect,
                255,
                fallback_color=QColor(0, 0, 0, 190),
                border=QColor(255, 255, 255, 120),
            )

        if (self._name_frame_path or "").strip():
            draw_image_in_rect(self._name_frame_path, self._name_rect, alpha=self._name_frame_alpha)
        else:
            draw_image_in_rect(
                "",
                self._name_rect,
                255,
                fallback_color=QColor(0, 0, 0, 180),
                border=QColor(255, 200, 120, 180),
            )

        # choice button group (visual)
        if self._choice_enabled:
            choice_rect = self._choice_rect
            wx, wy, ww, wh = self._base_to_widget_rect(choice_rect)
            # light container hint
            painter.setBrush(QBrush(QColor(255, 255, 255, 14)))
            painter.setPen(QPen(QColor(255, 255, 255, 80), 1))
            painter.drawRoundedRect(wx, wy, ww, wh, 10, 10)

            col = self._choice_color if isinstance(self._choice_color, (list, tuple)) else [230, 230, 230]
            hov = self._choice_hover_color if isinstance(self._choice_hover_color, (list, tuple)) else list(col)
            try:
                r, g, b = int(col[0]), int(col[1]), int(col[2])
            except Exception:
                r, g, b = 230, 230, 230
            try:
                hr, hg, hb = int(hov[0]), int(hov[1]), int(hov[2])
            except Exception:
                hr, hg, hb = r, g, b

            sx, sy = self._sx_sy()
            font = QFont("Arial")
            font.setPixelSize(max(8, int(float(self._choice_font_size) * float(self._choice_scale) * min(sx, sy))))
            painter.setFont(font)

            pad = self._choice_padding if isinstance(self._choice_padding, (list, tuple)) else [18, 10]
            try:
                px, py = int(pad[0]), int(pad[1])
            except Exception:
                px, py = 18, 10

            rects = self._choice_item_rects()
            bg_pix = self._pix(self._choice_bg_image)
            for idx, br in enumerate(rects):
                bx, by, bw, bh = br
                bwx, bwy, bww, bwh = self._base_to_widget_rect([bx, by, bw, bh])
                if bg_pix is not None:
                    painter.save()
                    painter.setOpacity(max(0.0, min(1.0, float(self._choice_bg_alpha) / 255.0)))
                    painter.drawPixmap(bwx, bwy, bww, bwh, bg_pix)
                    painter.restore()
                else:
                    painter.setBrush(QBrush(QColor(0, 0, 0, 130)))
                    painter.setPen(QPen(QColor(255, 255, 255, 110), 1))
                    painter.drawRoundedRect(bwx, bwy, bww, bwh, 8, 8)

                painter.setPen(QPen(QColor(hr, hg, hb, 220) if idx == 0 else QColor(r, g, b, 220), 1))
                label = (self._choice_sample_options[idx] if idx < len(self._choice_sample_options) else f"选项 {idx + 1}")
                painter.drawText(QRect(bwx, bwy, bww, bwh), Qt.AlignmentFlag.AlignCenter, str(label))

        # HUD button group (visual)
        if self._hud_enabled:
            hud_rect = self._hud_rect
            wx, wy, ww, wh = self._base_to_widget_rect(hud_rect)
            painter.setBrush(QBrush(QColor(255, 255, 255, 16)))
            painter.setPen(QPen(QColor(255, 255, 255, 90), 1))
            painter.drawRoundedRect(wx, wy, ww, wh, 8, 8)

            col = self._hud_color if isinstance(self._hud_color, (list, tuple)) else [255, 255, 255]
            try:
                r, g, b = int(col[0]), int(col[1]), int(col[2])
            except Exception:
                r, g, b = 255, 255, 255

            sx, sy = self._sx_sy()
            font = QFont("Arial")
            font.setPixelSize(max(8, int(18 * float(self._hud_scale) * min(sx, sy))))
            painter.setFont(font)

            rects = self._hud_item_rects()
            for idx, it in enumerate(self._hud_buttons):
                if idx >= len(rects):
                    break
                if not isinstance(it, dict):
                    continue
                bx, by, bw, bh = rects[idx]
                bwx, bwy, bww, bwh = self._base_to_widget_rect([bx, by, bw, bh])
                style = str(it.get("style") or "text").strip().lower()
                if style == "image":
                    img_path = str(it.get("image") or it.get("image_path") or "")
                    pix = self._pix(img_path)
                    if pix is not None:
                        painter.drawPixmap(bwx, bwy, bww, bwh, pix)
                    else:
                        painter.setBrush(QBrush(QColor(120, 160, 255, 60)))
                        painter.setPen(QPen(QColor(120, 160, 255, 180), 1))
                        painter.drawRect(bwx, bwy, bww, bwh)
                else:
                    painter.setBrush(QBrush(QColor(0, 0, 0, 140)))
                    painter.setPen(QPen(QColor(255, 255, 255, 100), 1))
                    painter.drawRoundedRect(bwx, bwy, bww, bwh, 6, 6)
                    painter.setPen(QPen(QColor(r, g, b, 230), 1))
                    label = str(it.get("label") or "")
                    painter.drawText(bwx + 6, bwy + int(bwh * 0.72), label)

        # outlines + handles
        for name, rect_vals in self._components():
            wx, wy, ww, wh = self._base_to_widget_rect(rect_vals)
            if ww <= 0 or wh <= 0:
                continue
            is_sel = name == self._selected
            is_hov = name == self._hovered
            if is_sel:
                painter.setPen(QPen(QColor(255, 255, 255, 220), 2))
            elif is_hov:
                painter.setPen(QPen(QColor(255, 255, 255, 140), 2))
            else:
                painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(wx, wy, ww, wh)

            if is_sel:
                painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
                painter.setPen(Qt.PenStyle.NoPen)
                for _, (hx, hy, hw, hh) in self._handles_for_rect(wx, wy, ww, wh).items():
                    painter.drawRect(hx, hy, hw, hh)

        # alignment guides (on top)
        if self._align_guides_enabled and self._active_guides:
            sx, sy = self._sx_sy()
            painter.setPen(QPen(QColor(255, 120, 220, 200), 1))
            for kind, pos in self._active_guides:
                if kind == "v":
                    wx = int(pos * sx)
                    painter.drawLine(wx, 0, wx, self.height())
                elif kind == "h":
                    wy = int(pos * sy)
                    painter.drawLine(0, wy, self.width(), wy)


class UILayoutDesigner(QDialog):
    """Very lightweight UI layout editor saving to JSON under project ui/ folder."""

    def __init__(self, project_dir: Path, base_size: tuple[int, int] | None = None, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
        self.base_size = base_size or (800, 600)
        self.setWindowTitle("UI 设计器")
        self.setMinimumWidth(760)
        self.resize(980, 720)
        self.setMaximumSize(1200, 900)
        self.layout_path: Path | None = None
        self._updating = False
        self._suppress_dirty = False
        self._dirty = False
        self._initialized = False

        main = QVBoxLayout(self)
        top_row = QHBoxLayout()

        # left pane in scroll area (categorized + collapsible)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # interaction toggles
        self.chk_grid_snap = QCheckBox("网格吸附")
        self.chk_align_guides = QCheckBox("对齐线")
        self.chk_align_snap = QCheckBox("对齐吸附")
        self.chk_grid_snap.setChecked(False)
        self.chk_align_guides.setChecked(True)
        self.chk_align_snap.setChecked(True)
        self.grid_size = self._spin(1, 200, 10)

        # text area
        self.text_x = self._spin(0, 4000, 40)
        self.text_y = self._spin(0, 4000, 400)
        self.text_w = self._spin(100, 4000, 720)
        self.text_h = self._spin(60, 4000, 180)

        sec_text = _CollapsibleSection("文本框")
        form_text = QFormLayout()
        form_text.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_text.addRow("x", self.text_x)
        form_text.addRow("y", self.text_y)
        form_text.addRow("宽", self.text_w)
        form_text.addRow("高", self.text_h)
        sec_text.setContentLayout(form_text)

        # name box
        self.name_x = self._spin(0, 4000, 40)
        self.name_y = self._spin(0, 4000, 360)
        self.name_w = self._spin(60, 4000, 200)
        self.name_h = self._spin(24, 4000, 32)

        sec_name = _CollapsibleSection("姓名框")
        form_name = QFormLayout()
        form_name.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_name.addRow("x", self.name_x)
        form_name.addRow("y", self.name_y)
        form_name.addRow("宽", self.name_w)
        form_name.addRow("高", self.name_h)
        sec_name.setContentLayout(form_name)

        # portrait position
        self.portrait_x = self._spin(-2000, 4000, 0)
        self.portrait_y = self._spin(-2000, 4000, 0)
        self.portrait_w = self._spin(0, 8000, 0)
        self.portrait_h = self._spin(0, 8000, 0)
        self.portrait_scale = self._dspin(0.1, 5.0, 1.0, 0.1)

        sec_portrait = _CollapsibleSection("立绘 1")
        form_portrait = QFormLayout()
        form_portrait.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_portrait.addRow("中心 x", self.portrait_x)
        form_portrait.addRow("中心 y", self.portrait_y)
        form_portrait.addRow("宽(0=自动)", self.portrait_w)
        form_portrait.addRow("高(0=自动)", self.portrait_h)
        form_portrait.addRow("缩放", self.portrait_scale)
        sec_portrait.setContentLayout(form_portrait)

        # portrait2 position
        self.portrait2_x = self._spin(-2000, 4000, 0)
        self.portrait2_y = self._spin(-2000, 4000, 0)
        self.portrait2_w = self._spin(0, 8000, 0)
        self.portrait2_h = self._spin(0, 8000, 0)
        self.portrait2_scale = self._dspin(0.1, 5.0, 1.0, 0.1)

        sec_portrait2 = _CollapsibleSection("立绘 2")
        form_portrait2 = QFormLayout()
        form_portrait2.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_portrait2.addRow("中心 x", self.portrait2_x)
        form_portrait2.addRow("中心 y", self.portrait2_y)
        form_portrait2.addRow("宽(0=自动)", self.portrait2_w)
        form_portrait2.addRow("高(0=自动)", self.portrait2_h)
        form_portrait2.addRow("缩放", self.portrait2_scale)
        sec_portrait2.setContentLayout(form_portrait2)

        # textbox/namebox frames
        self.text_frame_edit = QLineEdit()
        text_frame_row = self._make_file_row(
            self.text_frame_edit,
            lambda: self._pick_and_store_image(self.text_frame_edit, "resources/images/ui", "选择对话框图片"),
            lambda: self._clear_line(self.text_frame_edit),
            "选择图片",
        )
        self.text_frame_alpha = self._spin(0, 255, 255)

        self.name_frame_edit = QLineEdit()
        name_frame_row = self._make_file_row(
            self.name_frame_edit,
            lambda: self._pick_and_store_image(self.name_frame_edit, "resources/images/ui", "选择姓名框图片"),
            lambda: self._clear_line(self.name_frame_edit),
            "选择图片",
        )
        self.name_frame_alpha = self._spin(0, 255, 255)

        sec_frames = _CollapsibleSection("对话框/姓名框")
        form_frames = QFormLayout()
        form_frames.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_frames.addRow("对话框图片", text_frame_row)
        form_frames.addRow("对话框透明度(0-255)", self.text_frame_alpha)
        form_frames.addRow("姓名框图片", name_frame_row)
        form_frames.addRow("姓名框透明度(0-255)", self.name_frame_alpha)
        sec_frames.setContentLayout(form_frames)

        # in-game HUD button group (mouse-only)
        self.hud_enabled_chk = QCheckBox("启用游戏按钮组（仅鼠标）")
        self.hud_enabled_chk.setChecked(False)
        self.hud_orient_combo = QComboBox()
        self.hud_orient_combo.addItems(["纵向排列", "横向排列"])
        self.hud_x = self._spin(-2000, 8000, 20)
        self.hud_y = self._spin(-2000, 8000, 20)
        self.hud_spacing = self._spin(0, 200, 10)
        self.hud_scale = self._dspin(0.5, 5.0, 1.0, 0.1)
        self.hud_selected_zoom = self._dspin(1.0, 1.5, 1.08, 0.02)
        self.hud_color_edit = QLineEdit("#FFFFFF")
        self.hud_hover_color_edit = QLineEdit("#FFFFFF")

        self._hud_default_buttons: list[dict[str, str]] = [
            {"action": "save", "label": "存档"},
            {"action": "load", "label": "读档"},
            {"action": "settings", "label": "设置"},
            {"action": "history", "label": "历史记录"},
            {"action": "menu", "label": "返回主菜单"},
            {"action": "fullscreen", "label": "全屏"},
        ]
        self._hud_button_mode: list[QComboBox] = []
        self._hud_button_text: list[QLineEdit] = []
        self._hud_button_image: list[QLineEdit] = []
        self._hud_button_image_scale: list[QDoubleSpinBox] = []

        sec_hud = _CollapsibleSection("游戏界面按钮组")
        hud_box = QVBoxLayout()
        hud_form = QFormLayout()
        hud_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        hud_form.addRow(self.hud_enabled_chk)
        hud_form.addRow("排列", self.hud_orient_combo)
        hud_form.addRow("x", self.hud_x)
        hud_form.addRow("y", self.hud_y)
        hud_form.addRow("间距", self.hud_spacing)
        hud_form.addRow("缩放", self.hud_scale)
        hud_form.addRow("选中缩放(仅图片)", self.hud_selected_zoom)
        hud_form.addRow("文字颜色(#RRGGBB)", self._make_color_row(self.hud_color_edit))
        hud_form.addRow("悬停颜色(#RRGGBB)", self._make_color_row(self.hud_hover_color_edit))
        hud_box.addLayout(hud_form)

        for base in self._hud_default_buttons:
            action = base["action"]
            label = base["label"]

            mode = QComboBox()
            mode.addItems(["文字", "图片"])
            txt = QLineEdit(label)
            img = QLineEdit()
            img_row = self._make_file_row(
                img,
                self._make_pick_image_handler(img, "resources/images/ui", f"选择按钮图片：{label}"),
                lambda ed=img: self._clear_line(ed),
                "选择图片",
            )
            img_scale = self._dspin(0.1, 5.0, 1.0, 0.1)

            self._hud_button_mode.append(mode)
            self._hud_button_text.append(txt)
            self._hud_button_image.append(img)
            self._hud_button_image_scale.append(img_scale)

            sec_btn = _CollapsibleSection(f"按钮：{label}")
            form_btn = QFormLayout()
            form_btn.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            form_btn.addRow("样式", mode)
            form_btn.addRow("文字", txt)
            form_btn.addRow("图片", img_row)
            form_btn.addRow("图片缩放", img_scale)
            sec_btn.setContentLayout(form_btn)
            hud_box.addWidget(sec_btn)

        sec_hud.setContentLayout(hud_box)

        # choice button group (for choice nodes)
        self.choice_enabled_chk = QCheckBox("启用选项按钮组（choice 节点）")
        self.choice_enabled_chk.setChecked(False)
        self.choice_orient_combo = QComboBox()
        self.choice_orient_combo.addItems(["纵向排列", "横向排列"])
        self.choice_x = self._spin(-2000, 8000, 120)
        self.choice_y = self._spin(-2000, 8000, 140)
        self.choice_spacing = self._spin(0, 300, 12)
        self.choice_scale = self._dspin(0.5, 5.0, 1.0, 0.1)
        self.choice_hover_zoom = self._dspin(1.0, 1.8, 1.08, 0.02)
        self.choice_font_size = self._spin(8, 72, 20)
        self.choice_overlay_alpha = self._spin(0, 255, 180)
        self.choice_color_edit = QLineEdit("#E6E6E6")
        self.choice_hover_color_edit = QLineEdit("#FFFFFF")

        self.choice_bg_edit = QLineEdit()
        choice_bg_row = self._make_file_row(
            self.choice_bg_edit,
            lambda: self._pick_and_store_image(self.choice_bg_edit, "resources/images/ui", "选择选项按钮背景图"),
            lambda: self._clear_line(self.choice_bg_edit),
            "选择图片",
        )
        self.choice_bg_alpha = self._spin(0, 255, 255)
        self.choice_pad_x = self._spin(0, 200, 18)
        self.choice_pad_y = self._spin(0, 200, 10)
        self.choice_min_w = self._spin(0, 2000, 0)
        self.choice_min_h = self._spin(0, 2000, 0)

        sec_choice = _CollapsibleSection("选项按钮组")
        choice_box = QVBoxLayout()
        choice_form = QFormLayout()
        choice_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        choice_form.addRow(self.choice_enabled_chk)
        choice_form.addRow("排列", self.choice_orient_combo)
        choice_form.addRow("x", self.choice_x)
        choice_form.addRow("y", self.choice_y)
        choice_form.addRow("间距", self.choice_spacing)
        choice_form.addRow("缩放", self.choice_scale)
        choice_form.addRow("悬停缩放", self.choice_hover_zoom)
        choice_form.addRow("字体大小(px)", self.choice_font_size)
        choice_form.addRow("遮罩透明度(0-255)", self.choice_overlay_alpha)
        choice_form.addRow("文字颜色(#RRGGBB)", self._make_color_row(self.choice_color_edit))
        choice_form.addRow("悬停文字颜色(#RRGGBB)", self._make_color_row(self.choice_hover_color_edit))
        choice_form.addRow("按钮背景图", choice_bg_row)
        choice_form.addRow("背景透明度(0-255)", self.choice_bg_alpha)
        choice_form.addRow("内边距 x", self.choice_pad_x)
        choice_form.addRow("内边距 y", self.choice_pad_y)
        choice_form.addRow("最小宽", self.choice_min_w)
        choice_form.addRow("最小高", self.choice_min_h)
        choice_box.addLayout(choice_form)
        sec_choice.setContentLayout(choice_box)

        # preview sample images (only for designer preview)
        self.preview_bg_edit = QLineEdit()
        preview_bg_row = self._make_file_row(
            self.preview_bg_edit,
            lambda: self._pick_and_store_image(self.preview_bg_edit, "resources/images", "选择示例背景图"),
            lambda: self._clear_line(self.preview_bg_edit),
            "选择图片",
        )
        self.preview_portrait_edit = QLineEdit()
        preview_portrait_row = self._make_file_row(
            self.preview_portrait_edit,
            lambda: self._pick_and_store_image(self.preview_portrait_edit, "resources/portraits", "选择示例立绘1"),
            lambda: self._clear_line(self.preview_portrait_edit),
            "选择图片",
        )

        self.preview_portrait2_edit = QLineEdit()
        preview_portrait2_row = self._make_file_row(
            self.preview_portrait2_edit,
            lambda: self._pick_and_store_image(self.preview_portrait2_edit, "resources/portraits", "选择示例立绘2"),
            lambda: self._clear_line(self.preview_portrait2_edit),
            "选择图片",
        )

        sec_preview_assets = _CollapsibleSection("预览示例图（仅编辑器）")
        form_prev = QFormLayout()
        form_prev.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_prev.addRow("示例背景", preview_bg_row)
        form_prev.addRow("示例立绘1", preview_portrait_row)
        form_prev.addRow("示例立绘2", preview_portrait2_row)
        sec_preview_assets.setContentLayout(form_prev)

        preview_wrap = QVBoxLayout()
        w, h = self.base_size
        preview_label = QLabel(f"预览（基于 {w}x{h}，比例固定；立绘点为中心）")
        self.preview = LayoutPreview(base_size=self.base_size, path_base=self.project_dir)
        self.preview.layoutEdited.connect(self._on_preview_edited)
        self.preview.set_align_guides(self.chk_align_guides.isChecked(), snap=self.chk_align_snap.isChecked())
        self.preview.set_grid_snap(self.chk_grid_snap.isChecked(), self.grid_size.value())
        preview_wrap.addWidget(preview_label)
        self.preview_container = AspectRatioContainer(self.preview, self.base_size)
        preview_wrap.addWidget(self.preview_container)

        # left pane in scroll area
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
        sec_help.setContentLayout(help_form)

        left_layout.addWidget(sec_help)
        left_layout.addWidget(sec_text)
        left_layout.addWidget(sec_name)
        left_layout.addWidget(sec_portrait)
        left_layout.addWidget(sec_portrait2)
        left_layout.addWidget(sec_frames)
        left_layout.addWidget(sec_hud)
        left_layout.addWidget(sec_choice)
        left_layout.addWidget(sec_preview_assets)
        left_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(left_widget)

        top_row.addWidget(scroll, 1)
        top_row.addLayout(preview_wrap, 2)
        main.addLayout(top_row)

        btn_row = QHBoxLayout()
        btn_load = QPushButton("打开布局")
        btn_save = QPushButton("保存布局")
        btn_close = QPushButton("关闭")
        btn_load.clicked.connect(self._load_file)
        btn_save.clicked.connect(self._save_file)
        btn_close.clicked.connect(self.reject)
        try:
            btn_load.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        except Exception:
            pass
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
            self.portrait_w,
            self.portrait_h,
            self.portrait_scale,
            self.portrait2_x,
            self.portrait2_y,
            self.portrait2_w,
            self.portrait2_h,
            self.portrait2_scale,
            self.text_frame_alpha,
            self.name_frame_alpha,
            self.hud_x,
            self.hud_y,
            self.hud_spacing,
            self.hud_scale,
            self.hud_selected_zoom,
            self.choice_x,
            self.choice_y,
            self.choice_spacing,
            self.choice_scale,
            self.choice_hover_zoom,
            self.choice_font_size,
            self.choice_overlay_alpha,
            self.choice_bg_alpha,
            self.choice_pad_x,
            self.choice_pad_y,
            self.choice_min_w,
            self.choice_min_h,
        ]:
            sp.valueChanged.connect(self._update_preview)

        for ed in [
            self.text_frame_edit,
            self.name_frame_edit,
            self.preview_bg_edit,
            self.preview_portrait_edit,
            self.preview_portrait2_edit,
            self.hud_color_edit,
            self.hud_hover_color_edit,
            self.choice_color_edit,
            self.choice_hover_color_edit,
            self.choice_bg_edit,
        ]:
            ed.editingFinished.connect(self._update_preview)

        self.chk_grid_snap.toggled.connect(self._update_preview)
        self.chk_align_guides.toggled.connect(self._update_preview)
        self.chk_align_snap.toggled.connect(self._update_preview)
        self.grid_size.valueChanged.connect(self._update_preview)
        self.hud_enabled_chk.toggled.connect(self._update_preview)
        self.hud_orient_combo.currentIndexChanged.connect(self._update_preview)
        self.choice_enabled_chk.toggled.connect(self._update_preview)
        self.choice_orient_combo.currentIndexChanged.connect(self._update_preview)
        for w in self._hud_button_mode:
            w.currentIndexChanged.connect(self._update_preview)
        for w in self._hud_button_text:
            w.editingFinished.connect(self._update_preview)
        for w in self._hud_button_image:
            w.editingFinished.connect(self._update_preview)
        for w in self._hud_button_image_scale:
            w.valueChanged.connect(self._update_preview)
        self._update_preview()
        self._initialized = True

    def _make_pick_image_handler(self, target_edit: QLineEdit, subfolder: str, title: str):
        return lambda: self._pick_and_store_image(target_edit, subfolder, title)

    def _hex_to_rgb(self, text: str, fallback=(255, 255, 255)) -> list[int]:
        s = (text or "").strip()
        if s.startswith("#"):
            s = s[1:]
        if len(s) == 3:
            s = "".join([ch * 2 for ch in s])
        if len(s) != 6:
            return [int(fallback[0]), int(fallback[1]), int(fallback[2])]
        try:
            r = int(s[0:2], 16)
            g = int(s[2:4], 16)
            b = int(s[4:6], 16)
            return [max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))]
        except Exception:
            return [int(fallback[0]), int(fallback[1]), int(fallback[2])]

    def _rgb_to_hex(self, rgb, fallback="#FFFFFF") -> str:
        try:
            if isinstance(rgb, (list, tuple)) and len(rgb) >= 3:
                r = max(0, min(255, int(rgb[0])))
                g = max(0, min(255, int(rgb[1])))
                b = max(0, min(255, int(rgb[2])))
                return f"#{r:02X}{g:02X}{b:02X}"
        except Exception:
            pass
        return fallback

    def _pick_color(self, edit: QLineEdit) -> None:
        try:
            cur = QColor((edit.text() or "").strip() or "#FFFFFF")
        except Exception:
            cur = QColor("#FFFFFF")
        try:
            chosen = QColorDialog.getColor(cur, self, "选择颜色")
        except Exception:
            chosen = QColorDialog.getColor()
        if chosen and chosen.isValid():
            edit.setText(chosen.name(QColor.NameFormat.HexRgb))
            self._update_preview()

    def _make_color_row(self, edit: QLineEdit) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(edit)
        btn = QPushButton("选色")
        btn.clicked.connect(lambda: self._pick_color(edit))
        try:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        except Exception:
            pass
        layout.addWidget(btn)
        return row

    def _make_file_row(self, edit: QLineEdit, pick_handler, clear_handler=None, pick_label="选择") -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(edit)
        btn_pick = QPushButton(pick_label)
        btn_pick.clicked.connect(pick_handler)
        try:
            btn_pick.setCursor(Qt.CursorShape.PointingHandCursor)
        except Exception:
            pass
        layout.addWidget(btn_pick)
        if clear_handler:
            btn_clear = QPushButton("清空")
            btn_clear.clicked.connect(clear_handler)
            try:
                btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
            except Exception:
                pass
            layout.addWidget(btn_clear)
        return row

    def _clear_line(self, edit: QLineEdit):
        edit.setText("")
        self._update_preview()

    def _pick_and_store_image(self, target_edit: QLineEdit, subfolder: str, title: str):
        start = str((self.project_dir / subfolder) if self.project_dir else "")
        path_str, _ = QFileDialog.getOpenFileName(self, title, start, "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path_str:
            return
        stored = self._store_into_project(Path(path_str), subfolder)
        target_edit.setText(stored)
        self._update_preview()

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
            # Ensure preview image line edits take effect immediately.
            self._update_preview()
            self._dirty = False
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
            self._dirty = False
            QMessageBox.information(self, "保存成功", f"布局已保存到\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", f"无法保存布局：{exc}")

    def _update_preview(self):
        if self._updating:
            return
        if self._initialized and not self._suppress_dirty:
            self._dirty = True
        self.preview.set_grid_snap(self.chk_grid_snap.isChecked(), self.grid_size.value())
        self.preview.set_align_guides(self.chk_align_guides.isChecked(), snap=self.chk_align_snap.isChecked())
        self.preview.update_layout(self._collect_layout_data())

    def _on_preview_edited(self, changed: dict):
        # changed contains only layout geometry keys; keep other keys from current fields
        self._updating = True
        self._dirty = True
        try:
            ta = changed.get("text_area") or [40, 400, 720, 180]
            na = changed.get("name_area") or [40, 360, 200, 32]
            pp = changed.get("portrait_pos") or [0, 0]
            psz = changed.get("portrait_size") or [0, 0]
            ps = changed.get("portrait_scale", 1.0)
            pp2 = changed.get("portrait2_pos") or [0, 0]
            psz2 = changed.get("portrait2_size") or [0, 0]
            ps2 = changed.get("portrait2_scale", 1.0)

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
            if isinstance(psz, (list, tuple)) and len(psz) == 2:
                self.portrait_w.setValue(max(0, int(psz[0])))
                self.portrait_h.setValue(max(0, int(psz[1])))
            self.portrait_scale.setValue(float(ps))

            self.portrait2_x.setValue(int(pp2[0]))
            self.portrait2_y.setValue(int(pp2[1]))
            if isinstance(psz2, (list, tuple)) and len(psz2) == 2:
                self.portrait2_w.setValue(max(0, int(psz2[0])))
                self.portrait2_h.setValue(max(0, int(psz2[1])))
            self.portrait2_scale.setValue(float(ps2))

            hp = changed.get("hud_button_pos")
            hs = changed.get("hud_button_scale")
            if isinstance(hp, (list, tuple)) and len(hp) >= 2:
                self.hud_x.setValue(int(hp[0]))
                self.hud_y.setValue(int(hp[1]))
            if hs is not None:
                try:
                    self.hud_scale.setValue(float(hs))
                except Exception:
                    pass

            cp = changed.get("choice_button_pos")
            cs = changed.get("choice_button_scale")
            if isinstance(cp, (list, tuple)) and len(cp) >= 2:
                self.choice_x.setValue(int(cp[0]))
                self.choice_y.setValue(int(cp[1]))
            if cs is not None:
                try:
                    self.choice_scale.setValue(float(cs))
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            self._updating = False
        self._update_preview()

    def closeEvent(self, event):
        if self._confirm_close():
            event.accept()
        else:
            event.ignore()

    def reject(self):
        # handle ESC / cancel button
        if self._confirm_close():
            super().reject()

    def _confirm_close(self) -> bool:
        if not self._dirty:
            return True
        msg = QMessageBox(self)
        msg.setWindowTitle("确认关闭")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText("检测到未保存的 UI 布局更改，确定要关闭吗？")
        msg.setInformativeText("建议先保存，避免丢失修改。")
        btn_save = msg.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
        btn_discard = msg.addButton("不保存", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_save)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == btn_cancel:
            return False
        if clicked == btn_save:
            self._suppress_dirty = True
            try:
                self._save_file()
            finally:
                self._suppress_dirty = False
            return not self._dirty
        if clicked == btn_discard:
            return True
        return False

    def _collect_layout_data(self) -> dict:
        hud_buttons: list[dict] = []
        for idx, base in enumerate(self._hud_default_buttons):
            action = base["action"]
            mode = self._hud_button_mode[idx].currentIndex()  # 0 text / 1 image
            style = "image" if mode == 1 else "text"
            label = self._hud_button_text[idx].text().strip() or base["label"]
            image = self._hud_button_image[idx].text().strip()
            try:
                img_scale = float(self._hud_button_image_scale[idx].value())
            except Exception:
                img_scale = 1.0
            hud_buttons.append({
                "action": action,
                "label": label,
                "style": style,
                "image": image,
                "image_scale": float(img_scale),
            })

        return {
            "text_area": [self.text_x.value(), self.text_y.value(), self.text_w.value(), self.text_h.value()],
            "name_area": [self.name_x.value(), self.name_y.value(), self.name_w.value(), self.name_h.value()],
            "portrait_pos": [self.portrait_x.value(), self.portrait_y.value()],
            "portrait_size": [self.portrait_w.value(), self.portrait_h.value()],
            "portrait_scale": float(self.portrait_scale.value()),
            "portrait2_pos": [self.portrait2_x.value(), self.portrait2_y.value()],
            "portrait2_size": [self.portrait2_w.value(), self.portrait2_h.value()],
            "portrait2_scale": float(self.portrait2_scale.value()),
            "text_frame_image": self.text_frame_edit.text().strip(),
            "text_frame_alpha": int(self.text_frame_alpha.value()),
            "name_frame_image": self.name_frame_edit.text().strip(),
            "name_frame_alpha": int(self.name_frame_alpha.value()),
            "hud_buttons_enabled": bool(self.hud_enabled_chk.isChecked()),
            "hud_button_orientation": "horizontal" if self.hud_orient_combo.currentIndex() == 1 else "vertical",
            "hud_button_pos": [int(self.hud_x.value()), int(self.hud_y.value())],
            "hud_button_spacing": int(self.hud_spacing.value()),
            "hud_button_scale": float(self.hud_scale.value()),
            "hud_button_selected_zoom": float(self.hud_selected_zoom.value()),
            "hud_button_color": self._hex_to_rgb(self.hud_color_edit.text(), fallback=(255, 255, 255)),
            "hud_button_hover_color": self._hex_to_rgb(self.hud_hover_color_edit.text(), fallback=(255, 255, 255)),
            "hud_buttons": hud_buttons,

            "choice_buttons_enabled": bool(self.choice_enabled_chk.isChecked()),
            "choice_button_orientation": "horizontal" if self.choice_orient_combo.currentIndex() == 1 else "vertical",
            "choice_button_pos": [int(self.choice_x.value()), int(self.choice_y.value())],
            "choice_button_spacing": int(self.choice_spacing.value()),
            "choice_button_scale": float(self.choice_scale.value()),
            "choice_button_hover_zoom": float(self.choice_hover_zoom.value()),
            "choice_button_font_size": int(self.choice_font_size.value()),
            "choice_button_text_color": self._hex_to_rgb(self.choice_color_edit.text(), fallback=(230, 230, 230)),
            "choice_button_text_hover_color": self._hex_to_rgb(self.choice_hover_color_edit.text(), fallback=(255, 255, 255)),
            "choice_overlay_alpha": int(self.choice_overlay_alpha.value()),
            "choice_button_bg_image": self.choice_bg_edit.text().strip(),
            "choice_button_bg_alpha": int(self.choice_bg_alpha.value()),
            "choice_button_padding": [int(self.choice_pad_x.value()), int(self.choice_pad_y.value())],
            "choice_button_min_size": [int(self.choice_min_w.value()), int(self.choice_min_h.value())],

            "preview_background": self.preview_bg_edit.text().strip(),
            "preview_portrait": self.preview_portrait_edit.text().strip(),
            "preview_portrait2": self.preview_portrait2_edit.text().strip(),
        }

    def _apply_layout_data(self, data: dict):
        ta = data.get("text_area") or [40, 400, 720, 180]
        na = data.get("name_area") or [40, 360, 200, 32]
        pp = data.get("portrait_pos") or [0, 0]
        psz = data.get("portrait_size") or [0, 0]
        ps = data.get("portrait_scale", 1.0)
        pp2 = data.get("portrait2_pos") or [0, 0]
        psz2 = data.get("portrait2_size") or [0, 0]
        ps2 = data.get("portrait2_scale", 1.0)
        self._suppress_dirty = True
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
            if isinstance(psz, (list, tuple)) and len(psz) == 2:
                self.portrait_w.setValue(max(0, int(psz[0])))
                self.portrait_h.setValue(max(0, int(psz[1])))
            self.portrait_scale.setValue(float(ps))

            self.portrait2_x.setValue(int(pp2[0]))
            self.portrait2_y.setValue(int(pp2[1]))
            if isinstance(psz2, (list, tuple)) and len(psz2) == 2:
                self.portrait2_w.setValue(max(0, int(psz2[0])))
                self.portrait2_h.setValue(max(0, int(psz2[1])))
            self.portrait2_scale.setValue(float(ps2))

            self.text_frame_edit.setText(str(data.get("text_frame_image") or ""))
            self.name_frame_edit.setText(str(data.get("name_frame_image") or ""))
            try:
                self.text_frame_alpha.setValue(int(data.get("text_frame_alpha", 255)))
            except Exception:
                self.text_frame_alpha.setValue(255)
            try:
                self.name_frame_alpha.setValue(int(data.get("name_frame_alpha", 255)))
            except Exception:
                self.name_frame_alpha.setValue(255)

            self.preview_bg_edit.setText(str(data.get("preview_background") or ""))
            self.preview_portrait_edit.setText(str(data.get("preview_portrait") or ""))
            self.preview_portrait2_edit.setText(str(data.get("preview_portrait2") or ""))

            # HUD button group
            self.hud_enabled_chk.setChecked(bool(data.get("hud_buttons_enabled", False)))
            orient = str(data.get("hud_button_orientation") or "vertical").strip().lower()
            self.hud_orient_combo.setCurrentIndex(1 if orient in {"horizontal", "h", "row", "x"} else 0)
            pos = data.get("hud_button_pos")
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                try:
                    self.hud_x.setValue(int(pos[0]))
                    self.hud_y.setValue(int(pos[1]))
                except Exception:
                    pass
            try:
                self.hud_spacing.setValue(int(data.get("hud_button_spacing", 10) or 10))
            except Exception:
                self.hud_spacing.setValue(10)
            try:
                self.hud_scale.setValue(float(data.get("hud_button_scale", 1.0) or 1.0))
            except Exception:
                self.hud_scale.setValue(1.0)
            try:
                self.hud_selected_zoom.setValue(float(data.get("hud_button_selected_zoom", 1.08) or 1.08))
            except Exception:
                self.hud_selected_zoom.setValue(1.08)
            self.hud_color_edit.setText(self._rgb_to_hex(data.get("hud_button_color"), "#FFFFFF"))
            self.hud_hover_color_edit.setText(
                self._rgb_to_hex(data.get("hud_button_hover_color", data.get("hud_button_color")), "#FFFFFF")
            )

            buttons = data.get("hud_buttons")
            by_action = {}
            if isinstance(buttons, list):
                for it in buttons:
                    if isinstance(it, dict) and it.get("action"):
                        by_action[str(it.get("action"))] = it
            for idx, base in enumerate(self._hud_default_buttons):
                action = base["action"]
                it = by_action.get(action, {})
                style = str(it.get("style") or "text").strip().lower()
                self._hud_button_mode[idx].setCurrentIndex(1 if style == "image" else 0)
                self._hud_button_text[idx].setText(str(it.get("label") or base["label"]))
                self._hud_button_image[idx].setText(str(it.get("image") or it.get("image_path") or ""))
                try:
                    self._hud_button_image_scale[idx].setValue(float(it.get("image_scale", 1.0) or 1.0))
                except Exception:
                    self._hud_button_image_scale[idx].setValue(1.0)

            # choice button group
            self.choice_enabled_chk.setChecked(bool(data.get("choice_buttons_enabled", False)))
            orient = str(data.get("choice_button_orientation") or "vertical").strip().lower()
            self.choice_orient_combo.setCurrentIndex(1 if orient in {"horizontal", "h", "row", "x"} else 0)
            pos = data.get("choice_button_pos")
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                try:
                    self.choice_x.setValue(int(pos[0]))
                    self.choice_y.setValue(int(pos[1]))
                except Exception:
                    pass
            try:
                self.choice_spacing.setValue(int(data.get("choice_button_spacing", 12) or 12))
            except Exception:
                self.choice_spacing.setValue(12)
            try:
                self.choice_scale.setValue(float(data.get("choice_button_scale", 1.0) or 1.0))
            except Exception:
                self.choice_scale.setValue(1.0)
            try:
                self.choice_hover_zoom.setValue(float(data.get("choice_button_hover_zoom", 1.08) or 1.08))
            except Exception:
                self.choice_hover_zoom.setValue(1.08)
            try:
                self.choice_font_size.setValue(int(data.get("choice_button_font_size", 20) or 20))
            except Exception:
                self.choice_font_size.setValue(20)
            try:
                self.choice_overlay_alpha.setValue(int(data.get("choice_overlay_alpha", 180) or 180))
            except Exception:
                self.choice_overlay_alpha.setValue(180)
            self.choice_color_edit.setText(self._rgb_to_hex(data.get("choice_button_text_color"), "#E6E6E6"))
            self.choice_hover_color_edit.setText(
                self._rgb_to_hex(data.get("choice_button_text_hover_color", data.get("choice_button_text_color")), "#FFFFFF")
            )
            self.choice_bg_edit.setText(str(data.get("choice_button_bg_image") or ""))
            try:
                self.choice_bg_alpha.setValue(int(data.get("choice_button_bg_alpha", 255) or 255))
            except Exception:
                self.choice_bg_alpha.setValue(255)
            pad = data.get("choice_button_padding")
            if isinstance(pad, (list, tuple)) and len(pad) >= 2:
                try:
                    self.choice_pad_x.setValue(int(pad[0]))
                    self.choice_pad_y.setValue(int(pad[1]))
                except Exception:
                    pass
            ms = data.get("choice_button_min_size")
            if isinstance(ms, (list, tuple)) and len(ms) >= 2:
                try:
                    self.choice_min_w.setValue(int(ms[0]))
                    self.choice_min_h.setValue(int(ms[1]))
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            self._suppress_dirty = False


__all__ = ["UILayoutDesigner"]