# -*- coding: utf-8 -*-
"""
AI子界面基类
提供通用的信号和方法
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import pyqtSignal

from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.config_manager import ConfigManager


class AIBasePanelWidget(QWidget):
    """AI子界面基类"""
    
    # 信号：内容已修改
    modified = pyqtSignal()
    
    def __init__(self, project_manager: AIProjectManager, parent=None):
        super().__init__(parent)
        self.project_manager = project_manager
        
    def refresh(self):
        """刷新界面内容（子类实现）"""
        pass
    
    def save_to_project(self):
        """保存到工程（子类实现）"""
        pass
    
    def mark_modified(self):
        """标记为已修改"""
        self.modified.emit()
