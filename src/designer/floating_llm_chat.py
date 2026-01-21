# -*- coding: utf-8 -*-
"""Floating draggable ball + lightweight LLM chat widget for AIProjectWindow.

- No history persistence
- Runs LLM call in background thread to keep UI responsive
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import os

from PyQt6.QtCore import Qt, QPoint, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QWidget,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPlainTextEdit,
    QSizePolicy,
)

from src.ai.api.api_manager import APIManager
from src.ai.core.config_manager import ConfigManager


@dataclass
class _DragState:
    dragging: bool = False
    press_pos: QPoint | None = None
    start_pos: QPoint | None = None


class FloatingBall(QPushButton):
    """A circular draggable button that stays inside its parent."""

    def __init__(self, parent: QWidget):
        super().__init__("AI", parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedSize(46, 46)
        self.setStyleSheet(
            "QPushButton {"
            "  background: rgba(45, 140, 240, 220);"
            "  color: white;"
            "  border: 1px solid rgba(255,255,255,120);"
            "  border-radius: 23px;"
            "  font-weight: 700;"
            "}"
            "QPushButton:hover { background: rgba(45, 140, 240, 255); }"
            "QPushButton:pressed { background: rgba(30, 110, 200, 255); }"
        )
        self._drag = _DragState()
        self._moved = False
        self._debug = os.getenv("VNENGINE_FLOATING_DEBUG", "0").strip() in {"1", "true", "True", "YES", "yes"}

    def _dbg(self, msg: str):
        if not self._debug:
            return
        try:
            print(f"[FLOATING] {msg}")
        except Exception:
            pass

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag.dragging = True
            self._drag.press_pos = event.globalPosition().toPoint()
            self._drag.start_pos = self.pos()
            self._moved = False
            self._dbg(f"ball press pos={self.pos().x()},{self.pos().y()}")
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag.dragging and self._drag.press_pos is not None and self._drag.start_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag.press_pos
            # 只有超过阈值才认为是拖拽，避免轻微抖动影响点击
            if abs(delta.x()) + abs(delta.y()) >= 6:
                self._moved = True
            if self._moved:
                new_pos = self._drag.start_pos + delta
                self._move_clamped(new_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._drag.dragging:
            self._drag.dragging = False
            self._drag.press_pos = None
            self._drag.start_pos = None
            # 若几乎未移动，则视为点击（触发打开悬浮窗）
            if not self._moved:
                # 主动触发 clicked 信号（QPushButton 的 clicked(bool)）
                self._dbg("ball release -> click")
                try:
                    self.clicked.emit(False)
                except Exception:
                    pass
                event.accept()
                return
            self._dbg(f"ball release -> dragged to pos={self.pos().x()},{self.pos().y()}")
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _move_clamped(self, pos: QPoint):
        p = self.parentWidget()
        if not p:
            self.move(pos)
            return
        margin = 6
        max_x = max(margin, p.width() - self.width() - margin)
        max_y = max(margin, p.height() - self.height() - margin)
        x = max(margin, min(max_x, pos.x()))
        y = max(margin, min(max_y, pos.y()))
        self.move(x, y)


class _LLMThread(QThread):
    finishedText = pyqtSignal(str)
    failed = pyqtSignal(str)
    finishedWithHistory = pyqtSignal(str, list)

    def __init__(
        self,
        config_manager: ConfigManager,
        prompt: str,
        system: Optional[str] = None,
        history: Optional[list[dict]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._config_manager = config_manager
        self._prompt = prompt
        self._system = system
        self._history = history or []

    def run(self):  # noqa: N802
        try:
            api_manager = APIManager(self._config_manager)
            client = api_manager.get_llm_client(prefer_claude=True)
            if not client:
                self.failed.emit("无法获取LLM客户端：请先在工具->API配置中设置 Claude/Kimi")
                return

            # 需要上下文：优先走 multi_turn_conversation（若客户端提供），否则走 Messages(create_message)
            new_history = [m for m in self._history if isinstance(m, dict) and m.get("role") in {"user", "assistant"}]
            user_msg = {"role": "user", "content": self._prompt}

            if hasattr(client, "multi_turn_conversation"):
                reply, updated = client.multi_turn_conversation(
                    conversation_history=new_history,
                    new_message=self._prompt,
                    system=self._system,
                )
                if isinstance(updated, list):
                    new_history = updated
                else:
                    # 兜底：手工追加
                    new_history = [*new_history, user_msg, {"role": "assistant", "content": str(reply or "")}]
                self.finishedWithHistory.emit(str(reply or ""), new_history)
                return

            if hasattr(client, "create_message"):
                messages = [*new_history, user_msg]
                resp = client.create_message(messages=messages, system=self._system)
                blocks = resp.get("content", []) if isinstance(resp, dict) else []
                text = "".join(
                    b.get("text", "")
                    for b in blocks
                    if isinstance(blocks, list) and isinstance(b, dict)
                )
                new_history = [*messages, {"role": "assistant", "content": text or ""}]
                self.finishedWithHistory.emit(text or "", new_history)
                return

            # 最后兜底：无上下文
            text = client.generate_text(prompt=self._prompt, system=self._system)
            self.finishedText.emit(text or "")
        except Exception as exc:
            self.failed.emit(str(exc))


class FloatingChatWidget(QWidget):
    """A small draggable chat widget overlay inside a parent widget."""

    minimized = pyqtSignal()

    def __init__(self, parent: QWidget, config_manager: ConfigManager):
        super().__init__(parent)
        self._config_manager = config_manager
        self._drag = _DragState()
        self._thread: _LLMThread | None = None
        self._history: list[dict] = []
        self._max_history_turns = 12  # user+assistant pairs

        self.setFixedSize(420, 320)
        self.setStyleSheet(
            "QWidget {"
            "  background: rgba(25, 28, 36, 245);"
            "  border: 1px solid rgba(255,255,255,60);"
            "  border-radius: 10px;"
            "}"
            "QLabel { color: rgba(235,235,240,230); }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # title row (drag handle)
        title_row = QHBoxLayout()
        self._title = QLabel("LLM 悬浮助手")
        self._title.setStyleSheet("font-weight: 700;")
        title_row.addWidget(self._title)
        title_row.addStretch(1)

        self._status = QLabel("")
        self._status.setStyleSheet("color: rgba(180,200,255,220);")
        title_row.addWidget(self._status)

        self._min_btn = QPushButton("最小化")
        self._min_btn.setFixedHeight(30)
        self._min_btn.setStyleSheet(
            "QPushButton {"
            "  background: rgba(255, 255, 255, 70);"
            "  color: rgba(20, 24, 32, 245);"
            "  border: 1px solid rgba(255, 255, 255, 140);"
            "  border-radius: 6px;"
            "  padding: 0 12px;"
            "  font-weight: 700;"
            "}"
            "QPushButton:hover {"
            "  background: rgba(255, 255, 255, 95);"
            "  border: 1px solid rgba(80, 170, 255, 200);"
            "}"
            "QPushButton:pressed { background: rgba(255, 255, 255, 55); }"
        )
        self._min_btn.clicked.connect(self._on_minimize)
        title_row.addWidget(self._min_btn)

        self._clear_btn = QPushButton("清空上下文")
        self._clear_btn.setFixedHeight(30)
        self._clear_btn.setStyleSheet(
    "QPushButton {"
    "  background: rgba(255, 255, 255, 70);"
    "  color: rgba(20, 24, 32, 245);"
    "  border: 1px solid rgba(255, 255, 255, 140);"
    "  border-radius: 6px;"
    "  padding: 0 12px;"  # 原10px改为和最小化按钮一致的12px
    "  font-weight: 700;"  # 新增：和最小化按钮一致的加粗字体
    "}"
    "QPushButton:hover {"
    "  background: rgba(255, 255, 255, 95);"
    "  border: 1px solid rgba(80, 170, 255, 200);"  # 新增：hover时的边框样式
    "}"
    "QPushButton:pressed { background: rgba(255, 255, 255, 55); }"  # 新增：按下状态的背景
        )
        self._clear_btn.clicked.connect(self._clear_context)
        title_row.addWidget(self._clear_btn)

        root.addLayout(title_row)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("这里显示回复（不保存历史）")
        self.output.setStyleSheet(
            "QTextEdit {"
            "  background: rgba(10, 12, 18, 210);"
            "  color: rgba(245, 247, 252, 245);"
            "  border: 1px solid rgba(255,255,255,45);"
            "  border-radius: 8px;"
            "}"
            "QTextEdit:focus {"
            "  border: 1px solid rgba(80, 170, 255, 200);"
            "}"
            "QTextEdit::selection {"
            "  background: rgba(80, 170, 255, 140);"
            "}"
        )
        root.addWidget(self.output, 1)

        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("输入要问LLM的内容…")
        self.input.setFixedHeight(70)
        self.input.setStyleSheet(
            "QPlainTextEdit {"
            "  background: rgba(12, 14, 20, 230);"
            "  color: rgba(255, 255, 255, 245);"
            "  border: 1px solid rgba(255,255,255,55);"
            "  border-radius: 8px;"
            "  padding: 6px;"
            "  font-size: 12px;"
            "}"
            "QPlainTextEdit:focus {"
            "  border: 1px solid rgba(80, 170, 255, 220);"
            "}"
            "QPlainTextEdit::selection {"
            "  background: rgba(80, 170, 255, 150);"
            "}"
        )
        root.addWidget(self.input)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.send_btn = QPushButton("发送")
        self.send_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.send_btn.setFixedHeight(30)
        self.send_btn.setStyleSheet(
            "QPushButton {"
            "  background: rgba(45, 140, 240, 220);"
            "  color: white;"
            "  border: 1px solid rgba(255,255,255,50);"
            "  border-radius: 8px;"
            "  padding: 0 14px;"
            "  font-weight: 700;"
            "}"
            "QPushButton:hover { background: rgba(45, 140, 240, 255); }"
            "QPushButton:disabled { background: rgba(45, 140, 240, 120); }"
        )
        self.send_btn.clicked.connect(self._on_send)
        btn_row.addWidget(self.send_btn)
        root.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._elapsed = 0
        self._timer.timeout.connect(self._on_tick)

        self.hide()

    # --- dragging ---
    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag.dragging = True
            self._drag.press_pos = event.globalPosition().toPoint()
            self._drag.start_pos = self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag.dragging and self._drag.press_pos is not None and self._drag.start_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag.press_pos
            self._move_clamped(self._drag.start_pos + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._drag.dragging:
            self._drag.dragging = False
            self._drag.press_pos = None
            self._drag.start_pos = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _move_clamped(self, pos: QPoint):
        p = self.parentWidget()
        if not p:
            self.move(pos)
            return
        margin = 8
        max_x = max(margin, p.width() - self.width() - margin)
        max_y = max(margin, p.height() - self.height() - margin)
        x = max(margin, min(max_x, pos.x()))
        y = max(margin, min(max_y, pos.y()))
        self.move(x, y)

    # --- actions ---
    def show_default(self):
        p = self.parentWidget()
        if p:
            self._move_clamped(QPoint(p.width() - self.width() - 16, p.height() - self.height() - 16))
        self.show()
        self.raise_()

    def _on_minimize(self):
        self._stop_timer()
        self._cleanup_thread()
        self.hide()
        self.minimized.emit()

    def _on_send(self):
        prompt = self.input.toPlainText().strip()
        if not prompt:
            return
        # 显示区保留本窗口内对话（不落盘）
        self.output.append(f"[User]\n{prompt}\n")
        self._status.setText("生成中 0 秒")
        self._elapsed = 0
        self._timer.start()
        self.send_btn.setEnabled(False)

        system = "你是 VNEngine 的 AI 辅助小助手。请用简洁、可执行的方式回答用户问题。"
        self._cleanup_thread()
        self._thread = _LLMThread(self._config_manager, prompt=prompt, system=system, history=list(self._history), parent=self)
        self._thread.finishedText.connect(self._on_done)
        self._thread.finishedWithHistory.connect(self._on_done_with_history)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _on_tick(self):
        self._elapsed += 1
        self._status.setText(f"生成中 {self._elapsed} 秒")

    def _stop_timer(self):
        if self._timer.isActive():
            self._timer.stop()
        self._status.setText("")

    def _on_done(self, text: str):
        self._stop_timer()
        self.send_btn.setEnabled(True)
        self.output.append("[Assistant]\n" + (text.strip() or "(空响应)") + "\n")

    def _on_done_with_history(self, text: str, history: list):
        # 更新上下文（仅内存保留）
        if isinstance(history, list):
            self._history = [m for m in history if isinstance(m, dict) and m.get("role") in {"user", "assistant"}]
            # 限制长度：最多 N 轮（user+assistant 为一轮）
            max_msgs = max(2, int(self._max_history_turns) * 2)
            if len(self._history) > max_msgs:
                self._history = self._history[-max_msgs:]
        self._on_done(text)

    def _on_failed(self, msg: str):
        self._stop_timer()
        self.send_btn.setEnabled(True)
        self.output.append("[Error]\n" + (msg.strip() or "未知错误") + "\n")

    def _clear_context(self):
        self._history = []
        self.output.append("[System]\n已清空上下文（仅影响本窗口会话）。\n")

    def _cleanup_thread(self):
        if self._thread is None:
            return
        try:
            if self._thread.isRunning():
                self._thread.requestInterruption()
                self._thread.quit()
                self._thread.wait(300)
        except Exception:
            pass
        self._thread = None
