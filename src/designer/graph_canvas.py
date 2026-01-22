# -*- coding: utf-8 -*-
"""Flow graph canvas with grid, zoom, and simple text nodes."""
from math import hypot

from PyQt6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QGraphicsPathItem,
    QMenu,
    QInputDialog,
)
from PyQt6.QtGui import QColor, QPen, QPainter, QAction, QPainterPath
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal


class GraphScene(QGraphicsScene):
    """Scene with grid background."""

    def __init__(self, grid_size: int = 40, parent=None):
        super().__init__(parent)
        self.grid_size = grid_size
        self.setSceneRect(QRectF(-2000, -2000, 4000, 4000))

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        super().drawBackground(painter, rect)
        left = int(rect.left()) - (int(rect.left()) % self.grid_size)
        top = int(rect.top()) - (int(rect.top()) % self.grid_size)

        grid_pen = QPen(QColor(220, 220, 220))
        painter.setPen(grid_pen)

        x = float(left)
        right = float(rect.right())
        top_val = float(rect.top())
        bottom_val = float(rect.bottom())
        while x < right:
            painter.drawLine(QPointF(x, top_val), QPointF(x, bottom_val))
            x += float(self.grid_size)

        y = float(top)
        left_val = float(rect.left())
        while y < bottom_val:
            painter.drawLine(QPointF(left_val, y), QPointF(right, y))
            y += float(self.grid_size)


