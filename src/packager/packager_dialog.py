# -*- coding: utf-8 -*-
"""
打包配置对话框 - 提供图形化界面配置打包参数
"""
from pathlib import Path
from typing import Dict

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QCheckBox,
    QPushButton,
    QFileDialog,
    QGroupBox,
    QLabel,
    QTextEdit,
    QMessageBox,
    QSpinBox,
    QComboBox,
)
from PyQt6.QtCore import Qt


class PackagerDialog(QDialog):
    """打包配置对话框"""

    def __init__(self, project_dir: Path, config: Dict, packager_manager, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
        self.config = config.copy()
        self.packager_manager = packager_manager
        
        self.setWindowTitle("打包配置")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        
        self._init_ui()
        self._load_config_to_ui()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        
        # 基本信息组
        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout()
        
        self.app_name_edit = QLineEdit()
        self.app_name_edit.setPlaceholderText("游戏可执行文件名")
        basic_layout.addRow("应用名称:", self.app_name_edit)
        
        self.version_edit = QLineEdit()
        self.version_edit.setPlaceholderText("1.0.0")
        basic_layout.addRow("版本号:", self.version_edit)
        
        self.author_edit = QLineEdit()
        self.author_edit.setPlaceholderText("作者名称（可选）")
        basic_layout.addRow("作者:", self.author_edit)
        
        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText("游戏描述（可选）")
        basic_layout.addRow("描述:", self.description_edit)

        # 打包用 Python 解释器
        py_row = QHBoxLayout()
        self.python_path_edit = QLineEdit()
        self.python_path_edit.setPlaceholderText("优先使用项目旁的 venv_pack/venv1，如未填则自动探测")
        py_browse = QPushButton("浏览...")
        py_browse.clicked.connect(self._browse_python)
        py_clear = QPushButton("清除")
        py_clear.clicked.connect(lambda: self.python_path_edit.clear())
        py_row.addWidget(self.python_path_edit)
        py_row.addWidget(py_browse)
        py_row.addWidget(py_clear)
        basic_layout.addRow("Python路径:", py_row)
        
        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)
        
        # 图标选择
        icon_group = QGroupBox("应用图标")
        icon_layout = QHBoxLayout()
        
        self.icon_path_edit = QLineEdit()
        self.icon_path_edit.setPlaceholderText("选择.ico文件（可选）")
        self.icon_path_edit.setReadOnly(True)
        
        icon_browse_btn = QPushButton("浏览...")
        icon_browse_btn.clicked.connect(self._browse_icon)
        
        icon_clear_btn = QPushButton("清除")
        icon_clear_btn.clicked.connect(lambda: self.icon_path_edit.clear())
        
        icon_layout.addWidget(self.icon_path_edit)
        icon_layout.addWidget(icon_browse_btn)
        icon_layout.addWidget(icon_clear_btn)
        
        icon_group.setLayout(icon_layout)
        layout.addWidget(icon_group)
        
        # 打包选项组
        options_group = QGroupBox("打包选项")
        options_layout = QVBoxLayout()
        
        # 打包模式
        mode_layout = QHBoxLayout()
        mode_label = QLabel("打包模式:")
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("文件夹模式（推荐）", False)
        self.mode_combo.addItem("单文件模式", True)
        self.mode_combo.setToolTip(
            "文件夹模式：生成一个包含exe和资源的文件夹，启动快\n"
            "单文件模式：所有内容打包到单个exe，便于分发但启动稍慢"
        )
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        options_layout.addLayout(mode_layout)
        
        self.console_check = QCheckBox("显示控制台窗口（用于调试）")
        self.console_check.setToolTip("勾选后运行游戏时会显示黑色命令行窗口，可看到调试信息")
        options_layout.addWidget(self.console_check)
        
        self.clean_check = QCheckBox("打包前清理旧文件")
        self.clean_check.setToolTip("删除之前的build目录和spec文件")
        self.clean_check.setChecked(True)
        options_layout.addWidget(self.clean_check)
        
        self.resources_check = QCheckBox("包含资源文件")
        self.resources_check.setToolTip("自动包含resources、ui、saves等目录")
        self.resources_check.setChecked(True)
        options_layout.addWidget(self.resources_check)
        
        self.compression_check = QCheckBox("启用UPX压缩（如果可用）")
        self.compression_check.setToolTip("使用UPX压缩可执行文件，减小体积")
        self.compression_check.setChecked(True)
        options_layout.addWidget(self.compression_check)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # 高级选项组（可折叠）
        advanced_group = QGroupBox("高级选项（一般无需修改）")
        advanced_layout = QVBoxLayout()
        
        self.hidden_imports_edit = QTextEdit()
        self.hidden_imports_edit.setPlaceholderText("每行一个模块名，例如:\nmy_custom_module\nanother_module")
        self.hidden_imports_edit.setMaximumHeight(80)
        
        advanced_layout.addWidget(QLabel("隐藏导入（Hidden Imports）:"))
        advanced_layout.addWidget(self.hidden_imports_edit)
        
        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)
        
        # 说明文本
        info_label = QLabel(
            "💡 提示：\n"
            "• 打包需要安装PyInstaller (pip install pyinstaller)\n"
            "• 建议先在文件夹模式下测试，确认无误后再使用单文件模式\n"
            "• 打包时间取决于项目大小，一般需要1-5分钟\n"
            "• 首次打包建议启用控制台窗口，便于查看错误信息"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("QLabel { background-color: #f0f0f0; padding: 8px; border-radius: 4px; }")
        layout.addWidget(info_label)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        save_btn = QPushButton("保存配置")
        save_btn.clicked.connect(self._save_and_accept)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)

    def _load_config_to_ui(self):
        """从配置字典加载到UI控件"""
        self.app_name_edit.setText(self.config.get("app_name", "MyVNGame"))
        self.version_edit.setText(self.config.get("version", "1.0.0"))
        self.author_edit.setText(self.config.get("author", ""))
        self.description_edit.setText(self.config.get("description", ""))
        self.icon_path_edit.setText(self.config.get("icon_path", ""))

        # Python 路径
        self.python_path_edit.setText(self.config.get("python_path", ""))
        
        # 打包模式
        one_file = self.config.get("one_file", False)
        self.mode_combo.setCurrentIndex(1 if one_file else 0)
        
        self.console_check.setChecked(self.config.get("console", False))
        self.clean_check.setChecked(self.config.get("clean_before_build", True))
        self.resources_check.setChecked(self.config.get("include_resources", True))
        self.compression_check.setChecked(self.config.get("compression", True))
        
        # 隐藏导入
        hidden_imports = self.config.get("hidden_imports", [])
        if hidden_imports:
            self.hidden_imports_edit.setPlainText("\n".join(hidden_imports))

    def _save_and_accept(self):
        """保存UI配置到字典并关闭对话框"""
        # 验证必填项
        app_name = self.app_name_edit.text().strip()
        if not app_name:
            QMessageBox.warning(self, "验证失败", "应用名称不能为空！")
            self.app_name_edit.setFocus()
            return
        
        # 验证应用名称（不能包含特殊字符）
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        if any(c in app_name for c in invalid_chars):
            QMessageBox.warning(
                self,
                "验证失败",
                f"应用名称不能包含以下字符: {' '.join(invalid_chars)}"
            )
            self.app_name_edit.setFocus()
            return
        
        # 更新配置
        self.config["app_name"] = app_name
        self.config["version"] = self.version_edit.text().strip() or "1.0.0"
        self.config["author"] = self.author_edit.text().strip()
        self.config["description"] = self.description_edit.text().strip()
        self.config["icon_path"] = self.icon_path_edit.text().strip()
        self.config["python_path"] = self.python_path_edit.text().strip()
        
        # 打包选项
        self.config["one_file"] = self.mode_combo.currentData()
        self.config["console"] = self.console_check.isChecked()
        self.config["clean_before_build"] = self.clean_check.isChecked()
        self.config["include_resources"] = self.resources_check.isChecked()
        self.config["compression"] = self.compression_check.isChecked()
        
        # 隐藏导入
        hidden_text = self.hidden_imports_edit.toPlainText().strip()
        if hidden_text:
            self.config["hidden_imports"] = [
                line.strip() for line in hidden_text.split("\n")
                if line.strip()
            ]
        else:
            self.config["hidden_imports"] = []
        
        self.accept()

    def _browse_icon(self):
        """浏览选择图标文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择应用图标",
            str(self.project_dir),
            "图标文件 (*.ico);;所有文件 (*.*)"
        )
        if file_path:
            self.icon_path_edit.setText(file_path)

    def get_config(self) -> Dict:
        """获取配置字典"""
        return self.config

    def _browse_python(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择Python解释器",
            str(self.project_dir),
            "Python (python.exe);;所有文件 (*.*)"
        )
        if file_path:
            self.python_path_edit.setText(file_path)
