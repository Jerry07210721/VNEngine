# -*- coding: utf-8 -*-
"""Small helper to run long tasks off the UI thread and show elapsed time.

Specialist panels previously called agent.execute(...) on the UI thread, which
blocked the UI. This runner mirrors the pattern used in master control panel:
- execute a callable in a background QThread
- update a label with elapsed seconds while running

This module intentionally keeps API tiny and framework-agnostic.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable, Optional

from PyQt6.QtCore import QElapsedTimer, QObject, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QLabel, QMessageBox, QWidget


class _FunctionThread(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self._fn = fn

    def run(self) -> None:  # noqa: D401
        try:
            res = self._fn()
            self.result.emit(res)
        except Exception:  # noqa: BLE001
            self.error.emit(traceback.format_exc())


class AsyncElapsedRunner(QObject):
    """Run a callable in background and update a label with elapsed time."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._parent_widget = parent
        self._thread: Optional[_FunctionThread] = None
        self._timer: Optional[QTimer] = None
        self._elapsed: Optional[QElapsedTimer] = None
        self._label: Optional[QLabel] = None
        self._base_text: str = ""

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.isRunning())

    def update_base_text(self, base_text: str) -> None:
        """Update the base text shown on the label while running."""

        self._base_text = str(base_text or "")
        self._tick()

    def run(
        self,
        *,
        label: QLabel,
        base_text: str,
        fn: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Optional[Callable[[str], None]] = None,
        on_finally: Optional[Callable[[], None]] = None,
        tick_ms: int = 500,
    ) -> bool:
        """Start running `fn` in background.

        Returns False if a task is already running.
        """

        if self.is_running():
            return False

        self._label = label
        self._base_text = base_text
        self._elapsed = QElapsedTimer()
        self._elapsed.start()

        # Start elapsed ticker
        self._timer = QTimer(self._parent_widget)
        self._timer.setInterval(int(tick_ms))
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

        thread = _FunctionThread(fn)
        self._thread = thread

        def _cleanup() -> None:
            if self._timer is not None:
                self._timer.stop()
                self._timer.deleteLater()
                self._timer = None
            self._elapsed = None
            if self._thread is not None:
                self._thread.deleteLater()
                self._thread = None

        def _handle_error(err_text: str) -> None:
            try:
                if on_error is not None:
                    on_error(err_text)
                else:
                    QMessageBox.critical(self._parent_widget, "错误", err_text)
            finally:
                _cleanup()
                if on_finally is not None:
                    on_finally()

        def _handle_result(res: Any) -> None:
            try:
                on_success(res)
            finally:
                _cleanup()
                if on_finally is not None:
                    on_finally()

        thread.error.connect(_handle_error)
        thread.result.connect(_handle_result)
        thread.start()
        return True

    def _tick(self) -> None:
        if not self._label or not self._elapsed:
            return
        try:
            secs = int(self._elapsed.elapsed() / 1000)
            self._label.setText(f"{self._base_text} (已耗时 {secs}s)")
        except RuntimeError:
            # Label might be deleted when widget is closing.
            if self._timer is not None:
                self._timer.stop()
