# -*- coding: utf-8 -*-
"""AI 任务进度监控与结果预览对话框。"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QProgressBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class AIProgressDialog(QDialog):
    """显示 Agent 任务进度、阶段和生成结果的预览入口。"""

    canceled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 任务进度")
        self.resize(880, 640)

        self.stage_label = QLabel("当前阶段：准备中")
        self.progress_bar = QProgressBar()
        self.percent_label = QLabel("0%")

        top_row = QHBoxLayout()
        top_row.addWidget(self.stage_label)
        top_row.addStretch(1)
        top_row.addWidget(self.percent_label)

        self.progress_bar.setRange(0, 100)

        self.task_list = QListWidget()
        self.task_list.setMinimumWidth(260)

        # 预览区域
        self.preview_tabs = QTabWidget()
        self.text_preview = QTextEdit(); self.text_preview.setReadOnly(True)
        self.material_list = QListWidget()
        self.preview_tabs.addTab(self.text_preview, "剧情预览")
        self.preview_tabs.addTab(self.material_list, "素材预览")

        mid_row = QHBoxLayout()
        mid_row.addWidget(self.task_list, 1)
        mid_row.addWidget(self.preview_tabs, 2)

        self.log_view = QTextEdit(); self.log_view.setReadOnly(True)

        self.cancel_btn = QPushButton("取消任务")
        self.cancel_btn.clicked.connect(self.canceled.emit)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.cancel_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self.progress_bar)
        layout.addLayout(mid_row)
        layout.addWidget(QLabel("实时日志"))
        layout.addWidget(self.log_view, 1)
        layout.addLayout(btn_row)

    # --- 更新接口 ---
    def update_progress(self, progress: Any):
        """使用 ProgressTrack 或兼容字典更新界面。"""
        if progress is None:
            return
        pct = 0.0
        stage = ""
        details = []
        try:
            pct = float(progress.progress_percentage)
            stage = getattr(progress, "current_stage", "")
            details = getattr(progress, "task_details", [])
        except Exception:
            pct = float(progress.get("progress_percentage", 0)) if isinstance(progress, dict) else 0.0
            stage = progress.get("current_stage", "") if isinstance(progress, dict) else ""
            details = progress.get("task_details", []) if isinstance(progress, dict) else []

        self.progress_bar.setValue(int(pct))
        self.percent_label.setText(f"{pct:.1f}%")
        self.stage_label.setText(f"当前阶段：{stage or '进行中'}")
        self._refresh_tasks(details)

    def _refresh_tasks(self, details: Iterable[Any]):
        self.task_list.clear()
        for item in details or []:
            try:
                status = getattr(item, "status", None) or (item.get("status") if isinstance(item, dict) else "")
                msg = getattr(item, "message", None) or (item.get("message") if isinstance(item, dict) else "")
                task_id = getattr(item, "task_id", None) or (item.get("task_id") if isinstance(item, dict) else "")
                display = f"[{status}] {task_id} - {msg}"
            except Exception:
                display = str(item)
            self.task_list.addItem(QListWidgetItem(display))

    def append_log(self, text: str):
        if not text:
            return
        self.log_view.moveCursor(self.log_view.textCursor().MoveOperation.End)
        self.log_view.insertPlainText(text + "\n")
        self.log_view.moveCursor(self.log_view.textCursor().MoveOperation.End)

    def set_text_preview(self, content: str):
        self.text_preview.setPlainText(content or "")

    def set_materials(self, paths: list[str]):
        self.material_list.clear()
        for p in paths or []:
            self.material_list.addItem(QListWidgetItem(p))
