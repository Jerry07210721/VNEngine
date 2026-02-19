"""Properties dock for flow nodes with sub-dialog support."""
import ast
import html
import shutil
from pathlib import Path
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QDialog,
    QScrollArea,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QLabel,
    QDoubleSpinBox,
    QToolButton,
)
from PyQt6.QtCore import Qt

from src.designer.text_style_dialog import EntryTextStyleDialog


class _CollapsibleSection(QWidget):
    """A lightweight collapsible section with a rotating arrow indicator."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._expanded = True

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(6, 6, 6, 6)
        header_layout.setSpacing(6)

        self._toggle = QToolButton(header)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(True)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow)
        self._toggle.setAutoRaise(True)
        self._toggle.clicked.connect(self._on_toggled)
        header_layout.addWidget(self._toggle)

        self._title = QLabel(title, header)
        self._title.setStyleSheet("font-weight: 700;")
        header_layout.addWidget(self._title, 1)

        root.addWidget(header)

        self._content = QWidget(self)
        root.addWidget(self._content)

    def setContentLayout(self, layout):  # noqa: N802
        self._content.setLayout(layout)

    def setExpanded(self, expanded: bool):  # noqa: N802
        self._expanded = bool(expanded)
        self._toggle.setChecked(self._expanded)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if self._expanded else Qt.ArrowType.RightArrow)
        self._content.setVisible(self._expanded)

    def _on_toggled(self):
        self.setExpanded(self._toggle.isChecked())


class PropertiesDock(QDockWidget):
    """节点属性面板：四个分区，文本节点支持 1-50 条子对话。"""

    MAX_SUB_DIALOGUES = 50

    def __init__(self, parent=None):
        super().__init__("属性", parent)
        self.setObjectName("PropertiesDock")
        self._current_node = None
        self._updating = False
        self._sub_editing = False
        self._sub_dialogues: list[dict] = []
        self._options: list[str] = []
        self._var_ops: list[dict] = []
        self._cond_rules: list[dict] = []
        self._function_rules: list[dict] = []
        self._project_dir: Path | None = None
        self._graph_view = None
        self._media_section = None
        self._ui_section = None

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(10)

        self._build_panel_basic(main_layout)
        self._build_panel_content(main_layout)
        self._build_panel_media(main_layout)
        self._build_panel_ui(main_layout)
        main_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.setWidget(scroll)
        self.setMinimumWidth(340)

    # ------- UI 构建 -------
    def _build_panel_basic(self, parent_layout):
        section = _CollapsibleSection("面板一：基础")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.title_edit = QLineEdit()
        self.title_edit.editingFinished.connect(self._on_title_changed)
        form.addRow("标题", self.title_edit)

        self.type_combo = QComboBox()
        # 通用节点类型（不包含功能节点；功能节点是独立类型，不可在此下拉中选择）
        self.type_combo.addItems(["文本", "选择", "条件"])
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("节点类型", self.type_combo)
        section.setContentLayout(form)
        parent_layout.addWidget(section)

    def _build_panel_content(self, parent_layout):
        section = _CollapsibleSection("面板二：节点内容")
        vbox = QVBoxLayout()
        vbox.setContentsMargins(6, 0, 6, 6)
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self._build_text_page())
        self.content_stack.addWidget(self._build_choice_page())
        self.content_stack.addWidget(self._build_condition_page())
        self.content_stack.addWidget(self._build_function_page())
        vbox.addWidget(self.content_stack)
        section.setContentLayout(vbox)
        parent_layout.addWidget(section)

    def _build_text_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        btn_row = QHBoxLayout()
        self.add_sub_btn = QPushButton("新增子节点")
        self.del_sub_btn = QPushButton("删除")
        self.copy_sub_btn = QPushButton("复制")
        self.up_sub_btn = QPushButton("上移")
        self.down_sub_btn = QPushButton("下移")
        for btn in (self.add_sub_btn, self.del_sub_btn, self.copy_sub_btn, self.up_sub_btn, self.down_sub_btn):
            btn.setMinimumWidth(60)
        self.add_sub_btn.clicked.connect(self._on_add_sub)
        self.del_sub_btn.clicked.connect(self._on_delete_sub)
        self.copy_sub_btn.clicked.connect(self._on_copy_sub)
        self.up_sub_btn.clicked.connect(self._on_move_sub_up)
        self.down_sub_btn.clicked.connect(self._on_move_sub_down)
        btn_row.addWidget(self.add_sub_btn)
        btn_row.addWidget(self.del_sub_btn)
        btn_row.addWidget(self.copy_sub_btn)
        btn_row.addWidget(self.up_sub_btn)
        btn_row.addWidget(self.down_sub_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.sub_list = QListWidget()
        # UI-only: increase list height for better editing experience (3-4x of previous feel)
        self.sub_list.setMinimumHeight(320)
        self.sub_list.currentRowChanged.connect(self._on_sub_selection_changed)
        layout.addWidget(self.sub_list)

        detail = QFormLayout()
        detail.setContentsMargins(0, 0, 0, 0)
        self.sub_speaker_edit = QLineEdit()
        self.sub_speaker_edit.textChanged.connect(self._on_sub_detail_changed)
        detail.addRow("角色", self.sub_speaker_edit)

        self.sub_text_edit = QPlainTextEdit()
        self.sub_text_edit.textChanged.connect(self._on_sub_detail_changed)
        detail.addRow("文本", self.sub_text_edit)

        self.sub_voice_edit = QLineEdit()
        sub_voice_row = self._make_file_row(self.sub_voice_edit, self._pick_sub_voice, self._clear_sub_voice, "选择语音")
        detail.addRow("语音", sub_voice_row)

        self.sub_sfx_edit = QLineEdit()
        sub_sfx_row = self._make_file_row(self.sub_sfx_edit, self._pick_sub_sfx, self._clear_sub_sfx, "选择音效")
        detail.addRow("音效", sub_sfx_row)

        self.sub_text_style_enable_chk = QCheckBox("启用对白样式覆盖")
        self.sub_text_style_enable_chk.stateChanged.connect(self._on_sub_detail_changed)
        self.sub_edit_text_style_btn = QPushButton("编辑...")
        self.sub_edit_text_style_btn.clicked.connect(self._edit_sub_text_style)
        style_row = QWidget()
        style_row_lay = QHBoxLayout(style_row)
        style_row_lay.setContentsMargins(0, 0, 0, 0)
        style_row_lay.addWidget(self.sub_text_style_enable_chk)
        style_row_lay.addWidget(self.sub_edit_text_style_btn)
        style_row_lay.addStretch(1)
        detail.addRow("对白样式", style_row)

        self.sub_portrait_edit = QLineEdit()
        sub_portrait_row = self._make_file_row(self.sub_portrait_edit, self._pick_sub_portrait, self._clear_sub_portrait, "选择立绘")
        detail.addRow("立绘", sub_portrait_row)

        self.sub_portrait2_edit = QLineEdit()
        sub_portrait2_row = self._make_file_row(self.sub_portrait2_edit, self._pick_sub_portrait2, self._clear_sub_portrait2, "选择立绘")
        detail.addRow("立绘2", sub_portrait2_row)

        self.sub_ui_file_edit = QLineEdit()
        self.sub_ui_file_edit.textChanged.connect(self._on_sub_detail_changed)
        sub_ui_row = self._make_file_row(self.sub_ui_file_edit, self._pick_sub_ui_file, self._clear_sub_ui_file, "选择 .json")
        detail.addRow("UI文件", sub_ui_row)

        self.sub_hide_chk = QCheckBox("隐藏文本框")
        self.sub_hide_chk.stateChanged.connect(self._on_sub_detail_changed)
        detail.addRow("", self.sub_hide_chk)

        self.sub_fade_chk = QCheckBox("立绘淡入")
        self.sub_fade_chk.stateChanged.connect(self._on_sub_detail_changed)
        detail.addRow("", self.sub_fade_chk)

        self.sub_fade_out_chk = QCheckBox("立绘淡出（进入下一子节点前）")
        self.sub_fade_out_chk.stateChanged.connect(self._on_sub_detail_changed)
        detail.addRow("", self.sub_fade_out_chk)

        # 子节点级：进入该子节点时的立绘弹跳（与淡入/淡出放在一起）
        self.sub_portrait_bounce_chk = QCheckBox("立绘弹跳（进入该子节点时）")
        self.sub_portrait_bounce_chk.stateChanged.connect(self._on_sub_detail_changed)
        detail.addRow("", self.sub_portrait_bounce_chk)

        self.sub_fade2_chk = QCheckBox("立绘2淡入")
        self.sub_fade2_chk.stateChanged.connect(self._on_sub_detail_changed)
        detail.addRow("", self.sub_fade2_chk)

        self.sub_fade2_out_chk = QCheckBox("立绘2淡出（进入下一子节点前）")
        self.sub_fade2_out_chk.stateChanged.connect(self._on_sub_detail_changed)
        detail.addRow("", self.sub_fade2_out_chk)

        self.sub_portrait2_bounce_chk = QCheckBox("立绘2弹跳（进入该子节点时）")
        self.sub_portrait2_bounce_chk.stateChanged.connect(self._on_sub_detail_changed)
        detail.addRow("", self.sub_portrait2_bounce_chk)

        self.sub_fade_in_duration_spin = QDoubleSpinBox()
        self.sub_fade_in_duration_spin.setRange(0.0, 10.0)
        self.sub_fade_in_duration_spin.setSingleStep(0.05)
        self.sub_fade_in_duration_spin.setDecimals(2)
        self.sub_fade_in_duration_spin.valueChanged.connect(self._on_sub_detail_changed)
        detail.addRow("立绘淡入时长(秒)", self.sub_fade_in_duration_spin)

        self.sub_fade_out_duration_spin = QDoubleSpinBox()
        self.sub_fade_out_duration_spin.setRange(0.0, 10.0)
        self.sub_fade_out_duration_spin.setSingleStep(0.05)
        self.sub_fade_out_duration_spin.setDecimals(2)
        self.sub_fade_out_duration_spin.valueChanged.connect(self._on_sub_detail_changed)
        detail.addRow("立绘淡出时长(秒)", self.sub_fade_out_duration_spin)

        self.sub_fade2_in_duration_spin = QDoubleSpinBox()
        self.sub_fade2_in_duration_spin.setRange(0.0, 10.0)
        self.sub_fade2_in_duration_spin.setSingleStep(0.05)
        self.sub_fade2_in_duration_spin.setDecimals(2)
        self.sub_fade2_in_duration_spin.valueChanged.connect(self._on_sub_detail_changed)
        detail.addRow("立绘2淡入时长(秒)", self.sub_fade2_in_duration_spin)

        self.sub_fade2_out_duration_spin = QDoubleSpinBox()
        self.sub_fade2_out_duration_spin.setRange(0.0, 10.0)
        self.sub_fade2_out_duration_spin.setSingleStep(0.05)
        self.sub_fade2_out_duration_spin.setDecimals(2)
        self.sub_fade2_out_duration_spin.valueChanged.connect(self._on_sub_detail_changed)
        detail.addRow("立绘2淡出时长(秒)", self.sub_fade2_out_duration_spin)

        self.sub_auto_next_spin = QDoubleSpinBox()
        self.sub_auto_next_spin.setRange(0.0, 600.0)
        self.sub_auto_next_spin.setSingleStep(0.5)
        self.sub_auto_next_spin.setDecimals(1)
        self.sub_auto_next_spin.valueChanged.connect(self._on_sub_detail_changed)
        detail.addRow("自动进入下一句(秒，0=关闭)", self.sub_auto_next_spin)

        layout.addLayout(detail)

        # 变量处理列表
        var_group = QGroupBox("变量处理")
        var_form = QVBoxLayout(var_group)
        var_btn_row = QHBoxLayout()
        self.add_var_op_btn = QPushButton("新增处理")
        self.del_var_op_btn = QPushButton("删除")
        self.edit_var_op_btn = QPushButton("编辑")
        for btn in (self.add_var_op_btn, self.edit_var_op_btn, self.del_var_op_btn):
            btn.setMinimumWidth(60)
        self.add_var_op_btn.clicked.connect(self._on_add_var_op)
        self.edit_var_op_btn.clicked.connect(self._on_edit_var_op)
        self.del_var_op_btn.clicked.connect(self._on_delete_var_op)
        var_btn_row.addWidget(self.add_var_op_btn)
        var_btn_row.addWidget(self.edit_var_op_btn)
        var_btn_row.addWidget(self.del_var_op_btn)
        var_btn_row.addStretch(1)
        var_form.addLayout(var_btn_row)

        self.var_op_list = QListWidget()
        self.var_op_list.currentRowChanged.connect(self._on_var_op_selection_changed)
        self.var_op_list.itemDoubleClicked.connect(lambda _: self._on_edit_var_op())
        var_form.addWidget(self.var_op_list)
        var_group.setLayout(var_form)
        layout.addWidget(var_group)

        return page

    def _build_choice_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        # 选择节点扩展配置：倒计时 + 默认选项
        cfg_form = QFormLayout()
        cfg_form.setContentsMargins(0, 0, 0, 0)
        self.choice_timeout_spin = QDoubleSpinBox()
        self.choice_timeout_spin.setRange(0.0, 600.0)
        self.choice_timeout_spin.setDecimals(1)
        self.choice_timeout_spin.setSingleStep(0.5)
        self.choice_timeout_spin.setToolTip("0 表示不启用；到时未选择则自动选择默认选项（倒计时不显示）")
        self.choice_timeout_spin.valueChanged.connect(self._on_choice_timeout_changed)
        cfg_form.addRow("倒计时(秒,0=关闭)", self.choice_timeout_spin)

        self.choice_default_combo = QComboBox()
        self.choice_default_combo.setToolTip("到时自动选择该选项；不设置则不会自动选择")
        self.choice_default_combo.currentIndexChanged.connect(self._on_choice_default_changed)
        cfg_form.addRow("默认选项", self.choice_default_combo)

        layout.addLayout(cfg_form)

        btn_row = QHBoxLayout()
        self.add_option_btn = QPushButton("新增选项")
        self.del_option_btn = QPushButton("删除")
        self.up_option_btn = QPushButton("上移")
        self.down_option_btn = QPushButton("下移")
        for btn in (self.add_option_btn, self.del_option_btn, self.up_option_btn, self.down_option_btn):
            btn.setMinimumWidth(60)
        self.add_option_btn.clicked.connect(self._on_add_option)
        self.del_option_btn.clicked.connect(self._on_delete_option)
        self.up_option_btn.clicked.connect(self._on_move_option_up)
        self.down_option_btn.clicked.connect(self._on_move_option_down)
        btn_row.addWidget(self.add_option_btn)
        btn_row.addWidget(self.del_option_btn)
        btn_row.addWidget(self.up_option_btn)
        btn_row.addWidget(self.down_option_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.option_list = QListWidget()
        self.option_list.currentRowChanged.connect(self._on_option_selection_changed)
        layout.addWidget(self.option_list)

        detail = QFormLayout()
        detail.setContentsMargins(0, 0, 0, 0)
        self.option_text_edit = QLineEdit()
        self.option_text_edit.textChanged.connect(self._on_option_detail_changed)
        detail.addRow("选项文本", self.option_text_edit)

        self.option_target_label = QLabel("对应下游节点：未连接")
        self.option_target_label.setStyleSheet("color: #666; font-style: italic;")
        detail.addRow("", self.option_target_label)

        layout.addLayout(detail)

        # 基础展示信息（选择节点也允许展示文本/立绘）
        info_form = QFormLayout()
        self.choice_speaker_edit = QLineEdit()
        self.choice_speaker_edit.editingFinished.connect(self._on_choice_info_changed)
        info_form.addRow("角色", self.choice_speaker_edit)

        self.choice_text_edit = QPlainTextEdit()
        self.choice_text_edit.textChanged.connect(self._on_choice_info_changed)
        info_form.addRow("文本", self.choice_text_edit)

        self.choice_voice_edit = QLineEdit()
        choice_voice_row = self._make_file_row(self.choice_voice_edit, lambda: self._pick_generic_media(self.choice_voice_edit, "音频文件 (*.mp3 *.ogg *.wav)", "resources/voices"), lambda: self._clear_field(self.choice_voice_edit, "set_voice"), "选择语音")
        info_form.addRow("语音", choice_voice_row)

        self.choice_sfx_edit = QLineEdit()
        choice_sfx_row = self._make_file_row(self.choice_sfx_edit, lambda: self._pick_generic_media(self.choice_sfx_edit, "音频文件 (*.mp3 *.ogg *.wav)", "resources/audios"), lambda: self._clear_field(self.choice_sfx_edit, "set_sfx"), "选择音效")
        info_form.addRow("音效", choice_sfx_row)

        self.choice_text_style_enable_chk = QCheckBox("启用对白样式覆盖")
        self.choice_text_style_enable_chk.stateChanged.connect(self._on_choice_info_changed)
        self.choice_edit_text_style_btn = QPushButton("编辑...")
        self.choice_edit_text_style_btn.clicked.connect(self._edit_choice_text_style)
        style_row = QWidget()
        style_row_lay = QHBoxLayout(style_row)
        style_row_lay.setContentsMargins(0, 0, 0, 0)
        style_row_lay.addWidget(self.choice_text_style_enable_chk)
        style_row_lay.addWidget(self.choice_edit_text_style_btn)
        style_row_lay.addStretch(1)
        info_form.addRow("对白样式", style_row)

        self.choice_portrait_edit = QLineEdit()
        choice_portrait_row = self._make_file_row(self.choice_portrait_edit, lambda: self._pick_generic_media(self.choice_portrait_edit, "图片文件 (*.png *.jpg *.jpeg *.bmp)", "resources/portraits"), lambda: self._clear_field(self.choice_portrait_edit, "set_portrait"), "选择立绘")
        info_form.addRow("立绘", choice_portrait_row)

        self.choice_portrait2_edit = QLineEdit()
        choice_portrait2_row = self._make_file_row(self.choice_portrait2_edit, lambda: self._pick_generic_media(self.choice_portrait2_edit, "图片文件 (*.png *.jpg *.jpeg *.bmp)", "resources/portraits"), lambda: self._clear_field(self.choice_portrait2_edit, "set_portrait2"), "选择立绘")
        info_form.addRow("立绘2", choice_portrait2_row)

        self.choice_hide_chk = QCheckBox("隐藏文本框")
        self.choice_hide_chk.stateChanged.connect(self._on_choice_info_changed)
        info_form.addRow("", self.choice_hide_chk)

        self.choice_skip_dialogue_chk = QCheckBox("跳过本节点对白（进入节点时直接弹出选项）")
        self.choice_skip_dialogue_chk.setToolTip("勾选后，从上游进入该节点时将跳过文本/语音/立绘等展示，直接进入选项界面")
        self.choice_skip_dialogue_chk.stateChanged.connect(self._on_choice_info_changed)
        info_form.addRow("", self.choice_skip_dialogue_chk)

        self.choice_portrait_fade_chk = QCheckBox("立绘淡入")
        self.choice_portrait_fade_chk.stateChanged.connect(self._on_choice_info_changed)
        info_form.addRow("", self.choice_portrait_fade_chk)

        self.choice_portrait_bounce_chk = QCheckBox("立绘弹跳（进入节点时）")
        self.choice_portrait_bounce_chk.stateChanged.connect(self._on_portrait_bounce_changed)
        info_form.addRow("", self.choice_portrait_bounce_chk)

        self.choice_portrait2_fade_chk = QCheckBox("立绘2淡入")
        self.choice_portrait2_fade_chk.stateChanged.connect(self._on_choice_info_changed)
        info_form.addRow("", self.choice_portrait2_fade_chk)

        self.choice_portrait2_bounce_chk = QCheckBox("立绘2弹跳（进入节点时）")
        self.choice_portrait2_bounce_chk.stateChanged.connect(self._on_portrait_bounce_changed)
        info_form.addRow("", self.choice_portrait2_bounce_chk)

        layout.addLayout(info_form)
        return page

    def _build_condition_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # --- New rules editor ---
        rules_group = QGroupBox("条件规则（顺序匹配）")
        rules_layout = QVBoxLayout(rules_group)
        rules_layout.setContentsMargins(8, 8, 8, 8)
        rules_layout.setSpacing(6)

        hint = QLabel("按顺序评估规则：命中第一条规则则走对应出边；若全部为假，则走最后一条出边（否则）。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6B7280;")
        rules_layout.addWidget(hint)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.cond_rule_list = QListWidget()
        self.cond_rule_list.setMinimumHeight(180)
        self.cond_rule_list.currentRowChanged.connect(self._on_cond_rule_selection_changed)
        top_row.addWidget(self.cond_rule_list, 1)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)
        self.cond_add_rule_btn = QPushButton("新增")
        self.cond_del_rule_btn = QPushButton("删除")
        self.cond_up_rule_btn = QPushButton("上移")
        self.cond_down_rule_btn = QPushButton("下移")
        self.cond_add_rule_btn.clicked.connect(self._on_add_cond_rule)
        self.cond_del_rule_btn.clicked.connect(self._on_delete_cond_rule)
        self.cond_up_rule_btn.clicked.connect(self._on_move_cond_rule_up)
        self.cond_down_rule_btn.clicked.connect(self._on_move_cond_rule_down)
        for b in (self.cond_add_rule_btn, self.cond_del_rule_btn, self.cond_up_rule_btn, self.cond_down_rule_btn):
            b.setMinimumWidth(60)
        btn_col.addWidget(self.cond_add_rule_btn)
        btn_col.addWidget(self.cond_del_rule_btn)
        btn_col.addWidget(self.cond_up_rule_btn)
        btn_col.addWidget(self.cond_down_rule_btn)
        btn_col.addStretch(1)
        top_row.addLayout(btn_col)

        editor_box = QWidget()
        editor_form = QFormLayout(editor_box)
        editor_form.setContentsMargins(0, 0, 0, 0)

        self.cond_rule_name_edit = QLineEdit()
        self.cond_rule_name_edit.setPlaceholderText("可选：用于备注")
        self.cond_rule_name_edit.editingFinished.connect(self._on_cond_rule_detail_changed)
        editor_form.addRow("名称", self.cond_rule_name_edit)

        self.cond_rule_logic_combo = QComboBox()
        self.cond_rule_logic_combo.addItem("AND（全部满足）", "and")
        self.cond_rule_logic_combo.addItem("OR（任一满足）", "or")
        self.cond_rule_logic_combo.currentIndexChanged.connect(self._on_cond_rule_detail_changed)
        editor_form.addRow("连接", self.cond_rule_logic_combo)

        self.cond_rule_exprs_edit = QPlainTextEdit()
        self.cond_rule_exprs_edit.setMinimumHeight(96)
        self.cond_rule_exprs_edit.setPlaceholderText("一行一个表达式，例如：\nfavorability >= 60\nroute_flag == 1\n\n语法与菜单触发条件一致，支持 and/or/not、括号、比较与简单算术。")
        try:
            self.cond_rule_exprs_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        except Exception:
            pass
        self.cond_rule_exprs_edit.textChanged.connect(self._on_cond_rule_detail_changed)
        editor_form.addRow("表达式", self.cond_rule_exprs_edit)

        self.cond_rule_vars_label = QLabel("")
        self.cond_rule_vars_label.setWordWrap(True)
        # Use rich text so we can color unknown vars.
        try:
            self.cond_rule_vars_label.setTextFormat(Qt.TextFormat.RichText)
        except Exception:
            pass
        self.cond_rule_vars_label.setStyleSheet("color: #374151;")
        editor_form.addRow("变量", self.cond_rule_vars_label)

        self.cond_rule_expr_error_label = QLabel("")
        self.cond_rule_expr_error_label.setWordWrap(True)
        self.cond_rule_expr_error_label.setStyleSheet("color: #B45309;")
        editor_form.addRow("校验", self.cond_rule_expr_error_label)

        self.cond_rule_preview_label = QLabel("")
        self.cond_rule_preview_label.setWordWrap(True)
        self.cond_rule_preview_label.setStyleSheet("color: #6B7280;")
        editor_form.addRow("预览", self.cond_rule_preview_label)

        top_row.addWidget(editor_box, 2)
        rules_layout.addLayout(top_row)

        self.cond_branch_hint_label = QLabel("")
        self.cond_branch_hint_label.setWordWrap(True)
        self.cond_branch_hint_label.setStyleSheet("color: #6B7280;")
        rules_layout.addWidget(self.cond_branch_hint_label)

        self.cond_branch_map_view = QPlainTextEdit()
        self.cond_branch_map_view.setReadOnly(True)
        self.cond_branch_map_view.setMinimumHeight(78)
        try:
            self.cond_branch_map_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        except Exception:
            pass
        rules_layout.addWidget(self.cond_branch_map_view)

        root.addWidget(rules_group)

        # --- Display info (same as choice node) ---
        info_form = QFormLayout()
        info_form.setContentsMargins(0, 0, 0, 0)

        self.cond_speaker_edit = QLineEdit()
        self.cond_speaker_edit.editingFinished.connect(self._on_cond_info_changed)
        info_form.addRow("角色", self.cond_speaker_edit)

        self.cond_text_edit = QPlainTextEdit()
        self.cond_text_edit.textChanged.connect(self._on_cond_info_changed)
        info_form.addRow("文本", self.cond_text_edit)

        self.cond_voice_edit = QLineEdit()
        cond_voice_row = self._make_file_row(
            self.cond_voice_edit,
            lambda: self._pick_generic_media(self.cond_voice_edit, "音频文件 (*.mp3 *.ogg *.wav)", "resources/voices"),
            lambda: self._clear_field(self.cond_voice_edit, "set_voice"),
            "选择语音",
        )
        info_form.addRow("语音", cond_voice_row)

        self.cond_sfx_edit = QLineEdit()
        cond_sfx_row = self._make_file_row(
            self.cond_sfx_edit,
            lambda: self._pick_generic_media(self.cond_sfx_edit, "音频文件 (*.mp3 *.ogg *.wav)", "resources/audios"),
            lambda: self._clear_field(self.cond_sfx_edit, "set_sfx"),
            "选择音效",
        )
        info_form.addRow("音效", cond_sfx_row)

        self.cond_text_style_enable_chk = QCheckBox("启用对白样式覆盖")
        self.cond_text_style_enable_chk.stateChanged.connect(self._on_cond_info_changed)
        self.cond_edit_text_style_btn = QPushButton("编辑...")
        self.cond_edit_text_style_btn.clicked.connect(self._edit_cond_text_style)
        style_row = QWidget()
        style_row_lay = QHBoxLayout(style_row)
        style_row_lay.setContentsMargins(0, 0, 0, 0)
        style_row_lay.addWidget(self.cond_text_style_enable_chk)
        style_row_lay.addWidget(self.cond_edit_text_style_btn)
        style_row_lay.addStretch(1)
        info_form.addRow("对白样式", style_row)

        self.cond_portrait_edit = QLineEdit()
        cond_portrait_row = self._make_file_row(
            self.cond_portrait_edit,
            lambda: self._pick_generic_media(self.cond_portrait_edit, "图片文件 (*.png *.jpg *.jpeg *.bmp)", "resources/portraits"),
            lambda: self._clear_field(self.cond_portrait_edit, "set_portrait"),
            "选择立绘",
        )
        info_form.addRow("立绘", cond_portrait_row)

        self.cond_portrait2_edit = QLineEdit()
        cond_portrait2_row = self._make_file_row(
            self.cond_portrait2_edit,
            lambda: self._pick_generic_media(self.cond_portrait2_edit, "图片文件 (*.png *.jpg *.jpeg *.bmp)", "resources/portraits"),
            lambda: self._clear_field(self.cond_portrait2_edit, "set_portrait2"),
            "选择立绘",
        )
        info_form.addRow("立绘2", cond_portrait2_row)

        self.cond_hide_chk = QCheckBox("隐藏文本框")
        self.cond_hide_chk.stateChanged.connect(self._on_cond_info_changed)
        info_form.addRow("", self.cond_hide_chk)

        self.cond_skip_dialogue_chk = QCheckBox("跳过本节点对白（进入节点时直接判定并跳转）")
        self.cond_skip_dialogue_chk.setToolTip("勾选后，从上游进入该节点时将跳过文本/语音/立绘等展示，直接进行条件判断并走对应分支")
        self.cond_skip_dialogue_chk.stateChanged.connect(self._on_cond_info_changed)
        info_form.addRow("", self.cond_skip_dialogue_chk)

        self.cond_portrait_fade_chk = QCheckBox("立绘淡入")
        self.cond_portrait_fade_chk.stateChanged.connect(self._on_cond_info_changed)
        info_form.addRow("", self.cond_portrait_fade_chk)

        self.cond_portrait_bounce_chk = QCheckBox("立绘弹跳（进入节点时）")
        self.cond_portrait_bounce_chk.stateChanged.connect(self._on_portrait_bounce_changed)
        info_form.addRow("", self.cond_portrait_bounce_chk)

        self.cond_portrait2_fade_chk = QCheckBox("立绘2淡入")
        self.cond_portrait2_fade_chk.stateChanged.connect(self._on_cond_info_changed)
        info_form.addRow("", self.cond_portrait2_fade_chk)

        self.cond_portrait2_bounce_chk = QCheckBox("立绘2弹跳（进入节点时）")
        self.cond_portrait2_bounce_chk.stateChanged.connect(self._on_portrait_bounce_changed)
        info_form.addRow("", self.cond_portrait2_bounce_chk)

        root.addLayout(info_form)
        return page

    def _try_get_declared_global_var_names(self) -> set[str] | None:
        """Best-effort lookup for declared global variables in the current project.

        Returns:
            - set[str]: successfully located a project_manager; set may be empty.
            - None: could not locate project_manager, so we can't validate unknown vars.
        """

        candidates: list[object] = []

        def _add_parent_chain(obj):
            seen: set[int] = set()
            cur = obj
            for _ in range(20):
                if cur is None:
                    break
                ident = id(cur)
                if ident in seen:
                    break
                seen.add(ident)
                candidates.append(cur)
                try:
                    cur = cur.parent()
                except Exception:
                    break

        _add_parent_chain(self)
        try:
            if getattr(self, "_graph_view", None) is not None:
                _add_parent_chain(self._graph_view)
        except Exception:
            pass

        for obj in candidates:
            pm = getattr(obj, "project_manager", None)
            if pm is None:
                continue
            pdata = getattr(pm, "project_data", None)
            if not isinstance(pdata, dict):
                continue
            gv = pdata.get("global_variables")
            if gv is None:
                gv = []
            if not isinstance(gv, list):
                gv = []
            names: set[str] = set()
            for item in gv:
                if not isinstance(item, dict):
                    continue
                n = str(item.get("name") or "").strip()
                if n:
                    names.add(n)
            return names

        return None

    def _analyze_var_expr_lines(self, lines: list[str]) -> tuple[set[str], list[str]]:
        """Parse each line as a Python expr (var_expr) and return (names, errors)."""
        names: set[str] = set()
        errors: list[str] = []
        for idx, raw in enumerate(lines):
            expr = str(raw or "").strip()
            if not expr:
                continue
            try:
                tree = ast.parse(expr, mode="eval")
            except Exception as e:
                errors.append(f"第{idx + 1}行语法错误：{e}")
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    if node.id:
                        names.add(node.id)
        return names, errors

    def _update_cond_rule_expr_diagnostics(self):
        if not hasattr(self, "cond_rule_exprs_edit") or not hasattr(self, "cond_rule_vars_label") or not hasattr(self, "cond_rule_expr_error_label"):
            return

        # If no rule selected, keep it clean.
        row = -1
        try:
            row = int(self.cond_rule_list.currentRow()) if hasattr(self, "cond_rule_list") else -1
        except Exception:
            row = -1
        if row < 0:
            self.cond_rule_vars_label.setText("")
            self.cond_rule_expr_error_label.setText("")
            return

        lines = [ln.strip() for ln in (self.cond_rule_exprs_edit.toPlainText() or "").splitlines() if ln.strip()]
        used, parse_errors = self._analyze_var_expr_lines(lines)
        declared = self._try_get_declared_global_var_names()
        can_validate_unknown = declared is not None
        declared_names = declared or set()
        unknown = {n for n in used if can_validate_unknown and n not in declared_names}

        if not used:
            self.cond_rule_vars_label.setText("<span style='color:#6B7280'>未检测到变量引用</span>")
        else:
            parts: list[str] = []
            for n in sorted(used):
                safe = html.escape(n)
                if n in unknown:
                    parts.append(f"<span style='color:#DC2626; font-weight:700'>{safe}</span>")
                else:
                    parts.append(f"<span style='color:#111827'>{safe}</span>")
            suffix = ""
            if can_validate_unknown:
                suffix = f"<span style='color:#6B7280'>（已声明：{len(declared_names)}）</span>"
            else:
                suffix = "<span style='color:#6B7280'>（未读取到全局变量列表）</span>"
            self.cond_rule_vars_label.setText("变量引用：" + "， ".join(parts) + (" " + suffix if suffix else ""))

        msgs: list[str] = []
        if unknown:
            unk = "，".join(sorted(unknown))
            msgs.append(f"未知变量：{unk}（将按 0 参与计算，可能导致条件永远不成立）")
        msgs.extend(parse_errors)
        self.cond_rule_expr_error_label.setText("；".join(msgs) if msgs else "")

    def _build_function_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        bind_row = QWidget()
        bind_lay = QHBoxLayout(bind_row)
        bind_lay.setContentsMargins(0, 0, 0, 0)
        bind_lay.setSpacing(6)
        bind_lay.addWidget(QLabel("绑定到："))
        self.fn_bound_label = QLabel("未绑定")
        self.fn_bound_label.setStyleSheet("color: #6B7280;")
        bind_lay.addWidget(self.fn_bound_label, 1)
        self.fn_unbind_btn = QPushButton("解绑")
        self.fn_unbind_btn.clicked.connect(self._on_unbind_function_node)
        bind_lay.addWidget(self.fn_unbind_btn)
        layout.addWidget(bind_row)

        btn_row = QHBoxLayout()
        self.fn_add_rule_btn = QPushButton("新增规则")
        self.fn_del_rule_btn = QPushButton("删除")
        self.fn_copy_rule_btn = QPushButton("复制")
        self.fn_up_rule_btn = QPushButton("上移")
        self.fn_down_rule_btn = QPushButton("下移")
        for btn in (
            self.fn_add_rule_btn,
            self.fn_del_rule_btn,
            self.fn_copy_rule_btn,
            self.fn_up_rule_btn,
            self.fn_down_rule_btn,
        ):
            btn.setMinimumWidth(60)
        self.fn_add_rule_btn.clicked.connect(self._on_add_fn_rule)
        self.fn_del_rule_btn.clicked.connect(self._on_delete_fn_rule)
        self.fn_copy_rule_btn.clicked.connect(self._on_copy_fn_rule)
        self.fn_up_rule_btn.clicked.connect(self._on_move_fn_rule_up)
        self.fn_down_rule_btn.clicked.connect(self._on_move_fn_rule_down)
        btn_row.addWidget(self.fn_add_rule_btn)
        btn_row.addWidget(self.fn_del_rule_btn)
        btn_row.addWidget(self.fn_copy_rule_btn)
        btn_row.addWidget(self.fn_up_rule_btn)
        btn_row.addWidget(self.fn_down_rule_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.fn_rule_list = QListWidget()
        self.fn_rule_list.setMinimumHeight(200)
        self.fn_rule_list.currentRowChanged.connect(self._on_fn_rule_selection_changed)
        layout.addWidget(self.fn_rule_list)

        detail = QFormLayout()
        detail.setContentsMargins(0, 0, 0, 0)

        self.fn_rule_enabled_chk = QCheckBox("启用")
        self.fn_rule_enabled_chk.stateChanged.connect(self._on_fn_rule_detail_changed)
        detail.addRow("规则", self.fn_rule_enabled_chk)

        # 条件表达式：支持多行编辑（便于书写长表达式）；运行时会把换行当作空格处理。
        self.fn_rule_condition_edit = QPlainTextEdit()
        self.fn_rule_condition_edit.setPlaceholderText("Python 表达式；为空视为 True（支持多行）")
        self.fn_rule_condition_edit.setMinimumHeight(72)
        try:
            self.fn_rule_condition_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        except Exception:
            pass
        self.fn_rule_condition_edit.textChanged.connect(self._on_fn_rule_detail_changed)
        detail.addRow("条件", self.fn_rule_condition_edit)

        self.fn_rule_action_edit = QPlainTextEdit()
        self.fn_rule_action_edit.setPlaceholderText("Python 脚本（建议使用提供的 API，如 engine.xxx()）")
        self.fn_rule_action_edit.textChanged.connect(self._on_fn_rule_detail_changed)
        detail.addRow("动作", self.fn_rule_action_edit)

        layout.addLayout(detail)
        layout.addStretch(1)
        return page

    def _build_panel_media(self, parent_layout):
        section = _CollapsibleSection("面板三：媒体配置")
        self._media_section = section
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.bg_edit = QLineEdit()
        bg_row = self._make_file_row(self.bg_edit, self._on_pick_bg, lambda: self._clear_field(self.bg_edit, "set_background"), "选择背景")
        form.addRow("背景图", bg_row)

        self.bgm_edit = QLineEdit()
        bgm_row = self._make_file_row(self.bgm_edit, self._on_pick_bgm, lambda: self._clear_field(self.bgm_edit, "set_bgm"), "选择BGM")
        form.addRow("BGM", bgm_row)

        self.video_edit = QLineEdit()
        video_row = self._make_file_row(self.video_edit, self._on_pick_video, self._clear_video, "选择视频")
        form.addRow("视频", video_row)

        self.video_loop_chk = QCheckBox("视频循环播放")
        self.video_loop_chk.stateChanged.connect(self._on_video_loop_changed)
        form.addRow("", self.video_loop_chk)

        self.stop_bgm_chk = QCheckBox("进入该节点时停止当前BGM")
        self.stop_bgm_chk.stateChanged.connect(self._on_stop_bgm_changed)
        form.addRow("", self.stop_bgm_chk)

        self.bgm_loop_chk = QCheckBox("BGM循环播放")
        self.bgm_loop_chk.setChecked(True)
        self.bgm_loop_chk.stateChanged.connect(self._on_bgm_loop_changed)
        form.addRow("", self.bgm_loop_chk)

        self.bg_fade_in_chk = QCheckBox("背景渐显效果")
        self.bg_fade_in_chk.stateChanged.connect(self._on_bg_fade_in_changed)
        form.addRow("", self.bg_fade_in_chk)

        self.bg_fade_duration_spin = QDoubleSpinBox()
        self.bg_fade_duration_spin.setRange(0.0, 10.0)
        self.bg_fade_duration_spin.setSingleStep(0.05)
        self.bg_fade_duration_spin.setDecimals(2)
        self.bg_fade_duration_spin.valueChanged.connect(self._on_bg_fade_duration_changed)
        form.addRow("背景渐显时长(秒)", self.bg_fade_duration_spin)

        section.setContentLayout(form)
        parent_layout.addWidget(section)

    def _build_panel_ui(self, parent_layout):
        section = _CollapsibleSection("面板四：UI设计文件")
        self._ui_section = section
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.ui_file_edit = QLineEdit()
        ui_row = self._make_file_row(self.ui_file_edit, self._on_pick_ui_file, lambda: self._clear_field(self.ui_file_edit, "set_ui_file"), "选择 .json")
        form.addRow("UI文件", ui_row)

        section.setContentLayout(form)
        parent_layout.addWidget(section)

    def _make_file_row(self, edit: QLineEdit, pick_handler, clear_handler=None, pick_label="选择") -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(edit)
        btn_pick = QPushButton(pick_label)
        btn_pick.clicked.connect(pick_handler)
        layout.addWidget(btn_pick)
        if clear_handler:
            btn_clear = QPushButton("清空")
            btn_clear.clicked.connect(clear_handler)
            layout.addWidget(btn_clear)
        return row

    # ------- 数据绑定 -------
    def bind_node(self, node):
        self._current_node = node
        self._updating = True
        if node is None:
            self._reset_all_fields()
            self._set_enabled(False)
            self._updating = False
            return

        self._set_enabled(True)
        self.title_edit.setText(getattr(node, "_title", ""))
        node_type = getattr(node, "node_type", "text")
        is_function = str(node_type or "").lower() == "function"
        # 功能节点：类型固定，不允许在下拉里切换；但仍可进入功能节点编辑页
        try:
            self.type_combo.blockSignals(True)
            if is_function:
                self.type_combo.clear()
                self.type_combo.addItems(["功能"])
                self.type_combo.setCurrentIndex(0)
                self.type_combo.setEnabled(False)
            else:
                # 恢复通用节点类型下拉
                if self.type_combo.count() != 3 or self.type_combo.itemText(0) != "文本":
                    self.type_combo.clear()
                    self.type_combo.addItems(["文本", "选择", "条件"])
                self.type_combo.setEnabled(True)
                self._set_type_index(node_type)
        except Exception:
            pass
        finally:
            try:
                self.type_combo.blockSignals(False)
            except Exception:
                pass

        # 功能节点不需要媒体/UI 面板（依赖宿主节点渲染配置）
        try:
            if self._media_section is not None:
                self._media_section.setVisible(not is_function)
            if self._ui_section is not None:
                self._ui_section.setVisible(not is_function)
        except Exception:
            pass

        self._load_sub_dialogues(getattr(node, "sub_dialogues", []))
        self._load_options(getattr(node, "options", []))

        # choice timeout/default
        try:
            self._choice_timeout_seconds = float(getattr(node, "choice_timeout_seconds", 0.0) or 0.0)
        except Exception:
            self._choice_timeout_seconds = 0.0
        try:
            self._choice_default_index = int(getattr(node, "choice_default_index", -1))
        except Exception:
            self._choice_default_index = -1
        if hasattr(self, "choice_timeout_spin"):
            self.choice_timeout_spin.setValue(max(0.0, min(600.0, float(self._choice_timeout_seconds))))
        self._refresh_choice_default_combo()

        # condition rules (new-only)
        try:
            if str(getattr(node, "node_type", "text") or "text").lower() == "condition":
                rules = getattr(node, "condition_rules", [])
                self._load_condition_rules(rules if isinstance(rules, list) else [])
            else:
                self._load_condition_rules([])
        except Exception:
            self._load_condition_rules([])
        # 变量处理：
        # - 文本节点存在子对话时：var_ops 按“子对话”维度存储/编辑
        # - 其他情况：var_ops 按“节点”维度存储/编辑
        self._load_var_ops_from_context(node)
        self.bg_edit.setText(getattr(node, "background", ""))
        self.bgm_edit.setText(getattr(node, "bgm", ""))
        self.video_edit.setText(getattr(node, "video", ""))
        self.video_loop_chk.setChecked(bool(getattr(node, "video_loop", False)))
        self.stop_bgm_chk.setChecked(bool(getattr(node, "stop_bgm", False)))
        self.bgm_loop_chk.setChecked(bool(getattr(node, "bgm_loop", True)))
        self.bg_fade_in_chk.setChecked(bool(getattr(node, "bg_fade_in", False)))
        try:
            self.bg_fade_duration_spin.setValue(float(getattr(node, "bg_fade_duration", 0.45)))
        except Exception:
            self.bg_fade_duration_spin.setValue(0.45)

        self._sync_bounce_checkboxes_from_node(node)
        self.ui_file_edit.setText(getattr(node, "ui_file", ""))
        if hasattr(self, "ui_group"):
            self.ui_group.setVisible(True)

        # 选择/条件节点显示信息
        self.choice_speaker_edit.setText(getattr(node, "speaker", ""))
        self.choice_text_edit.setPlainText(getattr(node, "content", ""))
        self.choice_voice_edit.setText(getattr(node, "voice", ""))
        if hasattr(self, "choice_sfx_edit"):
            self.choice_sfx_edit.setText(getattr(node, "sfx", ""))
        self.choice_portrait_edit.setText(getattr(node, "portrait", ""))
        self.choice_portrait2_edit.setText(getattr(node, "portrait2", ""))
        self.choice_hide_chk.setChecked(bool(getattr(node, "hide_textbox", False)))
        if hasattr(self, "choice_skip_dialogue_chk"):
            self.choice_skip_dialogue_chk.setChecked(bool(getattr(node, "skip_dialogue", False)))
        self.choice_portrait_fade_chk.setChecked(bool(getattr(node, "portrait_fade", False)))
        self.choice_portrait2_fade_chk.setChecked(bool(getattr(node, "portrait2_fade", False)))
        if hasattr(self, "choice_text_style_enable_chk"):
            self.choice_text_style_enable_chk.setChecked(bool(getattr(node, "text_style_enabled", False)))

        self.cond_speaker_edit.setText(getattr(node, "speaker", ""))
        self.cond_text_edit.setPlainText(getattr(node, "content", ""))
        self.cond_voice_edit.setText(getattr(node, "voice", ""))
        if hasattr(self, "cond_sfx_edit"):
            self.cond_sfx_edit.setText(getattr(node, "sfx", ""))
        self.cond_portrait_edit.setText(getattr(node, "portrait", ""))
        self.cond_portrait2_edit.setText(getattr(node, "portrait2", ""))
        self.cond_hide_chk.setChecked(bool(getattr(node, "hide_textbox", False)))
        if hasattr(self, "cond_skip_dialogue_chk"):
            self.cond_skip_dialogue_chk.setChecked(bool(getattr(node, "skip_dialogue", False)))
        self.cond_portrait_fade_chk.setChecked(bool(getattr(node, "portrait_fade", False)))
        self.cond_portrait2_fade_chk.setChecked(bool(getattr(node, "portrait2_fade", False)))
        if hasattr(self, "cond_text_style_enable_chk"):
            self.cond_text_style_enable_chk.setChecked(bool(getattr(node, "text_style_enabled", False)))

        self._update_condition_targets()

        if is_function:
            self._load_function_rules(getattr(node, "rules", []) if hasattr(node, "rules") else [])
            self._sync_function_binding(node)

        self._updating = False
        self._update_content_stack()
        self._update_add_button_state()

    def refresh_function_binding(self, fn_node=None):
        try:
            cur = getattr(self, "_current_node", None)
            if fn_node is not None and cur is not fn_node:
                return
            if cur is None:
                return
            if str(getattr(cur, "node_type", "text") or "text").lower() != "function":
                return
            self._sync_function_binding(cur)
        except Exception:
            return

    def _var_ops_context(self, node=None) -> tuple[str, int | None]:
        n = node if node is not None else self._current_node
        if n is None:
            return ("node", None)
        if getattr(n, "node_type", "text") != "text":
            return ("node", None)
        # 文本节点：若存在子对话，则 var_ops 一律绑定到“当前子对话”。
        # 若 UI 当前未选中任何行，则默认绑定到第 1 条子对话，避免误写入节点级 var_ops。
        if hasattr(self, "sub_list") and isinstance(getattr(self, "_sub_dialogues", None), list) and self._sub_dialogues:
            row = self.sub_list.currentRow()
            if row < 0:
                row = 0
            if 0 <= row < len(self._sub_dialogues):
                return ("sub", row)
        return ("node", None)

    def _load_var_ops_from_context(self, node=None):
        scope, row = self._var_ops_context(node)
        if scope == "sub" and row is not None:
            try:
                item = self._sub_dialogues[row]
            except Exception:
                item = {}
            if isinstance(item, dict) and isinstance(item.get("var_ops"), list):
                self._load_var_ops(item.get("var_ops", []))
            else:
                self._load_var_ops([])
            return
        n = node if node is not None else self._current_node
        self._load_var_ops(getattr(n, "var_ops", []) if n is not None else [])

    def set_project_dir(self, project_dir: Path | None):
        self._project_dir = project_dir

    def _reset_all_fields(self):
        self.title_edit.setText("")
        self.type_combo.setCurrentIndex(0)
        self._load_sub_dialogues([])
        self._load_options([])
        self._load_var_ops([])
        self.bg_edit.setText("")
        self.cond_rule_preview_label.setText("")
        if hasattr(self, "cond_rule_vars_label"):
            self.cond_rule_vars_label.setText("")
        if hasattr(self, "cond_rule_expr_error_label"):
            self.cond_rule_expr_error_label.setText("")
        self.bgm_edit.setText("")
        self.video_edit.setText("")
        self.video_loop_chk.setChecked(False)
        self.stop_bgm_chk.setChecked(False)
        self.bgm_loop_chk.setChecked(True)
        self.bg_fade_in_chk.setChecked(False)
        if hasattr(self, "bg_fade_duration_spin"):
            self.bg_fade_duration_spin.setValue(0.45)
        self._sync_bounce_checkboxes(False, False)
        self.ui_file_edit.setText("")
        if hasattr(self, "sub_ui_file_edit"):
            self.sub_ui_file_edit.setText("")
        if hasattr(self, "sub_sfx_edit"):
            self.sub_sfx_edit.setText("")
        if hasattr(self, "sub_text_style_enable_chk"):
            self.sub_text_style_enable_chk.setChecked(False)
        self.choice_speaker_edit.setText("")
        self.choice_text_edit.setPlainText("")
        self.choice_voice_edit.setText("")
        if hasattr(self, "choice_sfx_edit"):
            self.choice_sfx_edit.setText("")
        if hasattr(self, "choice_text_style_enable_chk"):
            self.choice_text_style_enable_chk.setChecked(False)
        self.choice_portrait_edit.setText("")
        self.choice_portrait2_edit.setText("")
        self.choice_hide_chk.setChecked(False)
        if hasattr(self, "choice_skip_dialogue_chk"):
            self.choice_skip_dialogue_chk.setChecked(False)
        self.choice_portrait_fade_chk.setChecked(False)
        self.choice_portrait2_fade_chk.setChecked(False)
        self.cond_speaker_edit.setText("")
        self.cond_text_edit.setPlainText("")
        self.cond_voice_edit.setText("")
        if hasattr(self, "cond_sfx_edit"):
            self.cond_sfx_edit.setText("")
        if hasattr(self, "cond_text_style_enable_chk"):
            self.cond_text_style_enable_chk.setChecked(False)
        self.cond_portrait_edit.setText("")
        self.cond_portrait2_edit.setText("")
        self.cond_hide_chk.setChecked(False)
        if hasattr(self, "cond_skip_dialogue_chk"):
            self.cond_skip_dialogue_chk.setChecked(False)
        self.cond_portrait_fade_chk.setChecked(False)
        self.cond_portrait2_fade_chk.setChecked(False)
        try:
            self._cond_rules = []
            if hasattr(self, "cond_rule_list"):
                self.cond_rule_list.clear()
            if hasattr(self, "cond_rule_name_edit"):
                self.cond_rule_name_edit.setText("")
                self.cond_rule_name_edit.setEnabled(False)
            if hasattr(self, "cond_rule_logic_combo"):
                self.cond_rule_logic_combo.setCurrentIndex(0)
                self.cond_rule_logic_combo.setEnabled(False)
            if hasattr(self, "cond_rule_exprs_edit"):
                self.cond_rule_exprs_edit.setPlainText("")
                self.cond_rule_exprs_edit.setEnabled(False)
            if hasattr(self, "cond_branch_hint_label"):
                self.cond_branch_hint_label.setText("")
            if hasattr(self, "cond_branch_map_view"):
                self.cond_branch_map_view.setPlainText("")
            if hasattr(self, "cond_del_rule_btn"):
                self.cond_del_rule_btn.setEnabled(False)
            if hasattr(self, "cond_up_rule_btn"):
                self.cond_up_rule_btn.setEnabled(False)
            if hasattr(self, "cond_down_rule_btn"):
                self.cond_down_rule_btn.setEnabled(False)
        except Exception:
            pass
        if hasattr(self, "option_text_edit"):
            self.option_text_edit.setText("")
        if hasattr(self, "option_target_label"):
            self.option_target_label.setText("对应下游节点：未连接")
            self.option_target_label.setStyleSheet("color: #666; font-style: italic;")

        # choice timeout/default
        try:
            self._choice_timeout_seconds = 0.0
            self._choice_default_index = -1
        except Exception:
            pass
        if hasattr(self, "choice_timeout_spin"):
            self.choice_timeout_spin.setValue(0.0)
        if hasattr(self, "choice_default_combo"):
            self._refresh_choice_default_combo()

        # 功能节点
        try:
            self._load_function_rules([])
        except Exception:
            pass
        try:
            self.fn_bound_label.setText("未绑定")
            self.fn_bound_label.setStyleSheet("color: #6B7280;")
        except Exception:
            pass

    def _set_enabled(self, enabled: bool):
        for widget in [
            self.title_edit,
            self.type_combo,
            self.sub_list,
            self.add_sub_btn,
            self.del_sub_btn,
            self.copy_sub_btn,
            self.up_sub_btn,
            self.down_sub_btn,
            self.sub_speaker_edit,
            self.sub_text_edit,
            self.sub_voice_edit,
            self.sub_sfx_edit,
            self.sub_portrait_edit,
            self.sub_portrait2_edit,
            self.sub_ui_file_edit,
            self.sub_text_style_enable_chk,
            self.sub_edit_text_style_btn,
            self.sub_hide_chk,
            self.sub_fade_chk,
            self.sub_fade_out_chk,
            self.sub_portrait_bounce_chk,
            self.sub_fade2_chk,
            self.sub_fade2_out_chk,
            self.sub_portrait2_bounce_chk,
            self.sub_fade_in_duration_spin,
            self.sub_fade_out_duration_spin,
            self.sub_fade2_in_duration_spin,
            self.sub_fade2_out_duration_spin,
            self.sub_auto_next_spin,
            self.option_list,
            self.add_option_btn,
            self.del_option_btn,
            self.up_option_btn,
            self.down_option_btn,
            self.option_text_edit,
            self.choice_timeout_spin,
            self.choice_default_combo,
            self.bg_edit,
            self.bgm_edit,
            self.video_edit,
            self.video_loop_chk,
            self.ui_file_edit,
            self.stop_bgm_chk,
            self.bgm_loop_chk,
            self.bg_fade_in_chk,
            self.bg_fade_duration_spin,
            self.choice_portrait_bounce_chk,
            self.choice_portrait2_bounce_chk,
            self.cond_portrait_bounce_chk,
            self.cond_portrait2_bounce_chk,
            self.choice_speaker_edit,
            self.choice_text_edit,
            self.choice_voice_edit,
            self.choice_sfx_edit,
            self.choice_text_style_enable_chk,
            self.choice_edit_text_style_btn,
            self.choice_portrait_edit,
            self.choice_portrait2_edit,
            self.choice_hide_chk,
            self.choice_portrait_fade_chk,
            self.choice_portrait2_fade_chk,
            self.cond_speaker_edit,
            self.cond_text_edit,
            self.cond_voice_edit,
            self.cond_sfx_edit,
            self.cond_text_style_enable_chk,
            self.cond_edit_text_style_btn,
            self.cond_portrait_edit,
            self.cond_portrait2_edit,
            self.cond_hide_chk,
            self.cond_portrait_fade_chk,
            self.cond_portrait2_fade_chk,
            self.var_op_list,
            self.add_var_op_btn,
            self.edit_var_op_btn,
            self.del_var_op_btn,
            # function node
            self.fn_unbind_btn,
            self.fn_add_rule_btn,
            self.fn_del_rule_btn,
            self.fn_copy_rule_btn,
            self.fn_up_rule_btn,
            self.fn_down_rule_btn,
            self.fn_rule_list,
            self.fn_rule_enabled_chk,
            self.fn_rule_condition_edit,
            self.fn_rule_action_edit,
        ]:
            widget.setEnabled(enabled)

    def _on_portrait_bounce_changed(self, _state):
        if not self._current_node or self._updating:
            return

        sender = self.sender()
        portrait_bounce_senders = {
            getattr(self, "choice_portrait_bounce_chk", None),
            getattr(self, "cond_portrait_bounce_chk", None),
        }
        portrait2_bounce_senders = {
            getattr(self, "choice_portrait2_bounce_chk", None),
            getattr(self, "cond_portrait2_bounce_chk", None),
        }

        if sender in portrait_bounce_senders and hasattr(self._current_node, "set_portrait_bounce"):
            self._current_node.set_portrait_bounce(bool(sender.isChecked()))
        if sender in portrait2_bounce_senders and hasattr(self._current_node, "set_portrait2_bounce"):
            self._current_node.set_portrait2_bounce(bool(sender.isChecked()))

        # 保持三个页面上的弹跳开关一致
        self._sync_bounce_checkboxes_from_node(self._current_node)

    def _sync_bounce_checkboxes_from_node(self, node):
        if node is None:
            self._sync_bounce_checkboxes(False, False)
            return
        self._sync_bounce_checkboxes(
            bool(getattr(node, "portrait_bounce", False)),
            bool(getattr(node, "portrait2_bounce", False)),
        )

    def _sync_bounce_checkboxes(self, portrait_bounce: bool, portrait2_bounce: bool):
        prev = self._updating
        self._updating = True
        try:
            for attr in ("choice_portrait_bounce_chk", "cond_portrait_bounce_chk"):
                if hasattr(self, attr):
                    getattr(self, attr).setChecked(bool(portrait_bounce))
            for attr in ("choice_portrait2_bounce_chk", "cond_portrait2_bounce_chk"):
                if hasattr(self, attr):
                    getattr(self, attr).setChecked(bool(portrait2_bounce))
        finally:
            self._updating = prev

    # ------- 子对话操作 -------
    def _load_sub_dialogues(self, items: list[dict]):
        self._sub_dialogues = []
        if isinstance(items, list):
            for item in items[: self.MAX_SUB_DIALOGUES]:
                if isinstance(item, dict):
                    try:
                        fade_in_d = float(item.get("portrait_fade_duration", 0.4))
                    except Exception:
                        fade_in_d = 0.4
                    try:
                        fade_out_d = float(item.get("portrait_fade_out_duration", 0.4))
                    except Exception:
                        fade_out_d = 0.4
                    try:
                        auto_next = float(item.get("auto_next_seconds", 0.0))
                    except Exception:
                        auto_next = 0.0
                    try:
                        fade2_in_d = float(item.get("portrait2_fade_duration", item.get("portrait_fade_duration", 0.4)))
                    except Exception:
                        fade2_in_d = fade_in_d
                    try:
                        fade2_out_d = float(item.get("portrait2_fade_out_duration", item.get("portrait_fade_out_duration", 0.4)))
                    except Exception:
                        fade2_out_d = fade_out_d
                    self._sub_dialogues.append(
                        {
                            "speaker": item.get("speaker", ""),
                            "text": item.get("text", ""),
                            "voice": item.get("voice", ""),
                            "portrait": item.get("portrait", ""),
                            "portrait2": item.get("portrait2", ""),
                            "ui_file": item.get("ui_file", ""),
                            "hide_textbox": bool(item.get("hide_textbox", False)),
                            "var_ops": item.get("var_ops", []) if isinstance(item.get("var_ops"), list) else [],
                            "portrait_fade": bool(item.get("portrait_fade", False)),
                            "portrait_fade_out": bool(item.get("portrait_fade_out", False)),
                            "portrait2_fade": bool(item.get("portrait2_fade", False)),
                            "portrait2_fade_out": bool(item.get("portrait2_fade_out", False)),
                            "portrait_bounce": bool(item.get("portrait_bounce", False)),
                            "portrait2_bounce": bool(item.get("portrait2_bounce", False)),
                            "portrait_fade_duration": max(0.0, min(10.0, fade_in_d)),
                            "portrait_fade_out_duration": max(0.0, min(10.0, fade_out_d)),
                            "portrait2_fade_duration": max(0.0, min(10.0, fade2_in_d)),
                            "portrait2_fade_out_duration": max(0.0, min(10.0, fade2_out_d)),
                            "auto_next_seconds": max(0.0, min(600.0, auto_next)),
                        }
                    )
        self._refresh_sub_list(select_index=0 if self._sub_dialogues else -1)

    # ------- 选择节点选项操作 -------
    def _load_options(self, items: list[str]):
        self._options = []
        if isinstance(items, list):
            self._options = [str(opt) for opt in items if isinstance(opt, str)]
        self._refresh_option_list(select_index=0 if self._options else -1)
        self._refresh_choice_default_combo()

    # ------- 条件节点规则操作 -------
    def _load_condition_rules(self, rules: list[dict] | None):
        self._cond_rules = []
        if isinstance(rules, list):
            for r in rules[:20]:
                if not isinstance(r, dict):
                    continue
                name = str(r.get("name") or "").strip()
                logic = str(r.get("logic") or "and").strip().lower()
                if logic not in {"and", "or"}:
                    logic = "and"
                exprs = r.get("exprs")
                if isinstance(exprs, str):
                    expr_list = [line.strip() for line in exprs.splitlines() if line.strip()]
                elif isinstance(exprs, list):
                    expr_list = [str(x).strip() for x in exprs[:20] if str(x).strip()]
                else:
                    expr_list = []
                if not expr_list:
                    continue
                self._cond_rules.append({"name": name, "logic": logic, "exprs": expr_list})
        self._refresh_cond_rule_list(select_index=0 if self._cond_rules else -1)

    def _cond_rule_display_text(self, rule: dict, idx: int) -> str:
        if not isinstance(rule, dict):
            return f"{idx + 1}. <无效规则>"
        name = str(rule.get("name") or "").strip()
        logic = str(rule.get("logic") or "and").strip().lower() or "and"
        exprs = rule.get("exprs") if isinstance(rule.get("exprs"), list) else []
        first = str(exprs[0]).strip() if exprs else ""
        preview = first.replace("\n", " ")
        if len(preview) > 24:
            preview = preview[:24] + "..."
        tag = "AND" if logic == "and" else "OR"
        name_part = f" {name}" if name else ""
        return f"{idx + 1}. [{tag}]{name_part} {preview}".strip()

    def _refresh_cond_rule_list(self, select_index: int = -1):
        if not hasattr(self, "cond_rule_list"):
            return
        prev = self._updating
        self._updating = True
        try:
            self.cond_rule_list.blockSignals(True)
            self.cond_rule_list.clear()
            for idx, r in enumerate(self._cond_rules):
                self.cond_rule_list.addItem(QListWidgetItem(self._cond_rule_display_text(r, idx)))
            if select_index >= 0 and select_index < len(self._cond_rules):
                self.cond_rule_list.setCurrentRow(select_index)
            else:
                self.cond_rule_list.setCurrentRow(-1)
        finally:
            try:
                self.cond_rule_list.blockSignals(False)
            except Exception:
                pass
            self._updating = prev
        self._update_cond_rule_detail_fields(self.cond_rule_list.currentRow())
        self._update_condition_targets()

    def _update_cond_rule_detail_fields(self, row: int):
        prev = self._updating
        self._updating = True
        try:
            enabled = 0 <= row < len(self._cond_rules)
            try:
                self.cond_del_rule_btn.setEnabled(enabled)
                self.cond_up_rule_btn.setEnabled(enabled and row > 0)
                self.cond_down_rule_btn.setEnabled(enabled and row < len(self._cond_rules) - 1)
            except Exception:
                pass

            if not enabled:
                self.cond_rule_name_edit.setText("")
                self.cond_rule_logic_combo.setCurrentIndex(0)
                self.cond_rule_exprs_edit.setPlainText("")
                self._update_cond_rule_preview(None)
                try:
                    self.cond_rule_name_edit.setEnabled(False)
                    self.cond_rule_logic_combo.setEnabled(False)
                    self.cond_rule_exprs_edit.setEnabled(False)
                except Exception:
                    pass
                return

            try:
                self.cond_rule_name_edit.setEnabled(True)
                self.cond_rule_logic_combo.setEnabled(True)
                self.cond_rule_exprs_edit.setEnabled(True)
            except Exception:
                pass

            rule = self._cond_rules[row]
            self.cond_rule_name_edit.setText(str(rule.get("name") or ""))
            logic = str(rule.get("logic") or "and").strip().lower()
            if logic not in {"and", "or"}:
                logic = "and"
            # select by userData
            sel = 0
            for i in range(self.cond_rule_logic_combo.count()):
                if self.cond_rule_logic_combo.itemData(i) == logic:
                    sel = i
                    break
            self.cond_rule_logic_combo.setCurrentIndex(sel)
            exprs = rule.get("exprs") if isinstance(rule.get("exprs"), list) else []
            self.cond_rule_exprs_edit.setPlainText("\n".join([str(x) for x in exprs if str(x).strip()]))
            self._update_cond_rule_preview(rule)
        finally:
            self._updating = prev
            try:
                self._update_cond_rule_expr_diagnostics()
            except Exception:
                pass

    def _update_cond_rule_preview(self, rule: dict | None):
        if not hasattr(self, "cond_rule_preview_label"):
            return
        if not isinstance(rule, dict):
            self.cond_rule_preview_label.setText("")
            return
        logic = str(rule.get("logic") or "and").strip().lower()
        if logic not in {"and", "or"}:
            logic = "and"
        exprs = rule.get("exprs") if isinstance(rule.get("exprs"), list) else []
        exprs = [str(x).strip() for x in exprs if str(x).strip()]
        if not exprs:
            self.cond_rule_preview_label.setText("")
            return
        joiner = " AND " if logic == "and" else " OR "
        combined = joiner.join([f"({e})" for e in exprs])
        tag = "AND" if logic == "and" else "OR"
        self.cond_rule_preview_label.setText(f"本规则判定（{tag}）：{combined}")

    def _load_var_ops(self, items: list[dict]):
        self._var_ops = []
        if isinstance(items, list):
            for item in items[:50]:
                if not isinstance(item, dict):
                    continue
                self._var_ops.append(
                    {
                        "dest": item.get("dest", ""),
                        "left": item.get("left", ""),
                        "right": item.get("right", ""),
                        "op": item.get("op", "+"),
                        "left_const": bool(item.get("left_const", False)),
                        "right_const": bool(item.get("right_const", False)),
                    }
                )
        self._refresh_var_ops()

    def _refresh_option_list(self, select_index: int = -1):
        if not hasattr(self, "option_list"):
            return
        self.option_list.blockSignals(True)
        self.option_list.clear()
        for idx, text in enumerate(self._options):
            display = self._option_display_text(text, idx)
            self.option_list.addItem(QListWidgetItem(display))
        if select_index >= 0 and select_index < len(self._options):
            self.option_list.setCurrentRow(select_index)
        else:
            self.option_list.setCurrentRow(-1)
        self.option_list.blockSignals(False)
        self._update_option_detail_fields(self.option_list.currentRow())
        self._refresh_choice_default_combo()

    def _refresh_choice_default_combo(self):
        if not hasattr(self, "choice_default_combo"):
            return
        prev = self._updating
        self._updating = True
        try:
            self.choice_default_combo.blockSignals(True)
            self.choice_default_combo.clear()
            self.choice_default_combo.addItem("不自动选择", -1)
            for idx, text in enumerate(self._options or []):
                preview = (text or "").replace("\n", " ").strip() or "<空>"
                if len(preview) > 20:
                    preview = preview[:20] + "..."
                self.choice_default_combo.addItem(f"{idx + 1}. {preview}", idx)

            # clamp invalid default
            try:
                cur = int(getattr(self, "_choice_default_index", -1))
            except Exception:
                cur = -1
            if cur < -1 or cur >= len(self._options or []):
                cur = -1
                self._choice_default_index = -1

            # set selection by data
            sel = 0
            for i in range(self.choice_default_combo.count()):
                if self.choice_default_combo.itemData(i) == cur:
                    sel = i
                    break
            self.choice_default_combo.setCurrentIndex(sel)
        finally:
            try:
                self.choice_default_combo.blockSignals(False)
            except Exception:
                pass
            self._updating = prev

    def _commit_choice_timeout_default(self):
        if self._updating or self._current_node is None:
            return
        if hasattr(self._current_node, "set_choice_timeout_seconds"):
            self._current_node.set_choice_timeout_seconds(float(getattr(self, "_choice_timeout_seconds", 0.0) or 0.0))
        else:
            setattr(self._current_node, "choice_timeout_seconds", float(getattr(self, "_choice_timeout_seconds", 0.0) or 0.0))
        if hasattr(self._current_node, "set_choice_default_index"):
            self._current_node.set_choice_default_index(int(getattr(self, "_choice_default_index", -1)))
        else:
            setattr(self._current_node, "choice_default_index", int(getattr(self, "_choice_default_index", -1)))

    def _on_choice_timeout_changed(self, _val: float):
        if self._updating or self._current_node is None:
            return
        try:
            self._choice_timeout_seconds = float(self.choice_timeout_spin.value())
        except Exception:
            self._choice_timeout_seconds = 0.0
        self._commit_choice_timeout_default()

    def _on_choice_default_changed(self, _idx: int):
        if self._updating or self._current_node is None:
            return
        try:
            di = self.choice_default_combo.currentData()
            self._choice_default_index = int(di) if di is not None else -1
        except Exception:
            self._choice_default_index = -1
        self._commit_choice_timeout_default()

    def _option_display_text(self, text: str, idx: int) -> str:
        target = self._get_option_target(idx)
        target_hint = f" -> {target}" if target else ""
        preview = text.replace("\n", " ") if text else "<空>"
        if len(preview) > 20:
            preview = preview[:20] + "..."
        return f"{idx + 1}. {preview}{target_hint}"

    def _refresh_var_ops(self, select_index: int = -1):
        if not hasattr(self, "var_op_list"):
            return
        self.var_op_list.blockSignals(True)
        self.var_op_list.clear()
        for idx, item in enumerate(self._var_ops):
            left = f"{item.get('left', '')}{' (C)' if item.get('left_const') else ''}"
            right = f"{item.get('right', '')}{' (C)' if item.get('right_const') else ''}"
            dest = item.get("dest", "") or "?"
            op = item.get("op", "+")
            display = f"{idx + 1}. {dest} = {left} {op} {right}"
            self.var_op_list.addItem(display)
        if select_index >= 0 and select_index < len(self._var_ops):
            self.var_op_list.setCurrentRow(select_index)
        else:
            self.var_op_list.setCurrentRow(-1)
        self.var_op_list.blockSignals(False)

    def _on_var_op_selection_changed(self, _row: int):
        # keep buttons in sync
        has_sel = self.var_op_list.currentRow() >= 0
        for btn in (self.edit_var_op_btn, self.del_var_op_btn):
            btn.setEnabled(has_sel)

    def _on_add_var_op(self):
        new_item = self._edit_var_op_dialog(None)
        if new_item:
            self._var_ops.append(new_item)
            self._refresh_var_ops(select_index=len(self._var_ops) - 1)
            self._commit_var_ops()

    def _on_edit_var_op(self):
        row = self.var_op_list.currentRow()
        if row < 0 or row >= len(self._var_ops):
            return
        edited = self._edit_var_op_dialog(self._var_ops[row])
        if edited:
            self._var_ops[row] = edited
            self._refresh_var_ops(select_index=row)
            self._commit_var_ops()

    def _on_delete_var_op(self):
        row = self.var_op_list.currentRow()
        if row < 0 or row >= len(self._var_ops):
            return
        self._var_ops.pop(row)
        self._refresh_var_ops(select_index=min(row, len(self._var_ops) - 1))
        self._commit_var_ops()

    def _edit_var_op_dialog(self, data: dict | None) -> dict | None:
        dlg = QDialog(self)
        dlg.setWindowTitle("编辑变量处理")
        form = QFormLayout(dlg)
        dest_edit = QLineEdit(data.get("dest", "") if data else "")
        left_edit = QLineEdit(data.get("left", "") if data else "")
        right_edit = QLineEdit(data.get("right", "") if data else "")
        op_combo = QComboBox()
        op_combo.addItems(["+", "-", "*", "/", "="])
        if data:
            op_combo.setCurrentText(str(data.get("op", "+")))
        left_const_chk = QCheckBox("左操作数为常量")
        left_const_chk.setChecked(bool(data.get("left_const", False)) if data else False)
        right_const_chk = QCheckBox("右操作数为常量")
        right_const_chk.setChecked(bool(data.get("right_const", False)) if data else False)

        form.addRow("结果变量", dest_edit)
        form.addRow("左操作数", left_edit)
        form.addRow("运算符", op_combo)
        form.addRow("右操作数", right_edit)
        form.addRow("", left_const_chk)
        form.addRow("", right_const_chk)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(dlg.accept)
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        form.addRow(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        dest = dest_edit.text().strip()
        left = left_edit.text().strip()
        right = right_edit.text().strip()
        if not dest:
            return None
        return {
            "dest": dest,
            "left": left,
            "right": right,
            "op": op_combo.currentText(),
            "left_const": bool(left_const_chk.isChecked()),
            "right_const": bool(right_const_chk.isChecked()),
        }

    def _commit_var_ops(self):
        if self._updating:
            return
        if not self._current_node:
            return

        scope, row = self._var_ops_context()
        if scope == "sub" and row is not None and 0 <= row < len(self._sub_dialogues):
            self._sub_dialogues[row]["var_ops"] = list(self._var_ops)
            self._commit_sub_dialogues()
            # refresh display for that row (e.g. show "变量" flag)
            try:
                if self.sub_list.item(row) is not None:
                    self.sub_list.item(row).setText(self._sub_display_text(self._sub_dialogues[row], row))
            except Exception:
                pass
            return

        if hasattr(self._current_node, "set_var_ops"):
            self._current_node.set_var_ops(list(self._var_ops))

    def _get_option_target(self, idx: int) -> str:
        if not self._graph_view or not self._current_node:
            return ""
        targets = self._graph_view.get_outgoing_targets(self._current_node)
        if idx < 0 or idx >= len(targets):
            return ""
        target_node = targets[idx]
        title = getattr(target_node, "_title", "") or getattr(target_node, "title", "")
        return title or f"节点 {getattr(target_node, 'node_id', '?')}"

    def _on_option_selection_changed(self, row: int):
        self._update_option_detail_fields(row)

    def _update_option_detail_fields(self, row: int):
        if not hasattr(self, "option_text_edit"):
            return
        if row is None or row < 0 or row >= len(self._options):
            self.option_text_edit.setText("")
            self.option_target_label.setText("对应下游节点：未连接")
            detail_enabled = False
        else:
            self.option_text_edit.setText(self._options[row])
            target = self._get_option_target(row)
            if target:
                self.option_target_label.setText(f"对应下游节点：{target}")
                self.option_target_label.setStyleSheet("color: #1c7c3c;")
            else:
                self.option_target_label.setText("对应下游节点：未连接")
                self.option_target_label.setStyleSheet("color: #c04040;")
            detail_enabled = True
        for widget in [self.option_text_edit]:
            widget.setEnabled(detail_enabled)

    def _on_option_detail_changed(self):
        if self._updating or self._current_node is None:
            return
        row = self.option_list.currentRow()
        if row < 0 or row >= len(self._options):
            return
        self._options[row] = self.option_text_edit.text()
        self.option_list.item(row).setText(self._option_display_text(self._options[row], row))
        self._commit_options()

    def _on_add_option(self):
        self._options.append("")
        self._refresh_option_list(select_index=len(self._options) - 1)
        self._commit_options()

    def _on_delete_option(self):
        row = self.option_list.currentRow()
        if row < 0 or row >= len(self._options):
            return
        self._options.pop(row)
        # adjust default index
        try:
            di = int(getattr(self, "_choice_default_index", -1))
        except Exception:
            di = -1
        if di == row:
            self._choice_default_index = -1
        elif di > row:
            self._choice_default_index = di - 1
        new_idx = min(row, len(self._options) - 1)
        self._refresh_option_list(select_index=new_idx)
        self._commit_options()
        self._commit_choice_timeout_default()

    def _on_move_option_up(self):
        row = self.option_list.currentRow()
        if row <= 0:
            return
        self._options[row - 1], self._options[row] = self._options[row], self._options[row - 1]
        # swap default index if it targets one of the swapped items
        try:
            di = int(getattr(self, "_choice_default_index", -1))
        except Exception:
            di = -1
        if di == row:
            self._choice_default_index = row - 1
        elif di == row - 1:
            self._choice_default_index = row
        self._refresh_option_list(select_index=row - 1)
        self._commit_options()
        self._commit_choice_timeout_default()

    def _on_move_option_down(self):
        row = self.option_list.currentRow()
        if row < 0 or row >= len(self._options) - 1:
            return
        self._options[row + 1], self._options[row] = self._options[row], self._options[row + 1]
        try:
            di = int(getattr(self, "_choice_default_index", -1))
        except Exception:
            di = -1
        if di == row:
            self._choice_default_index = row + 1
        elif di == row + 1:
            self._choice_default_index = row
        self._refresh_option_list(select_index=row + 1)
        self._commit_options()
        self._commit_choice_timeout_default()

    def _commit_options(self):
        if self._current_node and hasattr(self._current_node, "set_options") and not self._updating:
            self._current_node.set_options(list(self._options))

    def _commit_condition_rules(self):
        if self._updating or self._current_node is None:
            return
        if str(getattr(self._current_node, "node_type", "text") or "text").lower() != "condition":
            return

        # sanitize: drop empty exprs and empty rules
        cleaned: list[dict] = []
        for r in (self._cond_rules or [])[:50]:
            if not isinstance(r, dict):
                continue
            name = str(r.get("name") or "").strip()
            logic = str(r.get("logic") or "and").strip().lower()
            if logic not in {"and", "or"}:
                logic = "and"
            exprs = r.get("exprs")
            if isinstance(exprs, str):
                expr_list = [line.strip() for line in exprs.splitlines() if line.strip()]
            elif isinstance(exprs, list):
                expr_list = [str(x).strip() for x in exprs[:20] if str(x).strip()]
            else:
                expr_list = []
            if not expr_list:
                continue
            cleaned.append({"name": name, "logic": logic, "exprs": expr_list})

        try:
            setattr(self._current_node, "condition_rules", cleaned)
        except Exception:
            pass
        try:
            self._current_node.update()
        except Exception:
            pass
        self._update_condition_targets()

    def _on_cond_rule_selection_changed(self, row: int):
        if self._updating:
            return
        self._update_cond_rule_detail_fields(int(row))

    def _on_add_cond_rule(self):
        if self._updating:
            return
        self._cond_rules.append({"name": "", "logic": "and", "exprs": ["favorability >= 60"]})
        self._refresh_cond_rule_list(select_index=len(self._cond_rules) - 1)
        self._commit_condition_rules()

    def _on_delete_cond_rule(self):
        if self._updating:
            return
        row = self.cond_rule_list.currentRow() if hasattr(self, "cond_rule_list") else -1
        if row < 0 or row >= len(self._cond_rules):
            return
        self._cond_rules.pop(row)
        new_sel = min(row, len(self._cond_rules) - 1)
        self._refresh_cond_rule_list(select_index=new_sel)
        self._commit_condition_rules()

    def _on_move_cond_rule_up(self):
        if self._updating:
            return
        row = self.cond_rule_list.currentRow() if hasattr(self, "cond_rule_list") else -1
        if row <= 0 or row >= len(self._cond_rules):
            return
        self._cond_rules[row - 1], self._cond_rules[row] = self._cond_rules[row], self._cond_rules[row - 1]
        # keep mapping: swap outgoing edges order as well
        try:
            if self._graph_view and self._current_node is not None:
                self._graph_view.swap_outgoing_targets(self._current_node, row, row - 1)
        except Exception:
            pass
        self._refresh_cond_rule_list(select_index=row - 1)
        self._commit_condition_rules()

    def _on_move_cond_rule_down(self):
        if self._updating:
            return
        row = self.cond_rule_list.currentRow() if hasattr(self, "cond_rule_list") else -1
        if row < 0 or row >= len(self._cond_rules) - 1:
            return
        self._cond_rules[row + 1], self._cond_rules[row] = self._cond_rules[row], self._cond_rules[row + 1]
        try:
            if self._graph_view and self._current_node is not None:
                self._graph_view.swap_outgoing_targets(self._current_node, row, row + 1)
        except Exception:
            pass
        self._refresh_cond_rule_list(select_index=row + 1)
        self._commit_condition_rules()

    def _on_cond_rule_detail_changed(self):
        if self._updating:
            return
        row = self.cond_rule_list.currentRow() if hasattr(self, "cond_rule_list") else -1
        if row < 0 or row >= len(self._cond_rules):
            return
        rule = self._cond_rules[row]
        rule["name"] = str(self.cond_rule_name_edit.text() or "").strip()
        logic = self.cond_rule_logic_combo.currentData()
        logic = str(logic or "and").strip().lower()
        if logic not in {"and", "or"}:
            logic = "and"
        rule["logic"] = logic
        expr_lines = [line.strip() for line in (self.cond_rule_exprs_edit.toPlainText() or "").splitlines() if line.strip()]
        rule["exprs"] = expr_lines
        self._update_cond_rule_preview(rule)
        try:
            self._update_cond_rule_expr_diagnostics()
        except Exception:
            pass
        try:
            item = self.cond_rule_list.item(row)
            if item is not None:
                item.setText(self._cond_rule_display_text(rule, row))
        except Exception:
            pass
        self._commit_condition_rules()

    def set_graph_view(self, graph_view):
        self._graph_view = graph_view

    def _target_display(self, node) -> str:
        if not node:
            return "-"
        title = getattr(node, "_title", "") or getattr(node, "title", "")
        name_part = f" {title}" if title else ""
        return f"{getattr(node, 'node_id', '-')}" + name_part

    def _update_condition_targets(self):
        if not hasattr(self, "cond_branch_map_view") or not hasattr(self, "cond_branch_hint_label"):
            return
        if not self._graph_view or not self._current_node or getattr(self._current_node, "node_type", "text") != "condition":
            self.cond_branch_hint_label.setText("")
            self.cond_branch_map_view.setPlainText("")
            return

        targets = self._graph_view.get_outgoing_targets(self._current_node)
        rules = getattr(self._current_node, "condition_rules", [])
        if not isinstance(rules, list):
            rules = []
        rule_cnt = len(rules)
        expected = rule_cnt + 1

        self.cond_branch_hint_label.setText(
            f"当前出边数：{len(targets)}；期望：{expected}。规则 i 对应第 i 条出边；最后一条出边为否则分支。"
        )

        lines: list[str] = []
        for idx, r in enumerate(rules):
            exprs = r.get("exprs") if isinstance(r, dict) and isinstance(r.get("exprs"), list) else []
            preview = (str(exprs[0]).strip() if exprs else "<空>").replace("\n", " ")
            if len(preview) > 40:
                preview = preview[:40] + "..."
            tgt = self._target_display(targets[idx]) if idx < len(targets) else "<未连接>"
            lines.append(f"规则{idx + 1} -> {tgt}    ({preview})")

        else_tgt = self._target_display(targets[rule_cnt]) if rule_cnt < len(targets) else "<未连接>"
        lines.append(f"否则 -> {else_tgt}")

        self.cond_branch_map_view.setPlainText("\n".join(lines))

    def _on_swap_condition_targets(self):
        if not self._graph_view or not self._current_node:
            return
        self._graph_view.swap_condition_targets(self._current_node)
        self._update_condition_targets()

    def _refresh_sub_list(self, select_index: int = -1):
        self._sub_editing = True
        self.sub_list.clear()
        for idx, item in enumerate(self._sub_dialogues):
            display = self._sub_display_text(item, idx)
            self.sub_list.addItem(QListWidgetItem(display))
        if select_index >= 0 and select_index < len(self._sub_dialogues):
            self.sub_list.setCurrentRow(select_index)
        else:
            self.sub_list.setCurrentRow(-1)
        self._update_sub_detail_fields(self.sub_list.currentRow())
        self._sub_editing = False
        self._update_add_button_state()

    def _sub_display_text(self, item: dict, idx: int) -> str:
        speaker = item.get("speaker") or "旁白"
        text_preview = (item.get("text") or "").replace("\n", " ")
        if len(text_preview) > 20:
            text_preview = text_preview[:20] + "..."
        flags = []
        if item.get("hide_textbox"):
            flags.append("隐藏框")
        if isinstance(item.get("var_ops"), list) and item.get("var_ops"):
            flags.append("变量")
        if (item.get("sfx") or "").strip():
            flags.append("音效")
        if bool(item.get("text_style_enabled", False)):
            flags.append("样式")
        if item.get("portrait_fade"):
            flags.append("淡入")
        if item.get("portrait_fade_out"):
            flags.append("淡出")
        if item.get("portrait_bounce"):
            flags.append("弹跳")
        if item.get("portrait2_bounce"):
            flags.append("2弹跳")
        try:
            auto_next = float(item.get("auto_next_seconds", 0.0))
        except Exception:
            auto_next = 0.0
        if auto_next and auto_next > 0:
            flags.append(f"自动{auto_next:g}s")
        flag_str = f" ({', '.join(flags)})" if flags else ""
        return f"{idx + 1}. {speaker} | {text_preview}{flag_str}"

    def _update_add_button_state(self):
        self.add_sub_btn.setEnabled(len(self._sub_dialogues) < self.MAX_SUB_DIALOGUES)

    def _on_add_sub(self):
        if len(self._sub_dialogues) >= self.MAX_SUB_DIALOGUES:
            self._update_add_button_state()
            return
        self._sub_dialogues.append(
            {
                "speaker": "",
                "text": "",
                "voice": "",
                "sfx": "",
                "portrait": "",
                "portrait2": "",
                "ui_file": "",
                "hide_textbox": False,
                "var_ops": [],
                "text_style_enabled": False,
                "text_styles": {},
                "portrait_fade": False,
                "portrait_fade_out": False,
                "portrait2_fade": False,
                "portrait2_fade_out": False,
                "portrait_bounce": False,
                "portrait2_bounce": False,
                "portrait_fade_duration": 0.4,
                "portrait_fade_out_duration": 0.4,
                "portrait2_fade_duration": 0.4,
                "portrait2_fade_out_duration": 0.4,
                "auto_next_seconds": 0.0,
            }
        )
        self._refresh_sub_list(select_index=len(self._sub_dialogues) - 1)
        self._commit_sub_dialogues()

    def _on_delete_sub(self):
        row = self.sub_list.currentRow()
        if row < 0 or row >= len(self._sub_dialogues):
            return
        self._sub_dialogues.pop(row)
        new_index = min(row, len(self._sub_dialogues) - 1)
        self._refresh_sub_list(select_index=new_index)
        self._commit_sub_dialogues()

    def _on_copy_sub(self):
        if len(self._sub_dialogues) >= self.MAX_SUB_DIALOGUES:
            self._update_add_button_state()
            return
        row = self.sub_list.currentRow()
        if row < 0 or row >= len(self._sub_dialogues):
            return
        src = self._sub_dialogues[row]
        def _safe_float(val, default: float) -> float:
            try:
                return float(val)
            except Exception:
                return default
        copied = {
            "speaker": src.get("speaker", ""),
            "text": src.get("text", ""),
            "voice": src.get("voice", ""),
            "sfx": src.get("sfx", ""),
            "portrait": src.get("portrait", ""),
            "portrait2": src.get("portrait2", ""),
            "ui_file": src.get("ui_file", ""),
            "hide_textbox": bool(src.get("hide_textbox", False)),
            "var_ops": list(src.get("var_ops", [])) if isinstance(src.get("var_ops"), list) else [],
            "text_style_enabled": bool(src.get("text_style_enabled", False)),
            "text_styles": dict(src.get("text_styles", {})) if isinstance(src.get("text_styles"), dict) else {},
            "portrait_fade": bool(src.get("portrait_fade", False)),
            "portrait_fade_out": bool(src.get("portrait_fade_out", False)),
            "portrait2_fade": bool(src.get("portrait2_fade", False)),
            "portrait2_fade_out": bool(src.get("portrait2_fade_out", False)),
            "portrait_bounce": bool(src.get("portrait_bounce", False)),
            "portrait2_bounce": bool(src.get("portrait2_bounce", False)),
            "portrait_fade_duration": _safe_float(src.get("portrait_fade_duration", 0.4), 0.4),
            "portrait_fade_out_duration": _safe_float(src.get("portrait_fade_out_duration", 0.4), 0.4),
            "portrait2_fade_duration": _safe_float(src.get("portrait2_fade_duration", src.get("portrait_fade_duration", 0.4)), 0.4),
            "portrait2_fade_out_duration": _safe_float(src.get("portrait2_fade_out_duration", src.get("portrait_fade_out_duration", 0.4)), 0.4),
            "auto_next_seconds": _safe_float(src.get("auto_next_seconds", 0.0), 0.0),
        }
        insert_at = min(row + 1, len(self._sub_dialogues))
        self._sub_dialogues.insert(insert_at, copied)
        self._refresh_sub_list(select_index=insert_at)
        self._commit_sub_dialogues()

    def _on_move_sub_up(self):
        row = self.sub_list.currentRow()
        if row <= 0:
            return
        self._sub_dialogues[row - 1], self._sub_dialogues[row] = self._sub_dialogues[row], self._sub_dialogues[row - 1]
        self._refresh_sub_list(select_index=row - 1)
        self._commit_sub_dialogues()

    def _on_move_sub_down(self):
        row = self.sub_list.currentRow()
        if row < 0 or row >= len(self._sub_dialogues) - 1:
            return
        self._sub_dialogues[row + 1], self._sub_dialogues[row] = self._sub_dialogues[row], self._sub_dialogues[row + 1]
        self._refresh_sub_list(select_index=row + 1)
        self._commit_sub_dialogues()

    def _on_sub_selection_changed(self, row: int):
        if self._sub_editing:
            return
        self._update_sub_detail_fields(row)
        # 文本节点：变量处理按子对话维度切换
        if not self._updating and self._current_node is not None and getattr(self._current_node, "node_type", "text") == "text":
            self._load_var_ops_from_context()

    def _update_sub_detail_fields(self, row: int):
        self._sub_editing = True
        if row is None or row < 0 or row >= len(self._sub_dialogues):
            self.sub_speaker_edit.setText("")
            self.sub_text_edit.setPlainText("")
            self.sub_voice_edit.setText("")
            self.sub_sfx_edit.setText("")
            self.sub_portrait_edit.setText("")
            self.sub_portrait2_edit.setText("")
            self.sub_ui_file_edit.setText("")
            self.sub_hide_chk.setChecked(False)
            self.sub_fade_chk.setChecked(False)
            self.sub_fade_out_chk.setChecked(False)
            self.sub_fade2_chk.setChecked(False)
            self.sub_fade2_out_chk.setChecked(False)
            if hasattr(self, "sub_portrait_bounce_chk"):
                self.sub_portrait_bounce_chk.setChecked(False)
            if hasattr(self, "sub_portrait2_bounce_chk"):
                self.sub_portrait2_bounce_chk.setChecked(False)
            self.sub_fade_in_duration_spin.setValue(0.4)
            self.sub_fade_out_duration_spin.setValue(0.4)
            self.sub_fade2_in_duration_spin.setValue(0.4)
            self.sub_fade2_out_duration_spin.setValue(0.4)
            self.sub_auto_next_spin.setValue(0.0)
            if hasattr(self, "sub_text_style_enable_chk"):
                self.sub_text_style_enable_chk.setChecked(False)
            detail_enabled = False
        else:
            item = self._sub_dialogues[row]
            self.sub_speaker_edit.setText(item.get("speaker", ""))
            self.sub_text_edit.setPlainText(item.get("text", ""))
            self.sub_voice_edit.setText(item.get("voice", ""))
            self.sub_sfx_edit.setText(item.get("sfx", ""))
            self.sub_portrait_edit.setText(item.get("portrait", ""))
            self.sub_portrait2_edit.setText(item.get("portrait2", ""))
            self.sub_ui_file_edit.setText(item.get("ui_file", ""))
            self.sub_hide_chk.setChecked(bool(item.get("hide_textbox", False)))
            self.sub_fade_chk.setChecked(bool(item.get("portrait_fade", False)))
            self.sub_fade_out_chk.setChecked(bool(item.get("portrait_fade_out", False)))
            self.sub_fade2_chk.setChecked(bool(item.get("portrait2_fade", False)))
            self.sub_fade2_out_chk.setChecked(bool(item.get("portrait2_fade_out", False)))
            if hasattr(self, "sub_portrait_bounce_chk"):
                self.sub_portrait_bounce_chk.setChecked(bool(item.get("portrait_bounce", False)))
            if hasattr(self, "sub_portrait2_bounce_chk"):
                self.sub_portrait2_bounce_chk.setChecked(bool(item.get("portrait2_bounce", False)))
            try:
                self.sub_fade_in_duration_spin.setValue(float(item.get("portrait_fade_duration", 0.4)))
            except Exception:
                self.sub_fade_in_duration_spin.setValue(0.4)
            try:
                self.sub_fade_out_duration_spin.setValue(float(item.get("portrait_fade_out_duration", 0.4)))
            except Exception:
                self.sub_fade_out_duration_spin.setValue(0.4)
            try:
                self.sub_fade2_in_duration_spin.setValue(float(item.get("portrait2_fade_duration", item.get("portrait_fade_duration", 0.4))))
            except Exception:
                self.sub_fade2_in_duration_spin.setValue(0.4)
            try:
                self.sub_fade2_out_duration_spin.setValue(float(item.get("portrait2_fade_out_duration", item.get("portrait_fade_out_duration", 0.4))))
            except Exception:
                self.sub_fade2_out_duration_spin.setValue(0.4)
            try:
                self.sub_auto_next_spin.setValue(float(item.get("auto_next_seconds", 0.0)))
            except Exception:
                self.sub_auto_next_spin.setValue(0.0)
            if hasattr(self, "sub_text_style_enable_chk"):
                self.sub_text_style_enable_chk.setChecked(bool(item.get("text_style_enabled", False)))
            detail_enabled = True
        for widget in [
            self.sub_speaker_edit,
            self.sub_text_edit,
            self.sub_voice_edit,
            self.sub_sfx_edit,
            self.sub_portrait_edit,
            self.sub_portrait2_edit,
            self.sub_ui_file_edit,
            self.sub_text_style_enable_chk,
            self.sub_edit_text_style_btn,
            self.sub_hide_chk,
            self.sub_fade_chk,
            self.sub_fade_out_chk,
            self.sub_portrait_bounce_chk,
            self.sub_fade_in_duration_spin,
            self.sub_fade_out_duration_spin,
            self.sub_fade2_chk,
            self.sub_fade2_out_chk,
            self.sub_portrait2_bounce_chk,
            self.sub_fade2_in_duration_spin,
            self.sub_fade2_out_duration_spin,
            self.sub_auto_next_spin,
        ]:
            widget.setEnabled(detail_enabled)
        self._sub_editing = False

    def _on_sub_detail_changed(self):
        if self._sub_editing or self._current_node is None:
            return
        row = self.sub_list.currentRow()
        if row < 0 or row >= len(self._sub_dialogues):
            return
        item = self._sub_dialogues[row]
        item["speaker"] = self.sub_speaker_edit.text()
        item["text"] = self.sub_text_edit.toPlainText()
        item["voice"] = self.sub_voice_edit.text()
        item["sfx"] = self.sub_sfx_edit.text()
        item["portrait"] = self.sub_portrait_edit.text()
        item["portrait2"] = self.sub_portrait2_edit.text()
        item["ui_file"] = self.sub_ui_file_edit.text()
        item["hide_textbox"] = bool(self.sub_hide_chk.isChecked())
        item["text_style_enabled"] = bool(self.sub_text_style_enable_chk.isChecked())
        item["portrait_fade"] = bool(self.sub_fade_chk.isChecked())
        item["portrait_fade_out"] = bool(self.sub_fade_out_chk.isChecked())
        item["portrait2_fade"] = bool(self.sub_fade2_chk.isChecked())
        item["portrait2_fade_out"] = bool(self.sub_fade2_out_chk.isChecked())
        if hasattr(self, "sub_portrait_bounce_chk"):
            item["portrait_bounce"] = bool(self.sub_portrait_bounce_chk.isChecked())
        if hasattr(self, "sub_portrait2_bounce_chk"):
            item["portrait2_bounce"] = bool(self.sub_portrait2_bounce_chk.isChecked())
        item["portrait_fade_duration"] = float(self.sub_fade_in_duration_spin.value())
        item["portrait_fade_out_duration"] = float(self.sub_fade_out_duration_spin.value())
        item["portrait2_fade_duration"] = float(self.sub_fade2_in_duration_spin.value())
        item["portrait2_fade_out_duration"] = float(self.sub_fade2_out_duration_spin.value())
        item["auto_next_seconds"] = float(self.sub_auto_next_spin.value())
        self.sub_list.item(row).setText(self._sub_display_text(item, row))
        self._commit_sub_dialogues()

    def _commit_sub_dialogues(self):
        if self._current_node and hasattr(self._current_node, "set_sub_dialogues") and not self._updating:
            self._current_node.set_sub_dialogues(list(self._sub_dialogues))
            first = self._sub_dialogues[0] if self._sub_dialogues else None
            if first and hasattr(self._current_node, "set_content"):
                self._current_node.set_content(first.get("text", ""))
            if first and hasattr(self._current_node, "set_speaker"):
                self._current_node.set_speaker(first.get("speaker", ""))
            if first and hasattr(self._current_node, "set_portrait"):
                self._current_node.set_portrait(first.get("portrait", ""))
            if first and hasattr(self._current_node, "set_portrait2"):
                self._current_node.set_portrait2(first.get("portrait2", ""))

    # ------- 事件处理：通用字段 -------
    def _on_title_changed(self):
        if not self._current_node or self._updating:
            return
        text = self.title_edit.text()
        if hasattr(self._current_node, "set_title"):
            self._current_node.set_title(text)

    def _on_type_changed(self):
        if self._updating or not self._current_node:
            self._update_content_stack()
            return
        idx = self.type_combo.currentIndex()
        node_type = {0: "text", 1: "choice", 2: "condition"}.get(idx, "text")
        if hasattr(self._current_node, "set_node_type"):
            self._current_node.set_node_type(node_type)
        self._update_content_stack()

    def _update_content_stack(self):
        # 通用节点页：0=text/1=choice/2=condition；功能节点页固定为 index=3
        if self._current_node is not None and str(getattr(self._current_node, "node_type", "") or "").lower() == "function":
            self.content_stack.setCurrentIndex(3)
            return
        idx = self.type_combo.currentIndex()
        self.content_stack.setCurrentIndex(max(0, min(2, int(idx))))

    def _on_options_changed(self):
        # legacy handler (no-op with new list UI)
        return

    def _on_choice_info_changed(self):
        if not self._current_node or self._updating:
            return
        if hasattr(self._current_node, "set_speaker"):
            self._current_node.set_speaker(self.choice_speaker_edit.text())
        if hasattr(self._current_node, "set_content"):
            self._current_node.set_content(self.choice_text_edit.toPlainText())
        if hasattr(self._current_node, "set_voice"):
            self._current_node.set_voice(self.choice_voice_edit.text())
        if hasattr(self._current_node, "set_sfx"):
            self._current_node.set_sfx(self.choice_sfx_edit.text())
        if hasattr(self._current_node, "set_portrait"):
            self._current_node.set_portrait(self.choice_portrait_edit.text())
        if hasattr(self._current_node, "set_portrait2"):
            self._current_node.set_portrait2(self.choice_portrait2_edit.text())
        if hasattr(self._current_node, "set_hide_textbox"):
            self._current_node.set_hide_textbox(bool(self.choice_hide_chk.isChecked()))
        if hasattr(self, "choice_skip_dialogue_chk"):
            if hasattr(self._current_node, "set_skip_dialogue"):
                self._current_node.set_skip_dialogue(bool(self.choice_skip_dialogue_chk.isChecked()))
            else:
                self._current_node.skip_dialogue = bool(self.choice_skip_dialogue_chk.isChecked())
        if hasattr(self._current_node, "set_portrait_fade"):
            self._current_node.set_portrait_fade(bool(self.choice_portrait_fade_chk.isChecked()))
        if hasattr(self._current_node, "set_portrait2_fade"):
            self._current_node.set_portrait2_fade(bool(self.choice_portrait2_fade_chk.isChecked()))
        if hasattr(self._current_node, "set_text_style_enabled"):
            self._current_node.set_text_style_enabled(bool(self.choice_text_style_enable_chk.isChecked()))
        else:
            self._current_node.text_style_enabled = bool(self.choice_text_style_enable_chk.isChecked())

    def _on_cond_info_changed(self):
        if not self._current_node or self._updating:
            return
        if hasattr(self._current_node, "set_speaker"):
            self._current_node.set_speaker(self.cond_speaker_edit.text())
        if hasattr(self._current_node, "set_content"):
            self._current_node.set_content(self.cond_text_edit.toPlainText())
        if hasattr(self._current_node, "set_voice"):
            self._current_node.set_voice(self.cond_voice_edit.text())
        if hasattr(self._current_node, "set_sfx"):
            self._current_node.set_sfx(self.cond_sfx_edit.text())
        if hasattr(self._current_node, "set_portrait"):
            self._current_node.set_portrait(self.cond_portrait_edit.text())
        if hasattr(self._current_node, "set_portrait2"):
            self._current_node.set_portrait2(self.cond_portrait2_edit.text())
        if hasattr(self._current_node, "set_hide_textbox"):
            self._current_node.set_hide_textbox(bool(self.cond_hide_chk.isChecked()))
        if hasattr(self, "cond_skip_dialogue_chk"):
            if hasattr(self._current_node, "set_skip_dialogue"):
                self._current_node.set_skip_dialogue(bool(self.cond_skip_dialogue_chk.isChecked()))
            else:
                self._current_node.skip_dialogue = bool(self.cond_skip_dialogue_chk.isChecked())
        if hasattr(self._current_node, "set_portrait_fade"):
            self._current_node.set_portrait_fade(bool(self.cond_portrait_fade_chk.isChecked()))
        if hasattr(self._current_node, "set_portrait2_fade"):
            self._current_node.set_portrait2_fade(bool(self.cond_portrait2_fade_chk.isChecked()))
        if hasattr(self._current_node, "set_text_style_enabled"):
            self._current_node.set_text_style_enabled(bool(self.cond_text_style_enable_chk.isChecked()))
        else:
            self._current_node.text_style_enabled = bool(self.cond_text_style_enable_chk.isChecked())

    # ------- 事件处理：文件选择 -------
    def _on_pick_bg(self):
        if not self._current_node:
            return
        file_path = self._choose_file("选择背景图片", "图片文件 (*.png *.jpg *.jpeg *.bmp)", "resources/images")
        if not file_path:
            return
        stored = self._store_into_project(file_path, "resources/images")
        self.bg_edit.setText(stored)
        # 背景与视频互斥
        self.video_edit.setText("")
        self.video_loop_chk.setChecked(False)
        if hasattr(self._current_node, "set_background"):
            self._current_node.set_background(stored)
        if hasattr(self._current_node, "set_video"):
            self._current_node.set_video("", False)

    def _on_pick_bgm(self):
        if not self._current_node:
            return
        file_path = self._choose_file("选择BGM", "音频文件 (*.mp3 *.ogg *.wav)", "resources/audios")
        if not file_path:
            return
        stored = self._store_into_project(file_path, "resources/audios")
        self.bgm_edit.setText(stored)
        if hasattr(self._current_node, "set_bgm"):
            self._current_node.set_bgm(stored)

    def _on_pick_video(self):
        if not self._current_node:
            return
        file_path = self._choose_file("选择视频", "视频文件 (*.mp4 *.mov *.avi *.mkv)", "resources/videos")
        if not file_path:
            return
        stored = self._store_into_project(file_path, "resources/videos")
        # 视频与图片互斥
        self.video_edit.setText(stored)
        self.bg_edit.setText("")
        if hasattr(self._current_node, "set_video"):
            self._current_node.set_video(stored, bool(self.video_loop_chk.isChecked()))
        if hasattr(self._current_node, "set_background"):
            self._current_node.set_background("")

    def _clear_video(self):
        self.video_edit.setText("")
        self.video_loop_chk.setChecked(False)
        if self._current_node and hasattr(self._current_node, "set_video") and not self._updating:
            self._current_node.set_video("", False)

    def _on_video_loop_changed(self, _state):
        if self._current_node and hasattr(self._current_node, "set_video") and not self._updating:
            self._current_node.set_video(self.video_edit.text(), bool(self.video_loop_chk.isChecked()))

    def _on_pick_ui_file(self):
        if not self._current_node:
            return
        file_path = self._choose_file("选择UI设计文件", "UI布局 (*.json)", "ui")
        if not file_path:
            return
        stored = self._store_into_project(file_path, "ui")
        self.ui_file_edit.setText(stored)
        if hasattr(self._current_node, "set_ui_file"):
            self._current_node.set_ui_file(stored)

    def _pick_sub_voice(self):
        file_path = self._choose_file("选择子节点语音", "音频文件 (*.mp3 *.ogg *.wav)", "resources/voices")
        if not file_path:
            return
        stored = self._store_into_project(file_path, "resources/voices")
        self.sub_voice_edit.setText(stored)
        self._on_sub_detail_changed()

    def _clear_sub_voice(self):
        self.sub_voice_edit.setText("")
        self._on_sub_detail_changed()

    def _pick_sub_sfx(self):
        file_path = self._choose_file("选择子节点音效", "音频文件 (*.mp3 *.ogg *.wav)", "resources/audios")
        if not file_path:
            return
        stored = self._store_into_project(file_path, "resources/audios")
        self.sub_sfx_edit.setText(stored)
        self._on_sub_detail_changed()

    def _clear_sub_sfx(self):
        self.sub_sfx_edit.setText("")
        self._on_sub_detail_changed()

    def _edit_sub_text_style(self):
        if self._current_node is None:
            return
        row = self.sub_list.currentRow() if hasattr(self, "sub_list") else -1
        if row < 0 or row >= len(self._sub_dialogues):
            return
        item = self._sub_dialogues[row]
        dlg = EntryTextStyleDialog(item.get("text_styles", {}) if isinstance(item, dict) else {}, self._project_dir, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        item["text_styles"] = dlg.get_text_styles()
        item["text_style_enabled"] = True
        try:
            self.sub_text_style_enable_chk.setChecked(True)
        except Exception:
            pass
        self._commit_sub_dialogues()

    def _edit_choice_text_style(self):
        if self._current_node is None:
            return
        dlg = EntryTextStyleDialog(getattr(self._current_node, "text_styles", {}) if hasattr(self._current_node, "text_styles") else {}, self._project_dir, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        styles = dlg.get_text_styles()
        if hasattr(self._current_node, "set_text_styles"):
            self._current_node.set_text_styles(styles)
        else:
            self._current_node.text_styles = styles
        if hasattr(self._current_node, "set_text_style_enabled"):
            self._current_node.set_text_style_enabled(True)
        else:
            self._current_node.text_style_enabled = True
        try:
            self.choice_text_style_enable_chk.setChecked(True)
        except Exception:
            pass

    def _edit_cond_text_style(self):
        if self._current_node is None:
            return
        dlg = EntryTextStyleDialog(getattr(self._current_node, "text_styles", {}) if hasattr(self._current_node, "text_styles") else {}, self._project_dir, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        styles = dlg.get_text_styles()
        if hasattr(self._current_node, "set_text_styles"):
            self._current_node.set_text_styles(styles)
        else:
            self._current_node.text_styles = styles
        if hasattr(self._current_node, "set_text_style_enabled"):
            self._current_node.set_text_style_enabled(True)
        else:
            self._current_node.text_style_enabled = True
        try:
            self.cond_text_style_enable_chk.setChecked(True)
        except Exception:
            pass

    def _pick_sub_portrait(self):
        file_path = self._choose_file("选择子节点立绘", "图片文件 (*.png *.jpg *.jpeg *.bmp)", "resources/portraits")
        if not file_path:
            return
        stored = self._store_into_project(file_path, "resources/portraits")
        self.sub_portrait_edit.setText(stored)
        self._on_sub_detail_changed()

    def _clear_sub_portrait(self):
        self.sub_portrait_edit.setText("")
        self._on_sub_detail_changed()

    def _pick_sub_portrait2(self):
        file_path = self._choose_file("选择子节点立绘2", "图片文件 (*.png *.jpg *.jpeg *.bmp)", "resources/portraits")
        if not file_path:
            return
        stored = self._store_into_project(file_path, "resources/portraits")
        self.sub_portrait2_edit.setText(stored)
        self._on_sub_detail_changed()

    def _clear_sub_portrait2(self):
        self.sub_portrait2_edit.setText("")
        self._on_sub_detail_changed()

    def _pick_sub_ui_file(self):
        file_path = self._choose_file("选择子节点UI设计文件", "UI布局 (*.json)", "ui")
        if not file_path:
            return
        stored = self._store_into_project(file_path, "ui")
        self.sub_ui_file_edit.setText(stored)
        self._on_sub_detail_changed()

    def _clear_sub_ui_file(self):
        self.sub_ui_file_edit.setText("")
        self._on_sub_detail_changed()

    # ------- 其他控制 -------
    def _clear_field(self, line_edit: QLineEdit, setter_name: str):
        line_edit.setText("")
        if self._current_node and hasattr(self._current_node, setter_name) and not self._updating:
            getattr(self._current_node, setter_name)("")

    def _on_stop_bgm_changed(self, _state):
        if self._current_node and hasattr(self._current_node, "set_stop_bgm") and not self._updating:
            self._current_node.set_stop_bgm(bool(self.stop_bgm_chk.isChecked()))

    def _on_bgm_loop_changed(self, _state):
        if self._current_node and hasattr(self._current_node, "set_bgm_loop") and not self._updating:
            self._current_node.set_bgm_loop(bool(self.bgm_loop_chk.isChecked()))

    def _on_bg_fade_in_changed(self, _state):
        if self._current_node and hasattr(self._current_node, "set_bg_fade_in") and not self._updating:
            self._current_node.set_bg_fade_in(bool(self.bg_fade_in_chk.isChecked()))

    def _on_bg_fade_duration_changed(self, _value):
        if self._current_node and hasattr(self._current_node, "set_bg_fade_duration") and not self._updating:
            self._current_node.set_bg_fade_duration(float(self.bg_fade_duration_spin.value()))

    def _set_type_index(self, node_type: str):
        idx = {"text": 0, "choice": 1, "condition": 2}.get(str(node_type or "text").lower(), 0)
        try:
            self.type_combo.setCurrentIndex(int(idx))
        except Exception:
            self.type_combo.setCurrentIndex(0)

    # ------- 功能节点：规则编辑 -------
    def _sync_function_binding(self, node):
        try:
            bid = getattr(node, "bound_to", None)
            if bid is None:
                self.fn_bound_label.setText("未绑定")
                self.fn_bound_label.setStyleSheet("color: #6B7280;")
            else:
                self.fn_bound_label.setText(str(bid))
                self.fn_bound_label.setStyleSheet("color: #92400E;")
        except Exception:
            return

    def _rule_default(self) -> dict:
        return {
            "enabled": True,
            "condition": "",
            "action": "",
        }

    def _load_function_rules(self, rules: list[dict]):
        self._function_rules = rules if isinstance(rules, list) else []
        normalized: list[dict] = []
        for r in self._function_rules:
            if not isinstance(r, dict):
                continue
            normalized.append(
                {
                    "enabled": bool(r.get("enabled", True)),
                    "condition": str(r.get("condition", r.get("when", "")) or ""),
                    "action": str(r.get("action", r.get("script", "")) or ""),
                }
            )
        self._function_rules = normalized
        self._refresh_fn_rule_list(select_index=0 if self._function_rules else -1)

    def _fn_rule_display_text(self, rule: dict, idx: int) -> str:
        enabled = bool(rule.get("enabled", True))
        cond = (rule.get("condition") or "").strip()
        cond = cond if cond else "True"
        prefix = "✓" if enabled else "✗"
        return f"{prefix} 规则 {idx + 1}: {cond}"[:120]

    def _refresh_fn_rule_list(self, select_index: int = -1):
        self.fn_rule_list.blockSignals(True)
        self.fn_rule_list.clear()
        for idx, r in enumerate(self._function_rules):
            self.fn_rule_list.addItem(QListWidgetItem(self._fn_rule_display_text(r, idx)))
        if 0 <= select_index < len(self._function_rules):
            self.fn_rule_list.setCurrentRow(select_index)
        else:
            self.fn_rule_list.setCurrentRow(-1)
        self.fn_rule_list.blockSignals(False)
        self._update_fn_rule_detail_fields(self.fn_rule_list.currentRow())

    def _update_fn_rule_detail_fields(self, row: int):
        self.fn_rule_enabled_chk.blockSignals(True)
        self.fn_rule_condition_edit.blockSignals(True)
        self.fn_rule_action_edit.blockSignals(True)
        try:
            if row < 0 or row >= len(self._function_rules):
                self.fn_rule_enabled_chk.setChecked(False)
                self.fn_rule_condition_edit.setPlainText("")
                self.fn_rule_action_edit.setPlainText("")
                self.fn_rule_enabled_chk.setEnabled(False)
                self.fn_rule_condition_edit.setEnabled(False)
                self.fn_rule_action_edit.setEnabled(False)
            else:
                r = self._function_rules[row]
                self.fn_rule_enabled_chk.setEnabled(True)
                self.fn_rule_condition_edit.setEnabled(True)
                self.fn_rule_action_edit.setEnabled(True)
                self.fn_rule_enabled_chk.setChecked(bool(r.get("enabled", True)))
                self.fn_rule_condition_edit.setPlainText(str(r.get("condition", "") or ""))
                self.fn_rule_action_edit.setPlainText(str(r.get("action", "") or ""))
        finally:
            self.fn_rule_enabled_chk.blockSignals(False)
            self.fn_rule_condition_edit.blockSignals(False)
            self.fn_rule_action_edit.blockSignals(False)

    def _commit_function_rules(self):
        if self._updating or self._current_node is None:
            return
        if str(getattr(self._current_node, "node_type", "")) != "function":
            return
        if hasattr(self._current_node, "set_rules"):
            self._current_node.set_rules(list(self._function_rules))
        else:
            self._current_node.rules = list(self._function_rules)

    def _on_fn_rule_selection_changed(self, row: int):
        if self._updating:
            return
        self._update_fn_rule_detail_fields(row)

    def _on_fn_rule_detail_changed(self):
        if self._updating or self._current_node is None:
            return
        row = self.fn_rule_list.currentRow()
        if row < 0 or row >= len(self._function_rules):
            return
        r = self._function_rules[row]
        r["enabled"] = bool(self.fn_rule_enabled_chk.isChecked())
        r["condition"] = self.fn_rule_condition_edit.toPlainText()
        r["action"] = self.fn_rule_action_edit.toPlainText()
        try:
            item = self.fn_rule_list.item(row)
            if item is not None:
                item.setText(self._fn_rule_display_text(r, row))
        except Exception:
            pass
        self._commit_function_rules()

    def _on_add_fn_rule(self):
        if self._updating or self._current_node is None:
            return
        if str(getattr(self._current_node, "node_type", "")) != "function":
            return
        self._function_rules.append(self._rule_default())
        self._refresh_fn_rule_list(select_index=len(self._function_rules) - 1)
        self._commit_function_rules()

    def _on_delete_fn_rule(self):
        row = self.fn_rule_list.currentRow()
        if self._updating or row < 0 or row >= len(self._function_rules):
            return
        self._function_rules.pop(row)
        self._refresh_fn_rule_list(select_index=min(row, len(self._function_rules) - 1))
        self._commit_function_rules()

    def _on_copy_fn_rule(self):
        row = self.fn_rule_list.currentRow()
        if self._updating or row < 0 or row >= len(self._function_rules):
            return
        src = self._function_rules[row]
        self._function_rules.insert(
            row + 1,
            {
                "enabled": bool(src.get("enabled", True)),
                "condition": src.get("condition", ""),
                "action": src.get("action", ""),
            },
        )
        self._refresh_fn_rule_list(select_index=row + 1)
        self._commit_function_rules()

    def _on_move_fn_rule_up(self):
        row = self.fn_rule_list.currentRow()
        if self._updating or row <= 0 or row >= len(self._function_rules):
            return
        self._function_rules[row - 1], self._function_rules[row] = self._function_rules[row], self._function_rules[row - 1]
        self._refresh_fn_rule_list(select_index=row - 1)
        self._commit_function_rules()

    def _on_move_fn_rule_down(self):
        row = self.fn_rule_list.currentRow()
        if self._updating or row < 0 or row >= len(self._function_rules) - 1:
            return
        self._function_rules[row + 1], self._function_rules[row] = self._function_rules[row], self._function_rules[row + 1]
        self._refresh_fn_rule_list(select_index=row + 1)
        self._commit_function_rules()

    def _on_unbind_function_node(self):
        if not self._graph_view or self._current_node is None:
            return
        if str(getattr(self._current_node, "node_type", "")) != "function":
            return
        try:
            if hasattr(self._graph_view, "unbind_function_node"):
                self._graph_view.unbind_function_node(self._current_node)
        finally:
            self._sync_function_binding(self._current_node)

    # ------- 路径与文件处理 -------
    def _choose_file(self, title: str, filters: str, subfolder: str) -> str:
        start_dir = str((self._project_dir / subfolder)) if self._project_dir else ""
        path, _ = QFileDialog.getOpenFileName(self, title, start_dir, filters)
        return path

    def _pick_generic_media(self, target_edit: QLineEdit, filters: str, subfolder: str):
        path = self._choose_file("选择文件", filters, subfolder)
        if not path:
            return
        stored = self._store_into_project(path, subfolder)
        target_edit.setText(stored)
        # 主动触发对应字段的保存逻辑，避免仅设置文本但未调用 setter
        if target_edit in (
            getattr(self, "choice_voice_edit", None),
            getattr(self, "choice_sfx_edit", None),
            getattr(self, "choice_portrait_edit", None),
            getattr(self, "choice_portrait2_edit", None),
        ):
            self._on_choice_info_changed()
        elif target_edit in (
            getattr(self, "cond_voice_edit", None),
            getattr(self, "cond_sfx_edit", None),
            getattr(self, "cond_portrait_edit", None),
            getattr(self, "cond_portrait2_edit", None),
        ):
            self._on_cond_info_changed()
        elif target_edit in (
            getattr(self, "sub_voice_edit", None),
            getattr(self, "sub_sfx_edit", None),
            getattr(self, "sub_portrait_edit", None),
            getattr(self, "sub_portrait2_edit", None),
        ):
            self._on_sub_detail_changed()

    def _store_into_project(self, src_path: str, subfolder: str) -> str:
        if not src_path:
            return ""
        if not self._project_dir:
            return src_path
        src = Path(src_path)
        target_dir = (self._project_dir / subfolder).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            if src.resolve().is_relative_to(self._project_dir.resolve()):
                return str(src.relative_to(self._project_dir))
        except Exception:
            pass
        target = target_dir / src.name
        counter = 1
        while target.exists():
            target = target_dir / f"{src.stem}_{counter}{src.suffix}"
            counter += 1
        try:
            shutil.copy2(src, target)
            return str(target.relative_to(self._project_dir))
        except Exception:
            return str(src)