class FlowTextNode(QGraphicsRectItem):
    """Draggable text/choice/condition node with inline title editing."""

    def __init__(self, title: str = "文本节点", speaker: str = "", content: str = "", background: str = "", portrait: str = "", portrait2: str = "", voice: str = "", bgm: str = "", stop_bgm: bool = False, bgm_loop: bool = True, bg_fade_in: bool = False, node_type: str = "text", options: list[str] | None = None, condition_var: str = "", condition_value: str = "", condition_op: str = "==", condition_const: bool = False, sub_dialogues: list[dict] | None = None, ui_file: str = "", video: str = "", video_loop: bool = False, var_ops: list[dict] | None = None, size=(200, 70), node_id: int | None = None, on_position_changed=None):
        super().__init__(0, 0, size[0], size[1])
        self.node_id = node_id
        self._size = size
        self._title = title
        self.speaker = speaker
        self.content = content
        self.background = background
        self.portrait = portrait
        self.portrait2 = portrait2
        self.voice = voice
        self.bgm = bgm
        self.stop_bgm = stop_bgm
        self.bgm_loop = bgm_loop
        self.bg_fade_in = bg_fade_in
        self.bg_fade_duration = 0.45
        self.node_type = node_type or "text"
        self.options = options or []
        self.condition_var = condition_var or ""
        self.condition_value = condition_value or ""
        self.condition_op = condition_op or "=="
        self.condition_const = bool(condition_const)
        self.sub_dialogues = self._normalize_sub_dialogues(sub_dialogues or [])
        self.ui_file = ui_file or ""
        self.video = video or ""
        self.video_loop = video_loop
        self.var_ops = self._normalize_var_ops(var_ops or [])
        self.hide_textbox = False
        self.portrait_fade = False
        self.portrait_fade_out = False
        self.portrait2_fade = False
        self.portrait2_fade_out = False
        self.portrait_bounce = False
        self.portrait2_bounce = False
        self.is_start = False
        self._normal_pen = QPen(QColor(120, 120, 120))
        self._selected_pen = QPen(QColor(60, 130, 255), 2)
        self._port_radius = 7
        self._on_position_changed = on_position_changed

        self.setBrush(QColor(250, 250, 250))
        self.setPen(self._normal_pen)
        self.setFlags(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )

        self.label = QGraphicsSimpleTextItem(self._title, self)
        self.label.setBrush(QColor(30, 30, 30))
        self._recenter_label()

    def _recenter_label(self):
        label_rect = self.label.boundingRect()
        self.label.setPos((self._size[0] - label_rect.width()) / 2, (self._size[1] - label_rect.height()) / 2)

    def set_title(self, title: str):
        self._title = title
        self.label.setText(self._title)
        self._recenter_label()

    def set_speaker(self, speaker: str):
        self.speaker = speaker

    def set_content(self, content: str):
        self.content = content

    def set_background(self, background: str):
        self.background = background

    def set_portrait(self, portrait: str):
        self.portrait = portrait

    def set_portrait2(self, portrait: str):
        self.portrait2 = portrait

    def set_portrait_bounce(self, bounce: bool):
        self.portrait_bounce = bool(bounce)

    def set_portrait2_bounce(self, bounce: bool):
        self.portrait2_bounce = bool(bounce)

    def set_voice(self, voice: str):
        self.voice = voice

    def set_bgm(self, bgm: str):
        self.bgm = bgm

    def set_stop_bgm(self, stop: bool):
        self.stop_bgm = stop

    def set_bgm_loop(self, loop: bool):
        self.bgm_loop = loop

    def set_bg_fade_in(self, fade: bool):
        self.bg_fade_in = fade

    def set_bg_fade_duration(self, duration: float):
        try:
            d = float(duration)
        except Exception:
            d = 0.45
        # clamp to a sensible range
        self.bg_fade_duration = max(0.0, min(10.0, d))

    def set_node_type(self, node_type: str):
        self.node_type = node_type or "text"

    def set_options(self, options: list[str]):
        self.options = options or []

    def set_condition_var(self, var: str):
        self.condition_var = var

    def set_condition_value(self, val: str):
        self.condition_value = val

    def set_condition_op(self, op: str):
        self.condition_op = op or "=="

    def set_condition_const(self, const: bool):
        self.condition_const = bool(const)

    def set_var_ops(self, ops: list[dict]):
        self.var_ops = self._normalize_var_ops(ops or [])

    def set_video(self, video: str, loop: bool):
        self.video = video or ""
        self.video_loop = bool(loop)

    def set_hide_textbox(self, hide: bool):
        self.hide_textbox = bool(hide)

    def set_portrait_fade(self, fade: bool):
        self.portrait_fade = bool(fade)

    def set_portrait_fade_out(self, fade: bool):
        self.portrait_fade_out = bool(fade)

    def set_portrait2_fade(self, fade: bool):
        self.portrait2_fade = bool(fade)

    def set_portrait2_fade_out(self, fade: bool):
        self.portrait2_fade_out = bool(fade)

    def set_sub_dialogues(self, items: list[dict]):
        # enforce bounded list with normalized keys
        normalized = []
        for item in (items or [])[:50]:
            if not isinstance(item, dict):
                continue
            try:
                fade_in_d = float(item.get("portrait_fade_duration", 0.4))
            except Exception:
                fade_in_d = 0.4
            try:
                fade_out_d = float(item.get("portrait_fade_out_duration", 0.4))
            except Exception:
                fade_out_d = 0.4
            try:
                fade2_in_d = float(item.get("portrait2_fade_duration", fade_in_d))
            except Exception:
                fade2_in_d = fade_in_d
            try:
                fade2_out_d = float(item.get("portrait2_fade_out_duration", fade_out_d))
            except Exception:
                fade2_out_d = fade_out_d
            try:
                auto_next = float(item.get("auto_next_seconds", 0.0))
            except Exception:
                auto_next = 0.0
            normalized.append(
                {
                    "speaker": item.get("speaker", ""),
                    "text": item.get("text", ""),
                    "voice": item.get("voice", ""),
                    "portrait": item.get("portrait", ""),
                    "portrait2": item.get("portrait2", ""),
                    "ui_file": item.get("ui_file", ""),
                    "hide_textbox": bool(item.get("hide_textbox", False)),
                    "portrait_fade": bool(item.get("portrait_fade", False)),
                    "portrait_fade_out": bool(item.get("portrait_fade_out", False)),
                    "portrait2_fade": bool(item.get("portrait2_fade", False)),
                    "portrait2_fade_out": bool(item.get("portrait2_fade_out", False)),
                    "portrait_bounce": bool(item.get("portrait_bounce", False)),
                    "portrait2_bounce": bool(item.get("portrait2_bounce", False)),
                    "portrait_fade_duration": max(0.0, min(10.0, fade_in_d)),
                    "portrait_fade_out_duration": max(0.0, min(10.0, fade_out_d)),
                    "portrait2_fade_duration": max(0.0, min(10.0, fade2_in_d)),
                    "portrait2_fade_out_duration": max(0.0, min(10.0, fade2_out_d)),
                    "auto_next_seconds": max(0.0, min(600.0, auto_next)),
                }
            )
        self.sub_dialogues = normalized

    def _normalize_sub_dialogues(self, items: list[dict]):
        normalized = []
        if isinstance(items, list):
            for item in items[:50]:
                if not isinstance(item, dict):
                    continue
                try:
                    fade_in_d = float(item.get("portrait_fade_duration", 0.4))
                except Exception:
                    fade_in_d = 0.4
                try:
                    fade_out_d = float(item.get("portrait_fade_out_duration", 0.4))
                except Exception:
                    fade_out_d = 0.4
                try:
                    fade2_in_d = float(item.get("portrait2_fade_duration", fade_in_d))
                except Exception:
                    fade2_in_d = fade_in_d
                try:
                    fade2_out_d = float(item.get("portrait2_fade_out_duration", fade_out_d))
                except Exception:
                    fade2_out_d = fade_out_d
                try:
                    auto_next = float(item.get("auto_next_seconds", 0.0))
                except Exception:
                    auto_next = 0.0
                normalized.append(
                    {
                        "speaker": item.get("speaker", ""),
                        "text": item.get("text", ""),
                        "voice": item.get("voice", ""),
                        "portrait": item.get("portrait", ""),
                        "portrait2": item.get("portrait2", ""),
                        "ui_file": item.get("ui_file", ""),
                        "hide_textbox": bool(item.get("hide_textbox", False)),
                        "portrait_fade": bool(item.get("portrait_fade", False)),
                        "portrait_fade_out": bool(item.get("portrait_fade_out", False)),
                        "portrait2_fade": bool(item.get("portrait2_fade", False)),
                        "portrait2_fade_out": bool(item.get("portrait2_fade_out", False)),
                        "portrait_bounce": bool(item.get("portrait_bounce", False)),
                        "portrait2_bounce": bool(item.get("portrait2_bounce", False)),
                        "portrait_fade_duration": max(0.0, min(10.0, fade_in_d)),
                        "portrait_fade_out_duration": max(0.0, min(10.0, fade_out_d)),
                        "portrait2_fade_duration": max(0.0, min(10.0, fade2_in_d)),
                        "portrait2_fade_out_duration": max(0.0, min(10.0, fade2_out_d)),
                        "auto_next_seconds": max(0.0, min(600.0, auto_next)),
                    }
                )
        return normalized

    def _normalize_var_ops(self, items: list[dict]):
        normalized = []
        if isinstance(items, list):
            for item in items[:50]:
                if not isinstance(item, dict):
                    continue
                normalized.append(
                    {
                        "dest": item.get("dest", ""),
                        "left": item.get("left", ""),
                        "right": item.get("right", ""),
                        "op": item.get("op", "+"),
                        "left_const": bool(item.get("left_const", False)),
                        "right_const": bool(item.get("right_const", False)),
                    }
                )
        return normalized

    def set_ui_file(self, ui_file: str):
        self.ui_file = ui_file or ""

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        view = self.scene().views()[0] if self.scene().views() else None
        parent = view if view is not None else None
        text, ok = QInputDialog.getText(parent, "编辑文本", "节点内容：", text=self._title)
        if ok and text:
            self.set_title(text)
        super().mouseDoubleClickEvent(event)

    def paint(self, painter, option, widget=None):  # noqa: D401
        # Highlight selection with a thicker blue border.
        self.setPen(self._selected_pen if self.isSelected() else self._normal_pen)
        super().paint(painter, option, widget)
        self.paint_ports(painter)
        if self.is_start:
            painter.setBrush(QColor(90, 200, 120))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(QRectF(self.rect().x(), self.rect().y(), self.rect().width(), 6.0))

    def itemChange(self, change, value):  # noqa: N802
        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionChange:
            if self._on_position_changed:
                self._on_position_changed(self)
        return super().itemChange(change, value)

    def get_input_pos(self) -> QPointF:
        # Left center
        return self.mapToScene(QPointF(0, self._size[1] / 2))

    def get_output_pos(self) -> QPointF:
        # Right center
        return self.mapToScene(QPointF(self._size[0], self._size[1] / 2))

    def hit_input(self, scene_pos: QPointF) -> bool:
        return hypot(scene_pos.x() - self.get_input_pos().x(), scene_pos.y() - self.get_input_pos().y()) <= self._port_radius

    def hit_output(self, scene_pos: QPointF) -> bool:
        return hypot(scene_pos.x() - self.get_output_pos().x(), scene_pos.y() - self.get_output_pos().y()) <= self._port_radius

    def paint_ports(self, painter: QPainter):
        painter.setBrush(QColor(200, 200, 200))
        painter.setPen(Qt.PenStyle.NoPen)
        inp = self.mapFromScene(self.get_input_pos())
        outp = self.mapFromScene(self.get_output_pos())
        painter.drawEllipse(inp, self._port_radius, self._port_radius)
        painter.drawEllipse(outp, self._port_radius, self._port_radius)


