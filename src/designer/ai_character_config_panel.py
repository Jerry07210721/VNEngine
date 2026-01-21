# -*- coding: utf-8 -*-
"""
AI角色配置界面
"""

from pathlib import Path

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QWidget,
    QFileDialog,
    QMessageBox,
    QTextEdit,
    QCheckBox,
    QSplitter,
    QDialog,
)
from PyQt6.QtCore import Qt

from src.designer.ai_base_panel import AIBasePanelWidget
from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.config_manager import ConfigManager
from src.ai.core.models import CharacterConfig
from src.designer.voice_model_dialog import VoiceModelPickerDialog, get_gptsovits_client


class AICharacterConfigPanel(AIBasePanelWidget):
    """角色配置界面"""
    
    def __init__(self, project_manager: AIProjectManager, config_manager: ConfigManager | None = None, parent=None):
        super().__init__(project_manager, parent)
        self.config_manager = config_manager or ConfigManager()
        self.current_char_index = -1
        self.init_ui()
        
    def init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # 标题
        title_label = QLabel("角色配置")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        main_layout.addWidget(title_label)
        
        # 使用分割器：左侧角色列表，右侧编辑区
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # ========== 左侧：角色列表 ==========
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        list_label = QLabel("角色列表")
        list_label.setStyleSheet("font-weight: bold; color: #34495e;")
        left_layout.addWidget(list_label)
        
        self.char_list = QListWidget()
        self.char_list.currentRowChanged.connect(self.on_char_selected)
        left_layout.addWidget(self.char_list)
        
        # 列表操作按钮
        list_button_layout = QHBoxLayout()
        
        self.add_button = QPushButton("添加角色")
        self.add_button.clicked.connect(self.add_character)
        list_button_layout.addWidget(self.add_button)
        
        self.remove_button = QPushButton("删除")
        self.remove_button.clicked.connect(self.remove_character)
        self.remove_button.setEnabled(False)
        list_button_layout.addWidget(self.remove_button)
        
        left_layout.addLayout(list_button_layout)
        
        splitter.addWidget(left_widget)
        
        # ========== 右侧：角色编辑区 ==========
        self.edit_widget = QWidget()
        edit_layout = QVBoxLayout(self.edit_widget)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        
        # 基础信息组
        basic_group = QGroupBox("基础信息")
        basic_layout = QFormLayout()
        
        self.char_id_edit = QLineEdit()
        self.char_id_edit.setPlaceholderText("如：char_001")
        self.char_id_edit.textChanged.connect(self.on_char_data_changed)
        basic_layout.addRow("角色ID:", self.char_id_edit)
        
        self.char_name_edit = QLineEdit()
        self.char_name_edit.setPlaceholderText("如：林风")
        self.char_name_edit.textChanged.connect(self.on_char_data_changed)
        basic_layout.addRow("角色名称:", self.char_name_edit)
        
        self.role_edit = QLineEdit()
        self.role_edit.setPlaceholderText("如：男主角、女主角、配角")
        self.role_edit.textChanged.connect(self.on_char_data_changed)
        basic_layout.addRow("角色定位:", self.role_edit)
        
        basic_group.setLayout(basic_layout)
        edit_layout.addWidget(basic_group)
        
        # 特殊标识组
        flag_group = QGroupBox("特殊标识")
        flag_layout = QVBoxLayout()
        
        self.is_player_check = QCheckBox("玩家角色（第一视角的\"我\"）")
        self.is_player_check.stateChanged.connect(self.on_char_data_changed)
        flag_layout.addWidget(self.is_player_check)
        
        hint_label = QLabel("勾选后，该角色将作为第一人称视角")
        hint_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        flag_layout.addWidget(hint_label)
        
        flag_group.setLayout(flag_layout)
        edit_layout.addWidget(flag_group)
        
        # 人设关键词组
        persona_group = QGroupBox("人设关键词")
        persona_layout = QVBoxLayout()
        
        self.persona_edit = QTextEdit()
        self.persona_edit.setPlaceholderText(
            "请输入角色人设关键词，用于AI生成详细人设...\n\n"
            "示例：阳光、温柔、喜欢摄影、成绩中等、善良体贴"
        )
        self.persona_edit.setMaximumHeight(100)
        self.persona_edit.textChanged.connect(self.on_char_data_changed)
        persona_layout.addWidget(self.persona_edit)
        
        persona_group.setLayout(persona_layout)
        edit_layout.addWidget(persona_group)
        
        # 参考图片组
        ref_group = QGroupBox("参考图片（可选）")
        ref_layout = QHBoxLayout()
        
        self.ref_image_edit = QLineEdit()
        self.ref_image_edit.setPlaceholderText("选择参考图片路径...")
        self.ref_image_edit.setReadOnly(True)
        ref_layout.addWidget(self.ref_image_edit)
        
        self.browse_button = QPushButton("浏览...")
        self.browse_button.clicked.connect(self.browse_reference_image)
        ref_layout.addWidget(self.browse_button)
        
        self.clear_ref_button = QPushButton("清除")
        self.clear_ref_button.clicked.connect(self._clear_reference_image)
        ref_layout.addWidget(self.clear_ref_button)
        
        ref_group.setLayout(ref_layout)
        edit_layout.addWidget(ref_group)
        
        # 音色配置组
        voice_group = QGroupBox("音色配置")
        voice_layout = QFormLayout()
        
        self.voice_tone_edit = QLineEdit()
        self.voice_tone_edit.setPlaceholderText("如：青年、温和、中等语速")
        self.voice_tone_edit.textChanged.connect(self.on_char_data_changed)
        voice_layout.addRow("音色描述:", self.voice_tone_edit)
        
        self.voice_model_id_edit = QLineEdit()
        self.voice_model_id_edit.setPlaceholderText("GPT-SoVITS模型ID（可选）")
        self.voice_model_id_edit.textChanged.connect(self.on_char_data_changed)

        voice_btn_row = QHBoxLayout()
        voice_btn_row.addWidget(self.voice_model_id_edit)
        query_btn = QPushButton("查询模型ID")
        query_btn.clicked.connect(self.query_voice_model)
        voice_btn_row.addWidget(query_btn)
        voice_layout.addRow("音色模型ID:", voice_btn_row)
        
        voice_group.setLayout(voice_layout)
        edit_layout.addWidget(voice_group)
        
        # 弹性空间
        edit_layout.addStretch()
        
        # 保存按钮
        save_button_layout = QHBoxLayout()
        save_button_layout.addStretch()
        
        self.save_char_button = QPushButton("保存当前角色")
        self.save_char_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        self.save_char_button.clicked.connect(self.save_current_character)
        save_button_layout.addWidget(self.save_char_button)
        
        edit_layout.addLayout(save_button_layout)
        
        self.edit_widget.setEnabled(False)  # 默认禁用，选中角色后启用
        splitter.addWidget(self.edit_widget)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(splitter)
        
        # ========== 底部批量操作按钮 ==========
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        
        self.save_all_button = QPushButton("保存所有角色到工程")
        self.save_all_button.setStyleSheet("""
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
        """)
        self.save_all_button.clicked.connect(self.save_to_project)
        bottom_layout.addWidget(self.save_all_button)
        
        self.refresh_button = QPushButton("重新加载")
        self.refresh_button.clicked.connect(self.refresh)
        bottom_layout.addWidget(self.refresh_button)
        
        main_layout.addLayout(bottom_layout)

    def _set_form_signals_blocked(self, blocked: bool):
        widgets = [
            self.char_id_edit,
            self.char_name_edit,
            self.role_edit,
            self.is_player_check,
            self.persona_edit,
            self.ref_image_edit,
            self.voice_tone_edit,
            self.voice_model_id_edit,
        ]
        for w in widgets:
            try:
                w.blockSignals(blocked)
            except Exception:
                pass

    def _clear_reference_image(self):
        self.ref_image_edit.clear()
        self.on_char_data_changed()
        
    def add_character(self):
        """添加新角色"""
        char_count = self.char_list.count()
        char_id = f"char_{str(char_count + 1).zfill(3)}"
        char_name = f"新角色{char_count + 1}"
        
        # 创建新角色配置
        new_char = CharacterConfig(
            char_id=char_id,
            char_name=char_name,
            role="配角",
            persona_keywords="",
            is_player=False
        )
        
        # 添加到列表
        item = QListWidgetItem(f"{char_name} ({char_id})")
        item.setData(Qt.ItemDataRole.UserRole, new_char)
        self.char_list.addItem(item)
        
        # 选中新添加的角色
        self.char_list.setCurrentRow(self.char_list.count() - 1)
        
        self.mark_modified()
    
    def remove_character(self):
        """删除当前角色"""
        current_row = self.char_list.currentRow()
        if current_row < 0:
            return
        
        item = self.char_list.item(current_row)
        char = item.data(Qt.ItemDataRole.UserRole)
        
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除角色 {char.char_name} ({char.char_id}) 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.char_list.takeItem(current_row)
            self.edit_widget.setEnabled(False)
            self.remove_button.setEnabled(False)
            self.mark_modified()
    
    def on_char_selected(self, row):
        """角色列表选择变化"""
        if row < 0:
            self.edit_widget.setEnabled(False)
            self.remove_button.setEnabled(False)
            self.current_char_index = -1
            return
        
        self.current_char_index = row
        self.edit_widget.setEnabled(True)
        self.remove_button.setEnabled(True)
        
        # 加载角色数据到编辑区
        item = self.char_list.item(row)
        char = item.data(Qt.ItemDataRole.UserRole)

        # 阻止控件信号（避免加载时触发 on_char_data_changed 覆盖原数据）
        self._set_form_signals_blocked(True)
        
        self.char_id_edit.setText(char.char_id)
        self.char_name_edit.setText(char.char_name)
        self.role_edit.setText(char.role)
        self.is_player_check.setChecked(char.is_player)
        self.persona_edit.setPlainText(char.persona_keywords)
        self.ref_image_edit.setText(char.reference_image or "")
        self.voice_tone_edit.setText(char.voice_tone or "")
        self.voice_model_id_edit.setText(char.voice_model_id or "")

        self._set_form_signals_blocked(False)
    
    def on_char_data_changed(self):
        """角色数据改变"""
        if self.current_char_index < 0:
            return
        
        # 更新当前角色数据（但不立即保存到工程）
        self.save_current_character()
    
    def save_current_character(self):
        """保存当前编辑的角色到列表"""
        if self.current_char_index < 0:
            return
        
        item = self.char_list.item(self.current_char_index)
        char = item.data(Qt.ItemDataRole.UserRole)
        
        # 更新角色数据
        char.char_id = self.char_id_edit.text().strip()
        char.char_name = self.char_name_edit.text().strip()
        char.role = self.role_edit.text().strip()
        char.is_player = self.is_player_check.isChecked()
        char.persona_keywords = self.persona_edit.toPlainText().strip()
        char.reference_image = self.ref_image_edit.text().strip() or None
        char.voice_tone = self.voice_tone_edit.text().strip() or None
        char.voice_model_id = self.voice_model_id_edit.text().strip() or None
        
        # 更新列表显示
        item.setText(f"{char.char_name} ({char.char_id})")
        item.setData(Qt.ItemDataRole.UserRole, char)
        
        self.mark_modified()
    
    def browse_reference_image(self):
        """浏览参考图片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择参考图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp)"
        )
        
        if file_path:
            self.ref_image_edit.setText(file_path)
            self.on_char_data_changed()

    def query_voice_model(self):
        client = get_gptsovits_client(self.config_manager, self)
        if not client:
            return

        dlg = VoiceModelPickerDialog(client, self, allow_manage=False)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            audio_id = dlg.selected_audio_id()
            if audio_id:
                self.voice_model_id_edit.setText(str(audio_id))
    
    def refresh(self):
        """刷新界面，从工程加载数据"""
        self.char_list.clear()
        
        if self.project_manager.current_project:
            for char in self.project_manager.current_project.character_config:
                item = QListWidgetItem(f"{char.char_name} ({char.char_id})")
                item.setData(Qt.ItemDataRole.UserRole, char)
                self.char_list.addItem(item)
        
        self.edit_widget.setEnabled(False)
        self.remove_button.setEnabled(False)
    
    def save_to_project(self, silent: bool = False):
        """保存所有角色到工程

        Args:
            silent: 为 True 时不弹出“保存成功”提示框（用于主控面板自动同步）。
        """
        if not self.project_manager.current_project:
            QMessageBox.warning(self, "提示", "没有打开的工程")
            return
        
        # 收集所有角色
        chars = []
        for i in range(self.char_list.count()):
            item = self.char_list.item(i)
            char = item.data(Qt.ItemDataRole.UserRole)
            chars.append(char)
        
        # 更新到工程
        self.project_manager.update_character_config(chars)
        
        if not silent:
            QMessageBox.information(self, "成功", f"已保存 {len(chars)} 个角色到工程")
        self.mark_modified()
