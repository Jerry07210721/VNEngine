# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - 通用API客户端
封装HTTP请求、重试机制、超时控制、密钥管理等通用能力
支持多种大模型API（OpenAI、Claude、DeepSeek、通义千问等）
"""
import requests
import httpx
from typing import Dict, Any, Optional, Union
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import json
import time


class APIError(Exception):
    """API调用错误"""
    pass


class CommonAPIClient:
    """
    通用API客户端基类
    所有专项API客户端继承此类
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str = "",
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        初始化API客户端
        
        Args:
            api_key: API密钥
            base_url: API基础URL
            model_name: 模型名称（如gpt-4o、claude-3-opus、deepseek-chat等）
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model_name = model_name
        self.timeout = timeout
        self.max_retries = max_retries
        
        # 初始化HTTP客户端
        self.session = requests.Session()
        self.session.headers.update(self._build_default_headers())
        
        # 异步HTTP客户端（可选）
        self.async_client = None
        
    def _build_default_headers(self) -> Dict[str, str]:
        """
        构建默认请求头
        
        Returns:
            Dict[str, str]: 请求头字典
        """
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "VNEngine-MultiAgent/1.0"
        }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, httpx.RequestError)),
        reraise=True
    )
    def send_post_request(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        custom_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        发送POST请求（带自动重试）
        
        Args:
            endpoint: API端点（如/v1/chat/completions）
            payload: 请求载荷
            custom_headers: 自定义请求头（可选）
            
        Returns:
            Dict[str, Any]: 响应数据
            
        Raises:
            APIError: API调用失败
        """
        url = f"{self.base_url}{endpoint}"
        headers = self.session.headers.copy()
        if custom_headers:
            headers.update(custom_headers)
        
        try:
            response = self.session.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP错误：{e.response.status_code} - {e.response.text}"
            raise APIError(error_msg) from e
        except requests.exceptions.Timeout as e:
            raise APIError(f"请求超时（{self.timeout}秒）") from e
        except requests.exceptions.RequestException as e:
            raise APIError(f"请求失败：{str(e)}") from e
        except json.JSONDecodeError as e:
            raise APIError(f"响应解析失败：{str(e)}") from e
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, httpx.RequestError)),
        reraise=True
    )
    def send_get_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        custom_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        发送GET请求（带自动重试）
        
        Args:
            endpoint: API端点
            params: 查询参数（可选）
            custom_headers: 自定义请求头（可选）
            
        Returns:
            Dict[str, Any]: 响应数据
            
        Raises:
            APIError: API调用失败
        """
        url = f"{self.base_url}{endpoint}"
        headers = self.session.headers.copy()
        if custom_headers:
            headers.update(custom_headers)
        
        try:
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP错误：{e.response.status_code} - {e.response.text}"
            raise APIError(error_msg) from e
        except requests.exceptions.Timeout as e:
            raise APIError(f"请求超时（{self.timeout}秒）") from e
        except requests.exceptions.RequestException as e:
            raise APIError(f"请求失败：{str(e)}") from e
        except json.JSONDecodeError as e:
            raise APIError(f"响应解析失败：{str(e)}") from e
    
    def download_file(
        self,
        url: str,
        save_path: str,
        custom_headers: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        下载文件
        
        Args:
            url: 文件URL
            save_path: 保存路径
            custom_headers: 自定义请求头（可选）
            
        Returns:
            bool: 下载是否成功
        """
        headers = self.session.headers.copy()
        if custom_headers:
            headers.update(custom_headers)
        
        try:
            response = self.session.get(url, headers=headers, timeout=self.timeout, stream=True)
            response.raise_for_status()
            
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            raise APIError(f"文件下载失败：{str(e)}") from e
    
    def validate_response(self, response: Dict[str, Any], required_fields: list[str]) -> bool:
        """
        校验响应数据完整性
        
        Args:
            response: 响应数据
            required_fields: 必需字段列表
            
        Returns:
            bool: 校验结果
        """
        for field in required_fields:
            if field not in response:
                raise APIError(f"响应缺少必需字段：{field}")
        return True
    
    def close(self):
        """关闭HTTP会话"""
        self.session.close()
        if self.async_client:
            self.async_client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def __repr__(self) -> str:
        return f"<CommonAPIClient(model={self.model_name}, base_url={self.base_url})>"


class ModelAPIFactory:
    """
    模型API工厂类
    根据模型类型自动选择合适的API客户端配置
    """
    
    # 预定义模型配置
    MODEL_CONFIGS = {
        # OpenAI系列（MetaChat代理）
        "gpt-4o": {
            "base_url": "https://llm-api.mmchat.xyz/v1",
            "endpoint": "/chat/completions"
        },
        "gpt-4o-mini": {
            "base_url": "https://llm-api.mmchat.xyz/v1",
            "endpoint": "/chat/completions"
        },
        "chatgpt-4o-latest": {
            "base_url": "https://llm-api.mmchat.xyz/v1",
            "endpoint": "/chat/completions"
        },
        # DeepSeek系列
        "deepseek-chat": {
            "base_url": "https://api.deepseek.com/v1",
            "endpoint": "/chat/completions"
        },
        "deepseek-coder": {
            "base_url": "https://api.deepseek.com/v1",
            "endpoint": "/chat/completions"
        },
        # 通义千问系列
        "qwen-max": {
            "base_url": "https://dashscope.aliyuncs.com/api/v1",
            "endpoint": "/services/aigc/text-generation/generation"
        },
        "qwen-plus": {
            "base_url": "https://dashscope.aliyuncs.com/api/v1",
            "endpoint": "/services/aigc/text-generation/generation"
        },
        # Claude系列
        "claude-3-opus": {
            "base_url": "https://api.anthropic.com/v1",
            "endpoint": "/messages"
        },
        "claude-3-sonnet": {
            "base_url": "https://api.anthropic.com/v1",
            "endpoint": "/messages"
        },
    }
    
    @classmethod
    def create_client(
        cls,
        model_name: str,
        api_key: str,
        custom_base_url: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3
    ) -> CommonAPIClient:
        """
        创建API客户端
        
        Args:
            model_name: 模型名称
            api_key: API密钥
            custom_base_url: 自定义基础URL（可选，优先级高于预定义配置）
            timeout: 超时时间
            max_retries: 最大重试次数
            
        Returns:
            CommonAPIClient: API客户端实例
        """
        # 优先使用自定义URL
        if custom_base_url:
            base_url = custom_base_url
        elif model_name in cls.MODEL_CONFIGS:
            base_url = cls.MODEL_CONFIGS[model_name]["base_url"]
        else:
            raise ValueError(f"不支持的模型：{model_name}，请提供custom_base_url")
        
        return CommonAPIClient(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            timeout=timeout,
            max_retries=max_retries
        )
    
    @classmethod
    def get_endpoint(cls, model_name: str) -> str:
        """
        获取模型的API端点
        
        Args:
            model_name: 模型名称
            
        Returns:
            str: API端点
        """
        if model_name in cls.MODEL_CONFIGS:
            return cls.MODEL_CONFIGS[model_name]["endpoint"]
        return "/chat/completions"  # 默认端点
