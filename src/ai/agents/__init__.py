# -*- coding: utf-8 -*-
"""
专项Agent模块：剧情对白、立绘差分、背景生成、CG生成、语音、BGM
"""

from .plot_agent import PlotAgent
from .portrait_agent import PortraitAgent
from .background_agent import BackgroundAgent
from .cg_agent import CGAgent
from .voice_agent import VoiceAgent
from .bgm_agent import BGMAgent
from .integrator_agent import IntegratorAgent

__all__ = [
    'PlotAgent',
    'PortraitAgent',
    'BackgroundAgent',
    'CGAgent',
    'VoiceAgent',
    'BGMAgent',
    'IntegratorAgent'
]
