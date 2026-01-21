# -*- coding: utf-8 -*-
"""Progress monitor with snapshot and persistence helpers."""

from pathlib import Path
from typing import Optional
from .models import ProgressTrack


class ProgressMonitor:
    def __init__(self):
        self.progress: Optional[ProgressTrack] = None

    def bind(self, progress: ProgressTrack):
        """Attach a ProgressTrack instance for subsequent updates."""
        self.progress = progress

    def snapshot(self) -> Optional[ProgressTrack]:
        return self.progress

    def save(self, path: Path):
        """Persist current progress to disk for resume."""
        if not self.progress:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.progress.model_dump_json(indent=2, ensure_ascii=False))

    def load(self, path: Path) -> Optional[ProgressTrack]:
        """Load progress snapshot from disk."""
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8")
        self.progress = ProgressTrack.model_validate_json(content)
        return self.progress

    # Lightweight hooks to tweak counters; MasterAgent remains the authority
    def on_task_started(self):
        # MasterAgent already维护计数，这里仅保留钩子以便未来扩展
        return

    def on_task_finished(self, success: bool):
        # 计数由MasterAgent管理，监控器保持轻量
        return
