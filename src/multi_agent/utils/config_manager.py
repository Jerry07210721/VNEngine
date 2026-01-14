# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - 配置管理模块
管理API密钥、模型配置、用户偏好设置等
"""
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
import json
from cryptography.fernet import Fernet
import base64


class ConfigManager:
    """
    配置管理器
    负责加载、保存、加密API配置
    """
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_dir: 配置目录路径（默认为用户目录下的.vnengine）
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            self.config_dir = Path.home() / ".vnengine"
        
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # 配置文件路径
        self.config_file = self.config_dir / "ai_config.yaml"
        self.encrypted_config_file = self.config_dir / "api_keys.enc"
        self.key_file = self.config_dir / ".key"
        
        # 加密密钥
        self._cipher = self._load_or_create_cipher()
    
    def _load_or_create_cipher(self) -> Fernet:
        """
        加载或创建加密密钥
        
        Returns:
            Fernet: 加密器
        """
        if self.key_file.exists():
            with open(self.key_file, 'rb') as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            # 设置文件权限（仅所有者可读写）
            self.key_file.chmod(0o600)
        
        return Fernet(key)
    
    def save_api_config(
        self,
        model_type: str,
        model_name: str,
        api_key: str,
        base_url: Optional[str] = None
    ):
        """
        保存API配置（加密存储API密钥）
        
        Args:
            model_type: 模型类型（llm/image/audio/video）
            model_name: 模型名称
            api_key: API密钥
            base_url: 自定义API地址
        """
        # 加载现有配置
        config = self.load_config()
        
        if "api_configs" not in config:
            config["api_configs"] = {}
        
        # 保存配置（API密钥加密）
        config["api_configs"][model_type] = {
            "model": model_name,
            "base_url": base_url
        }
        
        # 加密API密钥
        encrypted_key = self._cipher.encrypt(api_key.encode()).decode()
        
        # 保存到加密文件
        encrypted_keys = self.load_encrypted_keys()
        encrypted_keys[model_type] = encrypted_key
        self.save_encrypted_keys(encrypted_keys)
        
        # 保存主配置文件
        with open(self.config_file, 'w', encoding='utf-8') as f:
            yaml.safe_dump(config, f, allow_unicode=True)
    
    def get_api_config(self, model_type: str) -> Optional[Dict[str, str]]:
        """
        获取API配置（自动解密API密钥）
        
        Args:
            model_type: 模型类型
            
        Returns:
            Dict[str, str]: API配置（包含解密后的api_key）
        """
        config = self.load_config()
        
        if "api_configs" not in config or model_type not in config["api_configs"]:
            return None
        
        api_config = config["api_configs"][model_type].copy()
        
        # 解密API密钥
        encrypted_keys = self.load_encrypted_keys()
        if model_type in encrypted_keys:
            encrypted_key = encrypted_keys[model_type]
            api_key = self._cipher.decrypt(encrypted_key.encode()).decode()
            api_config["api_key"] = api_key
        else:
            api_config["api_key"] = ""
        
        return api_config
    
    def get_all_api_configs(self) -> Dict[str, Dict[str, str]]:
        """
        获取所有API配置
        
        Returns:
            Dict[str, Dict[str, str]]: 所有API配置
        """
        config = self.load_config()
        
        if "api_configs" not in config:
            return {}
        
        all_configs = {}
        for model_type in config["api_configs"].keys():
            all_configs[model_type] = self.get_api_config(model_type)
        
        return all_configs
    
    def load_config(self) -> Dict[str, Any]:
        """
        加载配置文件
        
        Returns:
            Dict[str, Any]: 配置数据
        """
        if not self.config_file.exists():
            return self._create_default_config()
        
        with open(self.config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        return config if config else {}
    
    def load_encrypted_keys(self) -> Dict[str, str]:
        """
        加载加密的API密钥
        
        Returns:
            Dict[str, str]: 加密密钥字典
        """
        if not self.encrypted_config_file.exists():
            return {}
        
        with open(self.encrypted_config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def save_encrypted_keys(self, encrypted_keys: Dict[str, str]):
        """
        保存加密的API密钥
        
        Args:
            encrypted_keys: 加密密钥字典
        """
        with open(self.encrypted_config_file, 'w', encoding='utf-8') as f:
            json.dump(encrypted_keys, f)
        
        # 设置文件权限
        self.encrypted_config_file.chmod(0o600)
    
    def _create_default_config(self) -> Dict[str, Any]:
        """
        创建默认配置
        
        Returns:
            Dict[str, Any]: 默认配置
        """
        default_config = {
            "version": "1.0.0",
            "api_configs": {},
            "generation_defaults": {
                "char_count": 2,
                "script_length": 5000,
                "branch_count": 2,
                "script_style": ["温馨", "浪漫"],
                "portrait_resolution": [896, 1408],
                "cg_resolution": [2048, 2048],
                "voice_language": "中文",
                "voice_speed": 1.0,
                "emotion_strength": 0.8,
                "bgm_duration": 120
            }
        }
        
        # 保存默认配置
        with open(self.config_file, 'w', encoding='utf-8') as f:
            yaml.safe_dump(default_config, f, allow_unicode=True)
        
        return default_config
    
    def get_generation_defaults(self) -> Dict[str, Any]:
        """
        获取默认生成配置
        
        Returns:
            Dict[str, Any]: 默认配置
        """
        config = self.load_config()
        return config.get("generation_defaults", {})
    
    def update_generation_defaults(self, defaults: Dict[str, Any]):
        """
        更新默认生成配置
        
        Args:
            defaults: 新的默认配置
        """
        config = self.load_config()
        if "generation_defaults" not in config:
            config["generation_defaults"] = {}
        
        config["generation_defaults"].update(defaults)
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            yaml.safe_dump(config, f, allow_unicode=True)
    
    def delete_api_config(self, model_type: str):
        """
        删除API配置
        
        Args:
            model_type: 模型类型
        """
        config = self.load_config()
        
        if "api_configs" in config and model_type in config["api_configs"]:
            del config["api_configs"][model_type]
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, allow_unicode=True)
        
        # 删除加密密钥
        encrypted_keys = self.load_encrypted_keys()
        if model_type in encrypted_keys:
            del encrypted_keys[model_type]
            self.save_encrypted_keys(encrypted_keys)
    
    def clear_all_configs(self):
        """清空所有配置"""
        if self.config_file.exists():
            self.config_file.unlink()
        if self.encrypted_config_file.exists():
            self.encrypted_config_file.unlink()


# 全局配置管理器实例
config_manager = ConfigManager()
