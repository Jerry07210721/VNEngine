# -*- coding: utf-8 -*-
"""
日志模块：统一日志管理
"""

from .logger import (
    get_logger,
    set_log_level,
    LOG_LEVEL_DEBUG,
    LOG_LEVEL_INFO,
    LOG_LEVEL_WARNING,
    LOG_LEVEL_ERROR,
    LOG_LEVEL_CRITICAL
)

__all__ = [
    'get_logger',
    'set_log_level',
    'LOG_LEVEL_DEBUG',
    'LOG_LEVEL_INFO',
    'LOG_LEVEL_WARNING',
    'LOG_LEVEL_ERROR',
    'LOG_LEVEL_CRITICAL'
]
