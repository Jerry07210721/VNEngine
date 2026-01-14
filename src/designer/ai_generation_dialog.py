# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - AI游戏生成对话框
用于在Designer主界面启动AI自动生成游戏的UI
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QSpinBox, QComboBox, QTextEdit,
    QPushButton, QProgressBar, QGroupBox, 
    QFormLayout, QFileDialog, QMessageBox, QTabWidget, QCheckBox, QScrollArea, QWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from typing import Dict, Any, Optional
import os
from pathlib import Path


class AIGenerationThread(QThread):
    """AI生成工作线程"""
    progress_updated = pyqtSignal(float, str)  # 进度, 状态信息
    generation_completed = pyqtSignal(bool, str, dict)  # 成功, 消息, 结果数据
    
    def __init__(self, generation_params: Dict[str, Any]):
        super().__init__()
        self.generation_params = generation_params
    
    def run(self):
        """执行AI生成任务"""
        try:
            from src.multi_agent.core.story_master_agent import StoryMasterAgent
            from src.multi_agent.core.signal_bus import SignalBus
            
            # 创建信号总线
            signal_bus = SignalBus()
            
            # 连接进度信号
            signal_bus.progress_updated.connect(self._on_progress)
            
            # 创建StoryMasterAgent
            master_agent = StoryMasterAgent()
            
            # 执行生成
            result = master_agent.run(self.generation_params)
            
            # 清理资源
            master_agent.close()
            
            if result.success:
                self.generation_completed.emit(True, "游戏生成完成！", result.data or {})
            else:
                self.generation_completed.emit(False, f"生成失败：{result.error_msg}", {})
        
        except Exception as e:
            self.generation_completed.emit(False, f"生成异常：{str(e)}", {})
    
    def _on_progress(self, agent_id: str, progress: float, message: str):
        """处理进度更新"""
        self.progress_updated.emit(progress, message)


