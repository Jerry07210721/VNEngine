# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - Agent基类
所有专项Agent的抽象基类，封装通用能力
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
import traceback

from src.multi_agent.core.data_models import TaskResultSchema


class BaseAgent(ABC):
    """
    Agent基类
    所有专项Agent必须继承此类并实现run方法
    """
    
    def __init__(self, agent_id: str, agent_name: str):
        """
        初始化Agent
        
        Args:
            agent_id: Agent唯一标识
            agent_name: Agent名称
        """
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.logger = None  # 延迟初始化，由子类注入
        self._current_progress = 0.0
        self._current_status = "未开始"
        
    def set_logger(self, logger):
        """
        设置日志工具
        
        Args:
            logger: AgentLogger实例
        """
        self.logger = logger
        
    @abstractmethod
    def run(self, task_params: Dict[str, Any]) -> TaskResultSchema:
        """
        执行核心任务（子类必须实现）
        
        Args:
            task_params: 任务参数字典
            
        Returns:
            TaskResultSchema: 标准化任务结果
        """
        raise NotImplementedError("子类必须实现run方法")
    
    def validate_params(self, params: Dict[str, Any], required_fields: List[str]) -> tuple[bool, str]:
        """
        校验任务参数完整性
        
        Args:
            params: 待校验的参数字典
            required_fields: 必需字段列表
            
        Returns:
            tuple[bool, str]: (校验结果, 错误消息)
        """
        missing_fields = [field for field in required_fields if field not in params]
        if missing_fields:
            error_msg = f"任务参数缺失：{', '.join(missing_fields)}"
            if self.logger:
                self.logger.error(f"[{self.agent_name}] {error_msg}")
            return False, error_msg
        return True, ""
    
    def report_progress(self, progress: float, status: str) -> None:
        """
        上报任务进度
        
        Args:
            progress: 进度值（0.0~1.0）
            status: 状态描述
        """
        self._current_progress = max(0.0, min(1.0, progress))
        self._current_status = status
        
        if self.logger:
            self.logger.info(f"[{self.agent_name}] 进度：{self._current_progress*100:.1f}%，状态：{status}")
        
        # 通过信号总线同步进度至UI
        from src.multi_agent.core.signal_bus import signal_bus
        signal_bus.emit_progress(self.agent_id, self._current_progress, status)
    
    def get_current_progress(self) -> tuple[float, str]:
        """
        获取当前进度
        
        Returns:
            tuple[float, str]: (进度值, 状态描述)
        """
        return self._current_progress, self._current_status
    
    def create_success_result(self, data: Optional[Dict[str, Any]] = None, message: str = "任务完成") -> TaskResultSchema:
        """
        创建成功结果
        
        Args:
            data: 结果数据
            message: 结果消息
            
        Returns:
            TaskResultSchema: 标准化成功结果
        """
        return TaskResultSchema(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            success=True,
            message=message,
            data=data,
            start_time=datetime.now(),
            end_time=datetime.now()
        )
    
    def create_error_result(self, error_msg: str, exception: Optional[Exception] = None) -> TaskResultSchema:
        """
        创建失败结果
        
        Args:
            error_msg: 错误消息
            exception: 异常对象（可选）
            
        Returns:
            TaskResultSchema: 标准化失败结果
        """
        if exception:
            error_detail = f"{error_msg}\n详细信息：{str(exception)}\n堆栈：{traceback.format_exc()}"
        else:
            error_detail = error_msg
            
        if self.logger:
            self.logger.error(f"[{self.agent_name}] {error_detail}")
        
        return TaskResultSchema(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            success=False,
            message=error_msg,
            data=None,
            start_time=datetime.now(),
            end_time=datetime.now(),
            error_msg=error_detail
        )
    
    def safe_run(self, task_params: Dict[str, Any]) -> TaskResultSchema:
        """
        安全执行任务（自动捕获异常）
        
        Args:
            task_params: 任务参数
            
        Returns:
            TaskResultSchema: 任务结果
        """
        try:
            self.report_progress(0.0, "开始执行任务")
            result = self.run(task_params)
            if result.success:
                self.report_progress(1.0, "任务完成")
            return result
        except Exception as e:
            return self.create_error_result(f"任务执行失败", exception=e)
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.agent_id}, name={self.agent_name})>"
