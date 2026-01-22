# -*- coding: utf-8 -*-
"""
BGM专项Agent界面
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
    QCheckBox,
    QScrollArea,
    QSplitter,
)
from PyQt6.QtCore import Qt, pyqtSignal

from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.config_manager import ConfigManager
from src.ai.core.models import PendingLists, BGMPendingItem, TaskAssignment
from src.ai.agents.bgm_agent import BGMAgent
from src.designer.async_elapsed_runner import AsyncElapsedRunner


class AIBGMPanel(QWidget):
    """BGM生成专项界面"""

    modified = pyqtSignal()

    def __init__(self, project_manager: AIProjectManager, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.project_manager = project_manager
        self.config_manager = config_manager
        self.pending_items: List[BGMPendingItem] = []
        self.current_item: Optional[BGMPendingItem] = None
        self.bgm_agent: Optional[BGMAgent] = None
        self._is_busy = False
        self._runner = AsyncElapsedRunner(self)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        self.project_label = QLabel("未加载AI工程")
        try:
            self.project_label.setProperty("pill", "true")
        except Exception:
            pass
        header.addWidget(self.project_label)
        self.reload_btn = QPushButton("刷新待生成列表")
        self.reload_btn.clicked.connect(self.refresh)
        header.addWidget(self.reload_btn)
        header.addStretch(1)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self.list_widget = QListWidget()
        self.list_widget.itemSelectionChanged.connect(self.on_item_selected)
        splitter.addWidget(self.list_widget)

        right_container = QWidget()
        right = QVBoxLayout(right_container)

        info_group = QGroupBox("BGM详情")
        form = QFormLayout()
        self.bgm_id_label = QLabel("-")
        form.addRow("ID", self.bgm_id_label)
        self.status_label = QLabel("-")
        form.addRow("状态", self.status_label)
        self.mood_label = QLabel("-")
        form.addRow("情绪", self.mood_label)
        self.style_label = QLabel("-")
        form.addRow("曲风", self.style_label)
        self.duration_label = QLabel("-")
        form.addRow("时长(秒)", self.duration_label)
        self.model_combo = QComboBox()
        self.model_combo.addItem("Suno", "suno")
        self.model_combo.setEnabled(False)
        form.addRow("模型", self.model_combo)
        info_group.setLayout(form)
        right.addWidget(info_group)

        param_group = QGroupBox("条目参数（可编辑并持久化）")
        param_form = QFormLayout()

        self.input_type_combo = QComboBox()
        self.input_type_combo.addItem("20 自定义/歌词模式", "20")
        self.input_type_combo.addItem("10 灵感模式", "10")
        param_form.addRow("inputType", self.input_type_combo)

        self.make_instrumental_check = QCheckBox("纯音乐（makeInstrumental=true）")
        self.make_instrumental_check.setChecked(True)
        self.make_instrumental_check.stateChanged.connect(self._sync_prompt_enabled)
        param_form.addRow("makeInstrumental", self.make_instrumental_check)

        self.mv_version_edit = QLineEdit()
        self.mv_version_edit.setPlaceholderText("可选：如 chirp-v4/chirp-v5；留空则使用 API 配置默认")
        param_form.addRow("mvVersion", self.mv_version_edit)

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("可选：风格 tags（如 piano, orchestral, cinematic）")
        param_form.addRow("tags", self.tags_edit)

        self.save_item_params_btn = QPushButton("保存条目参数")
        self.save_item_params_btn.clicked.connect(self._save_item_params)
        param_form.addRow("", self.save_item_params_btn)

        param_group.setLayout(param_form)
        right.addWidget(param_group)

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
        self.generate_btn = QPushButton("生成BGM")
        self.generate_btn.clicked.connect(self._generate_bgm)
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

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setWidget(right_container)
        splitter.addWidget(right_scroll)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)

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
        self.pending_items = list(pending_lists.bgms or [])
        self._populate_list()
        if self.pending_items:
            self.list_widget.setCurrentRow(0)
        else:
            self._clear_detail()
            self.progress_label.setText("状态：无待生成BGM")

    def _populate_list(self):
        self.list_widget.clear()
        for item in self.pending_items:
            text = f"{item.bgm_id} ({item.status})"
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

    def _get_item_by_id(self, item_id: str) -> Optional[BGMPendingItem]:
        for it in self.pending_items:
            if it.item_id == item_id:
                return it
        return None

    def _show_item(self, item: BGMPendingItem):
        self.bgm_id_label.setText(item.bgm_id)
        self.status_label.setText(item.status)
        self.mood_label.setText(item.mood or "-")
        self.style_label.setText(item.style or "-")
        self.duration_label.setText(str(item.duration))

        # 条目参数显示
        idx = self.input_type_combo.findData(str(getattr(item, "input_type", "20") or "20"))
        self.input_type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.make_instrumental_check.setChecked(bool(getattr(item, "make_instrumental", True)))
        self.mv_version_edit.setText(str(getattr(item, "mv_version", "") or ""))
        self.tags_edit.setText(str(getattr(item, "tags", "") or ""))
        self._sync_prompt_enabled()

        prompt_text = item.prompt or self._default_prompt(item)
        self.prompt_edit.setPlainText(prompt_text)
        self.path_edit.setText(self._resource_path(item.file_path or f"resources/audios/{item.bgm_id}.mp3").as_posix())
        self.file_label.setText(f"文件：{item.file_path or '待生成'}")
        self.progress_label.setText("状态：就绪")

    def _clear_detail(self):
        self.current_item = None
        self.bgm_id_label.setText("-")
        self.status_label.setText("-")
        self.mood_label.setText("-")
        self.style_label.setText("-")
        self.duration_label.setText("-")
        self.prompt_edit.clear()
        self.path_edit.clear()
        self.file_label.setText("文件：")
        self.progress_label.setText("状态：等待选择")

        self.input_type_combo.setCurrentIndex(0)
        self.make_instrumental_check.setChecked(True)
        self.mv_version_edit.clear()
        self.tags_edit.clear()

    def _sync_prompt_enabled(self):
        # 纯音乐时 prompt 允许为空；UI 上不强制禁用编辑，但给出更清晰的交互：纯音乐时允许留空。
        # 这里不 disable，避免用户仍想填描述；真正发送时会按接口要求置空。
        return

    def _save_item_params(self):
        if not self.current_item:
            return
        try:
            self.current_item.input_type = str(self.input_type_combo.currentData() or "20")
            self.current_item.make_instrumental = bool(self.make_instrumental_check.isChecked())
            mv = self.mv_version_edit.text().strip()
            self.current_item.mv_version = mv or None
            self.current_item.tags = self.tags_edit.text().strip()

            self._persist_pending_lists()
            self._refresh_list_texts()
            self.progress_label.setText("状态：条目参数已保存")
        except Exception as exc:
            QMessageBox.warning(self, "提示", f"保存条目参数失败: {exc}")

    # ==================== 工具 ====================
    def _default_prompt(self, item: BGMPendingItem) -> str:
        if self._ensure_agent():
            return self.bgm_agent.build_prompt(item.description, item.mood, item.style)
        return item.description

    def _ensure_project(self) -> bool:
        if self.project_manager.current_project is None:
            QMessageBox.warning(self, "提示", "请先创建或打开AI工程。")
            return False
        return True

    def _ensure_agent(self) -> bool:
        if self.bgm_agent:
            return True
        try:
            self.bgm_agent = BGMAgent(self.config_manager)
            return True
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"初始化BGM Agent失败: {exc}")
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
        default_dir = self._project_root() / "resources" / "bgm"
        default_dir.mkdir(parents=True, exist_ok=True)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存BGM",
            str(default_dir / f"{(self.current_item.bgm_id if self.current_item else 'bgm')}.mp3"),
            "音频文件 (*.mp3)",
        )
        if file_path:
            self.path_edit.setText(file_path)

    def _save_prompt_only(self):
        if not self.current_item:
            return
        text = self.prompt_edit.toPlainText()
        # 纯音乐允许保存空字符串
        if (not text.strip()) and (not bool(getattr(self.current_item, "make_instrumental", True))):
            QMessageBox.warning(self, "提示", "提示词为空，无法保存。")
            return
        self.current_item.prompt = text.strip() if text is not None else ""
        self._persist_pending_lists()
        self.progress_label.setText("状态：指令已保存")

    def _generate_bgm(self):
        if self._is_busy or not self._ensure_project() or not self.current_item or not self._ensure_agent():
            return

        make_instrumental = bool(getattr(self.current_item, "make_instrumental", True))
        if make_instrumental:
            prompt = ""
        else:
            prompt = self.prompt_edit.toPlainText().strip() or self._default_prompt(self.current_item)

        save_path = self.path_edit.text().strip()
        if not save_path:
            self._choose_path()
            save_path = self.path_edit.text().strip()
        if not save_path:
            QMessageBox.warning(self, "提示", "请先选择保存路径。")
            return

        params = {
            "bgm_id": self.current_item.bgm_id,
            "description": self.current_item.description,
            "mood": self.current_item.mood,
            "style": self.current_item.style,
            "duration": self.current_item.duration,
            "loop": self.current_item.loop,
            "prompt": prompt,
            "tags": getattr(self.current_item, "tags", "") or "",
            "input_type": getattr(self.current_item, "input_type", "20") or "20",
            "make_instrumental": bool(getattr(self.current_item, "make_instrumental", True)),
            "mv_version": getattr(self.current_item, "mv_version", None),
            "output_path": save_path,
            "project_root": str(self._project_root()),
        }
        task = TaskAssignment(
            task_id=f"bgm-{int(time.time()*1000)}",
            agent_type="bgm",
            task_type="generate_bgm_item",
            task_content=f"生成BGM {self.current_item.bgm_id}",
            parameters=params,
        )

        self._is_busy = True
        self.generate_btn.setEnabled(False)

        def _do_work():
            return self.bgm_agent.execute(task)

        def _on_success(resp):
            if resp.status != "success":
                QMessageBox.critical(self, "生成失败", resp.error_message or "生成失败")
                self.progress_label.setText("状态：生成失败")
                return

            outputs = self._normalize_paths(resp.output_files or [])
            if outputs:
                self.current_item.file_path = outputs[0]
            # 纯音乐时 prompt 允许为空字符串
            self.current_item.prompt = prompt
            self.current_item.model = self.model_combo.currentData()
            self.current_item.status = "generated"
            self.file_label.setText("文件：" + (self.current_item.file_path or ""))
            self._persist_pending_lists()
            self._refresh_list_texts()
            self.status_label.setText(self.current_item.status)
            self.progress_label.setText("状态：生成完成")

        def _on_finally():
            self._is_busy = False
            self.generate_btn.setEnabled(True)

        started = self._runner.run(
            label=self.progress_label,
            base_text="状态：生成中...",
            fn=_do_work,
            on_success=_on_success,
            on_finally=_on_finally,
        )
        if not started:
            self._is_busy = False
            self.generate_btn.setEnabled(True)
            QMessageBox.information(self, "提示", "已有任务在运行，请稍候。")

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
        project.pending_lists.bgms = self.pending_items
        self.project_manager.update_pending_lists(project.pending_lists)
        self.modified.emit()

    def _refresh_list_texts(self):
        for i in range(self.list_widget.count()):
            item_widget = self.list_widget.item(i)
            item_data = self._get_item_by_id(item_widget.data(Qt.ItemDataRole.UserRole))
            if not item_data:
                continue
            item_widget.setText(f"{item_data.bgm_id} ({item_data.status})")
