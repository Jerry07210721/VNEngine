# -*- coding: utf-8 -*-
"""
立绘专项Agent界面
支持两种模式：仅生成设定图 / 生成全部立绘（基准+表情差分）
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
from src.ai.core.models import PendingLists, PortraitPendingItem, TaskAssignment
from src.ai.agents.portrait_agent import PortraitAgent


class AIPortraitPanel(QWidget):
    """立绘生成专项界面"""

    modified = pyqtSignal()

    def __init__(self, project_manager: AIProjectManager, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.project_manager = project_manager
        self.config_manager = config_manager
        self.pending_items: List[PortraitPendingItem] = []
        self.current_item: Optional[PortraitPendingItem] = None
        self.portrait_agent: Optional[PortraitAgent] = None
        self._is_busy = False
        self.base_image_path: Optional[str] = None
        self.mode: str = "design"  # design 或 full
        self.init_ui()

    # ==================== UI ====================
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

        # 基本信息
        info_group = QGroupBox("立绘详情")
        form = QFormLayout()
        self.char_label = QLabel("-")
        form.addRow("角色", self.char_label)
        self.status_value = QLabel("-")
        form.addRow("状态", self.status_value)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("仅生成设定图", "design")
        self.mode_combo.addItem("生成所有立绘(Flux)", "full")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("模式", self.mode_combo)
        self.expressions_edit = QLineEdit()
        self.expressions_edit.setPlaceholderText("用逗号分隔，例如: neutral, happy, sad")
        form.addRow("表情", self.expressions_edit)

        self.aspect_combo = QComboBox()
        for ratio in ["2:3", "3:4", "1:1", "16:9"]:
            self.aspect_combo.addItem(ratio)
        form.addRow("画幅", self.aspect_combo)

        info_group.setLayout(form)
        right.addWidget(info_group)

        # 设定图模式
        self.design_group = QGroupBox("仅生成设定图")
        design_layout = QVBoxLayout()
        self.design_model_combo = QComboBox()
        self.design_model_combo.addItem("Midjourney", "midjourney")
        self.design_model_combo.addItem("FLUX", "flux")
        design_row = QHBoxLayout()
        design_row.addWidget(QLabel("模型"))
        design_row.addWidget(self.design_model_combo)
        design_row.addStretch(1)
        design_layout.addLayout(design_row)

        self.design_prompt = QTextEdit()
        self.design_prompt.setPlaceholderText("自动生成的设定图提示词，发送前可修改")
        self.design_prompt.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        design_layout.addWidget(self.design_prompt)

        path_row = QHBoxLayout()
        self.design_path_edit = QLineEdit()
        self.design_path_btn = QPushButton("选择保存路径")
        self.design_path_btn.clicked.connect(self._choose_design_path)
        path_row.addWidget(self.design_path_edit)
        path_row.addWidget(self.design_path_btn)
        design_layout.addLayout(path_row)

        action_row_d = QHBoxLayout()
        self.design_fill_btn = QPushButton("填充默认提示词")
        self.design_fill_btn.clicked.connect(self._fill_design_prompt)
        self.design_save_prompt_btn = QPushButton("保存指令")
        self.design_save_prompt_btn.clicked.connect(self._save_prompt_only)
        self.design_generate_btn = QPushButton("生成设定图")
        self.design_generate_btn.clicked.connect(self._generate_design_sheet)
        action_row_d.addWidget(self.design_fill_btn)
        action_row_d.addWidget(self.design_save_prompt_btn)
        action_row_d.addWidget(self.design_generate_btn)
        design_layout.addLayout(action_row_d)

        self.design_group.setLayout(design_layout)
        right.addWidget(self.design_group)

        # 全量生成模式
        self.full_group = QGroupBox("生成所有立绘 (基准+表情差分，仅Flux)")
        full_layout = QVBoxLayout()
        self.full_prompt = QTextEdit()
        self.full_prompt.setPlaceholderText("基准立绘提示词，默认使用角色描述")
        self.full_prompt.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        full_layout.addWidget(self.full_prompt)

        full_btn_row1 = QHBoxLayout()
        self.full_fill_btn = QPushButton("填充默认提示词")
        self.full_fill_btn.clicked.connect(self._fill_full_prompt)
        self.base_generate_btn = QPushButton("生成基准图")
        self.base_generate_btn.clicked.connect(self._generate_base)
        full_btn_row1.addWidget(self.full_fill_btn)
        full_btn_row1.addWidget(self.base_generate_btn)
        full_btn_row1.addStretch(1)
        full_layout.addLayout(full_btn_row1)

        self.base_path_label = QLabel("基准图：未生成")
        full_layout.addWidget(self.base_path_label)

        full_btn_row2 = QHBoxLayout()
        self.expr_generate_btn = QPushButton("生成表情差分")
        self.expr_generate_btn.clicked.connect(self._generate_expressions)
        full_btn_row2.addWidget(self.expr_generate_btn)
        full_btn_row2.addStretch(1)
        full_layout.addLayout(full_btn_row2)

        self.full_group.setLayout(full_layout)
        right.addWidget(self.full_group)

        # 通用行动按钮
        action_row = QHBoxLayout()
        self.mark_done_btn = QPushButton("标记完成")
        self.mark_done_btn.clicked.connect(self.mark_generated)
        self.reset_btn = QPushButton("重置为待生成")
        self.reset_btn.clicked.connect(self.reset_status)
        action_row.addWidget(self.mark_done_btn)
        action_row.addWidget(self.reset_btn)
        action_row.addStretch(1)
        right.addLayout(action_row)

        self.filepaths_label = QLabel("")
        self.filepaths_label.setWordWrap(True)
        right.addWidget(self.filepaths_label)

        self.progress_label = QLabel("状态：等待选择")
        right.addWidget(self.progress_label)

        right.addStretch(1)
        main.addLayout(right, 3)
        layout.addLayout(main)

        self._on_mode_changed()

    # ==================== 基础状态 ====================
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
        self.pending_items = list(pending_lists.portraits or [])
        self._populate_list()
        if self.pending_items:
            self.list_widget.setCurrentRow(0)
        else:
            self._clear_detail()
            self.progress_label.setText("状态：无待生成立绘")

    def _populate_list(self):
        self.list_widget.clear()
        for item in self.pending_items:
            expr_count = len(item.expressions or [])
            text = f"{item.char_name} ({item.status}) | {expr_count}表情"
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

    def _get_item_by_id(self, item_id: str) -> Optional[PortraitPendingItem]:
        for it in self.pending_items:
            if it.item_id == item_id:
                return it
        return None

    def _show_item(self, item: PortraitPendingItem):
        self.char_label.setText(f"{item.char_name} ({item.char_id})")
        self.status_value.setText(item.status)
        self.expressions_edit.setText(", ".join(item.expressions) if item.expressions else "neutral, happy, sad")

        prompt_text = item.prompt or self._default_prompt(item)
        self.design_prompt.setPlainText(prompt_text)
        self.full_prompt.setPlainText(prompt_text)
        self.base_image_path = item.base_image_path
        if self.base_image_path:
            self.base_path_label.setText(f"基准图：{self.base_image_path}")
        else:
            self.base_path_label.setText("基准图：未生成")

        if item.file_paths:
            self.filepaths_label.setText("文件：" + ", ".join(item.file_paths))
        else:
            self.filepaths_label.setText("文件：待生成")

        self.progress_label.setText("状态：就绪，可生成")

    def _clear_detail(self):
        self.current_item = None
        self.char_label.setText("-")
        self.status_value.setText("-")
        self.expressions_edit.clear()
        self.design_prompt.clear()
        self.full_prompt.clear()
        self.design_path_edit.clear()
        self.base_path_label.setText("基准图：未生成")
        self.filepaths_label.setText("")
        self.progress_label.setText("状态：等待选择")

    # ==================== 工具方法 ====================
    def _default_prompt(self, item: PortraitPendingItem) -> str:
        parts = [item.char_name]
        if item.description:
            parts.append(item.description)
        return " | ".join(parts)

    def _ensure_project(self) -> bool:
        if self.project_manager.current_project is None:
            QMessageBox.warning(self, "提示", "请先创建或打开AI工程。")
            return False
        return True

    def _ensure_agent(self) -> bool:
        if self.portrait_agent:
            return True
        try:
            self.portrait_agent = PortraitAgent(self.config_manager)
            return True
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"初始化立绘Agent失败: {exc}")
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
        return (self._project_root() / rel_path).expanduser().resolve()

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

    def _parse_expressions(self, fallback: List[str]) -> List[str]:
        raw = self.expressions_edit.text().strip()
        if not raw:
            return list(fallback)
        tokens = [part.strip() for part in raw.replace("，", ",").split(",") if part.strip()]
        return tokens or list(fallback)

    def _on_mode_changed(self):
        self.mode = self.mode_combo.currentData() or "design"
        self.design_group.setVisible(self.mode == "design")
        self.full_group.setVisible(self.mode == "full")

    # ==================== 设定图模式 ====================
    def _fill_design_prompt(self):
        if not self.current_item:
            return
        prompt = self.portrait_agent.build_design_prompt(
            self.current_item.char_name,
            self.current_item.description or "",
        ) if self._ensure_agent() else self._default_prompt(self.current_item)
        self.design_prompt.setPlainText(prompt)

    def _choose_design_path(self):
        default_dir = self._project_root() / "resources" / "portraits"
        default_dir.mkdir(parents=True, exist_ok=True)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存设定图",
            str(default_dir / f"{(self.current_item.char_id if self.current_item else 'character')}_design.png"),
            "PNG 图片 (*.png)"
        )
        if file_path:
            self.design_path_edit.setText(file_path)

    def _save_prompt_only(self):
        if not self.current_item:
            return
        text = (self.design_prompt if self.mode == "design" else self.full_prompt).toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "提示词为空，无法保存。")
            return
        self.current_item.prompt = text
        self._persist_pending_lists()
        self.progress_label.setText("状态：指令已保存")

    def _generate_design_sheet(self):
        if self._is_busy or not self._ensure_project() or not self.current_item or not self._ensure_agent():
            return
        prompt = self.design_prompt.toPlainText().strip() or self._default_prompt(self.current_item)
        save_path = self.design_path_edit.text().strip()
        if not save_path:
            self._choose_design_path()
            save_path = self.design_path_edit.text().strip()
        if not save_path:
            QMessageBox.warning(self, "提示", "请先选择设定图保存路径。")
            return

        params = {
            "character_name": self.current_item.char_name,
            "description": self.current_item.description,
            "prompt": prompt,
            "save_path": save_path,
            "aspect": self.aspect_combo.currentText(),
            "model": self.design_model_combo.currentData() or "midjourney",
        }

        task = TaskAssignment(
            task_id=f"design-{int(time.time()*1000)}",
            agent_type="portrait",
            task_type="generate_design_sheet",
            task_content=f"设定图 {self.current_item.char_name}",
            parameters=params,
        )
        self._is_busy = True
        self.progress_label.setText("状态：生成设定图...")
        try:
            resp = self.portrait_agent.execute(task)
        finally:
            self._is_busy = False
        if resp.status != "success":
            QMessageBox.critical(self, "生成失败", resp.error_message or "生成失败")
            self.progress_label.setText("状态：生成失败")
            return

        outputs = self._normalize_paths(resp.output_files or [])
        if outputs:
            self.current_item.file_paths = outputs
        self.current_item.prompt = prompt
        self.current_item.model = self.design_model_combo.currentData() or "midjourney"
        self.current_item.status = "generated"
        self.filepaths_label.setText("文件：" + ", ".join(outputs))
        self._persist_pending_lists()
        self._refresh_list_texts()
        self.status_value.setText(self.current_item.status)
        self.progress_label.setText("状态：设定图生成完成")

    # ==================== 全量生成模式 ====================
    def _fill_full_prompt(self):
        if not self.current_item:
            return
        prompt = self.portrait_agent.build_design_prompt(
            self.current_item.char_name,
            self.current_item.description or "",
        ) if self._ensure_agent() else self._default_prompt(self.current_item)
        self.full_prompt.setPlainText(prompt)

    def _generate_base(self):
        if self._is_busy or not self._ensure_project() or not self.current_item or not self._ensure_agent():
            return
        prompt = self.full_prompt.toPlainText().strip() or self._default_prompt(self.current_item)
        rel_path = f"resources/portraits/{self.current_item.char_id}_neutral.png"
        output_path = self._resource_path(rel_path)
        params = {
            "char_id": self.current_item.char_id,
            "character_name": self.current_item.char_name,
            "description": self.current_item.description,
            "prompt": prompt,
            "output_path": str(output_path),
            "aspect": self.aspect_combo.currentText(),
            "model": "flux",
        }
        task = TaskAssignment(
            task_id=f"base-{int(time.time()*1000)}",
            agent_type="portrait",
            task_type="generate_base_portrait",
            task_content=f"基准立绘 {self.current_item.char_name}",
            parameters=params,
        )
        self._is_busy = True
        self.progress_label.setText("状态：生成基准图...")
        try:
            resp = self.portrait_agent.execute(task)
        finally:
            self._is_busy = False
        if resp.status != "success":
            QMessageBox.critical(self, "生成失败", resp.error_message or "生成失败")
            self.progress_label.setText("状态：基准生成失败")
            return
        outputs = self._normalize_paths(resp.output_files or [])
        if outputs:
            self.base_image_path = outputs[0]
            self.current_item.base_image_path = outputs[0]
            self.base_path_label.setText(f"基准图：{outputs[0]}")
            if self.current_item.file_paths:
                if outputs[0] not in self.current_item.file_paths:
                    self.current_item.file_paths.insert(0, outputs[0])
            else:
                self.current_item.file_paths = [outputs[0]]
        self.current_item.prompt = prompt
        self.current_item.model = "flux"
        self._persist_pending_lists()
        self._refresh_list_texts()
        self.progress_label.setText("状态：基准图生成完成")

    def _generate_expressions(self):
        if self._is_busy or not self._ensure_project() or not self.current_item or not self._ensure_agent():
            return
        if not (self.base_image_path or self.current_item.base_image_path):
            QMessageBox.warning(self, "提示", "请先生成基准图。")
            return
        expressions = self._parse_expressions(self.current_item.expressions or ["neutral", "happy", "sad"])
        # 移除neutral避免重复
        expressions = [e for e in expressions if e.lower() != "neutral"]
        if not expressions:
            QMessageBox.warning(self, "提示", "没有需要生成的表情。")
            return

        batches = []
        current_batch: List[str] = []
        for exp in expressions:
            current_batch.append(exp)
            if len(current_batch) == 4:
                batches.append(current_batch)
                current_batch = []
        if current_batch:
            batches.append(current_batch)

        all_outputs: List[str] = []
        for batch in batches:
            params = {
                "char_id": self.current_item.char_id,
                "character_name": self.current_item.char_name,
                "description": self.current_item.description,
                "expressions": batch,
                "aspect": self.aspect_combo.currentText(),
                "model": "flux",
                "base_image_path": str(self._abs_path(self.base_image_path or self.current_item.base_image_path)),
                "output_dir": str(self._resource_path("resources/portraits")),
            }
            task = TaskAssignment(
                task_id=f"expr-{int(time.time()*1000)}",
                agent_type="portrait",
                task_type="generate_expression_batch",
                task_content=f"表情差分 {self.current_item.char_name}",
                parameters=params,
            )
            self._is_busy = True
            self.progress_label.setText(f"状态：生成表情 {batch}...")
            try:
                resp = self.portrait_agent.execute(task)
            finally:
                self._is_busy = False
            if resp.status != "success":
                QMessageBox.critical(self, "生成失败", resp.error_message or "生成失败")
                self.progress_label.setText("状态：表情生成失败")
                return
            outputs = self._normalize_paths(resp.output_files or [])
            all_outputs.extend(outputs)

        if all_outputs:
            exist = set(self.current_item.file_paths or [])
            for f in all_outputs:
                if f not in exist:
                    exist.add(f)
            self.current_item.file_paths = list(exist)
        self.current_item.status = "generated"
        self._persist_pending_lists()
        self._refresh_list_texts()
        self.filepaths_label.setText("文件：" + ", ".join(self.current_item.file_paths or []))
        self.status_value.setText(self.current_item.status)
        self.progress_label.setText("状态：表情差分生成完成")

    # ==================== 标记与保存 ====================
    def mark_generated(self):
        if not self.current_item:
            return
        self.current_item.status = "generated"
        self._persist_pending_lists()
        self._refresh_list_texts()
        self.status_value.setText(self.current_item.status)
        self.progress_label.setText("状态：已标记完成")

    def reset_status(self):
        if not self.current_item:
            return
        self.current_item.status = "pending"
        self._persist_pending_lists()
        self._refresh_list_texts()
        self.status_value.setText(self.current_item.status)
        self.progress_label.setText("状态：已重置")

    def _persist_pending_lists(self):
        project = self.project_manager.current_project
        if project is None:
            return
        project.pending_lists.portraits = self.pending_items
        self.project_manager.update_pending_lists(project.pending_lists)
        self.modified.emit()

    def _refresh_list_texts(self):
        for i in range(self.list_widget.count()):
            item_widget = self.list_widget.item(i)
            item_data = self._get_item_by_id(item_widget.data(Qt.ItemDataRole.UserRole))
            if not item_data:
                continue
            expr_count = len(item_data.expressions or [])
            item_widget.setText(f"{item_data.char_name} ({item_data.status}) | {expr_count}表情")
