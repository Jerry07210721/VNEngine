# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - 统一日志管理器
支持分模块日志记录、日志级别控制、按日期归档
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器（用于控制台输出）"""
    
    # ANSI颜色代码
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
    }
    RESET = '\033[0m'
    
    def format(self, record):
        # 添加颜色
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"
        
        return super().format(record)


class LoggerManager:
    """日志管理器"""
    
    _instance = None
    _loggers = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self.log_dir = Path(__file__).parent.parent.parent.parent / "logs" / "multi_agent"
            self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def get_logger(
        self,
        name: str,
        level: int = logging.INFO,
        log_to_file: bool = True,
        log_to_console: bool = True
    ) -> logging.Logger:
        """
        获取或创建日志记录器
        
        Args:
            name: 日志记录器名称（通常为模块名）
            level: 日志级别
            log_to_file: 是否输出到文件
            log_to_console: 是否输出到控制台
        
        Returns:
            日志记录器
        """
        # 如果已存在，直接返回
        if name in self._loggers:
            return self._loggers[name]
        
        # 创建新的日志记录器
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False  # 不传播到父logger
        
        # 清除已有的处理器（避免重复）
        logger.handlers.clear()
        
        # 日志格式
        file_formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_formatter = ColoredFormatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # 文件处理器（按日期归档）
        if log_to_file:
            log_file = self.log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log"
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(level)
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        
        # 控制台处理器
        if log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
        
        # 缓存日志记录器
        self._loggers[name] = logger
        
        return logger
    
    def set_level(self, name: str, level: int):
        """
        设置指定日志记录器的级别
        
        Args:
            name: 日志记录器名称
            level: 日志级别
        """
        if name in self._loggers:
            logger = self._loggers[name]
            logger.setLevel(level)
            for handler in logger.handlers:
                handler.setLevel(level)
    
    def set_all_level(self, level: int):
        """
        设置所有日志记录器的级别
        
        Args:
            level: 日志级别
        """
        for name in self._loggers:
            self.set_level(name, level)


# 全局日志管理器实例
_logger_manager = LoggerManager()


def get_logger(
    name: Optional[str] = None,
    level: int = logging.INFO,
    log_to_file: bool = True,
    log_to_console: bool = True
) -> logging.Logger:
    """
    获取日志记录器（便捷函数）
    
    Args:
        name: 日志记录器名称，默认为调用模块名
        level: 日志级别
        log_to_file: 是否输出到文件
        log_to_console: 是否输出到控制台
    
    Returns:
        日志记录器
    """
    if name is None:
        # 自动获取调用模块名
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            caller_module = frame.f_back.f_globals.get('__name__', 'vnengine.ai')
        else:
            caller_module = 'vnengine.ai'
        name = caller_module
    
    return _logger_manager.get_logger(name, level, log_to_file, log_to_console)


def set_log_level(level: int, logger_name: Optional[str] = None):
    """
    设置日志级别
    
    Args:
        level: 日志级别（logging.DEBUG/INFO/WARNING/ERROR/CRITICAL）
        logger_name: 日志记录器名称，为None时设置所有日志记录器
    """
    if logger_name:
        _logger_manager.set_level(logger_name, level)
    else:
        _logger_manager.set_all_level(level)


# 预定义常用日志级别
LOG_LEVEL_DEBUG = logging.DEBUG
LOG_LEVEL_INFO = logging.INFO
LOG_LEVEL_WARNING = logging.WARNING
LOG_LEVEL_ERROR = logging.ERROR
LOG_LEVEL_CRITICAL = logging.CRITICAL
