# -*- coding: utf-8 -*-
"""AI 主控 Agent 宿主面板。

- generate 模式：沿用现有 `AIMasterControlPanel`（故事生成模式），不改动其逻辑。
- import 模式：使用 `AIImportControlPanel`（完整故事导入模式）。

通过读取 `project.ai_project_info.project_mode` 决定展示哪一套 UI。
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.config_manager import ConfigManager
from src.designer.ai_import_control_panel import AIImportControlPanel
from src.designer.ai_master_control_panel import AIMasterControlPanel


class AIMasterControlHostPanel(QWidget):
    """根据工程类型切换主控面板。"""

    modified = pyqtSignal()

    def __init__(self, project_manager: AIProjectManager, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.project_manager = project_manager
        self.config_manager = config_manager

        self._stack = QStackedWidget(self)
        self._panel_generate = AIMasterControlPanel(project_manager, config_manager, self)
        self._panel_import = AIImportControlPanel(project_manager, config_manager, self)

        self._panel_generate.modified.connect(self.modified.emit)
        self._panel_import.modified.connect(self.modified.emit)

        self._stack.addWidget(self._panel_generate)
        self._stack.addWidget(self._panel_import)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self.refresh()

    def _get_project_mode(self) -> str:
        project = getattr(self.project_manager, "current_project", None)
        if not project:
            return "generate"
        info = getattr(project, "ai_project_info", None)
        mode = getattr(info, "project_mode", "generate") if info else "generate"
        mode = str(mode or "generate").strip().lower()
        return mode if mode in {"generate", "import"} else "generate"

    def refresh(self):
        mode = self._get_project_mode()
        self._stack.setCurrentIndex(1 if mode == "import" else 0)

        # 两套面板都做 refresh，避免切换回来时显示旧缓存。
        try:
            self._panel_generate.refresh()
        except Exception:
            pass
        try:
            self._panel_import.refresh()
        except Exception:
            pass
