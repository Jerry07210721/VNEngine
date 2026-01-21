# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - API统一管理器
统一管理所有API客户端，提供统一调用接口、成本监控、错误处理
"""

from typing import Dict, Any, Optional, Union
from ..core.config_manager import ConfigManager
from ..log.logger import get_logger
from .claude_client import ClaudeClient
from .kimi_client import KimiClient
from .midjourney_client import MidjourneyClient
from .flux_client import FluxClient
from .gptsovits_client import GPTSoVITSClient
from .suno_client import SunoClient


class APIManager:
    """API统一管理器"""
    
    def __init__(self, config_manager: Optional[ConfigManager] = None):
        """
        初始化API管理器
        
        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager or ConfigManager()
        self.logger = get_logger("APIManager")
        
        # API客户端实例缓存
        self._clients: Dict[str, Any] = {}
        
        # 成本追踪
        self._costs = {
            "claude": 0.0,
            "kimi": 0.0,
            "midjourney": 0.0,
            "flux": 0.0,
            "gptsovits": 0.0,
            "suno": 0.0
        }
        
        self.logger.info("API管理器初始化完成")
    
    def _get_or_create_client(
        self,
        api_name: str,
        force_recreate: bool = False
    ) -> Optional[Union[ClaudeClient, KimiClient, MidjourneyClient, FluxClient, GPTSoVITSClient, SunoClient]]:
        """
        获取或创建API客户端
        
        Args:
            api_name: API名称
            force_recreate: 是否强制重新创建
        
        Returns:
            API客户端实例
        """
        # 如果已存在且不强制重建，直接返回
        if not force_recreate and api_name in self._clients:
            return self._clients[api_name]
        
        # 获取API配置
        api_config = self.config_manager.get_api_config(api_name)
        
        if not api_config:
            self.logger.warning(f"未找到 {api_name} 的配置")
            return None
        
        # 创建客户端
        try:
            if api_name == "claude":
                client = ClaudeClient(
                    api_key=api_config["api_key"],
                    base_url=api_config.get("base_url", "https://llm-api.mmchat.xyz"),
                    model=api_config.get("primary_model", "claude-sonnet-4-20250514"),
                    max_tokens=api_config.get("max_tokens", 64000),
                    timeout=api_config.get("timeout", 300)
                )
            
            elif api_name == "kimi":
                client = KimiClient(
                    api_key=api_config["api_key"],
                    base_url=api_config.get("base_url", "https://llm-api.mmchat.xyz"),
                    model=api_config.get("primary_model", "anthropic/kimi-k2-0905-preview"),
                    max_tokens=api_config.get("max_tokens", 256000),
                    timeout=api_config.get("timeout", 300)
                )
            
            elif api_name == "midjourney":
                client = MidjourneyClient(
                    app_id=api_config["app_id"],
                    api_key=api_config["api_key"],
                    base_url=api_config.get("base_url", "https://api.mmchat.xyz"),
                    model=api_config.get("primary_model", "mj-v7"),
                    timeout=api_config.get("timeout", 1800),
                    poll_interval=api_config.get("poll_interval", 5.0)
                )
            
            elif api_name == "flux":
                client = FluxClient(
                    app_id=api_config["app_id"],
                    api_key=api_config["api_key"],
                    base_url=api_config.get("base_url", "https://api.mmchat.xyz"),
                    model=api_config.get("primary_model", "flux-kontext"),
                    timeout=api_config.get("timeout", 1800),
                    poll_interval=api_config.get("poll_interval", 5.0)
                )
            
            elif api_name == "gptsovits":
                client = GPTSoVITSClient(
                    sign=api_config["sign"],
                    base_url=api_config.get("base_url", "https://openapi.lipvoice.cn"),
                    style=api_config.get("style", "2"),
                    genre=api_config.get("genre", 1),
                    timeout=api_config.get("timeout", 300),
                    poll_interval=api_config.get("poll_interval", 5.0)
                )
            
            elif api_name == "suno":
                client = SunoClient(
                    token=api_config["token"],
                    user_id=api_config["user_id"],
                    base_url=api_config.get("base_url", "https://dzwlai.com/apiuser"),
                    model=api_config.get("suno_version", api_config.get("primary_model", "chirp-v5")),
                    timeout=api_config.get("timeout", 600),
                    poll_interval=api_config.get("poll_interval", 10.0)
                )
            
            else:
                self.logger.error(f"不支持的API类型: {api_name}")
                return None
            
            # 缓存客户端
            self._clients[api_name] = client
            self.logger.info(f"{api_name} 客户端创建成功")
            
            return client
            
        except Exception as e:
            self.logger.error(f"创建 {api_name} 客户端失败: {e}")
            return None
    
    def get_claude_client(self, force_recreate: bool = False) -> Optional[ClaudeClient]:
        """获取Claude客户端"""
        return self._get_or_create_client("claude", force_recreate)
    
    def get_kimi_client(self, force_recreate: bool = False) -> Optional[KimiClient]:
        """获取Kimi客户端"""
        return self._get_or_create_client("kimi", force_recreate)
    
    def get_midjourney_client(self, force_recreate: bool = False) -> Optional[MidjourneyClient]:
        """获取Midjourney客户端"""
        return self._get_or_create_client("midjourney", force_recreate)
    
    def get_flux_client(self, force_recreate: bool = False) -> Optional[FluxClient]:
        """获取FLUX客户端"""
        return self._get_or_create_client("flux", force_recreate)
    
    def get_gptsovits_client(self, force_recreate: bool = False) -> Optional[GPTSoVITSClient]:
        """获取GPT-SoVITS客户端"""
        return self._get_or_create_client("gptsovits", force_recreate)
    
    def get_suno_client(self, force_recreate: bool = False) -> Optional[SunoClient]:
        """获取Suno AI客户端"""
        return self._get_or_create_client("suno", force_recreate)
    
    def get_llm_client(self, prefer_claude: bool = True) -> Optional[Union[ClaudeClient, KimiClient]]:
        """
        获取语言模型客户端（Claude优先或Kimi优先）
        
        Args:
            prefer_claude: 是否优先使用Claude
        
        Returns:
            可用的LLM客户端
        """
        if prefer_claude:
            # 优先使用Claude
            claude = self.get_claude_client()
            if claude:
                return claude
            
            # Claude不可用，尝试Kimi
            self.logger.warning("Claude不可用，切换到Kimi")
            return self.get_kimi_client()
        else:
            # 优先使用Kimi
            kimi = self.get_kimi_client()
            if kimi:
                return kimi
            
            # Kimi不可用，尝试Claude
            self.logger.warning("Kimi不可用，切换到Claude")
            return self.get_claude_client()
    
    def get_image_client(self, prefer_midjourney: bool = True) -> Optional[Union[MidjourneyClient, FluxClient]]:
        """
        获取图像生成客户端（Midjourney优先或FLUX优先）
        
        Args:
            prefer_midjourney: 是否优先使用Midjourney
        
        Returns:
            可用的图像生成客户端
        """
        if prefer_midjourney:
            mj = self.get_midjourney_client()
            if mj:
                return mj
            
            self.logger.warning("Midjourney不可用，切换到FLUX")
            return self.get_flux_client()
        else:
            flux = self.get_flux_client()
            if flux:
                return flux
            
            self.logger.warning("FLUX不可用，切换到Midjourney")
            return self.get_midjourney_client()
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有API的统计信息
        
        Returns:
            统计信息字典
        """
        stats = {}
        
        for api_name, client in self._clients.items():
            client_stats = client.get_stats()
            
            # 添加token统计（如果支持）
            if hasattr(client, 'get_token_stats'):
                client_stats['tokens'] = client.get_token_stats()
            
            stats[api_name] = client_stats
        
        return stats
    
    def get_total_cost(self) -> Dict[str, float]:
        """
        获取总成本估算
        
        Returns:
            成本字典
        """
        return self._costs.copy()
    
    def close_all(self):
        """关闭所有API客户端"""
        for api_name, client in self._clients.items():
            try:
                client.close()
                self.logger.info(f"{api_name} 客户端已关闭")
            except Exception as e:
                self.logger.warning(f"关闭 {api_name} 客户端时出错: {e}")
        
        self._clients.clear()
        self.logger.info("所有API客户端已关闭")
