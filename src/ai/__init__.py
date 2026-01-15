# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统
Multi-Agent AI-Assisted GalGame Creation System
"""

__version__ = "2.0.0"
__author__ = "VNEngine Team"

from .core.config_manager import ConfigManager
from .core.master_agent import MasterAgent
from .api.api_manager import APIManager
from .log.logger import get_logger

__all__ = [
    'ConfigManager',
    'MasterAgent',
    'APIManager',
    'get_logger'
]
