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
    QSpinBox,
    QFormLayout,
    QFileDialog,
    QScrollArea,
    QSplitter,
)
from PyQt6.QtCore import Qt, pyqtSignal

from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.config_manager import ConfigManager
from src.ai.core.models import PendingLists, PortraitPendingItem, TaskAssignment
from src.ai.agents.portrait_agent import PortraitAgent
from src.designer.async_elapsed_runner import AsyncElapsedRunner
from src.ai.utils.image_utils import get_image_size


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
        self._runner = AsyncElapsedRunner(self)
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

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self.list_widget = QListWidget()
        self.list_widget.itemSelectionChanged.connect(self.on_item_selected)
        splitter.addWidget(self.list_widget)

        right_container = QWidget()
        right = QVBoxLayout(right_container)

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
        for ratio in ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "9:21", "21:9"]:
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
        self.design_model_combo.currentIndexChanged.connect(self._toggle_design_mj_group)
        design_row = QHBoxLayout()
        design_row.addWidget(QLabel("模型"))
        design_row.addWidget(self.design_model_combo)
        design_row.addStretch(1)
        design_layout.addLayout(design_row)

        # FLUX 设定图提示词/保存路径（Midjourney 三步模式下隐藏）
        self.design_prompt = QTextEdit()
        self.design_prompt.setPlaceholderText("自动生成的设定图提示词，发送前可修改")
        self.design_prompt.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        design_layout.addWidget(self.design_prompt)

        self.design_path_row_widget = QWidget()
        path_row = QHBoxLayout(self.design_path_row_widget)
        path_row.setContentsMargins(0, 0, 0, 0)
        self.design_path_edit = QLineEdit()
        self.design_path_btn = QPushButton("选择保存路径")
        self.design_path_btn.clicked.connect(self._choose_design_path)
        path_row.addWidget(self.design_path_edit)
        path_row.addWidget(self.design_path_btn)
        design_layout.addWidget(self.design_path_row_widget)

        # 设定图 - FLUX 参数（Midjourney 三步模式下隐藏）
        self.design_flux_params_group = QGroupBox("FLUX 参数")
        d_flux_form = QFormLayout()
        self.design_flux_model_combo = QComboBox()
        self.design_flux_model_combo.addItem("FLUX.1 Kontext", "flux-kontext")
        self.design_flux_model_combo.addItem("FLUX.2 Pro", "flux-2-pro")
        self.design_flux_model_combo.addItem("FLUX.2 Max", "flux-2-max")
        self.design_flux_model_combo.currentIndexChanged.connect(self._on_design_flux_model_changed)
        d_flux_form.addRow("模型版本", self.design_flux_model_combo)

        self.design_flux_mode_combo = QComboBox()
        self.design_flux_mode_combo.addItem("pro", "pro")
        self.design_flux_mode_combo.addItem("max", "max")
        d_flux_form.addRow("绘图模式", self.design_flux_mode_combo)

        self.design_flux_num_spin = QSpinBox()
        self.design_flux_num_spin.setRange(1, 4)
        self.design_flux_num_spin.setValue(1)
        d_flux_form.addRow("绘图数量", self.design_flux_num_spin)

        self.design_flux_size_combo = QComboBox()
        self.design_flux_size_combo.addItem("1MP(默认)", "1MP")
        self.design_flux_size_combo.addItem("2MP", "2MP")
        self.design_flux_size_combo.addItem("4MP", "4MP")
        d_flux_form.addRow("分辨率", self.design_flux_size_combo)

        self.design_flux_params_group.setLayout(d_flux_form)
        design_layout.addWidget(self.design_flux_params_group)

        # 设定图 - 参考图（最多3张，可选；Midjourney 三步模式下隐藏）
        self.design_flux_ref_group = QGroupBox("参考图(可选，最多3张)")
        d_ref_layout = QVBoxLayout()
        self.design_ref_path_edits: List[QLineEdit] = []
        self.design_ref_info_labels: List[QLabel] = []
        for i in range(3):
            row = QHBoxLayout()
            edit = QLineEdit()
            edit.setPlaceholderText("未选择")
            info = QLabel("")
            info.setMinimumWidth(220)
            btn_remove = QPushButton("移除")
            btn_remove.clicked.connect(lambda _=False, idx=i: self._remove_design_reference_image(idx))
            row.addWidget(edit, 3)
            row.addWidget(info, 2)
            row.addWidget(btn_remove)
            d_ref_layout.addLayout(row)
            self.design_ref_path_edits.append(edit)
            self.design_ref_info_labels.append(info)

        d_ref_btn_row = QHBoxLayout()
        self.design_ref_add_btn = QPushButton("添加参考图")
        self.design_ref_add_btn.clicked.connect(self._add_design_reference_images)
        self.design_ref_clear_btn = QPushButton("清空参考图")
        self.design_ref_clear_btn.clicked.connect(self._clear_design_reference_images)
        d_ref_btn_row.addWidget(self.design_ref_add_btn)
        d_ref_btn_row.addWidget(self.design_ref_clear_btn)
        d_ref_btn_row.addStretch(1)
        d_ref_layout.addLayout(d_ref_btn_row)
        self.design_flux_ref_group.setLayout(d_ref_layout)
        design_layout.addWidget(self.design_flux_ref_group)

        # Midjourney 三步工作流（仅设定图）
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
        self.mj_prompt_edit.setPlaceholderText("自动生成的设定图提示词，可修改后发送")
        self.mj_prompt_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        mj_prompt_layout.addWidget(self.mj_prompt_edit)
        mj_btn_row = QHBoxLayout()
        self.mj_fill_prompt_btn = QPushButton("填充默认提示词")
        self.mj_fill_prompt_btn.clicked.connect(self._fill_design_prompt)
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
        self.mj_final_path_btn.clicked.connect(self._mj_choose_design_final_path)
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
        design_layout.addWidget(self.mj_group)

        # FLUX 设定图行动按钮（Midjourney 三步模式下隐藏：不需要单独“生成设定图/保存路径”）
        self.design_action_row_widget = QWidget()
        action_row_d = QHBoxLayout(self.design_action_row_widget)
        action_row_d.setContentsMargins(0, 0, 0, 0)
        self.design_fill_btn = QPushButton("填充默认提示词")
        self.design_fill_btn.clicked.connect(self._fill_design_prompt)
        self.design_save_prompt_btn = QPushButton("保存指令")
        self.design_save_prompt_btn.clicked.connect(self._save_prompt_only)
        self.design_generate_btn = QPushButton("生成设定图")
        self.design_generate_btn.clicked.connect(self._generate_design_sheet)
        action_row_d.addWidget(self.design_fill_btn)
        action_row_d.addWidget(self.design_save_prompt_btn)
        action_row_d.addWidget(self.design_generate_btn)
        design_layout.addWidget(self.design_action_row_widget)

        self.design_group.setLayout(design_layout)
        right.addWidget(self.design_group)

        # 全量生成模式
        self.full_group = QGroupBox("生成所有立绘 (基准+表情差分，仅Flux)")
        full_layout = QVBoxLayout()
        self.full_prompt = QTextEdit()
        self.full_prompt.setPlaceholderText("基准立绘提示词（可编辑）")
        self.full_prompt.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        full_layout.addWidget(self.full_prompt)

        self.diff_prompt = QTextEdit()
        self.diff_prompt.setPlaceholderText("差分提示词模板（可编辑，支持 {expression} 占位符）")
        self.diff_prompt.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        full_layout.addWidget(self.diff_prompt)

        full_btn_row0 = QHBoxLayout()
        self.base_prompt_btn = QPushButton("生成基准图提示词")
        self.base_prompt_btn.clicked.connect(self._fill_full_base_prompt)
        self.diff_prompt_btn = QPushButton("生成差分提示词")
        self.diff_prompt_btn.clicked.connect(self._fill_full_diff_prompt)
        self.full_save_btn = QPushButton("保存指令/参数")
        self.full_save_btn.clicked.connect(self._save_full_flux_state_only)
        full_btn_row0.addWidget(self.base_prompt_btn)
        full_btn_row0.addWidget(self.diff_prompt_btn)
        full_btn_row0.addWidget(self.full_save_btn)
        full_btn_row0.addStretch(1)
        full_layout.addLayout(full_btn_row0)

        # 全量生成 - FLUX 参数
        self.full_flux_params_group = QGroupBox("FLUX 参数")
        f_flux_form = QFormLayout()
        self.full_flux_model_combo = QComboBox()
        self.full_flux_model_combo.addItem("FLUX.1 Kontext", "flux-kontext")
        self.full_flux_model_combo.addItem("FLUX.2 Pro", "flux-2-pro")
        self.full_flux_model_combo.addItem("FLUX.2 Max", "flux-2-max")
        self.full_flux_model_combo.currentIndexChanged.connect(self._on_full_flux_model_changed)
        f_flux_form.addRow("模型版本", self.full_flux_model_combo)

        self.full_flux_mode_combo = QComboBox()
        self.full_flux_mode_combo.addItem("pro", "pro")
        self.full_flux_mode_combo.addItem("max", "max")
        f_flux_form.addRow("绘图模式", self.full_flux_mode_combo)

        self.full_flux_num_spin = QSpinBox()
        self.full_flux_num_spin.setRange(1, 4)
        self.full_flux_num_spin.setValue(1)
        f_flux_form.addRow("绘图数量", self.full_flux_num_spin)

        self.full_flux_size_combo = QComboBox()
        self.full_flux_size_combo.addItem("1MP(默认)", "1MP")
        self.full_flux_size_combo.addItem("2MP", "2MP")
        self.full_flux_size_combo.addItem("4MP", "4MP")
        f_flux_form.addRow("分辨率", self.full_flux_size_combo)
        self.full_flux_params_group.setLayout(f_flux_form)
        full_layout.addWidget(self.full_flux_params_group)

        # 全量生成 - 参考图（最多3张，可选）
        self.full_flux_ref_group = QGroupBox("参考图(可选，最多3张)")
        f_ref_layout = QVBoxLayout()
        self.full_ref_path_edits: List[QLineEdit] = []
        self.full_ref_info_labels: List[QLabel] = []
        for i in range(3):
            row = QHBoxLayout()
            edit = QLineEdit()
            edit.setPlaceholderText("未选择")
            info = QLabel("")
            info.setMinimumWidth(220)
            btn_remove = QPushButton("移除")
            btn_remove.clicked.connect(lambda _=False, idx=i: self._remove_full_reference_image(idx))
            row.addWidget(edit, 3)
            row.addWidget(info, 2)
            row.addWidget(btn_remove)
            f_ref_layout.addLayout(row)
            self.full_ref_path_edits.append(edit)
            self.full_ref_info_labels.append(info)

        f_ref_btn_row = QHBoxLayout()
        self.full_ref_add_btn = QPushButton("添加参考图")
        self.full_ref_add_btn.clicked.connect(self._add_full_reference_images)
        self.full_ref_clear_btn = QPushButton("清空参考图")
        self.full_ref_clear_btn.clicked.connect(self._clear_full_reference_images)
        f_ref_btn_row.addWidget(self.full_ref_add_btn)
        f_ref_btn_row.addWidget(self.full_ref_clear_btn)
        f_ref_btn_row.addStretch(1)
        f_ref_layout.addLayout(f_ref_btn_row)
        self.full_flux_ref_group.setLayout(f_ref_layout)
        full_layout.addWidget(self.full_flux_ref_group)

        full_btn_row1 = QHBoxLayout()
        self.base_generate_btn = QPushButton("生成基准图")
        self.base_generate_btn.clicked.connect(self._generate_base)
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

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setWidget(right_container)
        splitter.addWidget(right_scroll)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)

        self._on_mode_changed()
        self._toggle_design_mj_group()
        self._on_design_flux_model_changed()
        self._on_full_flux_model_changed()

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
        self.mj_prompt_edit.setPlainText(prompt_text)
        self.full_prompt.setPlainText(prompt_text)
        self.diff_prompt.setPlainText("")

        if item.model in ("midjourney", "flux"):
            idx = self.design_model_combo.findData(item.model)
            if idx >= 0:
                self.design_model_combo.setCurrentIndex(idx)
        self._toggle_design_mj_group()
        self._load_mj_state(item)
        self._load_flux_state(item)
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
        self.mj_prompt_edit.clear()
        self.full_prompt.clear()
        self.diff_prompt.clear()
        self.design_path_edit.clear()
        self.mj_no_edit.clear()
        self.mj_grid_path_edit.clear()
        self.mj_sep_taskid_edit.clear()
        self.mj_sep_path_edit.clear()
        self.mj_up_taskid_edit.clear()
        self.mj_final_path_edit.clear()
        self.mj_task_label.setText("任务：-")
        # 设定图 FLUX
        if hasattr(self, "design_flux_model_combo"):
            self.design_flux_model_combo.setCurrentIndex(0)
            self.design_flux_mode_combo.setCurrentIndex(0)
            self.design_flux_num_spin.setValue(1)
            if hasattr(self, "design_flux_size_combo"):
                self.design_flux_size_combo.setCurrentIndex(0)
        if hasattr(self, "design_ref_path_edits"):
            for i in range(3):
                self.design_ref_path_edits[i].clear()
                self.design_ref_info_labels[i].setText("")
        # 全量 FLUX
        if hasattr(self, "full_flux_model_combo"):
            self.full_flux_model_combo.setCurrentIndex(0)
            self.full_flux_mode_combo.setCurrentIndex(0)
            self.full_flux_num_spin.setValue(1)
            if hasattr(self, "full_flux_size_combo"):
                self.full_flux_size_combo.setCurrentIndex(0)
        if hasattr(self, "full_ref_path_edits"):
            for i in range(3):
                self.full_ref_path_edits[i].clear()
                self.full_ref_info_labels[i].setText("")
        self.base_path_label.setText("基准图：未生成")
        self.filepaths_label.setText("")
        self.progress_label.setText("状态：等待选择")

    def _toggle_design_mj_group(self):
        is_mj = (self.design_model_combo.currentData() == "midjourney")
        is_mj_design = bool(is_mj) and self.mode == "design"
        self.mj_group.setVisible(is_mj_design)
        # Midjourney 三步模式：提示词/保存路径/单独生成按钮都归入 Step1/Step3
        self.design_prompt.setVisible(not is_mj_design)
        if hasattr(self, "design_path_row_widget"):
            self.design_path_row_widget.setVisible(not is_mj_design)
        if hasattr(self, "design_action_row_widget"):
            self.design_action_row_widget.setVisible(not is_mj_design)
        if hasattr(self, "design_flux_params_group"):
            self.design_flux_params_group.setVisible(not is_mj_design)
        if hasattr(self, "design_flux_ref_group"):
            self.design_flux_ref_group.setVisible(not is_mj_design)

    def _on_design_flux_model_changed(self):
        model = self.design_flux_model_combo.currentData() or "flux-kontext"
        need_mode = (model == "flux-kontext")
        self.design_flux_mode_combo.setEnabled(bool(need_mode))
        if not need_mode:
            idx = self.design_flux_mode_combo.findData("pro")
            if idx >= 0:
                self.design_flux_mode_combo.setCurrentIndex(idx)

    def _on_full_flux_model_changed(self):
        model = self.full_flux_model_combo.currentData() or "flux-kontext"
        need_mode = (model == "flux-kontext")
        self.full_flux_mode_combo.setEnabled(bool(need_mode))
        if not need_mode:
            idx = self.full_flux_mode_combo.findData("pro")
            if idx >= 0:
                self.full_flux_mode_combo.setCurrentIndex(idx)

    def _update_ref_info_label(self, path_text: str, label: QLabel):
        try:
            p = Path(path_text)
            if not p.exists():
                label.setText("路径不存在")
                return
            size = p.stat().st_size
            wh = get_image_size(p)
            if wh:
                label.setText(f"{p.suffix.lower()} {wh[0]}x{wh[1]} {size//1024}KB")
            else:
                label.setText(f"{p.suffix.lower()} {size//1024}KB")
        except Exception:
            label.setText("解析失败")

    def _add_design_reference_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择设定图参考图(最多3张)",
            str(self._project_root()),
            "图片 (*.png *.jpg *.jpeg *.webp)",
        )
        if not paths:
            return
        for p in paths:
            placed = False
            for i, edit in enumerate(self.design_ref_path_edits):
                if not edit.text().strip():
                    edit.setText(p)
                    self._update_ref_info_label(p, self.design_ref_info_labels[i])
                    placed = True
                    break
            if not placed:
                break
        self._save_design_flux_state_only()

    def _remove_design_reference_image(self, idx: int):
        if 0 <= idx < len(self.design_ref_path_edits):
            self.design_ref_path_edits[idx].clear()
            self.design_ref_info_labels[idx].setText("")
            self._save_design_flux_state_only()

    def _clear_design_reference_images(self):
        for i in range(len(self.design_ref_path_edits)):
            self.design_ref_path_edits[i].clear()
            self.design_ref_info_labels[i].setText("")
        self._save_design_flux_state_only()

    def _add_full_reference_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择立绘参考图(最多3张)",
            str(self._project_root()),
            "图片 (*.png *.jpg *.jpeg *.webp)",
        )
        if not paths:
            return
        for p in paths:
            placed = False
            for i, edit in enumerate(self.full_ref_path_edits):
                if not edit.text().strip():
                    edit.setText(p)
                    self._update_ref_info_label(p, self.full_ref_info_labels[i])
                    placed = True
                    break
            if not placed:
                break
        self._save_full_flux_state_only()

    def _remove_full_reference_image(self, idx: int):
        if 0 <= idx < len(self.full_ref_path_edits):
            self.full_ref_path_edits[idx].clear()
            self.full_ref_info_labels[idx].setText("")
            self._save_full_flux_state_only()

    def _clear_full_reference_images(self):
        for i in range(len(self.full_ref_path_edits)):
            self.full_ref_path_edits[i].clear()
            self.full_ref_info_labels[i].setText("")
        self._save_full_flux_state_only()

    def _save_design_flux_state_only(self):
        if not self.current_item:
            return
        self._save_design_flux_state()
        self._persist_pending_lists()

    def _save_full_flux_state_only(self):
        if not self.current_item:
            return
        self._save_full_flux_state()
        self._persist_pending_lists()

    def _save_design_flux_state(self):
        if not self.current_item:
            return
        images: List[dict] = []
        for edit in self.design_ref_path_edits:
            p = edit.text().strip()
            if p:
                images.append({"path": p})
        state = dict(self.current_item.flux_state or {})
        state["design"] = {
            "model": self.design_flux_model_combo.currentData() or "flux-kontext",
            "params": {
                "mode": self.design_flux_mode_combo.currentData() or "pro",
                "num": int(self.design_flux_num_spin.value()),
                "aspect": self.aspect_combo.currentText(),
                "size": (self.design_flux_size_combo.currentData() or "1MP") if hasattr(self, "design_flux_size_combo") else "1MP",
            },
            "images": images,
        }
        self.current_item.flux_state = state

    def _save_full_flux_state(self):
        if not self.current_item:
            return
        images: List[dict] = []
        for edit in self.full_ref_path_edits:
            p = edit.text().strip()
            if p:
                images.append({"path": p})
        # 同步用户编辑的表情列表
        self.current_item.expressions = self._parse_expressions(self.current_item.expressions or [
            "温柔微笑（嘴角轻微上扬；眼神柔和；无多余动作）",
            "傲娇撇嘴（嘴角向下撇；眉头微蹙；眼神带点小倔强）",
            "害羞脸红（脸颊淡粉红晕；眼神躲闪；嘴角抿起）",
            "惊讶瞪眼（眼睛睁大；瞳孔微缩；嘴巴小O型）",
        ])

        state = dict(self.current_item.flux_state or {})
        state["full"] = {
            "model": self.full_flux_model_combo.currentData() or "flux-kontext",
            "params": {
                "mode": self.full_flux_mode_combo.currentData() or "pro",
                "num": int(self.full_flux_num_spin.value()),
                "aspect": self.aspect_combo.currentText(),
                "size": (self.full_flux_size_combo.currentData() or "1MP") if hasattr(self, "full_flux_size_combo") else "1MP",
            },
            "images": images,
            "diff_prompt_template": self.diff_prompt.toPlainText().strip(),
        }
        self.current_item.flux_state = state

    def _load_flux_state(self, item: PortraitPendingItem):
        state = item.flux_state or {}
        d = state.get("design") if isinstance(state.get("design"), dict) else {}
        f = state.get("full") if isinstance(state.get("full"), dict) else {}

        d_model = d.get("model")
        if d_model:
            idx = self.design_flux_model_combo.findData(d_model)
            if idx >= 0:
                self.design_flux_model_combo.setCurrentIndex(idx)
        d_mode = (d.get("params") or {}).get("mode")
        if d_mode:
            idx = self.design_flux_mode_combo.findData(d_mode)
            if idx >= 0:
                self.design_flux_mode_combo.setCurrentIndex(idx)
        d_num = (d.get("params") or {}).get("num")
        if d_num:
            try:
                self.design_flux_num_spin.setValue(int(d_num))
            except Exception:
                pass
        d_size = (d.get("params") or {}).get("size")
        if d_size and hasattr(self, "design_flux_size_combo"):
            idx = self.design_flux_size_combo.findData(str(d_size).strip().upper())
            if idx >= 0:
                self.design_flux_size_combo.setCurrentIndex(idx)
        d_images = d.get("images") if isinstance(d.get("images"), list) else []
        for i in range(3):
            if i < len(d_images) and isinstance(d_images[i], dict):
                p = str(d_images[i].get("path") or "")
                self.design_ref_path_edits[i].setText(p)
                if p:
                    self._update_ref_info_label(p, self.design_ref_info_labels[i])
                else:
                    self.design_ref_info_labels[i].setText("")
            else:
                self.design_ref_path_edits[i].clear()
                self.design_ref_info_labels[i].setText("")
        self._on_design_flux_model_changed()

        f_model = f.get("model")
        if f_model:
            idx = self.full_flux_model_combo.findData(f_model)
            if idx >= 0:
                self.full_flux_model_combo.setCurrentIndex(idx)
        f_mode = (f.get("params") or {}).get("mode")
        if f_mode:
            idx = self.full_flux_mode_combo.findData(f_mode)
            if idx >= 0:
                self.full_flux_mode_combo.setCurrentIndex(idx)
        f_num = (f.get("params") or {}).get("num")
        if f_num:
            try:
                self.full_flux_num_spin.setValue(int(f_num))
            except Exception:
                pass
        f_size = (f.get("params") or {}).get("size")
        if f_size and hasattr(self, "full_flux_size_combo"):
            idx = self.full_flux_size_combo.findData(str(f_size).strip().upper())
            if idx >= 0:
                self.full_flux_size_combo.setCurrentIndex(idx)
        f_images = f.get("images") if isinstance(f.get("images"), list) else []
        for i in range(3):
            if i < len(f_images) and isinstance(f_images[i], dict):
                p = str(f_images[i].get("path") or "")
                self.full_ref_path_edits[i].setText(p)
                if p:
                    self._update_ref_info_label(p, self.full_ref_info_labels[i])
                else:
                    self.full_ref_info_labels[i].setText("")
            else:
                self.full_ref_path_edits[i].clear()
                self.full_ref_info_labels[i].setText("")
        diff_tpl = f.get("diff_prompt_template")
        if isinstance(diff_tpl, str) and diff_tpl.strip():
            self.diff_prompt.setPlainText(diff_tpl)
        self._on_full_flux_model_changed()

    def _mj_choose_design_final_path(self):
        default_dir = self._project_root() / "resources" / "portraits"
        default_dir.mkdir(parents=True, exist_ok=True)
        base = (self.current_item.char_id if self.current_item else "character")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存设定图",
            str(default_dir / f"{base}_design.png"),
            "PNG 图片 (*.png)",
        )
        if file_path:
            self.mj_final_path_edit.setText(file_path)
            # 兼容：保持与旧字段同步（虽然 Midjourney 模式下隐藏）
            self.design_path_edit.setText(file_path)

    def _mj_choose_path(self, target_edit: QLineEdit, suffix: str = "_grid.png"):
        default_dir = self._project_root() / "resources" / "mj" / "portraits" / (self.current_item.char_id if self.current_item else "character")
        default_dir.mkdir(parents=True, exist_ok=True)
        base = (self.current_item.char_id if self.current_item else "character")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存Midjourney中间结果",
            str(default_dir / f"{base}{suffix}"),
            "PNG 图片 (*.png)",
        )
        if file_path:
            target_edit.setText(file_path)

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
        client = self.portrait_agent.api_manager.get_midjourney_client()
        if not client:
            QMessageBox.warning(self, "提示", "Midjourney 客户端不可用，请检查 config/ai_config.yaml")
        return client

    def _load_mj_state(self, item: PortraitPendingItem):
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

        self.mj_sep_taskid_edit.setText(str(separate.get("input_id") or imagine.get("task_id") or ""))

        idx = separate.get("index")
        combo_idx = self.mj_index_combo.findData(idx)
        self.mj_index_combo.setCurrentIndex(combo_idx if combo_idx >= 0 else 0)
        self.mj_sep_path_edit.setText(str(separate.get("save_path") or ""))

        self.mj_up_taskid_edit.setText(str(upscale.get("input_id") or separate.get("task_id") or ""))
        up_type = upscale.get("type")
        up_idx = self.mj_up_type_combo.findData(up_type)
        if up_idx >= 0:
            self.mj_up_type_combo.setCurrentIndex(up_idx)

        final_path = str(upscale.get("save_path") or "")
        if final_path:
            self.mj_final_path_edit.setText(final_path)
            self.design_path_edit.setText(final_path)
        else:
            self.mj_final_path_edit.setText(self.design_path_edit.text().strip())

        parts = []
        if imagine.get("task_id"):
            parts.append(f"imagine={imagine.get('task_id')}")
        if separate.get("task_id"):
            parts.append(f"separate={separate.get('task_id')}")
        if upscale.get("task_id"):
            parts.append(f"upscale={upscale.get('task_id')}")
        self.mj_task_label.setText("任务：" + " | ".join(parts) if parts else "任务：-")

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
        upscale_save_path = (self.mj_final_path_edit.text().strip() or self.design_path_edit.text().strip() or "")
        upscale["save_path"] = upscale_save_path
        if upscale_save_path:
            self.mj_final_path_edit.setText(upscale_save_path)
            self.design_path_edit.setText(upscale_save_path)

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
            default_dir = self._project_root() / "resources" / "mj" / "portraits" / self.current_item.char_id
            default_dir.mkdir(parents=True, exist_ok=True)
            save_path = str(default_dir / f"{self.current_item.char_id}_design_grid.png")
            self.mj_grid_path_edit.setText(save_path)
            imagine["save_path"] = save_path

        self._is_busy = True
        self.design_generate_btn.setEnabled(False)
        for b in (self.mj_imagine_btn, self.mj_separate_btn, self.mj_upscale_btn):
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
            self._persist_pending_lists()
            self._load_mj_state(self.current_item)
            self.progress_label.setText("状态：四宫格已生成")

            if payload.get("task_id"):
                self.mj_sep_taskid_edit.setText(str(payload.get("task_id")))

        def _on_finally():
            self._is_busy = False
            self.design_generate_btn.setEnabled(True)
            for b in (self.mj_imagine_btn, self.mj_separate_btn, self.mj_upscale_btn):
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

        self._save_mj_state()

        state = self.current_item.mj_state
        base_task_id = (self.mj_sep_taskid_edit.text().strip() or (state.get("imagine") or {}).get("task_id"))
        if not base_task_id:
            QMessageBox.warning(self, "提示", "请先填写拆分任务ID（或先完成 1) Imagine）")
            return

        separate = state.get("separate") or {}
        index = int(self.mj_index_combo.currentData() or 1)
        save_path = separate.get("save_path") or ""
        if not save_path:
            default_dir = self._project_root() / "resources" / "mj" / "portraits" / self.current_item.char_id
            default_dir.mkdir(parents=True, exist_ok=True)
            save_path = str(default_dir / f"{self.current_item.char_id}_design_U{index}.png")
            self.mj_sep_path_edit.setText(save_path)
            separate["save_path"] = save_path

        self._is_busy = True
        self.design_generate_btn.setEnabled(False)
        for b in (self.mj_imagine_btn, self.mj_separate_btn, self.mj_upscale_btn):
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
            state["separate"] = separate
            self.current_item.mj_state = state
            self._persist_pending_lists()
            self._load_mj_state(self.current_item)
            self.progress_label.setText("状态：拆分图已生成")

            if payload.get("task_id"):
                self.mj_up_taskid_edit.setText(str(payload.get("task_id")))

        def _on_finally():
            self._is_busy = False
            self.design_generate_btn.setEnabled(True)
            for b in (self.mj_imagine_btn, self.mj_separate_btn, self.mj_upscale_btn):
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
            self._mj_choose_design_final_path()
            final_path = self.mj_final_path_edit.text().strip()
        if not final_path:
            QMessageBox.warning(self, "提示", "请先选择设定图保存路径。")
            return
        final_abs = str(self._abs_path(final_path))

        self._save_mj_state()

        state = self.current_item.mj_state
        upscale_state = dict(state.get("upscale") or {})
        separate_task_id = (self.mj_up_taskid_edit.text().strip() or upscale_state.get("input_id") or (state.get("separate") or {}).get("task_id"))
        if not separate_task_id:
            QMessageBox.warning(self, "提示", "请先填写高清任务ID（来自 2) Separate 返回的任务ID）")
            return
        upscale_type = (self.mj_up_type_combo.currentData() or "subtle")

        self._is_busy = True
        self.design_generate_btn.setEnabled(False)
        for b in (self.mj_imagine_btn, self.mj_separate_btn, self.mj_upscale_btn):
            b.setEnabled(False)

        def _do_work():
            task = client.upscale(task_id=separate_task_id, upscale_type=upscale_type)
            up_task_id = task.get("id")
            result = client.wait_for_completion(up_task_id)
            url = result.get("image_url")
            if not url:
                raise RuntimeError("upscale完成但未返回 image_url")
            ok = client.download_image(url, final_abs)
            if not ok:
                raise RuntimeError("最终图下载失败")
            return {"task_id": up_task_id, "image_url": url, "type": upscale_type, "save_path": final_abs}

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
                self.current_item.file_paths = [outputs[0]]
            self.current_item.prompt = self.mj_prompt_edit.toPlainText().strip() or self._default_prompt(self.current_item)
            self.current_item.model = "midjourney"
            self.current_item.status = "generated"
            self.filepaths_label.setText("文件：" + ", ".join(self.current_item.file_paths or []))
            self.status_value.setText(self.current_item.status)
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
            self.design_generate_btn.setEnabled(True)
            for b in (self.mj_imagine_btn, self.mj_separate_btn, self.mj_upscale_btn):
                b.setEnabled(True)

        self._runner.run(
            label=self.progress_label,
            base_text="状态：MJ upscale中...",
            fn=_do_work,
            on_success=_on_success,
            on_error=_on_error,
            on_finally=_on_finally,
        )

    # ==================== 工具方法 ====================
    def _persona_text_from_step1(self, char_id: str) -> str:
        """优先从主控 Agent Step1（角色人设）里取人物设定文本。

        兼容多种历史存储结构：
        - {"char_001": {"persona": "..."}, ...}
        - {"characters": [{"char_id": "char_001", "persona": "..."}, ...]}
        - [{"char_id": "char_001", "persona": "..."}, ...]
        """
        project = self.project_manager.current_project
        if project is None:
            return ""
        history = getattr(project, "generation_history", None)
        step1 = getattr(history, "step1_personas", None) if history is not None else None
        if not step1:
            return ""

        from src.ai.utils.persona_extract import extract_persona_map

        persona_by_id = extract_persona_map(step1)
        return (persona_by_id.get(str(char_id)) or "").strip()

    def _default_prompt(self, item: PortraitPendingItem) -> str:
        parts = [item.char_name]
        # 默认提示词里的人设描述：优先取 Step1 生成的人设，其次才用待生成项里的 description
        persona_text = self._persona_text_from_step1(item.char_id) or (item.description or "").strip()
        if persona_text:
            parts.append(persona_text)
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
        self._toggle_design_mj_group()

    # ==================== 设定图模式 ====================
    def _fill_design_prompt(self):
        if not self.current_item:
            return
        persona_text = self._persona_text_from_step1(self.current_item.char_id) or (self.current_item.description or "").strip()
        prompt = self.portrait_agent.build_design_prompt(
            self.current_item.char_name,
            persona_text,
        ) if self._ensure_agent() else self._default_prompt(self.current_item)
        if self.mode == "design" and (self.design_model_combo.currentData() == "midjourney"):
            self.mj_prompt_edit.setPlainText(prompt)
        else:
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
        if self.mode == "design":
            if self.design_model_combo.currentData() == "midjourney":
                text = self.mj_prompt_edit.toPlainText().strip()
            else:
                text = self.design_prompt.toPlainText().strip()
        else:
            text = self.full_prompt.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "提示词为空，无法保存。")
            return
        self.current_item.prompt = text
        # 同步保存 FLUX 参数/参考图/差分模板
        if self.mode == "design" and self.design_model_combo.currentData() != "midjourney":
            self._save_design_flux_state()
        if self.mode == "full":
            self._save_full_flux_state()
        self._persist_pending_lists()
        self.progress_label.setText("状态：指令已保存")

    def _generate_design_sheet(self):
        if self._is_busy or not self._ensure_project() or not self.current_item or not self._ensure_agent():
            return
        prompt = self.design_prompt.toPlainText().strip() or self._default_prompt(self.current_item)
        persona_text = self._persona_text_from_step1(self.current_item.char_id) or (self.current_item.description or "").strip()
        save_path = self.design_path_edit.text().strip()
        if not save_path:
            self._choose_design_path()
            save_path = self.design_path_edit.text().strip()
        if not save_path:
            QMessageBox.warning(self, "提示", "请先选择设定图保存路径。")
            return

        # 设定图为 FLUX 时：保存并透传参数/参考图
        if (self.design_model_combo.currentData() or "flux") != "midjourney":
            self._save_design_flux_state_only()
            ref_paths = [e.text().strip() for e in getattr(self, "design_ref_path_edits", []) if e.text().strip()]
            flux_model = self.design_flux_model_combo.currentData() or "flux-kontext"
            flux_mode = self.design_flux_mode_combo.currentData() or "pro"
            flux_num = int(self.design_flux_num_spin.value())
            flux_size = (self.design_flux_size_combo.currentData() or "1MP") if hasattr(self, "design_flux_size_combo") else "1MP"
        else:
            ref_paths = []
            flux_model = None
            flux_mode = None
            flux_num = None
            flux_size = None

        params = {
            "character_name": self.current_item.char_name,
            "description": persona_text,
            "prompt": prompt,
            "save_path": save_path,
            "aspect": self.aspect_combo.currentText(),
            "model": self.design_model_combo.currentData() or "midjourney",
            "flux_model": flux_model,
            "flux_mode": flux_mode,
            "flux_num": flux_num,
            "flux_size": flux_size,
            "reference_images": ref_paths,
        }

        task = TaskAssignment(
            task_id=f"design-{int(time.time()*1000)}",
            agent_type="portrait",
            task_type="generate_design_sheet",
            task_content=f"设定图 {self.current_item.char_name}",
            parameters=params,
        )

        self._is_busy = True
        self.design_generate_btn.setEnabled(False)

        def _do_work():
            return self.portrait_agent.execute(task)

        def _on_success(resp):
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

        def _on_finally():
            self._is_busy = False
            self.design_generate_btn.setEnabled(True)

        started = self._runner.run(
            label=self.progress_label,
            base_text="状态：生成设定图...",
            fn=_do_work,
            on_success=_on_success,
            on_finally=_on_finally,
        )
        if not started:
            self._is_busy = False
            self.design_generate_btn.setEnabled(True)
            QMessageBox.information(self, "提示", "已有任务在运行，请稍候。")

    # ==================== 全量生成模式 ====================
    def _fill_full_base_prompt(self):
        if not self.current_item:
            return
        desc = self._persona_text_from_step1(self.current_item.char_id) or (self.current_item.description or "").strip()
        char_name = self.current_item.char_name
        prompt = (
            f"日系二次元平涂风格，线条锐利，色彩干净且与设定一致，无阴影、无背景杂物。"
            f"单角色全身立绘，站姿，居中构图，纯白底色。"
            f"角色设定：{char_name}，{desc}。"
            "表情：中性自然。"
            "技术参数：分辨率2048×2560，高清细节，边缘清晰，无模糊噪点。"
        )
        self.full_prompt.setPlainText(prompt)

    def _fill_full_diff_prompt(self):
        if not self.current_item:
            return
        # 默认 4 表情指令（可在右侧“表情”输入框自行改）
        default_expr = [
            "温柔微笑（嘴角轻微上扬；眼神柔和；无多余动作）",
            "傲娇撇嘴（嘴角向下撇；眉头微蹙；眼神带点小倔强）",
            "害羞脸红（脸颊淡粉红晕；眼神躲闪；嘴角抿起）",
            "惊讶瞪眼（眼睛睁大；瞳孔微缩；嘴巴小O型）",
        ]
        self.expressions_edit.setText(", ".join(default_expr))

        tpl = (
            "严格遵循上传的二次元角色设定图，角色的脸型、发型、发色、瞳色、服饰、姿态、构图、纯白底色 **100%完全一致**，"
            "仅修改面部表情，无任何其他细节变动。\n"
            "当前表情：{expression}\n"
            "风格约束：日系二次元平涂风格，线条锐利，色彩与参考图一致，无阴影、无背景杂物。\n"
            "技术参数：分辨率2048×2560，高清细节，边缘清晰，无模糊噪点。\n"
            "negative prompt: 角色变形，比例失调，发型改动，服饰增减，发色偏差，背景杂色，阴影，模糊，噪点，重影，表情夸张变形，非纯白背景"
        )
        self.diff_prompt.setPlainText(tpl)

    def _generate_base(self):
        if self._is_busy or not self._ensure_project() or not self.current_item or not self._ensure_agent():
            return
        # 保存参数/参考图
        self._save_full_flux_state_only()

        prompt = self.full_prompt.toPlainText().strip() or self._default_prompt(self.current_item)
        persona_text = self._persona_text_from_step1(self.current_item.char_id) or (self.current_item.description or "").strip()
        rel_path = f"resources/portraits/{self.current_item.char_id}_neutral.png"
        output_path = self._resource_path(rel_path)
        ref_paths = [e.text().strip() for e in getattr(self, "full_ref_path_edits", []) if e.text().strip()]
        flux_model = self.full_flux_model_combo.currentData() or "flux-kontext"
        flux_mode = self.full_flux_mode_combo.currentData() or "pro"
        flux_num = int(self.full_flux_num_spin.value())
        flux_size = (self.full_flux_size_combo.currentData() or "1MP") if hasattr(self, "full_flux_size_combo") else "1MP"
        params = {
            "char_id": self.current_item.char_id,
            "character_name": self.current_item.char_name,
            "description": persona_text,
            "prompt": prompt,
            "output_path": str(output_path),
            "aspect": self.aspect_combo.currentText(),
            "model": "flux",
            "flux_model": flux_model,
            "flux_mode": flux_mode,
            "flux_num": flux_num,
            "flux_size": flux_size,
            "reference_images": ref_paths,
        }
        task = TaskAssignment(
            task_id=f"base-{int(time.time()*1000)}",
            agent_type="portrait",
            task_type="generate_base_portrait",
            task_content=f"基准立绘 {self.current_item.char_name}",
            parameters=params,
        )

        self._is_busy = True
        self.base_generate_btn.setEnabled(False)

        def _do_work():
            return self.portrait_agent.execute(task)

        def _on_success(resp):
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

        def _on_finally():
            self._is_busy = False
            self.base_generate_btn.setEnabled(True)

        started = self._runner.run(
            label=self.progress_label,
            base_text="状态：生成基准图...",
            fn=_do_work,
            on_success=_on_success,
            on_finally=_on_finally,
        )
        if not started:
            self._is_busy = False
            self.base_generate_btn.setEnabled(True)
            QMessageBox.information(self, "提示", "已有任务在运行，请稍候。")

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

        # 保存参数/参考图/差分模板
        self._save_full_flux_state_only()

        ref_paths = [e.text().strip() for e in getattr(self, "full_ref_path_edits", []) if e.text().strip()]
        flux_model = self.full_flux_model_combo.currentData() or "flux-kontext"
        flux_mode = self.full_flux_mode_combo.currentData() or "pro"
        flux_num = int(self.full_flux_num_spin.value())
        flux_size = (self.full_flux_size_combo.currentData() or "1MP") if hasattr(self, "full_flux_size_combo") else "1MP"
        prompt_template = self.diff_prompt.toPlainText().strip()
        persona_text = self._persona_text_from_step1(self.current_item.char_id) or (self.current_item.description or "").strip()

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

        base_image_abs = str(self._abs_path(self.base_image_path or self.current_item.base_image_path))
        output_dir = str(self._resource_path("resources/portraits"))
        tasks: List[TaskAssignment] = []
        for idx, batch in enumerate(batches):
            params = {
                "char_id": self.current_item.char_id,
                "character_name": self.current_item.char_name,
                "description": persona_text,
                "expressions": batch,
                "aspect": self.aspect_combo.currentText(),
                "model": "flux",
                "flux_model": flux_model,
                "flux_mode": flux_mode,
                "flux_num": flux_num,
                "flux_size": flux_size,
                "base_image_path": base_image_abs,
                "output_dir": output_dir,
                "reference_images": ref_paths,
                "prompt_template": prompt_template,
            }
            tasks.append(
                TaskAssignment(
                    task_id=f"expr-{int(time.time()*1000)}-{idx}",
                    agent_type="portrait",
                    task_type="generate_expression_batch",
                    task_content=f"表情差分 {self.current_item.char_name}",
                    parameters=params,
                )
            )

        self._is_busy = True
        self.expr_generate_btn.setEnabled(False)

        def _do_work():
            outputs_local: List[str] = []
            for t in tasks:
                resp = self.portrait_agent.execute(t)
                if resp.status != "success":
                    raise RuntimeError(resp.error_message or "生成失败")
                outputs_local.extend(resp.output_files or [])
            return outputs_local

        def _on_success(raw_outputs):
            nonlocal all_outputs
            outputs = self._normalize_paths(raw_outputs or [])
            all_outputs = outputs
            if all_outputs:
                exist = set(self.current_item.file_paths or [])
                for f in all_outputs:
                    exist.add(f)
                self.current_item.file_paths = list(exist)
            self.current_item.status = "generated"
            self._persist_pending_lists()
            self._refresh_list_texts()
            self.filepaths_label.setText("文件：" + ", ".join(self.current_item.file_paths or []))
            self.status_value.setText(self.current_item.status)
            self.progress_label.setText("状态：表情差分生成完成")

        def _on_error(err_text: str):
            QMessageBox.critical(self, "生成失败", err_text)
            self.progress_label.setText("状态：表情生成失败")

        def _on_finally():
            self._is_busy = False
            self.expr_generate_btn.setEnabled(True)

        started = self._runner.run(
            label=self.progress_label,
            base_text="状态：生成表情差分...",
            fn=_do_work,
            on_success=_on_success,
            on_error=_on_error,
            on_finally=_on_finally,
        )
        if not started:
            self._is_busy = False
            self.expr_generate_btn.setEnabled(True)
            QMessageBox.information(self, "提示", "已有任务在运行，请稍候。")

        return

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
