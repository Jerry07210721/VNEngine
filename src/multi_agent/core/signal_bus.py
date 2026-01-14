# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - 信号总线
提供Agent与UI之间的进度同步、状态更新等通信机制
"""
from PyQt6.QtCore import QObject, pyqtSignal
from typing import Any


class SignalBus(QObject):
    """
    信号总线
    所有Agent通过此类向UI发送进度与状态更新信号
    """
    
    # 进度更新信号：(agent_id, progress, status_message)
    progress_update = pyqtSignal(str, float, str)
    
    # 简化版进度信号（兼容AIGenerationThread）：(progress, message)
    progress_updated = pyqtSignal(float, str)
    
    # 任务完成信号：(agent_id, success, result_data)
    task_complete = pyqtSignal(str, bool, object)
    
    # 错误信号：(agent_id, error_message)
    error_occurred = pyqtSignal(str, str)
    
    # 日志信号：(agent_id, log_level, log_message)
    log_message = pyqtSignal(str, str, str)
    
    # 资源生成完成信号：(resource_type, resource_path)
    resource_generated = pyqtSignal(str, str)
    
    # 工程生成完成信号：(project_path)
    project_generated = pyqtSignal(str)
    
    def emit_progress(self, agent_id: str, progress: float, status: str):
        """
        发送进度更新信号
        
        Args:
            agent_id: Agent唯一标识
            progress: 进度值（0.0~1.0）
            status: 状态描述
        """
        self.progress_update.emit(agent_id, progress, status)
        self.progress_updated.emit(progress, status)  # 同时触发简化版信号
    
    def emit_task_complete(self, agent_id: str, success: bool, result_data: Any = None):
        """
        发送任务完成信号
        
        Args:
            agent_id: Agent唯一标识
            success: 是否成功
            result_data: 结果数据
        """
        self.task_complete.emit(agent_id, success, result_data)
    
    def emit_error(self, agent_id: str, error_msg: str):
        """
        发送错误信号
        
        Args:
            agent_id: Agent唯一标识
            error_msg: 错误消息
        """
        self.error_occurred.emit(agent_id, error_msg)
    
    def emit_log(self, agent_id: str, log_level: str, log_msg: str):
        """
        发送日志信号
        
        Args:
            agent_id: Agent唯一标识
            log_level: 日志级别（DEBUG/INFO/WARNING/ERROR）
            log_msg: 日志消息
        """
        self.log_message.emit(agent_id, log_level, log_msg)
    
    def emit_resource_generated(self, resource_type: str, resource_path: str):
        """
        发送资源生成完成信号
        
        Args:
            resource_type: 资源类型
            resource_path: 资源路径
        """
        self.resource_generated.emit(resource_type, resource_path)
    
    def emit_project_generated(self, project_path: str):
        """
        发送工程生成完成信号
        
        Args:
            project_path: 工程文件路径
        """
        self.project_generated.emit(project_path)


# 全局信号总线单例
signal_bus = SignalBus()
