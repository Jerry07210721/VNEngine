# -*- coding: utf-8 -*-
"""
AI剧情配置界面
"""

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QSpinBox,
    QCheckBox,
    QPushButton,
    QGroupBox,
    QScrollArea,
    QWidget,
    QDoubleSpinBox,
    QComboBox,
)
from PyQt6.QtCore import Qt

from src.designer.ai_base_panel import AIBasePanelWidget
from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.models import StoryConfig


class AIStoryConfigPanel(AIBasePanelWidget):
    """剧情配置界面"""
    
    def __init__(self, project_manager: AIProjectManager, parent=None):
        super().__init__(project_manager, parent)
        self.init_ui()
        
    def init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        
        # 标题
        title_label = QLabel("剧情配置")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title_label)
        
        # ========== 基础信息组 ==========
        basic_group = QGroupBox("基础信息")
        basic_layout = QFormLayout()
        
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("如：夏日的风")
        self.title_edit.textChanged.connect(self.mark_modified)
        basic_layout.addRow("故事标题:", self.title_edit)
        
        self.style_edit = QLineEdit()
        self.style_edit.setPlaceholderText("如：日系校园、纯爱、治愈")
        self.style_edit.textChanged.connect(self.mark_modified)
        basic_layout.addRow("故事风格:", self.style_edit)
        
        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)
        
        # ========== 剧情概要组 ==========
        outline_group = QGroupBox("剧情概要")
        outline_layout = QVBoxLayout()
        
        self.outline_edit = QTextEdit()
        self.outline_edit.setPlaceholderText(
            "请输入剧情概要，描述故事的主要情节、冲突和结局...\n\n"
            "示例：高中生男主与转校生女主在夏日里的相遇与成长，经历误会与和解，最终收获甜蜜结局。"
        )
        self.outline_edit.setMaximumHeight(150)
        self.outline_edit.textChanged.connect(self.mark_modified)
        outline_layout.addWidget(self.outline_edit)
        
        outline_group.setLayout(outline_layout)
        layout.addWidget(outline_group)
        
        # ========== 规模设置组 ==========
        scale_group = QGroupBox("规模设置")
        scale_layout = QFormLayout()
        
        self.text_volume_spin = QSpinBox()
        self.text_volume_spin.setRange(1000, 500000)
        self.text_volume_spin.setValue(5000)
        self.text_volume_spin.setSingleStep(1000)
        self.text_volume_spin.setSuffix(" 字")
        self.text_volume_spin.valueChanged.connect(self.mark_modified)
        scale_layout.addRow("目标文本量:", self.text_volume_spin)
        
        self.chapter_count_spin = QSpinBox()
        self.chapter_count_spin.setRange(1, 50)
        self.chapter_count_spin.setValue(5)
        self.chapter_count_spin.setSuffix(" 章")
        self.chapter_count_spin.valueChanged.connect(self.mark_modified)
        scale_layout.addRow("章节数量:", self.chapter_count_spin)

        self.cg_count_spin = QSpinBox()
        self.cg_count_spin.setRange(0, 20)
        self.cg_count_spin.setValue(0)
        self.cg_count_spin.setSuffix(" 张/章")
        self.cg_count_spin.valueChanged.connect(self.mark_modified)
        scale_layout.addRow("每章CG数量:", self.cg_count_spin)
        
        scale_group.setLayout(scale_layout)
        layout.addWidget(scale_group)

        # ========== 视角设置组 ==========
        pov_group = QGroupBox("叙述视角（POV）")
        pov_layout = QFormLayout()

        self.pov_combo = QComboBox()
        self.pov_combo.addItem("第三人称", "third")
        self.pov_combo.addItem("第一人称", "first")
        self.pov_combo.currentIndexChanged.connect(self._on_pov_changed)
        self.pov_combo.currentIndexChanged.connect(self.mark_modified)
        pov_layout.addRow("视角:", self.pov_combo)

        self.first_person_name_edit = QLineEdit()
        self.first_person_name_edit.setPlaceholderText("如：我")
        self.first_person_name_edit.textChanged.connect(self.mark_modified)
        pov_layout.addRow("第一人称代称:", self.first_person_name_edit)

        self.fp_has_portrait_check = QCheckBox("第一人称有立绘")
        self.fp_has_portrait_check.stateChanged.connect(self.mark_modified)
        pov_layout.addRow("立绘:", self.fp_has_portrait_check)

        self.fp_has_voice_check = QCheckBox("第一人称有配音")
        self.fp_has_voice_check.stateChanged.connect(self.mark_modified)
        pov_layout.addRow("语音:", self.fp_has_voice_check)

        self.fp_cg_presence_check = QCheckBox("第一人称会出现在CG中")
        self.fp_cg_presence_check.setChecked(True)
        self.fp_cg_presence_check.stateChanged.connect(self.mark_modified)
        pov_layout.addRow("CG出镜:", self.fp_cg_presence_check)

        self.fp_cg_notes_edit = QLineEdit()
        self.fp_cg_notes_edit.setPlaceholderText("如：只出现手/背影；不露脸等")
        self.fp_cg_notes_edit.textChanged.connect(self.mark_modified)
        pov_layout.addRow("CG说明:", self.fp_cg_notes_edit)

        pov_group.setLayout(pov_layout)
        layout.addWidget(pov_group)
        
        # ========== 节点类型组 ==========
        node_group = QGroupBox("节点类型")
        node_layout = QVBoxLayout()
        
        self.enable_choice_check = QCheckBox("启用选择节点（玩家可以做出选择）")
        # 仅在开启多分支时可用；默认关闭
        self.enable_choice_check.setChecked(False)
        self.enable_choice_check.stateChanged.connect(self.mark_modified)
        node_layout.addWidget(self.enable_choice_check)
        
        self.enable_condition_check = QCheckBox("启用条件节点（基于变量判断分支）")
        # 仅在开启多分支时可用；默认关闭
        self.enable_condition_check.setChecked(False)
        self.enable_condition_check.stateChanged.connect(self.mark_modified)
        self.enable_condition_check.stateChanged.connect(self.on_condition_check_changed)
        node_layout.addWidget(self.enable_condition_check)

        self.enable_single_route_check = QCheckBox("启用单线叙事（强制章节线性推进；不生成章节级分支）")
        self.enable_single_route_check.setChecked(False)
        self.enable_single_route_check.stateChanged.connect(self._on_single_route_changed)
        self.enable_single_route_check.stateChanged.connect(self.mark_modified)
        node_layout.addWidget(self.enable_single_route_check)

        self.enable_multi_branch_check = QCheckBox("开启多分支（允许并行路线/多结局；章节数按主线计）")
        self.enable_multi_branch_check.setChecked(False)
        self.enable_multi_branch_check.stateChanged.connect(self._on_multi_branch_changed)
        self.enable_multi_branch_check.stateChanged.connect(self.mark_modified)
        node_layout.addWidget(self.enable_multi_branch_check)
        
        # 条件类型子选项
        condition_type_layout = QHBoxLayout()
        condition_type_layout.addSpacing(30)
        condition_type_layout.addWidget(QLabel("条件变量类型:"))
        self.condition_type_edit = QLineEdit()
        self.condition_type_edit.setPlaceholderText("如：favorability（好感度）")
        self.condition_type_edit.setText("favorability")
        self.condition_type_edit.textChanged.connect(self.mark_modified)
        condition_type_layout.addWidget(self.condition_type_edit)
        node_layout.addLayout(condition_type_layout)
        
        node_group.setLayout(node_layout)
        layout.addWidget(node_group)
        
        # ========== 高级设置组 ==========
        advanced_group = QGroupBox("高级设置")
        advanced_layout = QFormLayout()
        
        self.char_hint_weight_spin = QDoubleSpinBox()
        self.char_hint_weight_spin.setRange(0.0, 1.0)
        self.char_hint_weight_spin.setValue(0.7)
        self.char_hint_weight_spin.setSingleStep(0.1)
        self.char_hint_weight_spin.setDecimals(1)
        self.char_hint_weight_spin.valueChanged.connect(self.mark_modified)
        advanced_layout.addRow(
            "角色设定权重:", 
            self.char_hint_weight_spin
        )
        
        hint_label = QLabel("权重越高，AI越严格遵循用户配置的角色人设；权重越低，AI创作自由度越高")
        hint_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        hint_label.setWordWrap(True)
        advanced_layout.addRow("", hint_label)
        
        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)
        
        # 弹性空间
        layout.addStretch()
        
        # ========== 底部按钮 ==========
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.save_button = QPushButton("保存配置")
        self.save_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
        """)
        self.save_button.clicked.connect(self.save_to_project)
        button_layout.addWidget(self.save_button)
        
        self.reset_button = QPushButton("重置")
        self.reset_button.clicked.connect(self.refresh)
        button_layout.addWidget(self.reset_button)
        
        layout.addLayout(button_layout)
        
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

        # 初始化POV可用性
        self._on_pov_changed()

        # 初始化“单线/多分支/节点开关”约束
        self._apply_story_mode_constraints()

    def _set_form_signals_blocked(self, blocked: bool):
        widgets = [
            self.title_edit,
            self.style_edit,
            self.outline_edit,
            self.text_volume_spin,
            self.chapter_count_spin,
            self.cg_count_spin,
            self.enable_choice_check,
            self.enable_condition_check,
            self.enable_single_route_check,
            self.enable_multi_branch_check,
            self.condition_type_edit,
            self.char_hint_weight_spin,
            self.pov_combo,
            self.first_person_name_edit,
            self.fp_has_portrait_check,
            self.fp_has_voice_check,
            self.fp_cg_presence_check,
            self.fp_cg_notes_edit,
        ]
        for w in widgets:
            try:
                w.blockSignals(blocked)
            except Exception:
                pass

    def _on_pov_changed(self, *_):
        pov = self.pov_combo.currentData() if hasattr(self, "pov_combo") else "third"
        enabled = (pov == "first")
        self.first_person_name_edit.setEnabled(enabled)
        self.fp_has_portrait_check.setEnabled(enabled)
        self.fp_has_voice_check.setEnabled(enabled)
        self.fp_cg_presence_check.setEnabled(enabled)
        self.fp_cg_notes_edit.setEnabled(enabled)
        
    def on_condition_check_changed(self, state):
        """条件节点复选框状态改变"""
        enabled = (state == Qt.CheckState.Checked.value)
        self.condition_type_edit.setEnabled(enabled)
        
    def refresh(self):
        """刷新界面，从工程加载数据"""
        if self.project_manager.current_project:
            story_config = self.project_manager.current_project.story_config

            # 阻止控件信号触发（避免刷新时触发 mark_modified）
            self._set_form_signals_blocked(True)
            
            self.title_edit.setText(story_config.title)
            self.style_edit.setText(story_config.style)
            self.outline_edit.setPlainText(story_config.plot_outline)
            self.text_volume_spin.setValue(story_config.text_volume)
            
            # 章节数量（如果有的话）
            if hasattr(story_config, 'chapter_count'):
                self.chapter_count_spin.setValue(story_config.chapter_count)

            if hasattr(story_config, 'cg_count'):
                self.cg_count_spin.setValue(getattr(story_config, 'cg_count', 0) or 0)
            
            self.enable_choice_check.setChecked(story_config.enable_choice_node)
            self.enable_condition_check.setChecked(story_config.enable_condition_node)
            self.enable_single_route_check.setChecked(bool(getattr(story_config, 'enable_single_route', False)))
            self.enable_multi_branch_check.setChecked(bool(getattr(story_config, 'enable_multi_branch', False)))
            self.condition_type_edit.setText(story_config.condition_type)
            self.char_hint_weight_spin.setValue(story_config.character_hint_weight)

            # POV
            pov = getattr(story_config, 'narrative_pov', 'third')
            idx = 0 if pov == 'third' else 1
            self.pov_combo.setCurrentIndex(idx)
            self.first_person_name_edit.setText(getattr(story_config, 'first_person_name', '我') or '我')
            self.fp_has_portrait_check.setChecked(bool(getattr(story_config, 'first_person_has_portrait', False)))
            self.fp_has_voice_check.setChecked(bool(getattr(story_config, 'first_person_has_voice', False)))
            self.fp_cg_presence_check.setChecked(bool(getattr(story_config, 'first_person_cg_presence', True)))
            self.fp_cg_notes_edit.setText(getattr(story_config, 'first_person_cg_notes', '') or '')

            self._on_pov_changed()

            # 刷新后同步“单线/多分支/节点开关”约束
            self._apply_story_mode_constraints()
            
            self._set_form_signals_blocked(False)
    
    def save_to_project(self, silent: bool = False):
        """保存到工程

        Args:
            silent: 为 True 时不弹出“保存成功”提示框（用于主控面板自动同步）。
        """
        if not self.project_manager.current_project:
            return

        current = self.project_manager.current_project.story_config
        
        # 创建新的故事配置
        story_config = StoryConfig(
            title=self.title_edit.text().strip(),
            style=self.style_edit.text().strip(),
            plot_outline=self.outline_edit.toPlainText().strip(),
            text_volume=self.text_volume_spin.value(),
            chapter_count=self.chapter_count_spin.value(),
            cg_count=self.cg_count_spin.value(),
            enable_choice_node=self.enable_choice_check.isChecked(),
            enable_condition_node=self.enable_condition_check.isChecked(),
            enable_multi_branch=self.enable_multi_branch_check.isChecked(),
            enable_single_route=self.enable_single_route_check.isChecked(),
            condition_type=self.condition_type_edit.text().strip(),
            character_hint_weight=self.char_hint_weight_spin.value(),
            narrative_pov=self.pov_combo.currentData() or getattr(current, 'narrative_pov', 'third'),
            first_person_name=self.first_person_name_edit.text().strip() or getattr(current, 'first_person_name', '我'),
            first_person_has_portrait=self.fp_has_portrait_check.isChecked(),
            first_person_has_voice=self.fp_has_voice_check.isChecked(),
            first_person_cg_presence=self.fp_cg_presence_check.isChecked(),
            first_person_cg_notes=self.fp_cg_notes_edit.text().strip(),
        )
        
        # 更新到工程
        self.project_manager.update_story_config(story_config)
        
        # 提示保存成功
        if not silent:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "成功", "剧情配置已保存到工程")
        
        # 触发修改信号（通知主窗口）
        self.mark_modified()

    def _on_single_route_changed(self, *_):
        enabled = bool(self.enable_single_route_check.isChecked())
        # 单线叙事与多分支互斥：启用时关闭并禁用多分支
        if enabled:
            try:
                self.enable_multi_branch_check.blockSignals(True)
                self.enable_multi_branch_check.setChecked(False)
            finally:
                self.enable_multi_branch_check.blockSignals(False)
        self.enable_multi_branch_check.setEnabled(not enabled)

        # 单线叙事开启时，多分支为 False => 选择/条件节点必须不可用
        self._apply_story_mode_constraints()

    def _on_multi_branch_changed(self, *_):
        enabled = bool(self.enable_multi_branch_check.isChecked())
        # 多分支与单线叙事互斥：启用多分支时关闭并禁用单线叙事
        if enabled:
            try:
                self.enable_single_route_check.blockSignals(True)
                self.enable_single_route_check.setChecked(False)
            finally:
                self.enable_single_route_check.blockSignals(False)
        self.enable_single_route_check.setEnabled(not enabled)

        # 多分支开启/关闭会影响选择/条件节点开关
        self._apply_story_mode_constraints()

    def _apply_story_mode_constraints(self):
        """根据当前勾选状态，强制互斥/依赖规则，并同步控件可用性。"""
        multi = bool(self.enable_multi_branch_check.isChecked())
        single = bool(self.enable_single_route_check.isChecked())

        # 互斥纠偏（尽量保持“用户刚勾选的”为真）：
        # - 如果单线为 True，则强制关闭多分支
        # - 如果多分支为 True，则强制关闭单线
        if single and multi:
            try:
                self.enable_multi_branch_check.blockSignals(True)
                self.enable_multi_branch_check.setChecked(False)
            finally:
                self.enable_multi_branch_check.blockSignals(False)
            multi = False

        # 只有多分支允许选择/条件节点
        self.enable_choice_check.setEnabled(multi)
        self.enable_condition_check.setEnabled(multi)
        if not multi:
            try:
                self.enable_choice_check.blockSignals(True)
                self.enable_condition_check.blockSignals(True)
                self.enable_choice_check.setChecked(False)
                self.enable_condition_check.setChecked(False)
            finally:
                self.enable_choice_check.blockSignals(False)
                self.enable_condition_check.blockSignals(False)
        else:
            # 开启多分支时，默认勾选两类节点（用户可再手动取消）
            if not self.enable_choice_check.isChecked() and not self.enable_condition_check.isChecked():
                try:
                    self.enable_choice_check.blockSignals(True)
                    self.enable_condition_check.blockSignals(True)
                    self.enable_choice_check.setChecked(True)
                    self.enable_condition_check.setChecked(True)
                finally:
                    self.enable_choice_check.blockSignals(False)
                    self.enable_condition_check.blockSignals(False)

        # 条件类型输入框仅在“条件节点启用”时可编辑
        self.condition_type_edit.setEnabled(multi and bool(self.enable_condition_check.isChecked()))