class ConnectionPath(QGraphicsPathItem):
    """Connection between two nodes."""

    def __init__(self, source_node: FlowTextNode, target_node: FlowTextNode):
        super().__init__()
        self.source_node = source_node
        self.target_node = target_node
        self._normal_pen = QPen(QColor(120, 120, 120), 2)
        self._selected_pen = QPen(QColor(60, 130, 255), 3)
        self.setFlags(
            QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setZValue(-1)
        self.update_path()

    def update_path(self):
        start = self.source_node.get_output_pos()
        end = self.target_node.get_input_pos()
        dx = end.x() - start.x()
        # push control points away from node edges to reduce overlap with nodes
        handle = max(abs(dx) * 0.5, 80.0)
        c1 = QPointF(start.x() + handle, start.y())
        c2 = QPointF(end.x() - handle, end.y())
        path = QPainterPath(start)
        path.cubicTo(c1, c2, end)
        self.setPath(path)

    def paint(self, painter, option, widget=None):  # noqa: D401
        self.setPen(self._selected_pen if self.isSelected() else self._normal_pen)
        super().paint(painter, option, widget)


class GraphView(QGraphicsView):
    """Graphics view with zoom, pan, and context menu."""

    previewFromNodeRequested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = GraphScene(parent=self)
        self.setScene(self.scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._min_zoom = 0.05
        self._max_zoom = 6.0
        self._is_panning = False
        self._last_mouse_pos = None
        self._node_counter = 1
        self._connecting = False
        self._connect_start_node = None
        self._temp_path_item = None
        self._copy_buffer = []
        self._connections: list[ConnectionPath] = []

    def wheelEvent(self, event):  # noqa: N802
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor
        current = float(self.transform().m11())
        if current <= 0:
            current = 1.0
        target = current * zoom_factor
        target = max(self._min_zoom, min(self._max_zoom, target))
        applied = target / current
        if abs(applied - 1.0) < 1e-6:
            event.accept()
            return
        self.scale(applied, applied)
        event.accept()

    def _ensure_scene_contains_rect(self, rect: QRectF, margin: float = 200.0):
        if rect.isNull() or rect.isEmpty():
            return
        rect = rect.adjusted(-margin, -margin, margin, margin)
        scene_rect = self.scene.sceneRect()
        if scene_rect.contains(rect):
            return
        self.scene.setSceneRect(scene_rect.united(rect))

    def fit_canvas_to_content(self, margin: float = 300.0):
        items = [i for i in self.scene.items() if isinstance(i, (FlowTextNode, ConnectionPath))]
        if not items:
            return
        rect = items[0].sceneBoundingRect()
        for it in items[1:]:
            rect = rect.united(it.sceneBoundingRect())
        rect = rect.adjusted(-margin, -margin, margin, margin)
        if rect.width() < 200:
            rect.setWidth(200)
        if rect.height() < 200:
            rect.setHeight(200)
        self.scene.setSceneRect(rect)

    def set_canvas_size(self, width: float, height: float):
        try:
            w = float(width)
            h = float(height)
        except Exception:
            return
        w = max(200.0, w)
        h = max(200.0, h)
        self.scene.setSceneRect(QRectF(-w / 2.0, -h / 2.0, w, h))

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._last_mouse_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            hit_node, port = self._detect_port(scene_pos)
            if hit_node and port == "output":
                self._start_connection(hit_node, scene_pos)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._is_panning and self._last_mouse_pos is not None:
            delta = event.pos() - self._last_mouse_pos
            self._last_mouse_pos = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return

        if self._connecting and self._temp_path_item:
            scene_pos = self.mapToScene(event.pos())
            self._update_temp_path(scene_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton and self._is_panning:
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._connecting:
            scene_pos = self.mapToScene(event.pos())
            hit_node, port = self._detect_port(scene_pos)
            if hit_node and port == "input" and hit_node is not self._connect_start_node:
                self._create_connection(self._connect_start_node, hit_node)
            self._end_temp_connection()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):  # noqa: N802
        menu = QMenu(self)
        add_text_action = QAction("添加文本节点", self)
        scene_pos = self.mapToScene(event.pos())
        add_text_action.triggered.connect(lambda: self.add_text_node(scene_pos))
        menu.addAction(add_text_action)

        # 节点级右键菜单：从该节点开始预览
        clicked = self.scene.itemAt(scene_pos, self.transform())
        while clicked is not None and not isinstance(clicked, FlowTextNode):
            clicked = clicked.parentItem()
        if isinstance(clicked, FlowTextNode) and getattr(clicked, "node_id", None) is not None:
            menu.addSeparator()
            preview_from_here = QAction("从该节点开始预览", self)
            preview_from_here.triggered.connect(lambda _=False, nid=int(clicked.node_id): self.previewFromNodeRequested.emit(nid))
            menu.addAction(preview_from_here)

        if self.scene.selectedItems():
            delete_action = QAction("删除选中节点", self)
            delete_action.triggered.connect(self.delete_selected_nodes)
            menu.addAction(delete_action)
            copy_action = QAction("复制选中节点", self)
            copy_action.triggered.connect(self.copy_selected_nodes)
            menu.addAction(copy_action)

        clear_action = QAction("清空画布", self)
        clear_action.triggered.connect(self.clear_scene)
        menu.addAction(clear_action)

        menu.addSeparator()
        canvas_size_action = QAction("调整画布大小...", self)
        canvas_size_action.triggered.connect(self._prompt_canvas_size)
        menu.addAction(canvas_size_action)
        fit_canvas_action = QAction("画布适配内容", self)
        fit_canvas_action.triggered.connect(self.fit_canvas_to_content)
        menu.addAction(fit_canvas_action)

        menu.exec(event.globalPos())

    def _prompt_canvas_size(self):
        rect = self.scene.sceneRect()
        w0 = int(max(200.0, rect.width()))
        h0 = int(max(200.0, rect.height()))
        w, ok = QInputDialog.getInt(self, "画布宽度", "请输入画布宽度：", w0, 200, 200000, 100)
        if not ok:
            return
        h, ok = QInputDialog.getInt(self, "画布高度", "请输入画布高度：", h0, 200, 200000, 100)
        if not ok:
            return
        self.set_canvas_size(w, h)

    def add_text_node(self, pos: QPointF):
        node_id = self._node_counter
        title = f"文本节点 {node_id}"
        self._node_counter += 1
        node = FlowTextNode(title=title, node_id=node_id, on_position_changed=self.on_node_moved)
        node.setPos(pos)
        self.scene.addItem(node)
        self._ensure_scene_contains_rect(node.sceneBoundingRect())
        return node

    def delete_selected_nodes(self):
        for item in list(self.scene.selectedItems()):
            self._safe_remove_item(item)

    def clear_scene(self):
        for item in list(self.scene.items()):
            if isinstance(item, (FlowTextNode, ConnectionPath)):
                self.scene.removeItem(item)
        self._node_counter = 1
        self._copy_buffer = []
        self._connections.clear()
        self.update_start_marks()

    def _detect_port(self, scene_pos: QPointF):
        for item in self.scene.items():
            if isinstance(item, FlowTextNode):
                if item.hit_output(scene_pos):
                    return item, "output"
                if item.hit_input(scene_pos):
                    return item, "input"
        return None, None

    def _start_connection(self, node: FlowTextNode, scene_pos: QPointF):
        self._connecting = True
        self._connect_start_node = node
        self._temp_path_item = QGraphicsPathItem()
        self._temp_path_item.setPen(QPen(QColor(150, 150, 150), 2, Qt.PenStyle.DashLine))
        self.scene.addItem(self._temp_path_item)
        self._update_temp_path(scene_pos)

    def _update_temp_path(self, scene_pos: QPointF):
        if not self._temp_path_item or not self._connect_start_node:
            return
        start = self._connect_start_node.get_output_pos()
        dx = scene_pos.x() - start.x()
        handle = max(abs(dx) * 0.5, 80.0)
        c1 = QPointF(start.x() + handle, start.y())
        c2 = QPointF(scene_pos.x() - handle, scene_pos.y())
        path = QPainterPath(start)
        path.cubicTo(c1, c2, scene_pos)
        self._temp_path_item.setPath(path)

    def _end_temp_connection(self):
        if self._temp_path_item:
            self.scene.removeItem(self._temp_path_item)
            self._temp_path_item = None
        self._connecting = False
        self._connect_start_node = None
        self.update_start_marks()

    def _create_connection(self, source: FlowTextNode, target: FlowTextNode):
        connection = ConnectionPath(source, target)
        self.scene.addItem(connection)
        self._connections.append(connection)
        self.update_start_marks()

    def export_scene(self) -> dict:
        nodes = []
        for item in self.scene.items():
            if isinstance(item, FlowTextNode):
                pos = item.pos()
                nodes.append({
                    "id": item.node_id,
                    "title": item._title,
                    "speaker": getattr(item, "speaker", ""),
                    "content": getattr(item, "content", ""),
                    "background": getattr(item, "background", ""),
                    "portrait": getattr(item, "portrait", ""),
                    "portrait2": getattr(item, "portrait2", ""),
                    "voice": getattr(item, "voice", ""),
                    "video": getattr(item, "video", ""),
                    "video_loop": getattr(item, "video_loop", False),
                    "bgm": getattr(item, "bgm", ""),
                    "stop_bgm": getattr(item, "stop_bgm", False),
                    "bgm_loop": getattr(item, "bgm_loop", True),
                    "bg_fade_in": getattr(item, "bg_fade_in", False),
                    "bg_fade_duration": getattr(item, "bg_fade_duration", 0.45),
                    "hide_textbox": getattr(item, "hide_textbox", False),
                    "portrait_fade": getattr(item, "portrait_fade", False),
                    "portrait_fade_out": getattr(item, "portrait_fade_out", False),
                    "portrait2_fade": getattr(item, "portrait2_fade", False),
                    "portrait2_fade_out": getattr(item, "portrait2_fade_out", False),
                    "portrait_bounce": getattr(item, "portrait_bounce", False),
                    "portrait2_bounce": getattr(item, "portrait2_bounce", False),
                    "node_type": getattr(item, "node_type", "text"),
                    "options": getattr(item, "options", []),
                    "condition_var": getattr(item, "condition_var", ""),
                    "condition_value": getattr(item, "condition_value", ""),
                    "condition_op": getattr(item, "condition_op", "=="),
                    "condition_const": getattr(item, "condition_const", False),
                    "sub_dialogues": getattr(item, "sub_dialogues", []),
                    "ui_file": getattr(item, "ui_file", ""),
                    "var_ops": getattr(item, "var_ops", []),
                    "x": pos.x(),
                    "y": pos.y(),
                })

        connections = []
        for item in self._connections:
            connections.append({
                "source": item.source_node.node_id,
                "target": item.target_node.node_id,
            })

        return {"nodes": nodes, "connections": connections}

    def load_scene(self, data: dict):
        self.clear_scene()
        id_to_node = {}
        max_id = 0

        for node_data in data.get("nodes", []):
            node = FlowTextNode(
                title=node_data.get("title", "文本节点"),
                speaker=node_data.get("speaker", ""),
                content=node_data.get("content", ""),
                background=node_data.get("background", ""),
                portrait=node_data.get("portrait", ""),
                portrait2=node_data.get("portrait2", ""),
                voice=node_data.get("voice", ""),
                video=node_data.get("video", ""),
                video_loop=bool(node_data.get("video_loop", False)),
                bgm=node_data.get("bgm", ""),
                stop_bgm=node_data.get("stop_bgm", False),
                bgm_loop=node_data.get("bgm_loop", True),
                bg_fade_in=node_data.get("bg_fade_in", False),
                node_type=node_data.get("node_type", "text"),
                options=node_data.get("options", []),
                condition_var=node_data.get("condition_var", ""),
                condition_value=node_data.get("condition_value", ""),
                condition_op=node_data.get("condition_op", "=="),
                condition_const=bool(node_data.get("condition_const", False)),
                sub_dialogues=node_data.get("sub_dialogues", []),
                ui_file=node_data.get("ui_file", ""),
                var_ops=node_data.get("var_ops", []),
                node_id=node_data.get("id"),
                on_position_changed=self.on_node_moved,
            )
            node.hide_textbox = bool(node_data.get("hide_textbox", False))
            node.portrait_fade = bool(node_data.get("portrait_fade", False))
            node.portrait_fade_out = bool(node_data.get("portrait_fade_out", False))
            node.portrait2_fade = bool(node_data.get("portrait2_fade", False))
            node.portrait2_fade_out = bool(node_data.get("portrait2_fade_out", False))
            node.portrait_bounce = bool(node_data.get("portrait_bounce", False))
            node.portrait2_bounce = bool(node_data.get("portrait2_bounce", False))
            try:
                node.set_bg_fade_duration(float(node_data.get("bg_fade_duration", getattr(node, "bg_fade_duration", 0.45))))
            except Exception:
                pass
            node.setPos(QPointF(node_data.get("x", 0), node_data.get("y", 0)))
            self.scene.addItem(node)
            id_to_node[node.node_id] = node
            if node.node_id and node.node_id > max_id:
                max_id = node.node_id

        for conn in data.get("connections", []):
            source = id_to_node.get(conn.get("source"))
            target = id_to_node.get(conn.get("target"))
            if source and target and source is not target:
                self._create_connection(source, target)

        self._node_counter = max_id + 1 if max_id else 1
        self._copy_buffer = []
        self.update_start_marks()

    # Clipboard-like operations
    def copy_selected_nodes(self):
        nodes = [item for item in self.scene.selectedItems() if isinstance(item, FlowTextNode)]
        if not nodes:
            return
        data = []
        for n in nodes:
            data.append({
                "title": n._title,
                "speaker": getattr(n, "speaker", ""),
                "content": getattr(n, "content", ""),
                "background": getattr(n, "background", ""),
                "portrait": getattr(n, "portrait", ""),
                "portrait2": getattr(n, "portrait2", ""),
                "voice": getattr(n, "voice", ""),
                "video": getattr(n, "video", ""),
                "video_loop": getattr(n, "video_loop", False),
                "bgm": getattr(n, "bgm", ""),
                "stop_bgm": getattr(n, "stop_bgm", False),
                "bgm_loop": getattr(n, "bgm_loop", True),
                "bg_fade_in": getattr(n, "bg_fade_in", False),
                "bg_fade_duration": getattr(n, "bg_fade_duration", 0.45),
                "hide_textbox": getattr(n, "hide_textbox", False),
                "portrait_fade": getattr(n, "portrait_fade", False),
                "portrait_fade_out": getattr(n, "portrait_fade_out", False),
                "portrait2_fade": getattr(n, "portrait2_fade", False),
                "portrait2_fade_out": getattr(n, "portrait2_fade_out", False),
                "portrait_bounce": getattr(n, "portrait_bounce", False),
                "portrait2_bounce": getattr(n, "portrait2_bounce", False),
                "node_type": getattr(n, "node_type", "text"),
                "options": getattr(n, "options", []),
                "condition_var": getattr(n, "condition_var", ""),
                "condition_value": getattr(n, "condition_value", ""),
                "condition_op": getattr(n, "condition_op", "=="),
                "condition_const": getattr(n, "condition_const", False),
                "sub_dialogues": getattr(n, "sub_dialogues", []),
                "ui_file": getattr(n, "ui_file", ""),
                "var_ops": getattr(n, "var_ops", []),
                "x": n.pos().x(),
                "y": n.pos().y(),
            })
        self._copy_buffer = data

    def paste_nodes(self, offset: QPointF = QPointF(30, 30)):
        if not self._copy_buffer:
            return
        new_nodes = []
        for item in self._copy_buffer:
            node_id = self._node_counter
            self._node_counter += 1
            node = FlowTextNode(
                title=item.get("title", f"文本节点 {node_id}"),
                speaker=item.get("speaker", ""),
                content=item.get("content", ""),
                background=item.get("background", ""),
                portrait=item.get("portrait", ""),
                portrait2=item.get("portrait2", ""),
                voice=item.get("voice", ""),
                video=item.get("video", ""),
                video_loop=bool(item.get("video_loop", False)),
                bgm=item.get("bgm", ""),
                stop_bgm=item.get("stop_bgm", False),
                bgm_loop=item.get("bgm_loop", True),
                bg_fade_in=item.get("bg_fade_in", False),
                node_type=item.get("node_type", "text"),
                options=item.get("options", []),
                condition_var=item.get("condition_var", ""),
                condition_value=item.get("condition_value", ""),
                condition_op=item.get("condition_op", "=="),
                condition_const=bool(item.get("condition_const", False)),
                sub_dialogues=item.get("sub_dialogues", []),
                ui_file=item.get("ui_file", ""),
                var_ops=item.get("var_ops", []),
                node_id=node_id,
                on_position_changed=self.on_node_moved,
            )
            node.hide_textbox = bool(item.get("hide_textbox", False))
            node.portrait_fade = bool(item.get("portrait_fade", False))
            node.portrait_fade_out = bool(item.get("portrait_fade_out", False))
            node.portrait2_fade = bool(item.get("portrait2_fade", False))
            node.portrait2_fade_out = bool(item.get("portrait2_fade_out", False))
            node.portrait_bounce = bool(item.get("portrait_bounce", False))
            node.portrait2_bounce = bool(item.get("portrait2_bounce", False))
            try:
                node.set_bg_fade_duration(float(item.get("bg_fade_duration", getattr(node, "bg_fade_duration", 0.45))))
            except Exception:
                pass
            node.setPos(QPointF(item.get("x", 0), item.get("y", 0)) + offset)
            self.scene.addItem(node)
            new_nodes.append(node)
        # select new nodes
        for n in new_nodes:
            n.setSelected(True)

    def _safe_remove_item(self, item):
        if isinstance(item, FlowTextNode):
            for edge in list(self._edges_for_node(item)):
                if edge in self._connections:
                    self._connections.remove(edge)
                self.scene.removeItem(edge)
            self.scene.removeItem(item)
        elif isinstance(item, ConnectionPath):
            if item in self._connections:
                self._connections.remove(item)
            self.scene.removeItem(item)
        self.update_start_marks()

    def _edges_for_node(self, node: FlowTextNode):
        for item in self._connections:
            if item.source_node is node or item.target_node is node:
                yield item

    def on_node_moved(self, node: FlowTextNode):
        for edge in self._edges_for_node(node):
            edge.update_path()
        self._ensure_scene_contains_rect(node.sceneBoundingRect())

    def update_start_marks(self):
        nodes = [i for i in self.scene.items() if isinstance(i, FlowTextNode)]
        connections = list(self._connections)
        indegree = {n.node_id: 0 for n in nodes if n.node_id is not None}
        for c in connections:
            s = c.source_node.node_id
            t = c.target_node.node_id
            if s is None or t is None:
                continue
            indegree[t] = indegree.get(t, 0) + 1

        for n in nodes:
            n.is_start = indegree.get(n.node_id, 0) == 0
            n.update()

    def analyze_flow(self) -> dict:
        nodes = [i for i in self.scene.items() if isinstance(i, FlowTextNode)]
        connections = list(self._connections)
        node_ids = {n.node_id for n in nodes if n.node_id is not None}
        adjacency = {nid: [] for nid in node_ids}
        indegree = {nid: 0 for nid in node_ids}
        for c in connections:
            s = c.source_node.node_id
            t = c.target_node.node_id
            if s in node_ids and t in node_ids and s != t:
                adjacency[s].append(t)
                indegree[t] = indegree.get(t, 0) + 1

        start_nodes = [nid for nid, deg in indegree.items() if deg == 0]
        visited = set()
        stack = []
        has_cycle = False

        def dfs(u):
            nonlocal has_cycle
            visited.add(u)
            stack.append(u)
            for v in adjacency.get(u, []):
                if v not in visited:
                    dfs(v)
                elif v in stack:
                    has_cycle = True
            stack.pop()

        for s in start_nodes or list(node_ids):
            if s not in visited:
                dfs(s)

        unreachable = list(node_ids - visited)
        choice_mismatch = []
        condition_mismatch = []
        id_to_node = {n.node_id: n for n in nodes if n.node_id is not None}
        for nid, targets in adjacency.items():
            node = id_to_node.get(nid)
            if not node:
                continue
            if getattr(node, "node_type", "text") == "choice":
                opt_cnt = len(getattr(node, "options", []) or [])
                out_cnt = len(targets)
                if opt_cnt != out_cnt:
                    choice_mismatch.append((nid, opt_cnt, out_cnt))
            if getattr(node, "node_type", "text") == "condition":
                out_cnt = len(targets)
                if out_cnt != 2:
                    condition_mismatch.append((nid, out_cnt))

        return {
            "start_nodes": start_nodes,
            "has_cycle": has_cycle,
            "unreachable": unreachable,
            "choice_mismatch": choice_mismatch,
            "condition_mismatch": condition_mismatch,
        }

    def get_outgoing_targets(self, node: FlowTextNode) -> list[FlowTextNode]:
        if not node or node.node_id is None:
            return []
        targets = []
        for c in self._connections:
            if c.source_node is node and isinstance(c.target_node, FlowTextNode):
                targets.append(c.target_node)
        return targets

    def swap_condition_targets(self, node: FlowTextNode):
        if not node:
            return
        matches = [idx for idx, c in enumerate(self._connections) if c.source_node is node]
        if len(matches) < 2:
            return
        first_idx, second_idx = matches[0], matches[1]
        self._connections[first_idx], self._connections[second_idx] = self._connections[second_idx], self._connections[first_idx]
        self.update()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Delete:
            self.delete_selected_nodes()
            event.accept()
            return
        if event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.copy_selected_nodes()
            event.accept()
            return
        if event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.paste_nodes()
            event.accept()
            return
        super().keyPressEvent(event)
