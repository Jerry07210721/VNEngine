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
    QSpinBox,
    QFormLayout,
    QFileDialog,
    QScrollArea,
    QSplitter,
)
from PyQt6.QtCore import Qt, pyqtSignal

from src.ai.utils.image_utils import get_image_size

from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.config_manager import ConfigManager
from src.ai.core.models import PendingLists, BackgroundPendingItem, TaskAssignment
from src.ai.agents.background_agent import BackgroundAgent
from src.designer.async_elapsed_runner import AsyncElapsedRunner


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

        info_group = QGroupBox("背景详情")
        form = QFormLayout()
        self.bg_id_label = QLabel("-")
        form.addRow("ID", self.bg_id_label)
        self.status_label = QLabel("-")
        form.addRow("状态", self.status_label)
        self.time_label = QLabel("-")
        form.addRow("时间/天气", self.time_label)
        self.aspect_combo = QComboBox()
        for ratio in ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "9:21", "21:9"]:
            self.aspect_combo.addItem(ratio)
        form.addRow("画幅", self.aspect_combo)
        self.model_combo = QComboBox()
        self.model_combo.addItem("FLUX", "flux")
        self.model_combo.addItem("Midjourney", "midjourney")
        form.addRow("模型", self.model_combo)
        info_group.setLayout(form)
        right.addWidget(info_group)

        # Midjourney 三步工作流
        self.mj_group = QGroupBox("Midjourney 三步工作流 (imagine → separate → upscale)")
        mj_form = QFormLayout()

        # Step1: imagine
        self.mj_model_combo = QComboBox()
        self.mj_model_combo.addItem("Midjourney V7", "mj-v7")
        self.mj_model_combo.addItem("Midjourney V6.1", "mj-v61")
        self.mj_model_combo.addItem("Niji 6", "mj-niji-6")
        mj_form.addRow("模型版本", self.mj_model_combo)

        # Step1 prompt（移动到 Step1）
        mj_prompt_box = QWidget()
        mj_prompt_layout = QVBoxLayout(mj_prompt_box)
        mj_prompt_layout.setContentsMargins(0, 0, 0, 0)
        self.mj_prompt_edit = QTextEdit()
        self.mj_prompt_edit.setPlaceholderText("自动生成的提示词，可修改后发送")
        self.mj_prompt_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        mj_prompt_layout.addWidget(self.mj_prompt_edit)
        mj_btn_row = QHBoxLayout()
        self.mj_fill_prompt_btn = QPushButton("填充默认提示词")
        self.mj_fill_prompt_btn.clicked.connect(self._fill_prompt)
        self.mj_save_prompt_btn = QPushButton("保存指令")
        self.mj_save_prompt_btn.clicked.connect(self._save_prompt_only)
        mj_btn_row.addWidget(self.mj_fill_prompt_btn)
        mj_btn_row.addWidget(self.mj_save_prompt_btn)
        mj_btn_row.addStretch(1)
        mj_prompt_layout.addLayout(mj_btn_row)
        mj_form.addRow("提示词", mj_prompt_box)

        self.mj_stylize_spin = QSpinBox()
        self.mj_stylize_spin.setRange(1, 1000)
        self.mj_stylize_spin.setValue(100)
        mj_form.addRow("风格化", self.mj_stylize_spin)

        self.mj_quality_combo = QComboBox()
        self.mj_quality_combo.addItem("0.5 标清", 0.5)
        self.mj_quality_combo.addItem("1 高清(默认)", 1)
        self.mj_quality_combo.addItem("2 超清", 2)
        self.mj_quality_combo.addItem("4 实验(仅v7)", 4)
        self.mj_quality_combo.setCurrentIndex(1)
        mj_form.addRow("画质", self.mj_quality_combo)

        self.mj_no_edit = QLineEdit()
        self.mj_no_edit.setPlaceholderText("排除关键词（逗号分隔，单个关键词不要包含空格）")
        mj_form.addRow("排除关键词", self.mj_no_edit)

        grid_row = QHBoxLayout()
        self.mj_grid_path_edit = QLineEdit()
        self.mj_grid_path_btn = QPushButton("选择四宫格保存路径")
        self.mj_grid_path_btn.clicked.connect(lambda: self._mj_choose_path(self.mj_grid_path_edit, suffix="_grid.png"))
        grid_row.addWidget(self.mj_grid_path_edit)
        grid_row.addWidget(self.mj_grid_path_btn)
        mj_form.addRow("四宫格保存", grid_row)

        self.mj_imagine_btn = QPushButton("1) Imagine 生成四宫格")
        self.mj_imagine_btn.clicked.connect(self._mj_imagine)
        mj_form.addRow("", self.mj_imagine_btn)

        # Step2: separate
        self.mj_sep_taskid_edit = QLineEdit()
        self.mj_sep_taskid_edit.setPlaceholderText("任务ID（来自 Step1 imagine 返回的 task id）")
        mj_form.addRow("拆分任务ID", self.mj_sep_taskid_edit)

        self.mj_index_combo = QComboBox()
        for i in [1, 2, 3, 4]:
            self.mj_index_combo.addItem(f"U{i}", i)
        mj_form.addRow("选择U图", self.mj_index_combo)

        sep_row = QHBoxLayout()
        self.mj_sep_path_edit = QLineEdit()
        self.mj_sep_path_btn = QPushButton("选择拆分图保存路径")
        self.mj_sep_path_btn.clicked.connect(lambda: self._mj_choose_path(self.mj_sep_path_edit, suffix="_U.png"))
        sep_row.addWidget(self.mj_sep_path_edit)
        sep_row.addWidget(self.mj_sep_path_btn)
        mj_form.addRow("拆分图保存", sep_row)

        self.mj_separate_btn = QPushButton("2) Separate 拆分U图")
        self.mj_separate_btn.clicked.connect(self._mj_separate)
        mj_form.addRow("", self.mj_separate_btn)

        # Step3: upscale
        self.mj_up_taskid_edit = QLineEdit()
        self.mj_up_taskid_edit.setPlaceholderText("任务ID（来自 Step2 separate 返回的 task id）")
        mj_form.addRow("高清任务ID", self.mj_up_taskid_edit)

        self.mj_up_type_combo = QComboBox()
        self.mj_up_type_combo.addItem("subtle（保留细节）", "subtle")
        self.mj_up_type_combo.addItem("creative（增强细节）", "creative")
        mj_form.addRow("放大类型", self.mj_up_type_combo)

        final_row = QHBoxLayout()
        self.mj_final_path_edit = QLineEdit()
        self.mj_final_path_btn = QPushButton("选择最终保存路径")
        self.mj_final_path_btn.clicked.connect(self._mj_choose_final_path)
        final_row.addWidget(self.mj_final_path_edit)
        final_row.addWidget(self.mj_final_path_btn)
        mj_form.addRow("最终保存", final_row)

        self.mj_upscale_btn = QPushButton("3) Upscale 高清放大并保存")
        self.mj_upscale_btn.clicked.connect(self._mj_upscale)
        mj_form.addRow("", self.mj_upscale_btn)

        self.mj_task_label = QLabel("任务：-")
        self.mj_task_label.setWordWrap(True)
        mj_form.addRow("任务信息", self.mj_task_label)

        self.mj_save_btn = QPushButton("保存MJ参数/状态")
        self.mj_save_btn.clicked.connect(self._mj_save_state_only)
        mj_form.addRow("", self.mj_save_btn)

        self.mj_group.setLayout(mj_form)
        right.addWidget(self.mj_group)

        # FLUX 指令区（Midjourney 三步模式下隐藏）
        self.prompt_group = QGroupBox("提示词")
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
        self.prompt_group.setLayout(prompt_layout)
        right.addWidget(self.prompt_group)

        # FLUX 参数（可编辑且可持久化）
        self.flux_params_group = QGroupBox("FLUX 参数")
        flux_form = QFormLayout()
        self.flux_model_combo = QComboBox()
        self.flux_model_combo.addItem("FLUX.1 Kontext", "flux-kontext")
        self.flux_model_combo.addItem("FLUX.2 Pro", "flux-2-pro")
        self.flux_model_combo.addItem("FLUX.2 Max", "flux-2-max")
        self.flux_model_combo.currentIndexChanged.connect(self._on_flux_model_changed)
        flux_form.addRow("模型版本", self.flux_model_combo)

        self.flux_mode_combo = QComboBox()
        self.flux_mode_combo.addItem("pro", "pro")
        self.flux_mode_combo.addItem("max", "max")
        flux_form.addRow("绘图模式", self.flux_mode_combo)

        self.flux_num_spin = QSpinBox()
        self.flux_num_spin.setRange(1, 4)
        self.flux_num_spin.setValue(1)
        flux_form.addRow("绘图数量", self.flux_num_spin)

        self.flux_size_combo = QComboBox()
        self.flux_size_combo.addItem("1MP(默认)", "1MP")
        self.flux_size_combo.addItem("2MP", "2MP")
        self.flux_size_combo.addItem("4MP", "4MP")
        flux_form.addRow("分辨率", self.flux_size_combo)

        self.flux_params_group.setLayout(flux_form)
        right.addWidget(self.flux_params_group)

        # FLUX 参考图（最多3张）
        self.flux_ref_group = QGroupBox("参考图(可选，最多3张)")
        ref_layout = QVBoxLayout()
        self.ref_path_edits: List[QLineEdit] = []
        self.ref_info_labels: List[QLabel] = []
        self.ref_remove_btns: List[QPushButton] = []

        for i in range(3):
            row = QHBoxLayout()
            edit = QLineEdit()
            edit.setPlaceholderText("未选择")
            info = QLabel("")
            info.setMinimumWidth(220)
            btn_remove = QPushButton("移除")
            btn_remove.clicked.connect(lambda _=False, idx=i: self._remove_reference_image(idx))
            row.addWidget(edit, 3)
            row.addWidget(info, 2)
            row.addWidget(btn_remove)
            ref_layout.addLayout(row)
            self.ref_path_edits.append(edit)
            self.ref_info_labels.append(info)
            self.ref_remove_btns.append(btn_remove)

        ref_btn_row = QHBoxLayout()
        self.ref_add_btn = QPushButton("添加参考图")
        self.ref_add_btn.clicked.connect(self._add_reference_images)
        self.ref_clear_btn = QPushButton("清空参考图")
        self.ref_clear_btn.clicked.connect(self._clear_reference_images)
        ref_btn_row.addWidget(self.ref_add_btn)
        ref_btn_row.addWidget(self.ref_clear_btn)
        ref_btn_row.addStretch(1)
        ref_layout.addLayout(ref_btn_row)
        self.flux_ref_group.setLayout(ref_layout)
        right.addWidget(self.flux_ref_group)

        # FLUX 保存路径（Midjourney 三步模式下隐藏）
        self.path_row_widget = QWidget()
        path_row = QHBoxLayout(self.path_row_widget)
        path_row.setContentsMargins(0, 0, 0, 0)
        self.path_edit = QLineEdit()
        self.path_btn = QPushButton("选择保存路径")
        self.path_btn.clicked.connect(self._choose_path)
        path_row.addWidget(self.path_edit)
        path_row.addWidget(self.path_btn)
        right.addWidget(self.path_row_widget)

        action_row = QHBoxLayout()
        self.generate_btn = QPushButton("生成背景")
        self.generate_btn.clicked.connect(self._generate_bg)
        self.force_stop_btn = QPushButton("强制停止")
        self.force_stop_btn.clicked.connect(self._force_stop_task)
        self.mark_btn = QPushButton("标记完成")
        self.mark_btn.clicked.connect(self.mark_generated)
        self.reset_btn = QPushButton("重置待生成")
        self.reset_btn.clicked.connect(self.reset_status)
        action_row.addWidget(self.generate_btn)
        action_row.addWidget(self.force_stop_btn)
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

        self.model_combo.currentIndexChanged.connect(self._toggle_mj_group)
        self._toggle_mj_group()
        self._on_flux_model_changed()

    def _force_stop_task(self):
        if self._runner.force_stop(stopped_text="状态：已强制停止"):
            return
        QMessageBox.information(self, "提示", "当前没有正在执行的任务。")

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
        self.mj_prompt_edit.setPlainText(prompt_text)
        self.path_edit.setText(self._resource_path(item.file_path or f"resources/images/{item.bg_id}.png").as_posix())
        self.file_label.setText(f"文件：{item.file_path or '待生成'}")
        self._load_mj_state(item)
        self._load_flux_state(item)
        self.progress_label.setText("状态：就绪")

    def _clear_detail(self):
        self.current_item = None
        self.bg_id_label.setText("-")
        self.status_label.setText("-")
        self.time_label.setText("-")
        self.prompt_edit.clear()
        self.mj_prompt_edit.clear()
        self.path_edit.clear()
        self.file_label.setText("文件：")
        self.progress_label.setText("状态：等待选择")

        # Midjourney 三步区块清理
        self.mj_no_edit.clear()
        self.mj_grid_path_edit.clear()
        self.mj_sep_taskid_edit.clear()
        self.mj_sep_path_edit.clear()
        self.mj_up_taskid_edit.clear()
        self.mj_final_path_edit.clear()
        self.mj_task_label.setText("任务：-")

        self.flux_model_combo.setCurrentIndex(0)
        self.flux_mode_combo.setCurrentIndex(0)
        self.flux_num_spin.setValue(1)
        if hasattr(self, "flux_size_combo"):
            self.flux_size_combo.setCurrentIndex(0)
        for i in range(3):
            if i < len(getattr(self, "ref_path_edits", [])):
                self.ref_path_edits[i].clear()
                self.ref_info_labels[i].setText("")

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
        text = self._default_prompt(self.current_item)
        if self.model_combo.currentData() == "midjourney":
            self.mj_prompt_edit.setPlainText(text)
        else:
            self.prompt_edit.setPlainText(text)

    def _mj_choose_final_path(self):
        default_dir = self._project_root() / "resources" / "images"
        default_dir.mkdir(parents=True, exist_ok=True)
        base = (self.current_item.bg_id if self.current_item else "bg")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存背景图",
            str(default_dir / f"{base}.png"),
            "PNG 图片 (*.png)",
        )
        if file_path:
            self.mj_final_path_edit.setText(file_path)
            self.path_edit.setText(file_path)

    def _choose_path(self):
        default_dir = self._project_root() / "resources" / "images"
        default_dir.mkdir(parents=True, exist_ok=True)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存背景图",
            str(default_dir / f"{(self.current_item.bg_id if self.current_item else 'bg')}.png"),
            "PNG 图片 (*.png)",
        )
        if file_path:
            self.path_edit.setText(file_path)

    def _mj_choose_path(self, target_edit: QLineEdit, suffix: str = "_grid.png"):
        default_dir = self._project_root() / "resources" / "mj" / "backgrounds"
        default_dir.mkdir(parents=True, exist_ok=True)
        base = (self.current_item.bg_id if self.current_item else "bg")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存Midjourney中间结果",
            str(default_dir / f"{base}{suffix}"),
            "PNG 图片 (*.png)",
        )
        if file_path:
            target_edit.setText(file_path)

    def _toggle_mj_group(self):
        is_mj = (self.model_combo.currentData() == "midjourney")
        self.mj_group.setVisible(bool(is_mj))
        if hasattr(self, "prompt_group"):
            self.prompt_group.setVisible(not bool(is_mj))
        if hasattr(self, "flux_params_group"):
            self.flux_params_group.setVisible(not bool(is_mj))
        if hasattr(self, "flux_ref_group"):
            self.flux_ref_group.setVisible(not bool(is_mj))
        if hasattr(self, "path_row_widget"):
            self.path_row_widget.setVisible(not bool(is_mj))
        if hasattr(self, "generate_btn"):
            self.generate_btn.setVisible(not bool(is_mj))

    def _on_flux_model_changed(self):
        model = self.flux_model_combo.currentData() or "flux-kontext"
        need_mode = (model == "flux-kontext")
        self.flux_mode_combo.setEnabled(bool(need_mode))
        if not need_mode:
            idx = self.flux_mode_combo.findData("pro")
            if idx >= 0:
                self.flux_mode_combo.setCurrentIndex(idx)

    def _add_reference_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择参考图(最多3张)",
            str(self._project_root()),
            "图片 (*.png *.jpg *.jpeg *.webp)",
        )
        if not paths:
            return
        for p in paths:
            placed = False
            for i, edit in enumerate(self.ref_path_edits):
                if not edit.text().strip():
                    edit.setText(p)
                    self._update_reference_info(i)
                    placed = True
                    break
            if not placed:
                break
        self._save_flux_state_only()

    def _remove_reference_image(self, idx: int):
        if 0 <= idx < len(self.ref_path_edits):
            self.ref_path_edits[idx].clear()
            self.ref_info_labels[idx].setText("")
            self._save_flux_state_only()

    def _clear_reference_images(self):
        for i in range(len(self.ref_path_edits)):
            self.ref_path_edits[i].clear()
            self.ref_info_labels[i].setText("")
        self._save_flux_state_only()

    def _update_reference_info(self, idx: int):
        try:
            p = Path(self.ref_path_edits[idx].text().strip())
            if not p.exists():
                self.ref_info_labels[idx].setText("路径不存在")
                return
            size = p.stat().st_size
            wh = get_image_size(p)
            if wh:
                w, h = wh
                self.ref_info_labels[idx].setText(f"{p.suffix.lower()} {w}x{h} {size//1024}KB")
            else:
                self.ref_info_labels[idx].setText(f"{p.suffix.lower()} {size//1024}KB")
        except Exception:
            self.ref_info_labels[idx].setText("解析失败")

    def _load_flux_state(self, item: BackgroundPendingItem):
        state = item.flux_state or {}
        model = state.get("model")
        if model:
            idx = self.flux_model_combo.findData(model)
            if idx >= 0:
                self.flux_model_combo.setCurrentIndex(idx)
        mode = state.get("mode") or (state.get("params") or {}).get("mode")
        if mode:
            idx = self.flux_mode_combo.findData(mode)
            if idx >= 0:
                self.flux_mode_combo.setCurrentIndex(idx)
        num = state.get("num") or (state.get("params") or {}).get("num")
        if num:
            try:
                self.flux_num_spin.setValue(int(num))
            except Exception:
                pass

        size = state.get("size") or (state.get("params") or {}).get("size")
        if size and hasattr(self, "flux_size_combo"):
            idx = self.flux_size_combo.findData(str(size).strip().upper())
            if idx >= 0:
                self.flux_size_combo.setCurrentIndex(idx)
        images = state.get("images") if isinstance(state.get("images"), list) else []
        for i in range(3):
            if i < len(images) and isinstance(images[i], dict):
                self.ref_path_edits[i].setText(str(images[i].get("path") or ""))
                self._update_reference_info(i)
            else:
                self.ref_path_edits[i].clear()
                self.ref_info_labels[i].setText("")
        self._on_flux_model_changed()

    def _save_flux_state_only(self):
        if not self.current_item:
            return
        self._save_flux_state()
        self._persist_pending_lists()

    def _save_flux_state(self):
        if not self.current_item:
            return
        images: List[dict] = []
        for edit in self.ref_path_edits:
            p = edit.text().strip()
            if not p:
                continue
            meta = {"path": p}
            try:
                pp = Path(p)
                if pp.exists():
                    meta["size"] = int(pp.stat().st_size)
                    wh = get_image_size(pp)
                    if wh:
                        meta["w"], meta["h"] = int(wh[0]), int(wh[1])
                    meta["type"] = {
                        ".png": "image/png",
                        ".jpg": "image/jpg",
                        ".jpeg": "image/jpeg",
                        ".webp": "image/webp",
                    }.get(pp.suffix.lower())
            except Exception:
                pass
            images.append(meta)

        self.current_item.flux_state = {
            "model": self.flux_model_combo.currentData() or "flux-kontext",
            "params": {
                "mode": self.flux_mode_combo.currentData() or "pro",
                "num": int(self.flux_num_spin.value()),
                "aspect": self.aspect_combo.currentText(),
                "size": (self.flux_size_combo.currentData() or "1MP") if hasattr(self, "flux_size_combo") else "1MP",
            },
            "images": images,
        }

    def _mj_parse_no_keywords(self, text: str) -> List[str]:
        raw = (text or "").strip()
        if not raw:
            return []
        tokens = []
        for part in raw.replace("，", ",").replace("\n", ",").replace(";", ",").split(","):
            t = part.strip()
            if not t:
                continue
            t = t.replace(" ", "")
            if t:
                tokens.append(t)
        seen = set()
        out = []
        for t in tokens:
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out

    def _mj_get_client(self):
        if not self._ensure_agent():
            return None
        client = self.bg_agent.api_manager.get_midjourney_client()
        if not client:
            QMessageBox.warning(self, "提示", "Midjourney 客户端不可用，请检查 config/ai_config.yaml")
        return client

    def _load_mj_state(self, item: BackgroundPendingItem):
        state = item.mj_state or {}
        imagine = state.get("imagine") or {}
        separate = state.get("separate") or {}
        upscale = state.get("upscale") or {}

        model = imagine.get("model") or (imagine.get("params") or {}).get("model")
        idx = self.mj_model_combo.findData(model)
        if idx >= 0:
            self.mj_model_combo.setCurrentIndex(idx)

        params = imagine.get("params") if isinstance(imagine.get("params"), dict) else {}
        stylize = imagine.get("stylize", params.get("stylize", 100))
        quality = imagine.get("quality", params.get("quality", 1))
        no_list = imagine.get("no")
        if not isinstance(no_list, list):
            no_list = params.get("no") if isinstance(params.get("no"), list) else []

        try:
            self.mj_stylize_spin.setValue(int(stylize))
        except Exception:
            self.mj_stylize_spin.setValue(100)
        q_idx = self.mj_quality_combo.findData(quality)
        if q_idx >= 0:
            self.mj_quality_combo.setCurrentIndex(q_idx)
        self.mj_no_edit.setText(", ".join([str(x) for x in (no_list or [])]))

        self.mj_grid_path_edit.setText(str(imagine.get("save_path") or ""))

        # Step2: separate
        self.mj_sep_taskid_edit.setText(str(separate.get("input_id") or imagine.get("task_id") or ""))

        idx = separate.get("index")
        combo_idx = self.mj_index_combo.findData(idx)
        self.mj_index_combo.setCurrentIndex(combo_idx if combo_idx >= 0 else 0)
        self.mj_sep_path_edit.setText(str(separate.get("save_path") or ""))

        # Step3: upscale
        self.mj_up_taskid_edit.setText(str(upscale.get("input_id") or separate.get("task_id") or ""))
        up_type = upscale.get("type")
        up_idx = self.mj_up_type_combo.findData(up_type)
        if up_idx >= 0:
            self.mj_up_type_combo.setCurrentIndex(up_idx)
        self.mj_final_path_edit.setText(str(upscale.get("save_path") or ""))
        if upscale.get("save_path"):
            self.path_edit.setText(str(upscale.get("save_path")))

        parts = []
        if imagine.get("task_id"):
            parts.append(f"imagine={imagine.get('task_id')}")
        if separate.get("task_id"):
            parts.append(f"separate={separate.get('task_id')}")
        if upscale.get("task_id"):
            parts.append(f"upscale={upscale.get('task_id')}")
        if parts:
            self.mj_task_label.setText("任务：" + " | ".join(parts))
        else:
            self.mj_task_label.setText("任务：-")

    def _save_mj_state(self):
        if not self.current_item:
            return
        state = dict(self.current_item.mj_state or {})
        imagine = dict(state.get("imagine") or {})
        separate = dict(state.get("separate") or {})
        upscale = dict(state.get("upscale") or {})

        imagine_model = self.mj_model_combo.currentData() or "mj-v61"
        imagine["model"] = imagine_model
        imagine["aspect"] = self.aspect_combo.currentText()
        imagine["stylize"] = int(self.mj_stylize_spin.value())
        imagine["quality"] = self.mj_quality_combo.currentData()
        imagine["no"] = self._mj_parse_no_keywords(self.mj_no_edit.text())
        imagine["save_path"] = self.mj_grid_path_edit.text().strip() or ""

        separate["input_id"] = self.mj_sep_taskid_edit.text().strip() or ""
        separate["index"] = int(self.mj_index_combo.currentData() or 1)
        separate["save_path"] = self.mj_sep_path_edit.text().strip() or ""

        upscale["input_id"] = self.mj_up_taskid_edit.text().strip() or ""
        upscale["type"] = self.mj_up_type_combo.currentData() or "subtle"
        upscale_save_path = (self.mj_final_path_edit.text().strip() or self.path_edit.text().strip() or "")
        upscale["save_path"] = upscale_save_path
        if upscale_save_path:
            self.mj_final_path_edit.setText(upscale_save_path)
            self.path_edit.setText(upscale_save_path)

        state["imagine"] = imagine
        state["separate"] = separate
        state["upscale"] = upscale
        self.current_item.mj_state = state

    def _mj_save_state_only(self):
        if not self.current_item:
            return
        try:
            self._save_mj_state()
            self._persist_pending_lists()
            self.progress_label.setText("状态：MJ参数已保存")
        except Exception as exc:
            QMessageBox.warning(self, "提示", f"保存MJ参数失败: {exc}")

    def _mj_imagine(self):
        if self._is_busy or not self._ensure_project() or not self.current_item:
            return
        client = self._mj_get_client()
        if not client:
            return

        prompt = self.mj_prompt_edit.toPlainText().strip() or self._default_prompt(self.current_item)
        self._save_mj_state()

        state = self.current_item.mj_state
        imagine = state.get("imagine") or {}
        params: dict = {
            "aspect": imagine.get("aspect") or self.aspect_combo.currentText(),
            "stylize": imagine.get("stylize", int(self.mj_stylize_spin.value())),
            "quality": imagine.get("quality", self.mj_quality_combo.currentData()),
        }
        no_list = imagine.get("no") or []
        if isinstance(no_list, list) and no_list:
            params["no"] = no_list
        model = imagine.get("model") or (self.mj_model_combo.currentData() or None)
        save_path = imagine.get("save_path") or ""
        if not save_path:
            default_dir = self._project_root() / "resources" / "mj" / "backgrounds"
            default_dir.mkdir(parents=True, exist_ok=True)
            save_path = str(default_dir / f"{self.current_item.bg_id}_grid.png")
            self.mj_grid_path_edit.setText(save_path)
            imagine["save_path"] = save_path

        self._is_busy = True
        for b in (self.mj_imagine_btn, self.mj_separate_btn, self.mj_upscale_btn, self.generate_btn):
            b.setEnabled(False)

        def _do_work():
            task = client.imagine(prompt=prompt, params=params, images=None, model=model)
            task_id = task.get("id")
            result = client.wait_for_completion(task_id)
            url = result.get("image_url")
            if not url:
                raise RuntimeError("任务完成但未返回 image_url")
            ok = client.download_image(url, save_path)
            if not ok:
                raise RuntimeError("四宫格下载失败")
            return {"task_id": task_id, "image_url": url, "save_path": save_path}

        def _on_success(payload):
            state = self.current_item.mj_state
            imagine = dict(state.get("imagine") or {})
            imagine["task_id"] = payload.get("task_id")
            imagine["image_url"] = payload.get("image_url")
            imagine["save_path"] = payload.get("save_path")
            imagine["prompt"] = prompt
            state["imagine"] = imagine
            self.current_item.mj_state = state
            self.current_item.prompt = prompt
            self.current_item.model = "midjourney"

            rels = self._normalize_paths([payload.get("save_path") or ""])
            if rels and rels[0]:
                imagine["file_path"] = rels[0]
                state["imagine"] = imagine
                self.current_item.mj_state = state

            self._persist_pending_lists()
            self._load_mj_state(self.current_item)
            self.progress_label.setText("状态：四宫格已生成")

            if payload.get("task_id"):
                self.mj_sep_taskid_edit.setText(str(payload.get("task_id")))

        def _on_finally():
            self._is_busy = False
            for b in (self.mj_imagine_btn, self.mj_separate_btn, self.mj_upscale_btn, self.generate_btn):
                b.setEnabled(True)

        self._runner.run(
            label=self.progress_label,
            base_text="状态：MJ imagine中...",
            fn=_do_work,
            on_success=_on_success,
            on_finally=_on_finally,
        )

    def _mj_separate(self):
        if self._is_busy or not self._ensure_project() or not self.current_item:
            return
        client = self._mj_get_client()
        if not client:
            return

        try:
            self._save_mj_state()
        except Exception as exc:
            QMessageBox.warning(self, "提示", f"参数错误: {exc}")
            return

        state = self.current_item.mj_state
        base_task_id = (self.mj_sep_taskid_edit.text().strip() or (state.get("imagine") or {}).get("task_id"))
        if not base_task_id:
            QMessageBox.warning(self, "提示", "请先填写拆分任务ID（或先完成 1) Imagine）")
            return

        separate = state.get("separate") or {}
        index = int(self.mj_index_combo.currentData() or 1)
        save_path = separate.get("save_path") or ""
        if not save_path:
            default_dir = self._project_root() / "resources" / "mj" / "backgrounds"
            default_dir.mkdir(parents=True, exist_ok=True)
            save_path = str(default_dir / f"{self.current_item.bg_id}_U{index}.png")
            self.mj_sep_path_edit.setText(save_path)
            separate["save_path"] = save_path

        self._is_busy = True
        for b in (self.mj_imagine_btn, self.mj_separate_btn, self.mj_upscale_btn, self.generate_btn):
            b.setEnabled(False)

        def _do_work():
            task = client.separate(task_id=base_task_id, index=index)
            sep_task_id = task.get("id")
            result = client.wait_for_completion(sep_task_id)
            url = result.get("image_url")
            if not url:
                raise RuntimeError("拆分完成但未返回 image_url")
            ok = client.download_image(url, save_path)
            if not ok:
                raise RuntimeError("拆分图下载失败")
            return {"task_id": sep_task_id, "image_url": url, "index": index, "save_path": save_path}

        def _on_success(payload):
            state = self.current_item.mj_state
            separate = dict(state.get("separate") or {})
            separate["task_id"] = payload.get("task_id")
            separate["image_url"] = payload.get("image_url")
            separate["index"] = payload.get("index")
            separate["save_path"] = payload.get("save_path")

            rels = self._normalize_paths([payload.get("save_path") or ""])
            if rels and rels[0]:
                separate["file_path"] = rels[0]

            state["separate"] = separate
            self.current_item.mj_state = state
            self._persist_pending_lists()
            self._load_mj_state(self.current_item)
            self.progress_label.setText("状态：拆分图已生成")

            if payload.get("task_id"):
                self.mj_up_taskid_edit.setText(str(payload.get("task_id")))

        def _on_finally():
            self._is_busy = False
            for b in (self.mj_imagine_btn, self.mj_separate_btn, self.mj_upscale_btn, self.generate_btn):
                b.setEnabled(True)

        self._runner.run(
            label=self.progress_label,
            base_text="状态：MJ separate中...",
            fn=_do_work,
            on_success=_on_success,
            on_finally=_on_finally,
        )

    def _mj_upscale(self):
        if self._is_busy or not self._ensure_project() or not self.current_item:
            return
        client = self._mj_get_client()
        if not client:
            return

        final_path = self.mj_final_path_edit.text().strip()
        if not final_path:
            self._mj_choose_final_path()
            final_path = self.mj_final_path_edit.text().strip()
        if not final_path:
            QMessageBox.warning(self, "提示", "请先选择最终保存路径")
            return

        self._save_mj_state()

        state = self.current_item.mj_state
        upscale_state = dict(state.get("upscale") or {})
        separate_task_id = (self.mj_up_taskid_edit.text().strip() or upscale_state.get("input_id") or (state.get("separate") or {}).get("task_id"))
        if not separate_task_id:
            QMessageBox.warning(self, "提示", "请先填写高清任务ID（来自 2) Separate 返回的任务ID）")
            return
        upscale_type = (self.mj_up_type_combo.currentData() or "subtle")

        self._is_busy = True
        for b in (self.mj_imagine_btn, self.mj_separate_btn, self.mj_upscale_btn, self.generate_btn):
            b.setEnabled(False)

        def _do_work():
            task = client.upscale(task_id=separate_task_id, upscale_type=upscale_type)
            up_task_id = task.get("id")
            result = client.wait_for_completion(up_task_id)
            url = result.get("image_url")
            if not url:
                raise RuntimeError("upscale完成但未返回 image_url")
            ok = client.download_image(url, final_path)
            if not ok:
                raise RuntimeError("最终图下载失败")
            return {"task_id": up_task_id, "image_url": url, "type": upscale_type, "save_path": final_path}

        def _on_success(payload):
            state = self.current_item.mj_state
            upscale_state = dict(state.get("upscale") or {})
            upscale_state["task_id"] = payload.get("task_id")
            upscale_state["image_url"] = payload.get("image_url")
            upscale_state["type"] = payload.get("type")
            upscale_state["save_path"] = payload.get("save_path")
            state["upscale"] = upscale_state
            self.current_item.mj_state = state

            outputs = self._normalize_paths([payload.get("save_path") or ""])
            if outputs and outputs[0]:
                self.current_item.file_path = outputs[0]
            self.current_item.prompt = self.prompt_edit.toPlainText().strip() or self._default_prompt(self.current_item)
            self.current_item.model = "midjourney"
            self.current_item.status = "generated"
            self.file_label.setText("文件：" + (self.current_item.file_path or ""))
            self.status_label.setText(self.current_item.status)
            self._persist_pending_lists()
            self._refresh_list_texts()
            self._load_mj_state(self.current_item)
            self.progress_label.setText("状态：upscale完成")

        def _on_error(msg: str):
            QMessageBox.warning(
                self,
                "提示",
                f"upscale失败: {msg}\n\n可选替代：使用 2) Separate 的拆分图作为最终图。",
            )

        def _on_finally():
            self._is_busy = False
            for b in (self.mj_imagine_btn, self.mj_separate_btn, self.mj_upscale_btn, self.generate_btn):
                b.setEnabled(True)

        self._runner.run(
            label=self.progress_label,
            base_text="状态：MJ upscale中...",
            fn=_do_work,
            on_success=_on_success,
            on_error=_on_error,
            on_finally=_on_finally,
        )

    def _save_prompt_only(self):
        if not self.current_item:
            return
        if self.model_combo.currentData() == "midjourney":
            text = self.mj_prompt_edit.toPlainText().strip()
        else:
            text = self.prompt_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "提示词为空，无法保存。")
            return
        self.current_item.prompt = text
        if self.model_combo.currentData() != "midjourney":
            self._save_flux_state()
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

        # 先保存 FLUX 参数/参考图配置，确保可持久化
        if self.model_combo.currentData() != "midjourney":
            self._save_flux_state_only()

        ref_paths = [e.text().strip() for e in getattr(self, "ref_path_edits", []) if e.text().strip()]
        flux_model = self.flux_model_combo.currentData() or "flux-kontext"
        flux_mode = self.flux_mode_combo.currentData() or "pro"
        flux_num = int(self.flux_num_spin.value())
        flux_size = (self.flux_size_combo.currentData() or "1MP") if hasattr(self, "flux_size_combo") else "1MP"

        params = {
            "bg_id": self.current_item.bg_id,
            "description": self.current_item.description,
            "atmosphere": self.current_item.atmosphere,
            "time_weather": self.current_item.time_weather,
            "prompt": prompt,
            "output_path": save_path,
            "aspect": self.aspect_combo.currentText(),
            "model": self.model_combo.currentData(),
            "flux_model": flux_model,
            "flux_mode": flux_mode,
            "flux_num": flux_num,
            "flux_size": flux_size,
            "reference_images": ref_paths,
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
        self.generate_btn.setEnabled(False)

        def _do_work():
            return self.bg_agent.execute(task)

        def _on_success(resp):
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
