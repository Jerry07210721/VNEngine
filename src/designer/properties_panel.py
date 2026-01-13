"""Properties dock for flow nodes with sub-dialog support."""
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
)
from PyQt6.QtCore import Qt


class PropertiesDock(QDockWidget):
    """节点属性面板：四个分区，文本节点支持 1-50 条子对话。"""

    MAX_SUB_DIALOGUES = 50

    def __init__(self, parent=None):
        super().__init__("属性", parent)
        self._current_node = None
        self._updating = False
        self._sub_editing = False
        self._sub_dialogues: list[dict] = []
        self._options: list[str] = []
        self._var_ops: list[dict] = []
        self._project_dir: Path | None = None
        self._graph_view = None

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
        group = QGroupBox("面板一：基础")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.title_edit = QLineEdit()
        self.title_edit.editingFinished.connect(self._on_title_changed)
        form.addRow("标题", self.title_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["文本", "选择", "条件"])
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("节点类型", self.type_combo)
        parent_layout.addWidget(group)

    def _build_panel_content(self, parent_layout):
        group = QGroupBox("面板二：节点内容")
        vbox = QVBoxLayout(group)
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self._build_text_page())
        self.content_stack.addWidget(self._build_choice_page())
        self.content_stack.addWidget(self._build_condition_page())
        vbox.addWidget(self.content_stack)
        parent_layout.addWidget(group)

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

        self.sub_portrait_edit = QLineEdit()
        sub_portrait_row = self._make_file_row(self.sub_portrait_edit, self._pick_sub_portrait, self._clear_sub_portrait, "选择立绘")
        detail.addRow("立绘", sub_portrait_row)

        self.sub_hide_chk = QCheckBox("隐藏文本框")
        self.sub_hide_chk.stateChanged.connect(self._on_sub_detail_changed)
        detail.addRow("", self.sub_hide_chk)

        self.sub_fade_chk = QCheckBox("立绘淡入")
        self.sub_fade_chk.stateChanged.connect(self._on_sub_detail_changed)
        detail.addRow("", self.sub_fade_chk)

        self.sub_fade_out_chk = QCheckBox("立绘淡出（进入下一子节点前）")
        self.sub_fade_out_chk.stateChanged.connect(self._on_sub_detail_changed)
        detail.addRow("", self.sub_fade_out_chk)

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

        self.choice_portrait_edit = QLineEdit()
        choice_portrait_row = self._make_file_row(self.choice_portrait_edit, lambda: self._pick_generic_media(self.choice_portrait_edit, "图片文件 (*.png *.jpg *.jpeg *.bmp)", "resources/portraits"), lambda: self._clear_field(self.choice_portrait_edit, "set_portrait"), "选择立绘")
        info_form.addRow("立绘", choice_portrait_row)

        self.choice_hide_chk = QCheckBox("隐藏文本框")
        self.choice_hide_chk.stateChanged.connect(self._on_choice_info_changed)
        info_form.addRow("", self.choice_hide_chk)

        self.choice_portrait_fade_chk = QCheckBox("立绘淡入")
        self.choice_portrait_fade_chk.stateChanged.connect(self._on_choice_info_changed)
        info_form.addRow("", self.choice_portrait_fade_chk)

        layout.addLayout(info_form)
        return page

    def _build_condition_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        self.cond_var_edit = QLineEdit()
        self.cond_var_edit.editingFinished.connect(self._on_condition_var_changed)
        form.addRow("变量名", self.cond_var_edit)

        self.cond_op_combo = QComboBox()
        self.cond_op_combo.addItems(["==", "!=", ">", ">=", "<", "<="])
        self.cond_op_combo.currentIndexChanged.connect(self._on_condition_op_changed)
        form.addRow("运算符", self.cond_op_combo)

        self.cond_value_edit = QLineEdit()
        self.cond_value_edit.editingFinished.connect(self._on_condition_value_changed)
        form.addRow("变量/常量", self.cond_value_edit)

        self.cond_const_chk = QCheckBox("右侧为常量")
        self.cond_const_chk.stateChanged.connect(self._on_condition_const_changed)
        form.addRow("", self.cond_const_chk)

        # 供条件节点展示的基本文本/立绘信息
        self.cond_speaker_edit = QLineEdit()
        self.cond_speaker_edit.editingFinished.connect(self._on_cond_info_changed)
        form.addRow("角色", self.cond_speaker_edit)

        self.cond_text_edit = QPlainTextEdit()
        self.cond_text_edit.textChanged.connect(self._on_cond_info_changed)
        form.addRow("文本", self.cond_text_edit)

        self.cond_voice_edit = QLineEdit()
        cond_voice_row = self._make_file_row(self.cond_voice_edit, lambda: self._pick_generic_media(self.cond_voice_edit, "音频文件 (*.mp3 *.ogg *.wav)", "resources/voices"), lambda: self._clear_field(self.cond_voice_edit, "set_voice"), "选择语音")
        form.addRow("语音", cond_voice_row)

        self.cond_portrait_edit = QLineEdit()
        cond_portrait_row = self._make_file_row(self.cond_portrait_edit, lambda: self._pick_generic_media(self.cond_portrait_edit, "图片文件 (*.png *.jpg *.jpeg *.bmp)", "resources/portraits"), lambda: self._clear_field(self.cond_portrait_edit, "set_portrait"), "选择立绘")
        form.addRow("立绘", cond_portrait_row)

        self.cond_hide_chk = QCheckBox("隐藏文本框")
        self.cond_hide_chk.stateChanged.connect(self._on_cond_info_changed)
        form.addRow("", self.cond_hide_chk)

        self.cond_portrait_fade_chk = QCheckBox("立绘淡入")
        self.cond_portrait_fade_chk.stateChanged.connect(self._on_cond_info_changed)
        form.addRow("", self.cond_portrait_fade_chk)

        target_row = QVBoxLayout()
        self.cond_true_label = QLabel("真分支: -")
        self.cond_false_label = QLabel("假分支: -")
        self.cond_swap_btn = QPushButton("交换真/假目标")
        self.cond_swap_btn.clicked.connect(self._on_swap_condition_targets)
        target_row.addWidget(self.cond_true_label)
        target_row.addWidget(self.cond_false_label)
        target_row.addWidget(self.cond_swap_btn)
        form.addRow("分支目标", target_row)

        return page

    def _build_panel_media(self, parent_layout):
        group = QGroupBox("面板三：媒体配置")
        form = QFormLayout(group)
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

        parent_layout.addWidget(group)

    def _build_panel_ui(self, parent_layout):
        group = QGroupBox("面板四：UI设计文件")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.ui_file_edit = QLineEdit()
        ui_row = self._make_file_row(self.ui_file_edit, self._on_pick_ui_file, lambda: self._clear_field(self.ui_file_edit, "set_ui_file"), "选择 .json")
        form.addRow("UI文件", ui_row)
        parent_layout.addWidget(group)

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
        self._set_type_index(node_type)

        self._load_sub_dialogues(getattr(node, "sub_dialogues", []))
        self._load_options(getattr(node, "options", []))
        self.cond_var_edit.setText(getattr(node, "condition_var", ""))
        self.cond_value_edit.setText(getattr(node, "condition_value", ""))
        self.cond_op_combo.setCurrentText(getattr(node, "condition_op", "=="))
        self.cond_const_chk.setChecked(bool(getattr(node, "condition_const", False)))
        self._load_var_ops(getattr(node, "var_ops", []))
        self.bg_edit.setText(getattr(node, "background", ""))
        self.bgm_edit.setText(getattr(node, "bgm", ""))
        self.video_edit.setText(getattr(node, "video", ""))
        self.video_loop_chk.setChecked(bool(getattr(node, "video_loop", False)))
        self.stop_bgm_chk.setChecked(bool(getattr(node, "stop_bgm", False)))
        self.bgm_loop_chk.setChecked(bool(getattr(node, "bgm_loop", True)))
        self.bg_fade_in_chk.setChecked(bool(getattr(node, "bg_fade_in", False)))
        self.ui_file_edit.setText(getattr(node, "ui_file", ""))

        # 选择/条件节点显示信息
        self.choice_speaker_edit.setText(getattr(node, "speaker", ""))
        self.choice_text_edit.setPlainText(getattr(node, "content", ""))
        self.choice_voice_edit.setText(getattr(node, "voice", ""))
        self.choice_portrait_edit.setText(getattr(node, "portrait", ""))
        self.choice_hide_chk.setChecked(bool(getattr(node, "hide_textbox", False)))
        self.choice_portrait_fade_chk.setChecked(bool(getattr(node, "portrait_fade", False)))

        self.cond_speaker_edit.setText(getattr(node, "speaker", ""))
        self.cond_text_edit.setPlainText(getattr(node, "content", ""))
        self.cond_voice_edit.setText(getattr(node, "voice", ""))
        self.cond_portrait_edit.setText(getattr(node, "portrait", ""))
        self.cond_hide_chk.setChecked(bool(getattr(node, "hide_textbox", False)))
        self.cond_portrait_fade_chk.setChecked(bool(getattr(node, "portrait_fade", False)))

        self._update_condition_targets()

        self._updating = False
        self._update_content_stack()
        self._update_add_button_state()

    def set_project_dir(self, project_dir: Path | None):
        self._project_dir = project_dir

    def _reset_all_fields(self):
        self.title_edit.setText("")
        self.type_combo.setCurrentIndex(0)
        self._load_sub_dialogues([])
        self._load_options([])
        self._load_var_ops([])
        self.cond_var_edit.setText("")
        self.cond_value_edit.setText("")
        self.cond_op_combo.setCurrentIndex(0)
        self.cond_const_chk.setChecked(False)
        self.bg_edit.setText("")
        self.bgm_edit.setText("")
        self.video_edit.setText("")
        self.video_loop_chk.setChecked(False)
        self.stop_bgm_chk.setChecked(False)
        self.bgm_loop_chk.setChecked(True)
        self.bg_fade_in_chk.setChecked(False)
        self.ui_file_edit.setText("")
        self.choice_speaker_edit.setText("")
        self.choice_text_edit.setPlainText("")
        self.choice_voice_edit.setText("")
        self.choice_portrait_edit.setText("")
        self.choice_hide_chk.setChecked(False)
        self.choice_portrait_fade_chk.setChecked(False)
        self.cond_speaker_edit.setText("")
        self.cond_text_edit.setPlainText("")
        self.cond_voice_edit.setText("")
        self.cond_portrait_edit.setText("")
        self.cond_hide_chk.setChecked(False)
        self.cond_portrait_fade_chk.setChecked(False)
        self.cond_true_label.setText("真分支: -")
        self.cond_false_label.setText("假分支: -")
        self.cond_swap_btn.setEnabled(False)
        if hasattr(self, "option_text_edit"):
            self.option_text_edit.setText("")
        if hasattr(self, "option_target_label"):
            self.option_target_label.setText("对应下游节点：未连接")
            self.option_target_label.setStyleSheet("color: #666; font-style: italic;")

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
            self.sub_portrait_edit,
            self.sub_hide_chk,
            self.sub_fade_chk,
            self.sub_fade_out_chk,
            self.option_list,
            self.add_option_btn,
            self.del_option_btn,
            self.up_option_btn,
            self.down_option_btn,
            self.option_text_edit,
            self.cond_var_edit,
            self.cond_value_edit,
            self.cond_op_combo,
            self.cond_const_chk,
            self.bg_edit,
            self.bgm_edit,
            self.video_edit,
            self.video_loop_chk,
            self.ui_file_edit,
            self.stop_bgm_chk,
            self.bgm_loop_chk,
            self.bg_fade_in_chk,
            self.choice_speaker_edit,
            self.choice_text_edit,
            self.choice_voice_edit,
            self.choice_portrait_edit,
            self.choice_hide_chk,
            self.choice_portrait_fade_chk,
            self.cond_speaker_edit,
            self.cond_text_edit,
            self.cond_voice_edit,
            self.cond_portrait_edit,
            self.cond_hide_chk,
            self.cond_portrait_fade_chk,
            self.var_op_list,
            self.add_var_op_btn,
            self.edit_var_op_btn,
            self.del_var_op_btn,
        ]:
            widget.setEnabled(enabled)

    # ------- 子对话操作 -------
    def _load_sub_dialogues(self, items: list[dict]):
        self._sub_dialogues = []
        if isinstance(items, list):
            for item in items[: self.MAX_SUB_DIALOGUES]:
                if isinstance(item, dict):
                    self._sub_dialogues.append(
                        {
                            "speaker": item.get("speaker", ""),
                            "text": item.get("text", ""),
                            "voice": item.get("voice", ""),
                            "portrait": item.get("portrait", ""),
                            "hide_textbox": bool(item.get("hide_textbox", False)),
                            "portrait_fade": bool(item.get("portrait_fade", False)),
                            "portrait_fade_out": bool(item.get("portrait_fade_out", False)),
                        }
                    )
        self._refresh_sub_list(select_index=0 if self._sub_dialogues else -1)

    # ------- 选择节点选项操作 -------
    def _load_options(self, items: list[str]):
        self._options = []
        if isinstance(items, list):
            self._options = [str(opt) for opt in items if isinstance(opt, str)]
        self._refresh_option_list(select_index=0 if self._options else -1)

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
        if self._current_node and hasattr(self._current_node, "set_var_ops") and not self._updating:
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
        new_idx = min(row, len(self._options) - 1)
        self._refresh_option_list(select_index=new_idx)
        self._commit_options()

    def _on_move_option_up(self):
        row = self.option_list.currentRow()
        if row <= 0:
            return
        self._options[row - 1], self._options[row] = self._options[row], self._options[row - 1]
        self._refresh_option_list(select_index=row - 1)
        self._commit_options()

    def _on_move_option_down(self):
        row = self.option_list.currentRow()
        if row < 0 or row >= len(self._options) - 1:
            return
        self._options[row + 1], self._options[row] = self._options[row], self._options[row + 1]
        self._refresh_option_list(select_index=row + 1)
        self._commit_options()

    def _commit_options(self):
        if self._current_node and hasattr(self._current_node, "set_options") and not self._updating:
            self._current_node.set_options(list(self._options))

    def set_graph_view(self, graph_view):
        self._graph_view = graph_view

    def _target_display(self, node) -> str:
        if not node:
            return "-"
        title = getattr(node, "_title", "") or getattr(node, "title", "")
        name_part = f" {title}" if title else ""
        return f"{getattr(node, 'node_id', '-')}" + name_part

    def _update_condition_targets(self):
        if not self._graph_view or not self._current_node or getattr(self._current_node, "node_type", "text") != "condition":
            self.cond_true_label.setText("真分支: -")
            self.cond_false_label.setText("假分支: -")
            self.cond_swap_btn.setEnabled(False)
            return
        targets = self._graph_view.get_outgoing_targets(self._current_node)
        true_target = self._target_display(targets[0]) if len(targets) >= 1 else "<未连接>"
        false_target = self._target_display(targets[1]) if len(targets) >= 2 else "<未连接>"
        self.cond_true_label.setText(f"真分支: {true_target}")
        self.cond_false_label.setText(f"假分支: {false_target}")
        self.cond_swap_btn.setEnabled(len(targets) >= 2)

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
        if item.get("portrait_fade"):
            flags.append("淡入")
        flag_str = f" ({', '.join(flags)})" if flags else ""
        return f"{idx + 1}. {speaker} | {text_preview}{flag_str}"

    def _update_add_button_state(self):
        self.add_sub_btn.setEnabled(len(self._sub_dialogues) < self.MAX_SUB_DIALOGUES)

    def _on_add_sub(self):
        if len(self._sub_dialogues) >= self.MAX_SUB_DIALOGUES:
            self._update_add_button_state()
            return
        self._sub_dialogues.append(
            {"speaker": "", "text": "", "voice": "", "portrait": "", "hide_textbox": False, "portrait_fade": False, "portrait_fade_out": False}
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
        copied = {
            "speaker": src.get("speaker", ""),
            "text": src.get("text", ""),
            "voice": src.get("voice", ""),
            "portrait": src.get("portrait", ""),
            "hide_textbox": bool(src.get("hide_textbox", False)),
            "portrait_fade": bool(src.get("portrait_fade", False)),
            "portrait_fade_out": bool(src.get("portrait_fade_out", False)),
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

    def _update_sub_detail_fields(self, row: int):
        self._sub_editing = True
        if row is None or row < 0 or row >= len(self._sub_dialogues):
            self.sub_speaker_edit.setText("")
            self.sub_text_edit.setPlainText("")
            self.sub_voice_edit.setText("")
            self.sub_portrait_edit.setText("")
            self.sub_hide_chk.setChecked(False)
            self.sub_fade_chk.setChecked(False)
            self.sub_fade_out_chk.setChecked(False)
            detail_enabled = False
        else:
            item = self._sub_dialogues[row]
            self.sub_speaker_edit.setText(item.get("speaker", ""))
            self.sub_text_edit.setPlainText(item.get("text", ""))
            self.sub_voice_edit.setText(item.get("voice", ""))
            self.sub_portrait_edit.setText(item.get("portrait", ""))
            self.sub_hide_chk.setChecked(bool(item.get("hide_textbox", False)))
            self.sub_fade_chk.setChecked(bool(item.get("portrait_fade", False)))
            self.sub_fade_out_chk.setChecked(bool(item.get("portrait_fade_out", False)))
            detail_enabled = True
        for widget in [
            self.sub_speaker_edit,
            self.sub_text_edit,
            self.sub_voice_edit,
            self.sub_portrait_edit,
            self.sub_hide_chk,
            self.sub_fade_chk,
            self.sub_fade_out_chk,
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
        item["portrait"] = self.sub_portrait_edit.text()
        item["hide_textbox"] = bool(self.sub_hide_chk.isChecked())
        item["portrait_fade"] = bool(self.sub_fade_chk.isChecked())
        item["portrait_fade_out"] = bool(self.sub_fade_out_chk.isChecked())
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
        idx = self.type_combo.currentIndex()
        self.content_stack.setCurrentIndex(idx)

    def _on_options_changed(self):
        # legacy handler (no-op with new list UI)
        return

    def _on_condition_var_changed(self):
        if not self._current_node or self._updating:
            return
        text = self.cond_var_edit.text()
        if hasattr(self._current_node, "set_condition_var"):
            self._current_node.set_condition_var(text)

    def _on_condition_op_changed(self):
        if not self._current_node or self._updating:
            return
        op = self.cond_op_combo.currentText()
        if hasattr(self._current_node, "set_condition_op"):
            self._current_node.set_condition_op(op)

    def _on_condition_value_changed(self):
        if not self._current_node or self._updating:
            return
        text = self.cond_value_edit.text()
        if hasattr(self._current_node, "set_condition_value"):
            self._current_node.set_condition_value(text)

    def _on_condition_const_changed(self, _state):
        if not self._current_node or self._updating:
            return
        if hasattr(self._current_node, "set_condition_const"):
            self._current_node.set_condition_const(bool(self.cond_const_chk.isChecked()))

    def _on_choice_info_changed(self):
        if not self._current_node or self._updating:
            return
        if hasattr(self._current_node, "set_speaker"):
            self._current_node.set_speaker(self.choice_speaker_edit.text())
        if hasattr(self._current_node, "set_content"):
            self._current_node.set_content(self.choice_text_edit.toPlainText())
        if hasattr(self._current_node, "set_voice"):
            self._current_node.set_voice(self.choice_voice_edit.text())
        if hasattr(self._current_node, "set_portrait"):
            self._current_node.set_portrait(self.choice_portrait_edit.text())
        if hasattr(self._current_node, "set_hide_textbox"):
            self._current_node.set_hide_textbox(bool(self.choice_hide_chk.isChecked()))
        if hasattr(self._current_node, "set_portrait_fade"):
            self._current_node.set_portrait_fade(bool(self.choice_portrait_fade_chk.isChecked()))

    def _on_cond_info_changed(self):
        if not self._current_node or self._updating:
            return
        if hasattr(self._current_node, "set_speaker"):
            self._current_node.set_speaker(self.cond_speaker_edit.text())
        if hasattr(self._current_node, "set_content"):
            self._current_node.set_content(self.cond_text_edit.toPlainText())
        if hasattr(self._current_node, "set_voice"):
            self._current_node.set_voice(self.cond_voice_edit.text())
        if hasattr(self._current_node, "set_portrait"):
            self._current_node.set_portrait(self.cond_portrait_edit.text())
        if hasattr(self._current_node, "set_hide_textbox"):
            self._current_node.set_hide_textbox(bool(self.cond_hide_chk.isChecked()))
        if hasattr(self._current_node, "set_portrait_fade"):
            self._current_node.set_portrait_fade(bool(self.cond_portrait_fade_chk.isChecked()))

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

    def _set_type_index(self, node_type: str):
        idx = {"text": 0, "choice": 1, "condition": 2}.get(node_type, 0)
        self.type_combo.setCurrentIndex(idx)

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
        if target_edit in (getattr(self, "choice_voice_edit", None), getattr(self, "choice_portrait_edit", None)):
            self._on_choice_info_changed()
        elif target_edit in (getattr(self, "cond_voice_edit", None), getattr(self, "cond_portrait_edit", None)):
            self._on_cond_info_changed()
        elif target_edit in (getattr(self, "sub_voice_edit", None), getattr(self, "sub_portrait_edit", None)):
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

