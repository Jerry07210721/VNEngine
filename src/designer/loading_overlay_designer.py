# -*- coding: utf-8 -*-
"""Loading overlay designer dialog.

This dialog mirrors the interaction model of the main menu designer:
- Left: parameter panels (collapsible)
- Right: letterboxed preview canvas
- Preview supports mouse drag + corner resize, with optional grid/align snapping.

Config is stored in game_config.loading_overlay.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any, Optional

from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
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


_COMPONENTS: list[str] = ["logo", "title", "message", "subtitle", "bar", "percent"]


def _rect_list(val: Any, default: list[int]) -> list[int]:
    if isinstance(val, (list, tuple)) and len(val) == 4:
        try:
            return [int(val[0]), int(val[1]), int(val[2]), int(val[3])]
        except Exception:
            return list(default)
    return list(default)


def _color_list(val: Any, default: list[int]) -> list[int]:
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("#") and len(s) == 7:
            try:
                return [int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16)]
            except Exception:
                return list(default)
    if isinstance(val, (list, tuple)) and len(val) == 3:
        try:
            return [max(0, min(255, int(val[0]))), max(0, min(255, int(val[1]))), max(0, min(255, int(val[2])))]
        except Exception:
            return list(default)
    return list(default)


def _normalize_loading_overlay_cfg(raw: Any, base_size: tuple[int, int]) -> dict[str, Any]:
    w, h = max(1, int(base_size[0])), max(1, int(base_size[1]))
    cfg = raw if isinstance(raw, dict) else {}

    # defaults mirror runtime fallbacks
    bar_w = min(420, w - 120)
    out: dict[str, Any] = {
        "enabled": bool(cfg.get("enabled", True)),
        "use_on_load_game": bool(cfg.get("use_on_load_game", True)),
        "use_on_enter_menu": bool(cfg.get("use_on_enter_menu", True)),
        "use_on_start_game": bool(cfg.get("use_on_start_game", True)),
        "use_on_load_save": bool(cfg.get("use_on_load_save", True)),
        "show_logo": bool(cfg.get("show_logo", True)),
        "show_title": bool(cfg.get("show_title", True)),
        "show_message": bool(cfg.get("show_message", True)),
        "show_subtitle": bool(cfg.get("show_subtitle", True)),
        "show_bar": bool(cfg.get("show_bar", True)),
        "background_color": _color_list(cfg.get("background_color"), [16, 18, 26]),
        "background_alpha": int(cfg.get("background_alpha", 255) or 255),
        "background_image": str(cfg.get("background_image", "") or ""),
        "logo_image": str(cfg.get("logo_image", "") or ""),
        "logo_rect": _rect_list(cfg.get("logo_rect"), [w // 2 - 60, h // 2 - 180, 120, 120]),
        "title_text": str(cfg.get("title_text", "VNEngine") or "VNEngine"),
        "title_rect": _rect_list(cfg.get("title_rect"), [0, h // 2 - 90, w, 60]),
        "title_style": dict(cfg.get("title_style") or {}),
        "message_template": str(cfg.get("message_template", "{message}") or "{message}"),
        "message_rect": _rect_list(cfg.get("message_rect"), [0, h // 2 - 30, w, 40]),
        "message_style": dict(cfg.get("message_style") or {}),
        "subtitle_template": str(cfg.get("subtitle_template", "{subtitle}") or "{subtitle}"),
        "subtitle_rect": _rect_list(cfg.get("subtitle_rect"), [0, h // 2 + 4, w, 40]),
        "subtitle_style": dict(cfg.get("subtitle_style") or {}),
        "bar_rect": _rect_list(cfg.get("bar_rect"), [w // 2 - bar_w // 2, h // 2 + 44, bar_w, 10]),
        "bar_bg_color": _color_list(cfg.get("bar_bg_color"), [60, 60, 70]),
        "bar_fg_color": _color_list(cfg.get("bar_fg_color"), [110, 160, 255]),
        "bar_radius": int(cfg.get("bar_radius", 6) or 6),
        "show_percent": bool(cfg.get("show_percent", True)),
        "percent_template": str(cfg.get("percent_template", "{percent}%") or "{percent}%"),
        "percent_rect": _rect_list(cfg.get("percent_rect"), [0, (h // 2 + 44) + 10 + 8, w, 28]),
        "percent_style": dict(cfg.get("percent_style") or {}),
    }

    out["background_alpha"] = max(0, min(255, int(out.get("background_alpha", 255))))
    out["bar_radius"] = max(0, min(30, int(out.get("bar_radius", 6))))

    return out


class _AspectRatioCanvas(QWidget):
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

    def base_rect_to_widget(self, rect_vals: list[int]) -> QRect:
        x, y, w, h = rect_vals
        x1, y1 = self.base_to_widget(x, y)
        x2, y2 = self.base_to_widget(x + w, y + h)
        return QRect(x1, y1, max(1, x2 - x1), max(1, y2 - y1))


class LoadingOverlayPreview(_AspectRatioCanvas):
    """Interactive preview with drag+corner-resize for loading overlay components."""

    layoutEdited = pyqtSignal(dict)

    def __init__(self, project_dir: Optional[Path], base_size: tuple[int, int], parent: Optional[QWidget] = None):
        super().__init__(base_size, parent)
        self.project_dir = project_dir
        self.setMouseTracking(True)
        self.setMinimumSize(520, 320)

        self._cfg: dict[str, Any] = {}
        self._bg_pixmap: Optional[QPixmap] = None
        self._logo_pixmap: Optional[QPixmap] = None
        self._bg_path: str = ""
        self._logo_path: str = ""

        self._selected: str | None = None
        self._hovered: str | None = None
        self._drag_mode: str | None = None  # 'move' | 'resize'
        self._drag_handle: str | None = None
        self._drag_start_pos: tuple[float, float] | None = None
        self._drag_start_rect: list[int] | None = None

        self._handle_px = 10
        self._min_w = 10
        self._min_h = 10

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
        self._cfg = cfg or {}
        # Avoid reloading pixmaps from disk on every tiny UI change.
        bg_path = str(self._cfg.get("background_image") or "")
        if bg_path != self._bg_path:
            self._bg_path = bg_path
            self._load_bg(bg_path)
        logo_path = str(self._cfg.get("logo_image") or "")
        if logo_path != self._logo_path:
            self._logo_path = logo_path
            self._load_logo(logo_path)
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
                px = QPixmap(str(resolved))
                self._bg_pixmap = px if not px.isNull() else None
                return
            except Exception:
                pass
        self._bg_pixmap = None

    def _load_logo(self, path_str: str):
        resolved = self._resolve(path_str)
        if resolved and resolved.exists():
            try:
                px = QPixmap(str(resolved))
                self._logo_pixmap = px if not px.isNull() else None
                return
            except Exception:
                pass
        self._logo_pixmap = None

    def _component_rect(self, key: str) -> list[int]:
        rect_key = f"{key}_rect" if key not in {"bar", "percent"} else f"{key}_rect"
        if key == "bar":
            rect_key = "bar_rect"
        if key == "percent":
            rect_key = "percent_rect"
        val = self._cfg.get(rect_key)
        if isinstance(val, list) and len(val) == 4:
            return [int(val[0]), int(val[1]), max(1, int(val[2])), max(1, int(val[3]))]
        return [0, 0, 10, 10]

    def _set_component_rect(self, key: str, rect_vals: list[int]) -> None:
        r = [int(rect_vals[0]), int(rect_vals[1]), max(1, int(rect_vals[2])), max(1, int(rect_vals[3]))]
        if key == "logo":
            self._cfg["logo_rect"] = r
        elif key == "title":
            self._cfg["title_rect"] = r
        elif key == "message":
            self._cfg["message_rect"] = r
        elif key == "subtitle":
            self._cfg["subtitle_rect"] = r
        elif key == "bar":
            self._cfg["bar_rect"] = r
        elif key == "percent":
            self._cfg["percent_rect"] = r

    def _handles_for_rect(self, r: QRect) -> dict[str, QRect]:
        hs = self._handle_px
        return {
            "tl": QRect(r.left() - hs // 2, r.top() - hs // 2, hs, hs),
            "tr": QRect(r.right() - hs // 2, r.top() - hs // 2, hs, hs),
            "bl": QRect(r.left() - hs // 2, r.bottom() - hs // 2, hs, hs),
            "br": QRect(r.right() - hs // 2, r.bottom() - hs // 2, hs, hs),
        }

    def _hit_test(self, pos) -> tuple[str | None, str | None]:
        # returns (component, handle)
        for key in reversed(_COMPONENTS):
            r = self.base_rect_to_widget(self._component_rect(key))
            if not r.contains(pos):
                continue
            handles = self._handles_for_rect(r)
            for hkey, hr in handles.items():
                if hr.contains(pos):
                    return key, hkey
            return key, None
        return None, None

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        comp, handle = self._hit_test(event.position().toPoint())
        self._selected = comp
        self._drag_handle = handle
        if comp is None:
            self._drag_mode = None
            self.update()
            return
        bx, by = self.widget_to_base(event.position().x(), event.position().y())
        self._drag_start_pos = (bx, by)
        self._drag_start_rect = list(self._component_rect(comp))
        self._drag_mode = "resize" if handle else "move"
        self.update()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        pos = event.position().toPoint()

        if self._drag_mode and self._selected and self._drag_start_pos and self._drag_start_rect:
            bx, by = self.widget_to_base(event.position().x(), event.position().y())
            sx, sy = self._drag_start_pos
            dx = bx - sx
            dy = by - sy

            r0 = list(self._drag_start_rect)
            r = list(r0)

            if self._drag_mode == "move":
                r[0] = int(round(r0[0] + dx))
                r[1] = int(round(r0[1] + dy))
            else:
                handle = self._drag_handle or "br"
                x, y, w, h = r0
                if handle in {"tl", "bl"}:
                    nx = int(round(x + dx))
                    nw = int(round((x + w) - nx))
                    r[0] = nx
                    r[2] = max(self._min_w, nw)
                if handle in {"tl", "tr"}:
                    ny = int(round(y + dy))
                    nh = int(round((y + h) - ny))
                    r[1] = ny
                    r[3] = max(self._min_h, nh)
                if handle in {"tr", "br"}:
                    r[2] = max(self._min_w, int(round(w + dx)))
                if handle in {"bl", "br"}:
                    r[3] = max(self._min_h, int(round(h + dy)))

            self._active_guides = []

            # grid snap
            if self._grid_snap_enabled:
                g = max(1, int(self._grid_size))
                r[0] = int(round(r[0] / g) * g)
                r[1] = int(round(r[1] / g) * g)
                if self._drag_mode == "resize":
                    r[2] = max(self._min_w, int(round(r[2] / g) * g))
                    r[3] = max(self._min_h, int(round(r[3] / g) * g))

            # align snap vs other components
            if self._align_guides_enabled and self._align_snap_enabled:
                tx1, ty1, tw, th = r
                tx2, ty2 = tx1 + tw, ty1 + th
                tcx, tcy = tx1 + tw / 2.0, ty1 + th / 2.0

                best_dx: float | None = None
                best_guide_x: float | None = None
                best_dy: float | None = None
                best_guide_y: float | None = None

                for other in _COMPONENTS:
                    if other == self._selected:
                        continue
                    ox, oy, ow, oh = self._component_rect(other)
                    ox2, oy2 = ox + ow, oy + oh
                    ocx, ocy = ox + ow / 2.0, oy + oh / 2.0

                    for cand in (ox, ocx, ox2):
                        for t in (tx1, tcx, tx2):
                            d = float(cand) - float(t)
                            if abs(d) <= self._align_threshold:
                                if best_dx is None or abs(d) < abs(best_dx):
                                    best_dx = d
                                    best_guide_x = float(cand)

                    for cand in (oy, ocy, oy2):
                        for t in (ty1, tcy, ty2):
                            d = float(cand) - float(t)
                            if abs(d) <= self._align_threshold:
                                if best_dy is None or abs(d) < abs(best_dy):
                                    best_dy = d
                                    best_guide_y = float(cand)

                if best_dx is not None:
                    r[0] = int(round(r[0] + best_dx))
                    self._active_guides.append(("v", float(best_guide_x or 0.0)))
                if best_dy is not None:
                    r[1] = int(round(r[1] + best_dy))
                    self._active_guides.append(("h", float(best_guide_y or 0.0)))

            self._set_component_rect(self._selected, r)
            self.layoutEdited.emit(dict(self._cfg))
            self.update()
            return

        comp, handle = self._hit_test(pos)
        self._hovered = comp
        self.update()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_mode = None
        self._drag_handle = None
        self._drag_start_pos = None
        self._drag_start_rect = None
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        base_w, base_h = self._base_size
        scale, ox, oy, view_w, view_h = self._transform()

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # letterbox background
        p.fillRect(self.rect(), QColor(28, 28, 30))

        view = QRect(ox, oy, view_w, view_h)

        # background
        bg_rgb = _color_list(self._cfg.get("background_color"), [16, 18, 26])
        alpha = int(self._cfg.get("background_alpha", 255) or 255)
        alpha = max(0, min(255, alpha))
        if self._bg_pixmap is not None:
            try:
                p.setOpacity(alpha / 255.0)
                p.drawPixmap(view, self._bg_pixmap)
                p.setOpacity(1.0)
            except Exception:
                p.fillRect(view, QColor(bg_rgb[0], bg_rgb[1], bg_rgb[2], alpha))
        else:
            p.fillRect(view, QColor(bg_rgb[0], bg_rgb[1], bg_rgb[2], alpha))

        # helper: draw component box + label/text
        def _safe_format(tpl: str, mapping: dict[str, str]) -> str:
            try:
                class _SafeDict(dict):
                    def __missing__(self, k):
                        return ""

                return str(tpl or "").format_map(_SafeDict(mapping))
            except Exception:
                return str(tpl or "")

        def _text_style(name: str) -> dict[str, Any]:
            st = self._cfg.get(name)
            return dict(st) if isinstance(st, dict) else {}

        def _font_from_style(st: dict[str, Any], default_size: int, *, bold_default: bool) -> QFont:
            try:
                size = int(st.get("size", default_size) or default_size)
            except Exception:
                size = int(default_size)
            size = max(8, min(96, int(size)))
            family = str(st.get("family", "Microsoft YaHei") or "Microsoft YaHei")
            f = QFont(family, int(size))
            try:
                f.setBold(bool(st.get("bold", bold_default)))
            except Exception:
                f.setBold(bool(bold_default))
            return f

        def _align_flags(st: dict[str, Any]) -> Qt.AlignmentFlag:
            a = str(st.get("align", "center") or "center").lower()
            if a == "left":
                ha = Qt.AlignmentFlag.AlignLeft
            elif a == "right":
                ha = Qt.AlignmentFlag.AlignRight
            else:
                ha = Qt.AlignmentFlag.AlignHCenter
            return ha | Qt.AlignmentFlag.AlignVCenter

        def _draw_text_in_rect(text: str, rect: QRect, *, st: dict[str, Any], default_color: QColor) -> None:
            if st.get("visible", True) is False:
                return
            p.setFont(_font_from_style(st, int(st.get("size", 24) or 24), bold_default=bool(st.get("bold", False))))
            rgb = _color_list(st.get("color"), [default_color.red(), default_color.green(), default_color.blue()])
            p.setPen(QColor(rgb[0], rgb[1], rgb[2]))
            p.drawText(rect, _align_flags(st), str(text or ""))

        def draw_component(key: str, label: str, *, fill: QColor | None = None, text: str | None = None, style_key: str | None = None):
            rect_base = self._component_rect(key)
            r = self.base_rect_to_widget(rect_base)
            if fill is not None:
                p.fillRect(r, fill)

            is_sel = key == self._selected
            is_hover = key == self._hovered
            pen = QPen(QColor(120, 160, 255) if is_sel else QColor(180, 180, 180))
            pen.setWidth(2 if is_sel else 1)
            p.setPen(pen)
            p.drawRect(r)

            # label
            try:
                p.setPen(QColor(220, 220, 230))
                p.setFont(QFont("Microsoft YaHei", 10))
                p.drawText(r.adjusted(6, 4, -6, -4), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, label)
            except Exception:
                pass

            # sample text rendering
            if text is not None and style_key:
                try:
                    st = _text_style(style_key)
                    _draw_text_in_rect(text, r.adjusted(8, 14, -8, -8), st=st, default_color=QColor(210, 210, 210))
                except Exception:
                    pass

            # handles
            if is_sel:
                p.setBrush(QColor(120, 160, 255))
                p.setPen(Qt.PenStyle.NoPen)
                for hr in self._handles_for_rect(r).values():
                    p.drawRect(hr)

        # draw components
        sample = {
            "message": "加载资源...",
            "subtitle": "demo_project",
            "percent": "62",
            "pct": "62",
        }

        show_logo = bool(self._cfg.get("show_logo", True))
        show_title = bool(self._cfg.get("show_title", True))
        show_message = bool(self._cfg.get("show_message", True))
        show_subtitle = bool(self._cfg.get("show_subtitle", True))
        show_bar = bool(self._cfg.get("show_bar", True))

        if show_logo and self._logo_pixmap is not None:
            lr = self.base_rect_to_widget(self._component_rect("logo"))
            try:
                p.drawPixmap(lr, self._logo_pixmap)
            except Exception:
                pass
        draw_component("logo", "Logo" + ("（隐藏）" if not show_logo else ""))

        title_text = str(self._cfg.get("title_text", "VNEngine") or "VNEngine")
        draw_component("title", "标题" + ("（隐藏）" if not show_title else ""), text=(title_text if show_title else None), style_key="title_style")

        msg_tpl = str(self._cfg.get("message_template", "{message}") or "{message}")
        msg_text = _safe_format(msg_tpl, sample)
        draw_component("message", "消息" + ("（隐藏）" if not show_message else ""), text=(msg_text if show_message else None), style_key="message_style")

        sub_tpl = str(self._cfg.get("subtitle_template", "{subtitle}") or "{subtitle}")
        sub_text = _safe_format(sub_tpl, sample)
        draw_component("subtitle", "副标题" + ("（隐藏）" if not show_subtitle else ""), text=(sub_text if show_subtitle else None), style_key="subtitle_style")

        # progress bar preview fill
        bar_r = self.base_rect_to_widget(self._component_rect("bar"))
        bgc = _color_list(self._cfg.get("bar_bg_color"), [60, 60, 70])
        fgc = _color_list(self._cfg.get("bar_fg_color"), [110, 160, 255])
        if show_bar:
            p.fillRect(bar_r, QColor(bgc[0], bgc[1], bgc[2]))
            fill = QRect(bar_r.left(), bar_r.top(), int(bar_r.width() * 0.62), bar_r.height())
            p.fillRect(fill, QColor(fgc[0], fgc[1], fgc[2]))
        draw_component("bar", "进度条" + ("（隐藏）" if not show_bar else ""))

        if bool(self._cfg.get("show_percent", True)):
            pct_tpl = str(self._cfg.get("percent_template", "{percent}%") or "{percent}%")
            pct_text = _safe_format(pct_tpl, sample)
            draw_component("percent", "百分比", text=pct_text, style_key="percent_style")

        # guides
        if self._align_guides_enabled and self._active_guides:
            guide_pen = QPen(QColor(255, 120, 120))
            guide_pen.setWidth(1)
            p.setPen(guide_pen)
            for axis, v in self._active_guides:
                if axis == "v":
                    x, _ = self.base_to_widget(float(v), 0)
                    p.drawLine(x, view.top(), x, view.bottom())
                else:
                    _, y = self.base_to_widget(0, float(v))
                    p.drawLine(view.left(), y, view.right(), y)

        p.end()


class LoadingOverlayDesigner(QDialog):
    def __init__(
        self,
        project_dir: Path,
        project_manager,
        base_size: tuple[int, int] = (800, 600),
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("加载遮罩样式")
        self.setMinimumSize(980, 620)
        self.project_dir = Path(project_dir) if project_dir else None
        self.project_manager = project_manager
        self.base_size = (max(1, int(base_size[0])), max(1, int(base_size[1])))

        raw = {}
        try:
            raw = (self.project_manager.project_data or {}).get("game_config", {}).get("loading_overlay")
        except Exception:
            raw = {}
        self._cfg: dict[str, Any] = _normalize_loading_overlay_cfg(raw, self.base_size)
        self._updating_ui = False
        self._initialized = False
        self._suppress_dirty = False
        self._dirty = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        # left panel (scrollable content)
        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        left_scroll = QScrollArea(self)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setMinimumWidth(380)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setWidget(left_widget)

        # right preview
        self.preview = LoadingOverlayPreview(self.project_dir, self.base_size, self)
        self.preview.layoutEdited.connect(self._on_preview_layout_edited)

        preview_wrap = QVBoxLayout()
        preview_wrap.addWidget(QLabel("加载遮罩预览（比例固定；拖拽/四角缩放）", self))
        preview_wrap.addWidget(self.preview)

        top_row.addWidget(left_scroll, 1)
        top_row.addLayout(preview_wrap, 2)
        layout.addLayout(top_row, 1)

        # --- Sections ---
        sec_general = _CollapsibleSection("启用与使用场景")
        gen_form = QFormLayout()
        self.enabled_cb = QCheckBox("启用加载遮罩")
        self.enabled_cb.setChecked(bool(self._cfg.get("enabled", True)))
        self.use_load_game_cb = QCheckBox("加载游戏/启动时使用")
        self.use_load_game_cb.setChecked(bool(self._cfg.get("use_on_load_game", True)))
        self.use_enter_menu_cb = QCheckBox("返回标题/主菜单时使用")
        self.use_enter_menu_cb.setChecked(bool(self._cfg.get("use_on_enter_menu", True)))
        self.use_start_game_cb = QCheckBox("开始游戏按钮使用")
        self.use_start_game_cb.setChecked(bool(self._cfg.get("use_on_start_game", True)))
        self.use_load_save_cb = QCheckBox("读取存档使用")
        self.use_load_save_cb.setChecked(bool(self._cfg.get("use_on_load_save", True)))
        gen_form.addRow(self.enabled_cb)
        gen_form.addRow(self.use_load_game_cb)
        gen_form.addRow(self.use_enter_menu_cb)
        gen_form.addRow(self.use_start_game_cb)
        gen_form.addRow(self.use_load_save_cb)
        sec_general.setContentLayout(gen_form)
        left_layout.addWidget(sec_general)

        sec_preview = _CollapsibleSection("预览交互")
        pv_form = QFormLayout()
        self.grid_snap_cb = QCheckBox("网格吸附")
        self.grid_snap_size = QSpinBox(); self.grid_snap_size.setRange(1, 100); self.grid_snap_size.setValue(10)
        self.align_guides_cb = QCheckBox("对齐线")
        self.align_guides_cb.setChecked(True)
        self.align_snap_cb = QCheckBox("对齐吸附")
        self.align_snap_cb.setChecked(True)
        pv_form.addRow(self.grid_snap_cb, self.grid_snap_size)
        pv_form.addRow(self.align_guides_cb)
        pv_form.addRow(self.align_snap_cb)
        sec_preview.setContentLayout(pv_form)
        left_layout.addWidget(sec_preview)

        sec_bg = _CollapsibleSection("背景")
        bgf = QFormLayout()
        self.bg_color_btn = QPushButton("选择颜色")
        self.bg_alpha = QSpinBox(); self.bg_alpha.setRange(0, 255); self.bg_alpha.setValue(int(self._cfg.get("background_alpha", 255)))
        self.bg_img = QLineEdit(str(self._cfg.get("background_image", "") or ""))
        bgf.addRow("背景色", self.bg_color_btn)
        bgf.addRow("透明度", self.bg_alpha)
        bgf.addRow("背景图", self._make_file_row(self.bg_img, self._pick_bg, with_clear=True))
        sec_bg.setContentLayout(bgf)
        left_layout.addWidget(sec_bg)

        # components sections
        self._rect_controls: dict[str, dict[str, QSpinBox]] = {}
        self._style_controls: dict[str, dict[str, Any]] = {}

        def add_rect_section(title: str, key: str):
            sec = _CollapsibleSection(title)
            wgt = QWidget()
            form = QFormLayout(wgt)
            x = QSpinBox(); y = QSpinBox(); ww = QSpinBox(); hh = QSpinBox()
            for sp in (x, y):
                sp.setRange(-9999, 9999)
            ww.setRange(1, 9999)
            hh.setRange(1, 9999)
            rx, ry, rw, rh = self._component_rect_cfg(key)
            x.setValue(rx); y.setValue(ry); ww.setValue(rw); hh.setValue(rh)
            row = QWidget(); rlay = QHBoxLayout(row); rlay.setContentsMargins(0, 0, 0, 0)
            rlay.addWidget(QLabel("x")); rlay.addWidget(x)
            rlay.addWidget(QLabel("y")); rlay.addWidget(y)
            rlay.addWidget(QLabel("w")); rlay.addWidget(ww)
            rlay.addWidget(QLabel("h")); rlay.addWidget(hh)
            form.addRow("位置/大小", row)
            sec.setContentLayout(form)
            left_layout.addWidget(sec)
            self._rect_controls[key] = {"x": x, "y": y, "w": ww, "h": hh}
            for sp in (x, y, ww, hh):
                sp.valueChanged.connect(lambda _=0, k=key: self._on_rect_changed(k))
            return sec, wgt

        sec_logo = _CollapsibleSection("Logo")
        lf = QFormLayout()
        self.show_logo_cb = QCheckBox("显示 Logo")
        self.show_logo_cb.setChecked(bool(self._cfg.get("show_logo", True)))
        lf.addRow(self.show_logo_cb)
        self.logo_img = QLineEdit(str(self._cfg.get("logo_image", "") or ""))
        lf.addRow("图片", self._make_file_row(self.logo_img, self._pick_logo, with_clear=True))
        sec_logo.setContentLayout(lf)
        left_layout.addWidget(sec_logo)
        add_rect_section("Logo 区域", "logo")

        sec_title = _CollapsibleSection("标题")
        tf = QFormLayout()
        self.show_title_cb = QCheckBox("显示标题")
        self.show_title_cb.setChecked(bool(self._cfg.get("show_title", True)))
        tf.addRow(self.show_title_cb)
        self.title_text = QLineEdit(str(self._cfg.get("title_text", "VNEngine") or "VNEngine"))
        tf.addRow("文本", self.title_text)
        self._add_style_editor(tf, "title_style", default_size=42, default_color=[220, 230, 255], allow_bold=True)
        sec_title.setContentLayout(tf)
        left_layout.addWidget(sec_title)
        add_rect_section("标题区域", "title")

        sec_msg = _CollapsibleSection("消息")
        mf = QFormLayout()
        self.show_message_cb = QCheckBox("显示消息")
        self.show_message_cb.setChecked(bool(self._cfg.get("show_message", True)))
        mf.addRow(self.show_message_cb)
        self.msg_tpl = QLineEdit(str(self._cfg.get("message_template", "{message}") or "{message}"))
        mf.addRow("模板", self.msg_tpl)
        self._add_style_editor(mf, "message_style", default_size=24, default_color=[210, 210, 210], allow_bold=True)
        sec_msg.setContentLayout(mf)
        left_layout.addWidget(sec_msg)
        add_rect_section("消息区域", "message")

        sec_sub = _CollapsibleSection("副标题")
        sf = QFormLayout()
        self.show_subtitle_cb = QCheckBox("显示副标题")
        self.show_subtitle_cb.setChecked(bool(self._cfg.get("show_subtitle", True)))
        sf.addRow(self.show_subtitle_cb)
        self.sub_tpl = QLineEdit(str(self._cfg.get("subtitle_template", "{subtitle}") or "{subtitle}"))
        sf.addRow("模板", self.sub_tpl)
        self._add_style_editor(sf, "subtitle_style", default_size=24, default_color=[170, 170, 170], allow_bold=True)
        sec_sub.setContentLayout(sf)
        left_layout.addWidget(sec_sub)
        add_rect_section("副标题区域", "subtitle")

        sec_bar = _CollapsibleSection("进度条")
        bf = QFormLayout()
        self.show_bar_cb = QCheckBox("显示进度条")
        self.show_bar_cb.setChecked(bool(self._cfg.get("show_bar", True)))
        bf.addRow(self.show_bar_cb)
        self.bar_radius = QSpinBox(); self.bar_radius.setRange(0, 30); self.bar_radius.setValue(int(self._cfg.get("bar_radius", 6)))
        self.bar_bg_btn = QPushButton("选择颜色")
        self.bar_fg_btn = QPushButton("选择颜色")
        bf.addRow("圆角", self.bar_radius)
        bf.addRow("背景色", self.bar_bg_btn)
        bf.addRow("前景色", self.bar_fg_btn)
        sec_bar.setContentLayout(bf)
        left_layout.addWidget(sec_bar)
        add_rect_section("进度条区域", "bar")

        sec_pct = _CollapsibleSection("百分比")
        pf = QFormLayout()
        self.show_pct_cb = QCheckBox("显示百分比")
        self.show_pct_cb.setChecked(bool(self._cfg.get("show_percent", True)))
        self.pct_tpl = QLineEdit(str(self._cfg.get("percent_template", "{percent}%") or "{percent}%"))
        pf.addRow(self.show_pct_cb)
        pf.addRow("模板", self.pct_tpl)
        self._add_style_editor(pf, "percent_style", default_size=18, default_color=[170, 180, 200], allow_bold=True)
        sec_pct.setContentLayout(pf)
        left_layout.addWidget(sec_pct)
        add_rect_section("百分比区域", "percent")

        left_layout.addStretch(1)

        # wire events (match menu_designer: avoid per-keystroke refresh)
        self.enabled_cb.stateChanged.connect(self._update_preview)
        self.use_load_game_cb.stateChanged.connect(self._update_preview)
        self.use_enter_menu_cb.stateChanged.connect(self._update_preview)
        self.use_start_game_cb.stateChanged.connect(self._update_preview)
        self.use_load_save_cb.stateChanged.connect(self._update_preview)
        self.bg_alpha.valueChanged.connect(self._update_preview)
        self.bg_color_btn.clicked.connect(self._pick_bg_color)
        self.bg_img.editingFinished.connect(self._update_preview)
        self.logo_img.editingFinished.connect(self._update_preview)
        self.show_logo_cb.stateChanged.connect(self._update_preview)
        self.title_text.editingFinished.connect(self._update_preview)
        self.show_title_cb.stateChanged.connect(self._update_preview)
        self.msg_tpl.editingFinished.connect(self._update_preview)
        self.show_message_cb.stateChanged.connect(self._update_preview)
        self.sub_tpl.editingFinished.connect(self._update_preview)
        self.show_subtitle_cb.stateChanged.connect(self._update_preview)
        self.bar_radius.valueChanged.connect(self._update_preview)
        self.show_bar_cb.stateChanged.connect(self._update_preview)
        self.bar_bg_btn.clicked.connect(lambda: self._pick_color_into("bar_bg_color"))
        self.bar_fg_btn.clicked.connect(lambda: self._pick_color_into("bar_fg_color"))
        self.show_pct_cb.stateChanged.connect(self._update_preview)
        self.pct_tpl.editingFinished.connect(self._update_preview)

        self.grid_snap_cb.stateChanged.connect(self._update_preview)
        self.grid_snap_size.valueChanged.connect(self._update_preview)
        self.align_guides_cb.stateChanged.connect(self._update_preview)
        self.align_snap_cb.stateChanged.connect(self._update_preview)

        self._update_color_button(self.bg_color_btn, self._cfg.get("background_color"))
        self._update_color_button(self.bar_bg_btn, self._cfg.get("bar_bg_color"))
        self._update_color_button(self.bar_fg_btn, self._cfg.get("bar_fg_color"))

        # footer (fixed)
        hint = QLabel("说明：拖拽/四角缩放预览区域可改 rect；模板支持 {message}/{subtitle}/{percent}。", self)
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

        self._update_preview()
        self._initialized = True
    def _mark_dirty(self):
        if not self._initialized or self._suppress_dirty:
            return
        self._dirty = True

    def _make_file_row(self, edit: QLineEdit, handler, *, with_clear: bool = False) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit)
        btn = QPushButton("选择")
        btn.clicked.connect(handler)
        try:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        except Exception:
            pass
        layout.addWidget(btn)
        if with_clear:
            btn_clear = QPushButton("清除")
            btn_clear.clicked.connect(lambda: (edit.setText(""), self._update_preview()))
            try:
                btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
            except Exception:
                pass
            layout.addWidget(btn_clear)
        return row


    def _add_style_editor(
        self,
        form: QFormLayout,
        style_key: str,
        *,
        default_size: int,
        default_color: list[int],
        allow_bold: bool,
    ) -> None:
        st = self._cfg.get(style_key)
        st = dict(st) if isinstance(st, dict) else {}
        size = QSpinBox(); size.setRange(8, 96)
        try:
            size.setValue(int(st.get("size", default_size) or default_size))
        except Exception:
            size.setValue(int(default_size))

        bold = QCheckBox("加粗")
        bold.setChecked(bool(st.get("bold", False)))
        if not allow_bold:
            bold.setEnabled(False)

        align = QComboBox()
        align.addItems(["left", "center", "right"])
        a = str(st.get("align", "center") or "center").lower()
        align.setCurrentText(a if a in {"left", "center", "right"} else "center")

        color_btn = QPushButton("选择颜色")
        rgb = _color_list(st.get("color"), list(default_color))
        color_btn.setText(f"RGB({rgb[0]},{rgb[1]},{rgb[2]})")

        row = QWidget(); lay = QHBoxLayout(row); lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("size")); lay.addWidget(size)
        lay.addWidget(bold)
        lay.addWidget(QLabel("align")); lay.addWidget(align)
        lay.addStretch(1)
        form.addRow("样式", row)
        form.addRow("颜色", color_btn)

        self._style_controls[style_key] = {
            "size": size,
            "bold": bold,
            "align": align,
            "color_btn": color_btn,
            "color": rgb,
            "default_color": list(default_color),
        }

        size.valueChanged.connect(self._sync_from_ui)
        bold.stateChanged.connect(self._sync_from_ui)
        align.currentIndexChanged.connect(self._sync_from_ui)
        color_btn.clicked.connect(lambda: self._pick_style_color(style_key))

    def _pick_style_color(self, style_key: str) -> None:
        c = self._style_controls.get(style_key)
        if not c:
            return
        cur = _color_list(c.get("color"), list(c.get("default_color") or [255, 255, 255]))
        col = QColorDialog.getColor(QColor(cur[0], cur[1], cur[2]), self, "选择文字颜色")
        if not col.isValid():
            return
        rgb = [col.red(), col.green(), col.blue()]
        c["color"] = rgb
        try:
            btn: QPushButton = c["color_btn"]
            btn.setText(f"RGB({rgb[0]},{rgb[1]},{rgb[2]})")
        except Exception:
            pass
        self._sync_from_ui()

    def _update_color_button(self, btn: QPushButton, rgb: Any):
        c = _color_list(rgb, [0, 0, 0])
        btn.setText(f"RGB({c[0]},{c[1]},{c[2]})")

    def _component_rect_cfg(self, key: str) -> list[int]:
        if key == "logo":
            return list(self._cfg.get("logo_rect") or [0, 0, 10, 10])
        if key == "title":
            return list(self._cfg.get("title_rect") or [0, 0, 10, 10])
        if key == "message":
            return list(self._cfg.get("message_rect") or [0, 0, 10, 10])
        if key == "subtitle":
            return list(self._cfg.get("subtitle_rect") or [0, 0, 10, 10])
        if key == "bar":
            return list(self._cfg.get("bar_rect") or [0, 0, 10, 10])
        if key == "percent":
            return list(self._cfg.get("percent_rect") or [0, 0, 10, 10])
        return [0, 0, 10, 10]

    def _set_component_rect_cfg(self, key: str, rect_vals: list[int]) -> None:
        r = [int(rect_vals[0]), int(rect_vals[1]), max(1, int(rect_vals[2])), max(1, int(rect_vals[3]))]
        if key == "logo":
            self._cfg["logo_rect"] = r
        elif key == "title":
            self._cfg["title_rect"] = r
        elif key == "message":
            self._cfg["message_rect"] = r
        elif key == "subtitle":
            self._cfg["subtitle_rect"] = r
        elif key == "bar":
            self._cfg["bar_rect"] = r
        elif key == "percent":
            self._cfg["percent_rect"] = r

    def _sync_preview_flags(self):
        self.preview.set_grid_snap(bool(self.grid_snap_cb.isChecked()), int(self.grid_snap_size.value()))
        self.preview.set_align_guides(bool(self.align_guides_cb.isChecked()), snap=bool(self.align_snap_cb.isChecked()))

    def _pick_bg_color(self):
        cur = _color_list(self._cfg.get("background_color"), [16, 18, 26])
        col = QColorDialog.getColor(QColor(cur[0], cur[1], cur[2]), self, "选择背景色")
        if not col.isValid():
            return
        self._cfg["background_color"] = [col.red(), col.green(), col.blue()]
        self._update_color_button(self.bg_color_btn, self._cfg.get("background_color"))
        self._update_preview()

    def _pick_color_into(self, key: str):
        cur = _color_list(self._cfg.get(key), [0, 0, 0])
        col = QColorDialog.getColor(QColor(cur[0], cur[1], cur[2]), self, "选择颜色")
        if not col.isValid():
            return
        self._cfg[key] = [col.red(), col.green(), col.blue()]
        if key == "bar_bg_color":
            self._update_color_button(self.bar_bg_btn, self._cfg.get(key))
        if key == "bar_fg_color":
            self._update_color_button(self.bar_fg_btn, self._cfg.get(key))
        self._update_preview()

    def _pick_bg(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择背景图", str(self.project_dir or ""), "图片 (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        self.bg_img.setText(self._store_into_project(path, "resources/images"))
        self._update_preview()

    def _pick_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择Logo", str(self.project_dir or ""), "图片 (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        self.logo_img.setText(self._store_into_project(path, "resources/images"))
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

    def _collect_cfg(self) -> dict[str, Any]:
        cfg = dict(self._cfg or {})
        cfg["enabled"] = bool(self.enabled_cb.isChecked())
        cfg["use_on_load_game"] = bool(self.use_load_game_cb.isChecked())
        cfg["use_on_enter_menu"] = bool(self.use_enter_menu_cb.isChecked())
        cfg["use_on_start_game"] = bool(self.use_start_game_cb.isChecked())
        cfg["use_on_load_save"] = bool(self.use_load_save_cb.isChecked())
        cfg["show_logo"] = bool(self.show_logo_cb.isChecked())
        cfg["show_title"] = bool(self.show_title_cb.isChecked())
        cfg["show_message"] = bool(self.show_message_cb.isChecked())
        cfg["show_subtitle"] = bool(self.show_subtitle_cb.isChecked())
        cfg["show_bar"] = bool(self.show_bar_cb.isChecked())
        cfg["background_alpha"] = int(self.bg_alpha.value())
        cfg["background_image"] = str(self.bg_img.text().strip())
        cfg["logo_image"] = str(self.logo_img.text().strip())
        cfg["title_text"] = str(self.title_text.text())
        cfg["message_template"] = str(self.msg_tpl.text())
        cfg["subtitle_template"] = str(self.sub_tpl.text())
        cfg["bar_radius"] = int(self.bar_radius.value())
        cfg["show_percent"] = bool(self.show_pct_cb.isChecked())
        cfg["percent_template"] = str(self.pct_tpl.text())

        # rects
        for key, ctrls in (self._rect_controls or {}).items():
            r = [int(ctrls["x"].value()), int(ctrls["y"].value()), int(ctrls["w"].value()), int(ctrls["h"].value())]
            if key == "logo":
                cfg["logo_rect"] = r
            elif key == "title":
                cfg["title_rect"] = r
            elif key == "message":
                cfg["message_rect"] = r
            elif key == "subtitle":
                cfg["subtitle_rect"] = r
            elif key == "bar":
                cfg["bar_rect"] = r
            elif key == "percent":
                cfg["percent_rect"] = r

        # text styles
        for style_key, c in (self._style_controls or {}).items():
            try:
                st = dict(cfg.get(style_key) or {}) if isinstance(cfg.get(style_key), dict) else {}
                st["size"] = int(c["size"].value())
                st["bold"] = bool(c["bold"].isChecked())
                st["align"] = str(c["align"].currentText() or "center")
                st["color"] = list(_color_list(c.get("color"), list(c.get("default_color") or [255, 255, 255])))
                cfg[style_key] = st
            except Exception:
                continue

        # colors
        cfg["background_color"] = _color_list(cfg.get("background_color"), [16, 18, 26])
        cfg["bar_bg_color"] = _color_list(cfg.get("bar_bg_color"), [60, 60, 70])
        cfg["bar_fg_color"] = _color_list(cfg.get("bar_fg_color"), [110, 160, 255])
        return cfg

    def _sync_from_ui(self):
        # Compatibility shim for existing connections (e.g. style controls).
        self._update_preview()

    def _on_rect_changed(self, key: str):
        if self._updating_ui:
            return
        c = self._rect_controls.get(key)
        if not c:
            return
        r = [int(c["x"].value()), int(c["y"].value()), int(c["w"].value()), int(c["h"].value())]
        self._set_component_rect_cfg(key, r)
        self._update_preview()

    def _on_preview_layout_edited(self, new_cfg: dict):
        # Sync back interactive edits to the controls.
        if self._updating_ui:
            return
        self._cfg = dict(new_cfg or {})
        # reflect rects into controls
        self._updating_ui = True
        self._suppress_dirty = True
        try:
            for key, ctrls in (self._rect_controls or {}).items():
                r = self._component_rect_cfg(key)
                ctrls["x"].setValue(int(r[0]))
                ctrls["y"].setValue(int(r[1]))
                ctrls["w"].setValue(int(r[2]))
                ctrls["h"].setValue(int(r[3]))
        finally:
            self._suppress_dirty = False
            self._updating_ui = False
        self._dirty = True
        self._update_preview()

    def _update_preview(self):
        if self._updating_ui:
            return
        self._mark_dirty()
        self._sync_preview_flags()
        collected = self._collect_cfg()
        # keep cfg normalized (rect lists etc.)
        self._cfg = _normalize_loading_overlay_cfg(collected, self.base_size)
        self.preview.update_state(self._cfg)

    def _save(self):
        ok = self._write_to_project(show_message=True)
        if ok:
            self.accept()

    def _write_to_project(self, show_message: bool) -> bool:
        if not self.project_manager:
            if show_message:
                QMessageBox.warning(self, "无法保存", "当前没有工程管理器，无法写入工程配置。")
            return False
        cfg = self.project_manager.project_data.setdefault("game_config", {})
        cfg["loading_overlay"] = dict(self._cfg)
        self._dirty = False
        if show_message:
            QMessageBox.information(self, "已保存", "加载遮罩配置已写入工程，保存工程文件后生效。")
        return True

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
        box.setText("加载遮罩配置尚未保存，是否保存后退出？")
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
        ok = self._write_to_project(show_message=False)
        return bool(ok)
