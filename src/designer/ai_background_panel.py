# -*- coding: utf-8 -*-
"""
背景专项Agent界面
"""

import time
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QComboBox,
    QGroupBox,
    QWidget,
    QMessageBox,
    QLineEdit,
    QFormLayout,
    QFileDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal

from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.config_manager import ConfigManager
from src.ai.core.models import PendingLists, BackgroundPendingItem, TaskAssignment
from src.ai.agents.background_agent import BackgroundAgent


class AIBackgroundPanel(QWidget):
    """背景生成专项界面"""

    modified = pyqtSignal()

    def __init__(self, project_manager: AIProjectManager, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.project_manager = project_manager
        self.config_manager = config_manager
        self.pending_items: List[BackgroundPendingItem] = []
        self.current_item: Optional[BackgroundPendingItem] = None
        self.bg_agent: Optional[BackgroundAgent] = None
        self._is_busy = False
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        self.project_label = QLabel("未加载AI工程")
        header.addWidget(self.project_label)
        self.reload_btn = QPushButton("刷新待生成列表")
        self.reload_btn.clicked.connect(self.refresh)
        header.addWidget(self.reload_btn)
        header.addStretch(1)
        layout.addLayout(header)

        main = QHBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.itemSelectionChanged.connect(self.on_item_selected)
        main.addWidget(self.list_widget, 2)

        right = QVBoxLayout()

        info_group = QGroupBox("背景详情")
        form = QFormLayout()
        self.bg_id_label = QLabel("-")
        form.addRow("ID", self.bg_id_label)
        self.status_label = QLabel("-")
        form.addRow("状态", self.status_label)
        self.time_label = QLabel("-")
        form.addRow("时间/天气", self.time_label)
        self.aspect_combo = QComboBox()
        for ratio in ["16:9", "3:2", "4:3", "1:1"]:
            self.aspect_combo.addItem(ratio)
        form.addRow("画幅", self.aspect_combo)
        self.model_combo = QComboBox()
        self.model_combo.addItem("FLUX", "flux")
        self.model_combo.addItem("Midjourney", "midjourney")
        form.addRow("模型", self.model_combo)
        info_group.setLayout(form)
        right.addWidget(info_group)

        prompt_group = QGroupBox("提示词")
        prompt_layout = QVBoxLayout()
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("自动生成的提示词，可修改后发送")
        self.prompt_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        prompt_layout.addWidget(self.prompt_edit)
        btn_row = QHBoxLayout()
        self.fill_prompt_btn = QPushButton("填充默认提示词")
        self.fill_prompt_btn.clicked.connect(self._fill_prompt)
        self.save_prompt_btn = QPushButton("保存指令")
        self.save_prompt_btn.clicked.connect(self._save_prompt_only)
        btn_row.addWidget(self.fill_prompt_btn)
        btn_row.addWidget(self.save_prompt_btn)
        btn_row.addStretch(1)
        prompt_layout.addLayout(btn_row)
        prompt_group.setLayout(prompt_layout)
        right.addWidget(prompt_group)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_btn = QPushButton("选择保存路径")
        self.path_btn.clicked.connect(self._choose_path)
        path_row.addWidget(self.path_edit)
        path_row.addWidget(self.path_btn)
        right.addLayout(path_row)

        action_row = QHBoxLayout()
        self.generate_btn = QPushButton("生成背景")
        self.generate_btn.clicked.connect(self._generate_bg)
        self.mark_btn = QPushButton("标记完成")
        self.mark_btn.clicked.connect(self.mark_generated)
        self.reset_btn = QPushButton("重置待生成")
        self.reset_btn.clicked.connect(self.reset_status)
        action_row.addWidget(self.generate_btn)
        action_row.addWidget(self.mark_btn)
        action_row.addWidget(self.reset_btn)
        action_row.addStretch(1)
        right.addLayout(action_row)

        self.file_label = QLabel("文件：")
        self.file_label.setWordWrap(True)
        right.addWidget(self.file_label)
        self.progress_label = QLabel("状态：等待选择")
        right.addWidget(self.progress_label)
        right.addStretch(1)

        main.addLayout(right, 3)
        layout.addLayout(main)

    # ==================== 列表刷新 ====================
    def refresh(self):
        project = self.project_manager.current_project
        if project is None:
            self.project_label.setText("未加载AI工程")
            self.pending_items = []
            self.list_widget.clear()
            self._clear_detail()
            return

        self.project_label.setText(f"工程：{project.ai_project_info.name}")
        pending_lists: PendingLists = project.pending_lists or PendingLists()
        self.pending_items = list(pending_lists.backgrounds or [])
        self._populate_list()
        if self.pending_items:
            self.list_widget.setCurrentRow(0)
        else:
            self._clear_detail()
            self.progress_label.setText("状态：无待生成背景")

    def _populate_list(self):
        self.list_widget.clear()
        for item in self.pending_items:
            text = f"{item.bg_id} ({item.status})"
            lw = QListWidgetItem(text)
            lw.setData(Qt.ItemDataRole.UserRole, item.item_id)
            self.list_widget.addItem(lw)

    def on_item_selected(self):
        current = self.list_widget.currentItem()
        if not current:
            self._clear_detail()
            return

        item_id = current.data(Qt.ItemDataRole.UserRole)
        item = self._get_item_by_id(item_id)
        self.current_item = item
        if item:
            self._show_item(item)

    def _get_item_by_id(self, item_id: str) -> Optional[BackgroundPendingItem]:
        for it in self.pending_items:
            if it.item_id == item_id:
                return it
        return None

    def _show_item(self, item: BackgroundPendingItem):
        self.bg_id_label.setText(item.bg_id)
        self.status_label.setText(item.status)
        self.time_label.setText(item.time_weather or "-")
        prompt_text = item.prompt or self._default_prompt(item)
        self.prompt_edit.setPlainText(prompt_text)
        self.path_edit.setText(self._resource_path(item.file_path or f"resources/backgrounds/{item.bg_id}.png").as_posix())
        self.file_label.setText(f"文件：{item.file_path or '待生成'}")
        self.progress_label.setText("状态：就绪")

    def _clear_detail(self):
        self.current_item = None
        self.bg_id_label.setText("-")
        self.status_label.setText("-")
        self.time_label.setText("-")
        self.prompt_edit.clear()
        self.path_edit.clear()
        self.file_label.setText("文件：")
        self.progress_label.setText("状态：等待选择")

    # ==================== 工具 ====================
    def _default_prompt(self, item: BackgroundPendingItem) -> str:
        if self._ensure_agent():
            return self.bg_agent.build_prompt(item.description, item.atmosphere, item.time_weather)
        return item.description

    def _ensure_project(self) -> bool:
        if self.project_manager.current_project is None:
            QMessageBox.warning(self, "提示", "请先创建或打开AI工程。")
            return False
        return True

    def _ensure_agent(self) -> bool:
        if self.bg_agent:
            return True
        try:
            self.bg_agent = BackgroundAgent(self.config_manager)
            return True
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"初始化背景Agent失败: {exc}")
            return False

    def _project_root(self) -> Path:
        project = self.project_manager.current_project
        if project is None:
            return Path.cwd() / "output" / "ai_project"

        if project.ai_project_info.vng_project_path:
            return Path(project.ai_project_info.vng_project_path).expanduser().resolve().parent

        if self.project_manager.current_file_path:
            return (
                Path(self.project_manager.current_file_path)
                .expanduser()
                .resolve()
                .parent
                / project.ai_project_info.name
            )

        return Path.cwd() / "output" / (project.ai_project_info.name or "ai_project")

    def _resource_path(self, rel_path: str) -> Path:
        p = Path(rel_path)
        return p.expanduser().resolve() if p.is_absolute() else (self._project_root() / p).expanduser().resolve()

    def _abs_path(self, path_str: str) -> Path:
        p = Path(path_str)
        return p if p.is_absolute() else (self._project_root() / p).resolve()

    def _normalize_paths(self, paths: List[str]) -> List[str]:
        root = self._project_root()
        normalized = []
        for p in paths:
            try:
                rel = self._abs_path(p).relative_to(root).as_posix()
                normalized.append(rel)
            except Exception:
                normalized.append(Path(p).as_posix())
        return normalized

    # ==================== 交互 ====================
    def _fill_prompt(self):
        if not self.current_item:
            return
        self.prompt_edit.setPlainText(self._default_prompt(self.current_item))

    def _choose_path(self):
        default_dir = self._project_root() / "resources" / "backgrounds"
        default_dir.mkdir(parents=True, exist_ok=True)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存背景图",
            str(default_dir / f"{(self.current_item.bg_id if self.current_item else 'bg')}.png"),
            "PNG 图片 (*.png)",
        )
        if file_path:
            self.path_edit.setText(file_path)

    def _save_prompt_only(self):
        if not self.current_item:
            return
        text = self.prompt_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "提示词为空，无法保存。")
            return
        self.current_item.prompt = text
        self._persist_pending_lists()
        self.progress_label.setText("状态：指令已保存")

    def _generate_bg(self):
        if self._is_busy or not self._ensure_project() or not self.current_item or not self._ensure_agent():
            return
        prompt = self.prompt_edit.toPlainText().strip() or self._default_prompt(self.current_item)
        save_path = self.path_edit.text().strip()
        if not save_path:
            self._choose_path()
            save_path = self.path_edit.text().strip()
        if not save_path:
            QMessageBox.warning(self, "提示", "请先选择保存路径。")
            return

        params = {
            "bg_id": self.current_item.bg_id,
            "description": self.current_item.description,
            "atmosphere": self.current_item.atmosphere,
            "time_weather": self.current_item.time_weather,
            "prompt": prompt,
            "output_path": save_path,
            "aspect": self.aspect_combo.currentText(),
            "model": self.model_combo.currentData(),
            "project_root": str(self._project_root()),
        }
        task = TaskAssignment(
            task_id=f"bg-{int(time.time()*1000)}",
            agent_type="background",
            task_type="generate_background_item",
            task_content=f"生成背景 {self.current_item.bg_id}",
            parameters=params,
        )
        self._is_busy = True
        self.progress_label.setText("状态：生成中...")
        try:
            resp = self.bg_agent.execute(task)
        finally:
            self._is_busy = False
        if resp.status != "success":
            QMessageBox.critical(self, "生成失败", resp.error_message or "生成失败")
            self.progress_label.setText("状态：生成失败")
            return

        outputs = self._normalize_paths(resp.output_files or [])
        if outputs:
            self.current_item.file_path = outputs[0]
        self.current_item.prompt = prompt
        self.current_item.model = self.model_combo.currentData()
        self.current_item.status = "generated"
        self.file_label.setText("文件：" + (self.current_item.file_path or ""))
        self._persist_pending_lists()
        self._refresh_list_texts()
        self.status_label.setText(self.current_item.status)
        self.progress_label.setText("状态：生成完成")

    def mark_generated(self):
        if not self.current_item:
            return
        self.current_item.status = "generated"
        self._persist_pending_lists()
        self._refresh_list_texts()
        self.status_label.setText(self.current_item.status)
        self.progress_label.setText("状态：已标记完成")

    def reset_status(self):
        if not self.current_item:
            return
        self.current_item.status = "pending"
        self._persist_pending_lists()
        self._refresh_list_texts()
        self.status_label.setText(self.current_item.status)
        self.progress_label.setText("状态：已重置")

    def _persist_pending_lists(self):
        project = self.project_manager.current_project
        if project is None:
            return
        project.pending_lists.backgrounds = self.pending_items
        self.project_manager.update_pending_lists(project.pending_lists)
        self.modified.emit()

    def _refresh_list_texts(self):
        for i in range(self.list_widget.count()):
            item_widget = self.list_widget.item(i)
            item_data = self._get_item_by_id(item_widget.data(Qt.ItemDataRole.UserRole))
            if not item_data:
                continue
            item_widget.setText(f"{item_data.bg_id} ({item_data.status})")