class AIGenerationDialog(QDialog):
    """AI游戏生成对话框"""
    
    generation_completed = pyqtSignal(str)  # 完成后发射工程文件路径
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI游戏生成")
        self.resize(800, 700)
        
        self.generation_thread: Optional[AIGenerationThread] = None
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        
        # 标签栏
        tab_widget = QTabWidget()
        
        # 基础设置标签页
        basic_tab = self._create_basic_settings_tab()
        tab_widget.addTab(basic_tab, "基础设置")
        
        # API配置标签页
        api_tab = self._create_api_settings_tab()
        tab_widget.addTab(api_tab, "API配置")
        
        layout.addWidget(tab_widget)
        
        # 进度条
        progress_group = QGroupBox("生成进度")
        progress_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.status_label)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("开始生成")
        self.start_btn.clicked.connect(self._on_start_generation)
        button_layout.addWidget(self.start_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        
        # 初始化控件状态
        self._on_portrait_toggle(2)     # 默认启用立绘
        self._on_background_toggle(2)   # 默认启用背景/CG
        self._on_tts_toggle(0)          # 默认禁用
        self._on_music_toggle(0)        # 默认禁用
    
    def _create_basic_settings_tab(self) -> QScrollArea:
        """创建基础设置标签页"""
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        # 内容容器
        widget = QWidget()
        layout = QFormLayout()
        
        # 游戏名称
        self.game_name_edit = QLineEdit()
        self.game_name_edit.setPlaceholderText("例如：夏日回忆")
        layout.addRow("游戏名称*:", self.game_name_edit)
        
        # 游戏主题
        self.game_theme_edit = QLineEdit()
        self.game_theme_edit.setPlaceholderText("例如：青春校园恋爱")
        layout.addRow("游戏主题*:", self.game_theme_edit)
        
        # 游戏简介
        self.game_desc_edit = QTextEdit()
        self.game_desc_edit.setPlaceholderText("请描述游戏的故事背景、氛围、主要冲突等...")
        self.game_desc_edit.setMaximumHeight(100)
        layout.addRow("游戏简介:", self.game_desc_edit)
        
        # 角色数量
        self.char_count_spin = QSpinBox()
        self.char_count_spin.setRange(2, 10)
        self.char_count_spin.setValue(3)
        layout.addRow("角色数量:", self.char_count_spin)
        
        # 剧情长度
        self.script_length_combo = QComboBox()
        self.script_length_combo.addItems(["短篇(20-30节点)", "中篇(40-60节点)", "长篇(80-120节点)"])
        self.script_length_combo.setCurrentIndex(1)
        layout.addRow("剧情长度:", self.script_length_combo)
        
        # 分支数量
        self.branch_count_spin = QSpinBox()
        self.branch_count_spin.setRange(0, 5)
        self.branch_count_spin.setValue(2)
        layout.addRow("分支数量:", self.branch_count_spin)
        
        # 剧情风格
        self.style_combo = QComboBox()
        self.style_combo.addItems(["轻松欢快", "悬疑推理", "恐怖惊悚", "励志成长", "奇幻冒险"])
        layout.addRow("剧情风格:", self.style_combo)
        
        # 保存路径
        path_layout = QHBoxLayout()
        self.save_path_edit = QLineEdit()
        self.save_path_edit.setPlaceholderText("选择工程保存路径")
        path_layout.addWidget(self.save_path_edit)
        
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._on_browse_path)
        path_layout.addWidget(browse_btn)
        
        layout.addRow("保存路径*:", path_layout)
        
        widget.setLayout(layout)
        scroll_area.setWidget(widget)
        return scroll_area
    
    def _create_api_settings_tab(self) -> QScrollArea:
        """创建 API配置标签页"""
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        # 内容容器
        widget = QWidget()
        layout = QFormLayout()
        
        # LLM配置
        llm_group = QGroupBox("LLM配置（用于剧情生成）")
        llm_layout = QFormLayout()
        
        self.llm_model_combo = QComboBox()
        self.llm_model_combo.addItems(["gpt-4o", "deepseek-chat", "claude-3-5-sonnet", "qwen-max"])
        llm_layout.addRow("模型:", self.llm_model_combo)
        
        self.llm_key_edit = QLineEdit()
        self.llm_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.llm_key_edit.setPlaceholderText("输入LLM API Key")
        llm_layout.addRow("API Key*:", self.llm_key_edit)
        
        self.llm_url_edit = QLineEdit()
        self.llm_url_edit.setText("https://llm-api.mmchat.xyz/v1")
        self.llm_url_edit.setPlaceholderText("MetaChat代理地址")
        llm_layout.addRow("Base URL:", self.llm_url_edit)
        
        llm_group.setLayout(llm_layout)
        layout.addRow(llm_group)
        
        # 立绘生成配置
        portrait_group = QGroupBox("立绘生成配置（用于角色立绘，可选）")
        portrait_layout = QFormLayout()
        
        self.enable_portrait_check = QCheckBox("启用立绘生成")
        self.enable_portrait_check.setChecked(True)
        self.enable_portrait_check.stateChanged.connect(self._on_portrait_toggle)
        portrait_layout.addRow("", self.enable_portrait_check)
        
        self.portrait_provider_combo = QComboBox()
        self.portrait_provider_combo.addItems(["FLUX (推荐-MetaChat)", "SDXL", "通义万相"])
        portrait_layout.addRow("模型:", self.portrait_provider_combo)
        
        self.portrait_key_edit = QLineEdit()
        self.portrait_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.portrait_key_edit.setPlaceholderText("输入API Key")
        portrait_layout.addRow("API Key:", self.portrait_key_edit)
        
        self.portrait_app_id_edit = QLineEdit()
        self.portrait_app_id_edit.setPlaceholderText("FLUX/MidJourney需要填写App ID")
        portrait_layout.addRow("App ID:", self.portrait_app_id_edit)
        
        self.portrait_url_edit = QLineEdit()
        self.portrait_url_edit.setText("https://api.mmchat.xyz/open/v1")
        self.portrait_url_edit.setPlaceholderText("MetaChat代理地址")
        portrait_layout.addRow("Base URL:", self.portrait_url_edit)
        
        portrait_group.setLayout(portrait_layout)
        layout.addRow(portrait_group)
        
        # 背景/CG生成配置
        background_group = QGroupBox("背景/CG生成配置（用于场景背景和CG，可选）")
        background_layout = QFormLayout()
        
        self.enable_background_check = QCheckBox("启用背景/CG生成")
        self.enable_background_check.setChecked(True)
        self.enable_background_check.stateChanged.connect(self._on_background_toggle)
        background_layout.addRow("", self.enable_background_check)
        
        self.background_provider_combo = QComboBox()
        self.background_provider_combo.addItems(["FLUX (推荐-MetaChat)", "SDXL", "通义万相", "MidJourney (高质量)"])
        background_layout.addRow("模型:", self.background_provider_combo)
        
        self.background_key_edit = QLineEdit()
        self.background_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.background_key_edit.setPlaceholderText("输入API Key（可与立绘共用）")
        background_layout.addRow("API Key:", self.background_key_edit)
        
        self.background_app_id_edit = QLineEdit()
        self.background_app_id_edit.setPlaceholderText("FLUX/MidJourney需要填写App ID")
        background_layout.addRow("App ID:", self.background_app_id_edit)
        
        self.background_url_edit = QLineEdit()
        self.background_url_edit.setText("https://api.mmchat.xyz/open/v1")
        self.background_url_edit.setPlaceholderText("MetaChat代理地址")
        background_layout.addRow("Base URL:", self.background_url_edit)
        
        background_group.setLayout(background_layout)
        layout.addRow(background_group)
        
        # TTS配置
        tts_group = QGroupBox("TTS配置（用于角色配音，可选）")
        tts_layout = QFormLayout()
        
        self.enable_tts_check = QCheckBox("启用语音合成")
        self.enable_tts_check.setChecked(False)
        self.enable_tts_check.stateChanged.connect(self._on_tts_toggle)
        tts_layout.addRow("", self.enable_tts_check)
        
        self.tts_provider_combo = QComboBox()
        self.tts_provider_combo.addItems(["GPT-SoVITS (推荐)", "Bert-VITS2", "Azure TTS", "OpenAI TTS", "阿里云TTS"])
        tts_layout.addRow("服务商:", self.tts_provider_combo)
        
        self.tts_key_edit = QLineEdit()
        self.tts_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.tts_key_edit.setPlaceholderText("输入TTS API Key（本地部署可留空）")
        tts_layout.addRow("API Key:", self.tts_key_edit)
        
        self.tts_url_edit = QLineEdit()
        self.tts_url_edit.setPlaceholderText("GPT-SoVITS: http://127.0.0.1:9880")
        tts_layout.addRow("Base URL:", self.tts_url_edit)
        
        self.tts_region_edit = QLineEdit()
        self.tts_region_edit.setText("eastus")
        self.tts_region_edit.setPlaceholderText("Azure需要，如eastus")
        tts_layout.addRow("Region:", self.tts_region_edit)
        
        tts_group.setLayout(tts_layout)
        layout.addRow(tts_group)
        
        # 音乐生成配置
        music_group = QGroupBox("音乐生成配置（用于BGM，可选）")
        music_layout = QFormLayout()
        
        self.enable_music_check = QCheckBox("启用BGM生成")
        self.enable_music_check.setChecked(False)
        self.enable_music_check.stateChanged.connect(self._on_music_toggle)
        music_layout.addRow("", self.enable_music_check)
        
        self.music_provider_combo = QComboBox()
        self.music_provider_combo.addItems(["Suno AI (推荐)", "MusicGen"])
        music_layout.addRow("服务商:", self.music_provider_combo)
        
        self.music_key_edit = QLineEdit()
        self.music_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.music_key_edit.setPlaceholderText("输入x-token（可选，不生成BGM可留空）")
        music_layout.addRow("x-token:", self.music_key_edit)
        
        self.music_user_id_edit = QLineEdit()
        self.music_user_id_edit.setPlaceholderText("输入x-userId（Suno代理需要）")
        music_layout.addRow("x-userId:", self.music_user_id_edit)
        
        self.music_url_edit = QLineEdit()
        self.music_url_edit.setText("https://dzwlai.com/apiuser")
        self.music_url_edit.setPlaceholderText("Suno4.cn国内代理地址")
        music_layout.addRow("Base URL:", self.music_url_edit)
        
        music_group.setLayout(music_layout)
        layout.addRow(music_group)
        
        # 提示信息
        tip_label = QLabel("提示：API Key会被加密存储在本地配置文件中")
        tip_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addRow(tip_label)
        
        widget.setLayout(layout)
        scroll_area.setWidget(widget)
        return scroll_area
    
    def _on_portrait_toggle(self, state):
        """切换立绘生成启用状态"""
        enabled = state == 2  # Qt.CheckState.Checked
        self.portrait_provider_combo.setEnabled(enabled)
        self.portrait_key_edit.setEnabled(enabled)
        self.portrait_app_id_edit.setEnabled(enabled)
        self.portrait_url_edit.setEnabled(enabled)
    
    def _on_background_toggle(self, state):
        """切换背景/CG生成启用状态"""
        enabled = state == 2
        self.background_provider_combo.setEnabled(enabled)
        self.background_key_edit.setEnabled(enabled)
        self.background_app_id_edit.setEnabled(enabled)
        self.background_url_edit.setEnabled(enabled)
    
    def _on_tts_toggle(self, state):
        """切换TTS启用状态"""
        enabled = state == 2
        self.tts_provider_combo.setEnabled(enabled)
        self.tts_key_edit.setEnabled(enabled)
        self.tts_url_edit.setEnabled(enabled)
        self.tts_region_edit.setEnabled(enabled)
    
    def _on_music_toggle(self, state):
        """切换音乐生成启用状态"""
        enabled = state == 2
        self.music_provider_combo.setEnabled(enabled)
        self.music_key_edit.setEnabled(enabled)
        self.music_user_id_edit.setEnabled(enabled)
        self.music_url_edit.setEnabled(enabled)
    
    def _on_browse_path(self):
        """浏览保存路径"""
        path = QFileDialog.getExistingDirectory(
            self,
            "选择工程保存目录",
            str(Path.home())
        )
        if path:
            self.save_path_edit.setText(path)
    
    def _on_start_generation(self):
        """开始生成"""
        # 校验必填项
        if not self.game_name_edit.text():
            QMessageBox.warning(self, "参数错误", "请输入游戏名称")
            return
        
        if not self.game_theme_edit.text():
            QMessageBox.warning(self, "参数错误", "请输入游戏主题")
            return
        
        if not self.save_path_edit.text():
            QMessageBox.warning(self, "参数错误", "请选择保存路径")
            return
        
        if not self.llm_key_edit.text():
            QMessageBox.warning(self, "参数错误", "请输入LLM API Key")
            return
        
        # 解析剧情长度
        script_length_map = {
            0: 25,  # 短篇
            1: 50,  # 中篇
            2: 100  # 长篇
        }
        script_length = script_length_map[self.script_length_combo.currentIndex()]
        
        # 构建生成参数
        generation_params = {
            "game_name": self.game_name_edit.text(),
            "game_theme": self.game_theme_edit.text(),
            "game_description": self.game_desc_edit.toPlainText(),
            "char_count": self.char_count_spin.value(),
            "script_length": script_length,
            "branch_count": self.branch_count_spin.value(),
            "script_style": self.style_combo.currentText(),
            "save_path": self.save_path_edit.text(),
            "api_configs": {
                "llm": {
                    "model": self.llm_model_combo.currentText(),
                    "api_key": self.llm_key_edit.text(),
                    "base_url": self.llm_url_edit.text() or None
                }
            }
        }
        
        # 添加立绘生成配置（根据复选框状态）
        if self.enable_portrait_check.isChecked() and self.portrait_key_edit.text():
            provider_map = {
                "FLUX (推荐-MetaChat)": "flux",
                "SDXL": "sdxl",
                "通义万相": "tongyi"
            }
            generation_params["api_configs"]["portrait"] = {
                "provider": provider_map[self.portrait_provider_combo.currentText()],
                "api_key": self.portrait_key_edit.text(),
                "app_id": self.portrait_app_id_edit.text() or None,
                "base_url": self.portrait_url_edit.text() or None
            }
        
        # 添加背景/CG生成配置（根据复选框状态）
        if self.enable_background_check.isChecked() and self.background_key_edit.text():
            provider_map = {
                "FLUX (推荐-MetaChat)": "flux",
                "SDXL": "sdxl",
                "通义万相": "tongyi",
                "MidJourney (高质量)": "midjourney"
            }
            generation_params["api_configs"]["background"] = {
                "provider": provider_map[self.background_provider_combo.currentText()],
                "api_key": self.background_key_edit.text(),
                "app_id": self.background_app_id_edit.text() or None,
                "base_url": self.background_url_edit.text() or None
            }
        
        # 添加TTS配置（根据复选框状态）
        if self.enable_tts_check.isChecked() and (self.tts_key_edit.text() or self.tts_url_edit.text()):
            provider_map = {
                "GPT-SoVITS (推荐)": "gpt_sovits",
                "Bert-VITS2": "bert_vits2",
                "Azure TTS": "azure",
                "OpenAI TTS": "openai",
                "阿里云TTS": "aliyun"
            }
            generation_params["api_configs"]["tts"] = {
                "provider": provider_map[self.tts_provider_combo.currentText()],
                "api_key": self.tts_key_edit.text() or "",
                "base_url": self.tts_url_edit.text() or None,
                "region": self.tts_region_edit.text() or "eastus"
            }
        
        # 添加音乐生成配置（根据复选框状态）
        if self.enable_music_check.isChecked() and self.music_key_edit.text():
            provider_map = {
                "Suno AI (推荐)": "suno",
                "MusicGen": "musicgen"
            }
            generation_params["api_configs"]["music"] = {
                "provider": provider_map[self.music_provider_combo.currentText()],
                "api_key": self.music_key_edit.text(),
                "user_id": self.music_user_id_edit.text() or "default_user",
                "base_url": self.music_url_edit.text() or None
            }
        
        # 禁用按钮
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        
        # 创建并启动生成线程
        self.generation_thread = AIGenerationThread(generation_params)
        self.generation_thread.progress_updated.connect(self._on_progress_updated)
        self.generation_thread.generation_completed.connect(self._on_generation_completed)
        self.generation_thread.start()
    
    def _on_progress_updated(self, progress: float, message: str):
        """更新进度"""
        self.progress_bar.setValue(int(progress * 100))
        self.status_label.setText(message)
    
    def _on_generation_completed(self, success: bool, message: str, result_data: Dict[str, Any]):
        """生成完成"""
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        
        if success:
            QMessageBox.information(self, "生成完成", message)
            
            # 发射完成信号（传递工程文件路径）
            project_file = result_data.get("project_file")
            if project_file:
                self.generation_completed.emit(project_file)
            
            self.accept()
        else:
            QMessageBox.critical(self, "生成失败", message)
            self.progress_bar.setValue(0)
            self.status_label.setText("生成失败")
