# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - 专用日志工具
提供格式化日志、多级别日志、文件日志等能力
"""
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


class AgentLogger:
    """
    Agent专用日志工具
    支持控制台输出与文件输出，格式化日志信息
    """
    
    # 日志级别映射
    LOG_LEVELS = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    
    def __init__(
        self,
        name: str,
        log_file: Optional[str] = None,
        level: str = "INFO",
        console_output: bool = True
    ):
        """
        初始化日志工具
        
        Args:
            name: 日志名称（通常为Agent名称）
            log_file: 日志文件路径（可选）
            level: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
            console_output: 是否输出到控制台
        """
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self.LOG_LEVELS.get(level, logging.INFO))
        
        # 清空已有处理器
        self.logger.handlers.clear()
        
        # 创建格式化器
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # 添加控制台处理器
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        # 添加文件处理器
        if log_file:
            # 确保日志目录存在
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
    
    def debug(self, message: str):
        """
        输出DEBUG级别日志
        
        Args:
            message: 日志消息
        """
        self.logger.debug(message)
    
    def info(self, message: str):
        """
        输出INFO级别日志
        
        Args:
            message: 日志消息
        """
        self.logger.info(message)
    
    def warning(self, message: str):
        """
        输出WARNING级别日志
        
        Args:
            message: 日志消息
        """
        self.logger.warning(message)
    
    def error(self, message: str):
        """
        输出ERROR级别日志
        
        Args:
            message: 日志消息
        """
        self.logger.error(message)
    
    def critical(self, message: str):
        """
        输出CRITICAL级别日志
        
        Args:
            message: 日志消息
        """
        self.logger.critical(message)
    
    def log_task_start(self, task_name: str, params: dict):
        """
        记录任务开始
        
        Args:
            task_name: 任务名称
            params: 任务参数
        """
        self.info(f"========== 任务开始：{task_name} ==========")
        self.info(f"任务参数：{params}")
    
    def log_task_end(self, task_name: str, success: bool, message: str = ""):
        """
        记录任务结束
        
        Args:
            task_name: 任务名称
            success: 是否成功
            message: 结果消息
        """
        status = "成功" if success else "失败"
        self.info(f"========== 任务结束：{task_name} - {status} ==========")
        if message:
            if success:
                self.info(f"结果：{message}")
            else:
                self.error(f"错误：{message}")
    
    def log_api_call(self, api_name: str, endpoint: str, params: dict):
        """
        记录API调用
        
        Args:
            api_name: API名称
            endpoint: 端点
            params: 调用参数
        """
        self.debug(f"API调用：{api_name} - {endpoint}")
        self.debug(f"参数：{params}")
    
    def log_api_response(self, api_name: str, status_code: int, response: dict):
        """
        记录API响应
        
        Args:
            api_name: API名称
            status_code: HTTP状态码
            response: 响应数据
        """
        self.debug(f"API响应：{api_name} - 状态码：{status_code}")
        self.debug(f"响应数据：{response}")
    
    def log_progress(self, current: int, total: int, item_name: str = "项"):
        """
        记录进度
        
        Args:
            current: 当前进度
            total: 总数
            item_name: 项目名称
        """
        percentage = (current / total * 100) if total > 0 else 0
        self.info(f"进度：{current}/{total} {item_name}（{percentage:.1f}%）")


class LoggerFactory:
    """
    日志工具工厂类
    统一管理所有Agent的日志工具
    """
    
    _loggers = {}
    _default_log_dir = Path("logs/multi_agent")
    
    @classmethod
    def set_log_directory(cls, log_dir: str):
        """
        设置日志目录
        
        Args:
            log_dir: 日志目录路径
        """
        cls._default_log_dir = Path(log_dir)
        cls._default_log_dir.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def get_logger(
        cls,
        agent_name: str,
        level: str = "INFO",
        console_output: bool = True,
        file_output: bool = True
    ) -> AgentLogger:
        """
        获取或创建日志工具
        
        Args:
            agent_name: Agent名称
            level: 日志级别
            console_output: 是否输出到控制台
            file_output: 是否输出到文件
            
        Returns:
            AgentLogger: 日志工具实例
        """
        # 如果已存在，直接返回
        if agent_name in cls._loggers:
            return cls._loggers[agent_name]
        
        # 创建新日志工具
        log_file = None
        if file_output:
            # 日志文件名：agent_name_YYYYMMDD.log
            timestamp = datetime.now().strftime("%Y%m%d")
            log_file = str(cls._default_log_dir / f"{agent_name}_{timestamp}.log")
        
        logger = AgentLogger(
            name=agent_name,
            log_file=log_file,
            level=level,
            console_output=console_output
        )
        
        cls._loggers[agent_name] = logger
        return logger
    
    @classmethod
    def clear_all_loggers(cls):
        """清空所有日志工具缓存"""
        cls._loggers.clear()
