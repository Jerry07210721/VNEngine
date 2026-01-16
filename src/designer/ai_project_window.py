# -*- coding: utf-8 -*-
"""
AI辅助工程主窗口
独立进程运行，提供完整的AI辅助制作流程
"""

import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QMenuBar,
    QMenu,
    QStatusBar,
    QFileDialog,
    QMessageBox,
    QToolBar,
    QPushButton,
    QLabel,
    QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QIcon

from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.config_manager import ConfigManager

# 导入子界面（占位）
from src.designer.ai_story_config_panel import AIStoryConfigPanel
from src.designer.ai_character_config_panel import AICharacterConfigPanel
from src.designer.ai_master_control_panel import AIMasterControlPanel
from src.designer.ai_portrait_panel import AIPortraitPanel
from src.designer.ai_cg_panel import AICGPanel
from src.designer.ai_background_panel import AIBackgroundPanel
from src.designer.ai_voice_panel import AIVoicePanel
from src.designer.ai_bgm_panel import AIBGMPanel


class AIProjectWindow(QMainWindow):
    """AI辅助工程主窗口"""
    
    # 信号：工程已保存
    project_saved = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.project_manager = AIProjectManager()
        self.config_manager = ConfigManager()
        
        # 当前工程状态
        self.is_modified = False
        
        self.init_ui()
        self.update_window_title()
        
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("VNEngine - AI辅助工程")
        self.resize(1400, 900)
        
        # 初始化各部分
        self.init_menu_bar()
        self.init_tool_bar()
        self.init_central_widget()
        self.init_status_bar()
        
    def init_menu_bar(self):
        """初始化菜单栏"""
        menu_bar = self.menuBar()
        
        # 文件菜单
        file_menu = QMenu("文件(&F)", self)
        
        new_action = QAction("新建AI工程(&N)", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_project)
        file_menu.addAction(new_action)
        
        open_action = QAction("打开AI工程(&O)", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_project)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        save_action = QAction("保存工程(&S)", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)
        
        save_as_action = QAction("另存为(&A)...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self.save_project_as)
        file_menu.addAction(save_as_action)
        
        file_menu.addSeparator()
        
        export_json_action = QAction("导出为JSON", self)
        export_json_action.triggered.connect(self.export_to_json)
        file_menu.addAction(export_json_action)
        
        file_menu.addSeparator()
        
        close_action = QAction("关闭工程", self)
        close_action.triggered.connect(self.close_project)
        file_menu.addAction(close_action)
        
        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Alt+F4")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        menu_bar.addMenu(file_menu)
        
        # 工具菜单
        tools_menu = QMenu("工具(&T)", self)
        
        api_config_action = QAction("API配置", self)
        api_config_action.triggered.connect(self.open_api_config)
        tools_menu.addAction(api_config_action)
        
        project_summary_action = QAction("工程摘要", self)
        project_summary_action.triggered.connect(self.show_project_summary)
        tools_menu.addAction(project_summary_action)
        
        menu_bar.addMenu(tools_menu)
        
        # 帮助菜单
        help_menu = QMenu("帮助(&H)", self)
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        menu_bar.addMenu(help_menu)
        
    def init_tool_bar(self):
        """初始化工具栏"""
        tool_bar = QToolBar("常用工具", self)
        self.addToolBar(tool_bar)
        
        # 快捷按钮
        new_btn = QPushButton("新建工程")
        new_btn.clicked.connect(self.new_project)
        tool_bar.addWidget(new_btn)
        
        open_btn = QPushButton("打开工程")
        open_btn.clicked.connect(self.open_project)
        tool_bar.addWidget(open_btn)
        
        save_btn = QPushButton("保存工程")
        save_btn.clicked.connect(self.save_project)
        tool_bar.addWidget(save_btn)
        
        tool_bar.addSeparator()
        
        # 工程信息显示
        self.project_info_label = QLabel("未打开工程")
        tool_bar.addWidget(self.project_info_label)
        
    def init_central_widget(self):
        """初始化中心部件 - 多标签页"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 创建标签页
        self.tab_widget = QTabWidget()

        # 滚动包装函数，避免超大内容撑开窗口
        def wrap_with_scroll(widget: QWidget) -> QScrollArea:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setWidget(widget)
            return scroll
        
        # 各子界面
        self.story_panel = AIStoryConfigPanel(self.project_manager, self)
        self.character_panel = AICharacterConfigPanel(self.project_manager, self.config_manager, self)
        self.master_panel = AIMasterControlPanel(self.project_manager, self.config_manager, self)
        self.portrait_panel = AIPortraitPanel(self.project_manager, self.config_manager, self)
        self.cg_panel = AICGPanel(self.project_manager, self.config_manager, self)
        self.background_panel = AIBackgroundPanel(self.project_manager, self.config_manager, self)
        self.voice_panel = AIVoicePanel(self.project_manager, self.config_manager, self)
        self.bgm_panel = AIBGMPanel(self.project_manager, self.config_manager, self)
        
        # 添加到标签页
        self.tab_widget.addTab(wrap_with_scroll(self.story_panel), "剧情配置")
        self.tab_widget.addTab(wrap_with_scroll(self.character_panel), "角色配置")
        self.tab_widget.addTab(wrap_with_scroll(self.master_panel), "主控Agent")
        self.tab_widget.addTab(wrap_with_scroll(self.portrait_panel), "立绘生成")
        self.tab_widget.addTab(wrap_with_scroll(self.cg_panel), "CG生成")
        self.tab_widget.addTab(wrap_with_scroll(self.background_panel), "背景生成")
        self.tab_widget.addTab(wrap_with_scroll(self.voice_panel), "语音生成")
        self.tab_widget.addTab(wrap_with_scroll(self.bgm_panel), "BGM生成")
        
        layout.addWidget(self.tab_widget)
        
        # 监听子界面的修改信号（后续实现）
        self.story_panel.modified.connect(self.on_content_modified)
        self.character_panel.modified.connect(self.on_content_modified)
        self.master_panel.modified.connect(self.on_content_modified)
        
    def init_status_bar(self):
        """初始化状态栏"""
        status_bar = QStatusBar()
        status_bar.showMessage("就绪")
        self.setStatusBar(status_bar)
        
    # ==================== 工程操作 ====================
    
    def new_project(self):
        """新建AI工程"""
        if not self.check_save_current():
            return
        
        # 选择保存路径
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "新建AI工程",
            "",
            "AI工程文件 (*.vnai)"
        )
        
        if not file_path:
            return
        
        # 获取工程名称
        project_name = Path(file_path).stem
        
        # 创建工程
        project = self.project_manager.create_new_project(
            project_name=project_name,
            save_path=file_path,
            story_title=project_name
        )
        
        if project:
            self.is_modified = False
            self.update_window_title()
            self.refresh_all_panels()
            self.statusBar().showMessage(f"已创建新工程: {project_name}")
            QMessageBox.information(self, "成功", f"AI工程已创建：\n{file_path}")
        else:
            QMessageBox.critical(self, "错误", "创建工程失败")
    
    def open_project(self):
        """打开AI工程"""
        if not self.check_save_current():
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "打开AI工程",
            "",
            "AI工程文件 (*.vnai)"
        )
        
        if not file_path:
            return
        
        project = self.project_manager.load_project(file_path)
        
        if project:
            self.is_modified = False
            self.update_window_title()
            self.refresh_all_panels()
            self.statusBar().showMessage(f"已加载工程: {project.ai_project_info.name}")
        else:
            QMessageBox.critical(self, "错误", "加载工程失败，请检查文件格式")
    
    def save_project(self):
        """保存工程"""
        if self.project_manager.current_project is None:
            QMessageBox.warning(self, "提示", "没有打开的工程")
            return
        
        if self.project_manager.save_project():
            self.is_modified = False
            self.update_window_title()
            self.statusBar().showMessage("工程已保存")
            self.project_saved.emit(self.project_manager.current_file_path)
        else:
            QMessageBox.critical(self, "错误", "保存失败")
    
    def save_project_as(self):
        """另存为"""
        if self.project_manager.current_project is None:
            QMessageBox.warning(self, "提示", "没有打开的工程")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "另存为",
            "",
            "AI工程文件 (*.vnai)"
        )
        
        if not file_path:
            return
        
        if self.project_manager.save_project(file_path):
            self.is_modified = False
            self.update_window_title()
            self.statusBar().showMessage(f"工程已另存为: {file_path}")
        else:
            QMessageBox.critical(self, "错误", "保存失败")
    
    def close_project(self):
        """关闭当前工程"""
        if not self.check_save_current():
            return
        
        self.project_manager.current_project = None
        self.project_manager.current_file_path = None
        self.is_modified = False
        self.update_window_title()
        self.refresh_all_panels()
        self.statusBar().showMessage("工程已关闭")
    
    def export_to_json(self):
        """导出为JSON"""
        if self.project_manager.current_project is None:
            QMessageBox.warning(self, "提示", "没有打开的工程")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出为JSON",
            "",
            "JSON文件 (*.json)"
        )
        
        if not file_path:
            return
        
        if self.project_manager.export_to_json(file_path):
            QMessageBox.information(self, "成功", f"已导出到:\n{file_path}")
        else:
            QMessageBox.critical(self, "错误", "导出失败")
    
    # ==================== 辅助功能 ====================
    
    def check_save_current(self) -> bool:
        """检查是否需要保存当前工程，返回是否继续操作"""
        if not self.is_modified:
            return True
        
        reply = QMessageBox.question(
            self,
            "保存确认",
            "当前工程有未保存的修改，是否保存？",
            QMessageBox.StandardButton.Yes | 
            QMessageBox.StandardButton.No | 
            QMessageBox.StandardButton.Cancel
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.save_project()
            return True
        elif reply == QMessageBox.StandardButton.No:
            return True
        else:
            return False
    
    def on_content_modified(self):
        """内容被修改"""
        self.is_modified = True
        self.update_window_title()
    
    def update_window_title(self):
        """更新窗口标题"""
        if self.project_manager.current_project is None:
            title = "VNEngine - AI辅助工程"
            self.project_info_label.setText("未打开工程")
        else:
            project_name = self.project_manager.current_project.ai_project_info.name
            modified_mark = " *" if self.is_modified else ""
            title = f"VNEngine - AI辅助工程 - {project_name}{modified_mark}"
            
            # 更新工具栏信息
            char_count = len(self.project_manager.current_project.character_config)
            self.project_info_label.setText(f"工程: {project_name} | 角色: {char_count}")
        
        self.setWindowTitle(title)
    
    def refresh_all_panels(self):
        """刷新所有子界面"""
        self.story_panel.refresh()
        self.character_panel.refresh()
        self.master_panel.refresh()
        self.portrait_panel.refresh()
        self.cg_panel.refresh()
        self.background_panel.refresh()
        self.voice_panel.refresh()
        self.bgm_panel.refresh()
    
    def open_api_config(self):
        """打开API配置对话框"""
        # TODO: 复用主设计器的API配置对话框
        QMessageBox.information(self, "提示", "API配置功能将在后续实现")
    
    def show_project_summary(self):
        """显示工程摘要"""
        if self.project_manager.current_project is None:
            QMessageBox.warning(self, "提示", "没有打开的工程")
            return
        
        summary = self.project_manager.get_project_summary()
        
        text = "工程摘要\n" + "=" * 50 + "\n\n"
        for key, value in summary.items():
            text += f"{key}: {value}\n"
        
        QMessageBox.information(self, "工程摘要", text)
    
    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于",
            "VNEngine AI辅助工程\n\n"
            "版本: V2.1\n"
            "多智能体协作GalGame制作引擎\n\n"
            "© 2026 VNEngine Team"
        )
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        if self.check_save_current():
            event.accept()
        else:
            event.ignore()


def run_ai_project_window():
    """独立运行AI辅助工程窗口"""
    app = QApplication(sys.argv)
    window = AIProjectWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_ai_project_window()
