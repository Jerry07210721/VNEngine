# -*- coding: utf-8 -*-
"""
API客户端封装模块：Claude、Kimi、Midjourney、FLUX、GPT-SoVITS、Suno AI
"""

from .base_client import BaseAPIClient, APIError, APITimeoutError, APIRateLimitError, APIAuthError
from .claude_client import ClaudeClient
from .kimi_client import KimiClient
from .midjourney_client import MidjourneyClient
from .flux_client import FluxClient
from .gptsovits_client import GPTSoVITSClient
from .suno_client import SunoClient
from .api_manager import APIManager

__all__ = [
    'BaseAPIClient',
    'APIError',
    'APITimeoutError',
    'APIRateLimitError',
    'APIAuthError',
    'ClaudeClient',
    'KimiClient',
    'MidjourneyClient',
    'FluxClient',
    'GPTSoVITSClient',
    'SunoClient',
    'APIManager'
]
