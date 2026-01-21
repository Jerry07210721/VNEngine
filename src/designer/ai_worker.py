# -*- coding: utf-8 -*-
"""后台线程执行 MasterAgent 任务并通过信号反馈进度。"""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal


class AITaskWorker(QThread):
    progress_signal = pyqtSignal(object)
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, master_agent, parent=None):
        super().__init__(parent)
        self.master_agent = master_agent
        self.cancel_requested = False

    def request_cancel(self):
        self.cancel_requested = True
        try:
            if getattr(self.master_agent, "scheduler", None):
                self.master_agent.scheduler.queue.clear()
                self.master_agent.pending_task_list = []
        except Exception:
            pass

    def run(self):
        try:
            while (
                self.master_agent
                and getattr(self.master_agent, "pending_task_list", None)
                and len(self.master_agent.pending_task_list) > 0
                and not self.cancel_requested
            ):
                response = self.master_agent.execute_next_task(callback=self._emit_progress)
                if response and response.message:
                    self.log_signal.emit(response.message)
                if self.cancel_requested:
                    break
            self._emit_progress(self.master_agent.get_progress() if self.master_agent else None)
        except Exception as exc:  # pragma: no cover - runtime safety
            self.log_signal.emit(f"任务执行异常: {exc}")
        finally:
            self.finished_signal.emit()

    def _emit_progress(self, progress):
        self.progress_signal.emit(progress)
