# -*- coding: utf-8 -*-
"""
AI辅助工程主窗口
独立进程运行，提供完整的AI辅助制作流程
"""

import sys
import os
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
    QProgressDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QIcon

from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.config_manager import ConfigManager
from src.designer.ai_assist_dialog import APIConfigDialog

# 导入子界面（占位）
from src.designer.ai_story_config_panel import AIStoryConfigPanel
from src.designer.ai_character_config_panel import AICharacterConfigPanel
from src.designer.ai_master_control_panel import AIMasterControlPanel
from src.designer.ai_portrait_panel import AIPortraitPanel
from src.designer.ai_cg_panel import AICGPanel
from src.designer.ai_background_panel import AIBackgroundPanel
from src.designer.ai_voice_panel import AIVoicePanel
from src.designer.ai_bgm_panel import AIBGMPanel
from src.designer.voice_model_dialog import VoiceModelPickerDialog, get_gptsovits_client
from src.designer.floating_llm_chat import FloatingBall, FloatingChatWidget


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

        # 悬浮球/悬浮窗（在 init_central_widget 中创建）
        self._floating_ball: FloatingBall | None = None
        self._floating_chat: FloatingChatWidget | None = None
        
        self.init_ui()
        self.update_window_title()
        
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("VNEngine - AI辅助工程")
        self.setObjectName("AIProjectWindow")
        # AI辅助界面默认窗口大小：1280x720
        self.resize(1280, 720)
        
        # 初始化各部分
        self.init_menu_bar()
        self.init_tool_bar()
        self.init_central_widget()
        self.init_status_bar()

        # debug: floating widgets
        self._floating_debug = os.getenv("VNENGINE_FLOATING_DEBUG", "0").strip() in {"1", "true", "True", "YES", "yes"}

    def _fdebug(self, msg: str):
        if not getattr(self, "_floating_debug", False):
            return
        try:
            print(f"[FLOATING] {msg}")
        except Exception:
            pass
        try:
            sb = self.statusBar()
            if sb:
                sb.showMessage(msg, 5000)
        except Exception:
            pass
        
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

        voice_model_action = QAction("语音模型配置", self)
        voice_model_action.triggered.connect(self.open_voice_model_manager)
        tools_menu.addAction(voice_model_action)
        
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
        try:
            new_btn.setProperty("variant", "primary")
        except Exception:
            pass
        new_btn.clicked.connect(self.new_project)
        tool_bar.addWidget(new_btn)
        
        open_btn = QPushButton("打开工程")
        open_btn.clicked.connect(self.open_project)
        tool_bar.addWidget(open_btn)
        
        save_btn = QPushButton("保存工程")
        try:
            save_btn.setProperty("variant", "primary")
        except Exception:
            pass
        save_btn.clicked.connect(self.save_project)
        tool_bar.addWidget(save_btn)
        
        tool_bar.addSeparator()
        
        # 工程信息显示
        self.project_info_label = QLabel("未打开工程")
        try:
            self.project_info_label.setProperty("pill", "true")
        except Exception:
            pass
        tool_bar.addWidget(self.project_info_label)

    def open_voice_model_manager(self):
        """打开 GPT-SoVITS 语音模型配置（分页查询/上传/删除）。"""

        client = get_gptsovits_client(self.config_manager, self)
        if not client:
            return
        dlg = VoiceModelPickerDialog(client, self, allow_manage=True)
        dlg.exec()
        
    def init_central_widget(self):
        """初始化中心部件 - 多标签页"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 创建标签页
        self.tab_widget = QTabWidget()
        try:
            self.tab_widget.setDocumentMode(True)
        except Exception:
            pass

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
        # 专项Agent页签：左右区域各自滚动（面板内部已使用 QSplitter + QScrollArea），避免外层滚动条干扰
        self.tab_widget.addTab(self.portrait_panel, "立绘生成")
        self.tab_widget.addTab(self.cg_panel, "CG生成")
        self.tab_widget.addTab(self.background_panel, "背景生成")
        self.tab_widget.addTab(self.voice_panel, "语音生成")
        self.tab_widget.addTab(self.bgm_panel, "BGM生成")
        
        layout.addWidget(self.tab_widget)

        # 悬浮球：始终处于最上层（不进入 layout）
        self._floating_ball = FloatingBall(central_widget)
        # clicked 信号带 bool 参数，使用 lambda 丢弃，避免槽函数签名不匹配导致无响应
        self._floating_ball.clicked.connect(lambda _checked=False: self._open_floating_chat())
        self._floating_ball.show()
        # 默认右下角
        self._floating_ball.move(max(6, central_widget.width() - self._floating_ball.width() - 12), max(6, central_widget.height() - self._floating_ball.height() - 12))
        self._floating_ball.raise_()

        # 悬浮聊天窗
        self._floating_chat = FloatingChatWidget(central_widget, config_manager=self.config_manager)
        self._floating_chat.minimized.connect(self._restore_floating_ball)
        self._floating_chat.hide()

        # tab切换时确保悬浮控件仍在顶层
        self.tab_widget.currentChanged.connect(lambda _i: self._raise_floating_overlays())
        
        # 监听子界面的修改信号（后续实现）
        self.story_panel.modified.connect(self.on_content_modified)
        self.character_panel.modified.connect(self.on_content_modified)
        self.master_panel.modified.connect(self.on_content_modified)

    def _raise_floating_overlays(self):
        if self._floating_chat and self._floating_chat.isVisible():
            self._floating_chat.raise_()
        if self._floating_ball and self._floating_ball.isVisible():
            self._floating_ball.raise_()

    def _open_floating_chat(self):
        self._fdebug("open floating chat requested")
        if not self._floating_chat or not self._floating_ball:
            self._fdebug(f"floating widgets not ready: chat={bool(self._floating_chat)} ball={bool(self._floating_ball)}")
            return
        self._floating_ball.hide()
        self._floating_chat.show_default()
        self._raise_floating_overlays()
        try:
            self._fdebug(
                f"chat shown={self._floating_chat.isVisible()} pos={self._floating_chat.pos().x()},{self._floating_chat.pos().y()} size={self._floating_chat.width()}x{self._floating_chat.height()}"
            )
        except Exception:
            pass

    def _restore_floating_ball(self):
        self._fdebug("restore floating ball")
        if not self._floating_ball:
            return
        self._floating_ball.show()
        self._floating_ball.raise_()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        # 约束悬浮控件始终留在界面内
        cw = self.centralWidget()
        if not cw:
            return
        if self._floating_ball and self._floating_ball.isVisible():
            # clamp by re-moving to current pos
            self._floating_ball._move_clamped(self._floating_ball.pos())
            self._floating_ball.raise_()
        if self._floating_chat and self._floating_chat.isVisible():
            self._floating_chat._move_clamped(self._floating_chat.pos())
            self._floating_chat.raise_()
        self._raise_floating_overlays()
        
    def init_status_bar(self):
        """初始化状态栏"""
        status_bar = QStatusBar()
        status_bar.showMessage("就绪")
        self.setStatusBar(status_bar)

    def _show_busy_dialog(self, text: str) -> QProgressDialog:
        """显示不可取消的忙碌提示，用于大文件打开/保存时避免“卡死”错觉。"""
        dlg = QProgressDialog(text, None, 0, 0, self)
        dlg.setWindowTitle("请稍候")
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setValue(0)
        dlg.show()
        QApplication.processEvents()
        return dlg

    def load_project_file(self, file_path: str) -> bool:
        """从指定路径加载 AI 工程文件（用于被设计模式调用自动加载）。"""
        if not file_path:
            return False
        if not self.check_save_current():
            return False

        busy = None
        try:
            busy = self._show_busy_dialog("正在打开AI工程文件，请稍候...")
            project = self.project_manager.load_project(file_path)
            if project:
                self.is_modified = False
                self.update_window_title()
                self.refresh_all_panels()
                self.statusBar().showMessage(f"已加载工程: {project.ai_project_info.name}")
                return True
            QMessageBox.critical(self, "错误", "加载工程失败，请检查文件格式")
            return False
        finally:
            if busy is not None:
                try:
                    busy.close()
                    busy.deleteLater()
                except Exception:
                    pass
        
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
        
        busy = None
        try:
            busy = self._show_busy_dialog("正在创建/保存AI工程文件，请稍候...")
            # 创建工程
            project = self.project_manager.create_new_project(
                project_name=project_name,
                save_path=file_path,
                story_title=project_name
            )
        finally:
            if busy is not None:
                try:
                    busy.close()
                    busy.deleteLater()
                except Exception:
                    pass
        
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
        
        self.load_project_file(file_path)
    
    def save_project(self):
        """保存工程"""
        if self.project_manager.current_project is None:
            QMessageBox.warning(self, "提示", "没有打开的工程")
            return

        busy = None
        try:
            busy = self._show_busy_dialog("正在保存AI工程文件，请稍候...")
            if self.project_manager.save_project():
                self.is_modified = False
                self.update_window_title()
                self.statusBar().showMessage("工程已保存")
                self.project_saved.emit(self.project_manager.current_file_path)
            else:
                QMessageBox.critical(self, "错误", "保存失败")
        finally:
            if busy is not None:
                try:
                    busy.close()
                    busy.deleteLater()
                except Exception:
                    pass
    
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
        
        busy = None
        try:
            busy = self._show_busy_dialog("正在保存AI工程文件，请稍候...")
            if self.project_manager.save_project(file_path):
                self.is_modified = False
                self.update_window_title()
                self.statusBar().showMessage(f"工程已另存为: {file_path}")
            else:
                QMessageBox.critical(self, "错误", "保存失败")
        finally:
            if busy is not None:
                try:
                    busy.close()
                    busy.deleteLater()
                except Exception:
                    pass
    
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
        dlg = APIConfigDialog(config_manager=self.config_manager, parent=self)
        dlg.exec()
    
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
            "版本: V2.4\n"
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
    try:
        from src.designer.ui_theme import apply_vnengine_theme

        apply_vnengine_theme(app)
    except Exception:
        pass
    window = AIProjectWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_ai_project_window()
