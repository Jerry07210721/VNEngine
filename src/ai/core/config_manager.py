# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - 配置管理器
负责读取、保存、验证AI配置文件
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional
from .models import UserConfig
from .secret_store import decrypt_str, encrypt_str


class ConfigManager:
    """AI配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径，默认为 config/ai_config.yaml
        """
        if config_path is None:
            # 默认配置文件路径
            project_root = Path(__file__).parent.parent.parent.parent
            config_path = project_root / "config" / "ai_config.yaml"
        
        self.config_path = Path(config_path)
        self.config_data: Dict[str, Any] = {}
        
        # 如果配置文件不存在，创建默认配置
        if not self.config_path.exists():
            self._create_default_config()
        
        # 加载配置
        self.load_config()
    
    def _create_default_config(self) -> None:
        """创建默认配置文件"""
        default_config = {
            "api_keys": {
                "claude": {
                    "api_key": "YOUR_METACHAT_API_KEY",
                    "base_url": "https://llm-api.mmchat.xyz",
                    "primary_model": "claude-sonnet-4-20250514",
                    "fallback_model": "claude-sonnet-4-5-20250929",
                    "max_tokens": 64000,
                    "timeout": 300
                },
                "kimi": {
                    "api_key": "YOUR_METACHAT_API_KEY",
                    "base_url": "https://llm-api.mmchat.xyz",
                    "primary_model": "anthropic/kimi-k2-0905-preview",
                    "fallback_model": "anthropic/kimi-k2-thinking",
                    "max_tokens": 256000,
                    "timeout": 300
                },
                "midjourney": {
                    "app_id": "YOUR_METACHAT_APP_ID",
                    "api_key": "YOUR_METACHAT_API_KEY",
                    "base_url": "https://llm-api.mmchat.xyz",
                    "primary_model": "mj-v7",
                    "fallback_model": "mj-v61",
                    "timeout": 1800,
                    "poll_interval": 5
                },
                "flux": {
                    "app_id": "YOUR_METACHAT_APP_ID",
                    "api_key": "YOUR_METACHAT_API_KEY",
                    "base_url": "https://llm-api.mmchat.xyz",
                    "primary_model": "flux-kontext",
                    "fallback_model": "flux-2-pro",
                    "timeout": 1800,
                    "poll_interval": 5
                },
                "gptsovits": {
                    "api_key": "",
                    "sign": "YOUR_GPTSOVITS_SIGN",
                    "base_url": "https://openapi.lipvoice.cn",
                    "style": "2",
                    "genre": 1,
                    "timeout": 300,
                    "poll_interval": 5
                },
                "suno": {
                    "token": "YOUR_SUNO_TOKEN",
                    "user_id": "YOUR_SUNO_USER_ID",
                    "base_url": "https://dzwlai.com/apiuser",
                    "suno_version": "chirp-v5",
                    "primary_model": "chirp-v5",
                    "fallback_model": "chirp-v4-5+",
                    "timeout": 600,
                    "poll_interval": 10
                }
            },
            "agent_settings": {
                "enable_agents": {
                    "plot_agent": True,
                    "portrait_agent": True,
                    "background_agent": True,
                    "cg_agent": True,
                    "voice_api": True,
                    "bgm_api": True
                },
                "retry_settings": {
                    "max_retries": 3,
                    "retry_delay": 5
                },
                "concurrent_tasks": {
                    "portrait": 3,
                    "background": 3,
                    "cg": 2,
                    "voice": 5,
                    "bgm": 2
                }
            },
            "material_settings": {
                "portrait": {
                    "format": "png",
                    "size": "2048x2048",
                    "transparent": True,
                    "expressions": ["happy", "sad", "shy", "angry", "calm"],
                    "actions": ["stand", "sit"]
                },
                "background": {
                    "format": "jpg",
                    "quality": 1,
                    "variants": ["day", "night", "sunny", "rainy"]
                },
                "cg": {
                    "format": "png",
                    "size": "2560x1440",
                    "quality": 2
                },
                "voice": {
                    "format": "mp3",
                    "emotions": {
                        "happy": 0.0,
                        "angry": 0.0,
                        "sad": 0.0,
                        "afraid": 0.0,
                        "disgusted": 0.0,
                        "melancholic": 0.0,
                        "surprised": 0.0,
                        "calm": 0.0
                    }
                },
                "bgm": {
                    "format": "mp3",
                    "duration": 120,
                    "loop": True
                }
            },
            "project_settings": {
                "default_window_width": 1280,
                "default_window_height": 720,
                "engine_version": "V2.0-AI",
                "auto_save_interval": 300,
                "resource_root": "output/projects"
            }
        }
        
        # 确保配置目录存在
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存默认配置
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, allow_unicode=True, default_flow_style=False, indent=2)
        
        print(f"[OK] 已创建默认配置文件: {self.config_path}")
        print("[WARN] 请在配置文件中填写您的API密钥")
    
    def load_config(self) -> Dict[str, Any]:
        """
        加载配置文件
        
        Returns:
            配置字典
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config_data = yaml.safe_load(f) or {}
            self._ensure_defaults()
            self._decrypt_api_secrets_inplace()
            return self.config_data
        except Exception as e:
            print(f"[ERROR] 配置文件加载失败: {e}")
            return {}

    def _decrypt_api_secrets_inplace(self) -> None:
        """Decrypt sensitive fields in-memory after loading.

        On disk, secrets are stored as ENC::... strings. In memory we keep them
        decrypted so the rest of the system (UI + API clients) continues to use
        plain values.
        """
        api_keys = self.config_data.get("api_keys")
        if not isinstance(api_keys, dict):
            return

        secret_fields = {"api_key", "token", "sign"}
        for _, cfg in api_keys.items():
            if not isinstance(cfg, dict):
                continue
            for field in secret_fields:
                val = cfg.get(field)
                if isinstance(val, str) and val:
                    cfg[field] = decrypt_str(val)

    def _encrypted_dump_copy(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Return a deep-ish copy of config with secrets encrypted for disk."""
        # Manual copy to avoid importing copy.deepcopy for large configs.
        out: Dict[str, Any] = {}
        for k, v in (data or {}).items():
            if isinstance(v, dict):
                out[k] = self._encrypted_dump_copy(v)
            elif isinstance(v, list):
                out[k] = [self._encrypted_dump_copy(i) if isinstance(i, dict) else i for i in v]
            else:
                out[k] = v

        # Encrypt only under api_keys.* for known sensitive fields.
        api_keys = out.get("api_keys")
        if isinstance(api_keys, dict):
            secret_fields = {"api_key", "token", "sign"}
            for _, cfg in api_keys.items():
                if not isinstance(cfg, dict):
                    continue
                for field in secret_fields:
                    val = cfg.get(field)
                    if isinstance(val, str) and val:
                        cfg[field] = encrypt_str(val)
        return out

    def _ensure_defaults(self):
        """在缺省字段时填充默认值，避免KeyError。"""
        if "api_keys" not in self.config_data:
            self.config_data["api_keys"] = {}

        api_defaults = {
            "timeout": 300,
            "poll_interval": 5,
            "base_url": "https://llm-api.mmchat.xyz",
        }

        for name, defaults in {
            "claude": api_defaults,
            "kimi": api_defaults,
            "midjourney": {"timeout": 1800, "poll_interval": 5, "base_url": "https://llm-api.mmchat.xyz"},
            "flux": {"timeout": 1800, "poll_interval": 5, "base_url": "https://llm-api.mmchat.xyz"},
            "gptsovits": {"timeout": 300, "poll_interval": 5, "base_url": "https://openapi.lipvoice.cn"},
            "suno": {"timeout": 600, "poll_interval": 10, "base_url": "https://dzwlai.com/apiuser", "suno_version": "chirp-v5"},
        }.items():
            cfg = self.config_data["api_keys"].setdefault(name, {})
            for key, value in defaults.items():
                cfg.setdefault(key, value)

        self.config_data.setdefault("project_settings", {})
        self.config_data["project_settings"].setdefault("default_window_width", 1280)
        self.config_data["project_settings"].setdefault("default_window_height", 720)
        self.config_data["project_settings"].setdefault("engine_version", "V2.0-AI")
        self.config_data["project_settings"].setdefault("resource_root", "output/projects")
    
    def save_config(self, config_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        保存配置文件
        
        Args:
            config_data: 配置数据，如果为None则保存当前内存中的配置
        
        Returns:
            是否保存成功
        """
        try:
            if config_data is not None:
                self.config_data = config_data

            # Persist secrets encrypted at rest.
            dump_data = self._encrypted_dump_copy(self.config_data)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(dump_data, f, allow_unicode=True, default_flow_style=False, indent=2)
            
            print(f"[OK] 配置文件保存成功: {self.config_path}")
            return True
        except Exception as e:
            print(f"[ERROR] 配置文件保存失败: {e}")
            return False
    
    def get_api_config(self, api_name: str) -> Dict[str, Any]:
        """
        获取指定API的配置
        
        Args:
            api_name: API名称（claude/kimi/midjourney/flux/gptsovits/suno）
        
        Returns:
            API配置字典
        """
        return self.config_data.get("api_keys", {}).get(api_name, {})
    
    def get_agent_settings(self) -> Dict[str, Any]:
        """
        获取Agent设置
        
        Returns:
            Agent设置字典
        """
        return self.config_data.get("agent_settings", {})
    
    def get_material_settings(self, material_type: Optional[str] = None) -> Dict[str, Any]:
        """
        获取素材设置
        
        Args:
            material_type: 素材类型（portrait/background/cg/voice/bgm），为None时返回全部
        
        Returns:
            素材设置字典
        """
        material_settings = self.config_data.get("material_settings", {})
        if material_type:
            return material_settings.get(material_type, {})
        return material_settings
    
    def get_project_settings(self) -> Dict[str, Any]:
        """
        获取工程设置
        
        Returns:
            工程设置字典
        """
        return self.config_data.get("project_settings", {})
    
    def update_api_key(self, api_name: str, api_key: str) -> bool:
        """
        更新API密钥
        
        Args:
            api_name: API名称
            api_key: 新的API密钥
        
        Returns:
            是否更新成功
        """
        if "api_keys" not in self.config_data:
            self.config_data["api_keys"] = {}
        
        if api_name not in self.config_data["api_keys"]:
            self.config_data["api_keys"][api_name] = {}
        
        self.config_data["api_keys"][api_name]["api_key"] = api_key
        return self.save_config()
    
    def validate_config(self) -> tuple[bool, list[str]]:
        """
        验证配置有效性
        
        Returns:
            (是否有效, 错误列表)
        """
        errors = []
        
        # 检查API密钥配置
        api_keys = self.config_data.get("api_keys", {})
        
        # 必需的API（剧情生成必须有Claude或Kimi）
        if not api_keys.get("claude", {}).get("api_key") and \
           not api_keys.get("kimi", {}).get("api_key"):
            errors.append("必须配置Claude或Kimi的API密钥（用于剧情生成）")
        
        # 检查可选API的完整性
        for api_name in ["midjourney", "flux", "gptsovits", "suno"]:
            api_config = api_keys.get(api_name, {})
            if api_config:
                # 如果配置了该API，检查必要字段
                if api_name in ["midjourney", "flux"]:
                    if not api_config.get("app_id") or not api_config.get("api_key"):
                        errors.append(f"{api_name}的App ID和API Key必须同时配置")
                elif api_name == "gptsovits":
                    if not api_config.get("sign"):
                        errors.append("GPT-SoVITS的Sign必须配置")
                elif api_name == "suno":
                    if not api_config.get("token") or not api_config.get("user_id"):
                        errors.append("Suno AI的Token和User ID必须同时配置")
        
        return (len(errors) == 0, errors)
    
    def is_api_enabled(self, api_name: str) -> bool:
        """
        检查指定API是否启用
        
        Args:
            api_name: API名称
        
        Returns:
            是否启用
        """
        api_config = self.get_api_config(api_name)
        if not api_config:
            return False
        
        # 检查必要的配置字段是否存在且不为默认值
        if api_name in ["claude", "kimi"]:
            api_key = api_config.get("api_key", "")
            return api_key and not api_key.startswith("YOUR_")
        elif api_name in ["midjourney", "flux"]:
            app_id = api_config.get("app_id", "")
            api_key = api_config.get("api_key", "")
            return app_id and api_key and not app_id.startswith("YOUR_") and not api_key.startswith("YOUR_")
        elif api_name == "gptsovits":
            sign = api_config.get("sign", "")
            return sign and not sign.startswith("YOUR_")
        elif api_name == "suno":
            token = api_config.get("token", "")
            user_id = api_config.get("user_id", "")
            return token and user_id and not token.startswith("YOUR_") and not user_id.startswith("YOUR_")
        
        return False
