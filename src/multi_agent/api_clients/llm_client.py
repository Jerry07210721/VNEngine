# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - 大语言模型API客户端
支持多种文本生成模型：GPT-4o、DeepSeek、通义千问、Claude等
"""
from typing import Dict, Any, List, Optional
import json
from src.multi_agent.api_clients.common_client import CommonAPIClient, APIError, ModelAPIFactory


class LLMClient:
    """
    大语言模型统一客户端
    根据模型类型自动适配不同API的请求格式
    """
    
    def __init__(
        self,
        model_name: str,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 3
    ):
        """
        初始化LLM客户端
        
        Args:
            model_name: 模型名称（如gpt-4o、deepseek-chat、qwen-max等）
            api_key: API密钥
            base_url: 自定义基础URL（可选）
            timeout: 超时时间（秒）
            max_retries: 最大重试次数
        """
        self.model_name = model_name
        self.api_key = api_key
        
        # 创建通用客户端
        self.client = ModelAPIFactory.create_client(
            model_name=model_name,
            api_key=api_key,
            custom_base_url=base_url,
            timeout=timeout,
            max_retries=max_retries
        )
        
        # 获取模型端点
        self.endpoint = ModelAPIFactory.get_endpoint(model_name)
        
        # 判断模型类型（用于适配请求格式）
        self.model_type = self._detect_model_type()
    
    def _detect_model_type(self) -> str:
        """
        检测模型类型
        
        Returns:
            str: 模型类型（openai/anthropic/qwen/deepseek）
        """
        if "gpt" in self.model_name.lower():
            return "openai"
        elif "claude" in self.model_name.lower():
            return "anthropic"
        elif "qwen" in self.model_name.lower():
            return "qwen"
        elif "deepseek" in self.model_name.lower():
            return "deepseek"
        else:
            return "openai"  # 默认使用OpenAI格式
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        对话补全（统一接口）
        
        Args:
            messages: 消息列表，格式：[{"role": "user", "content": "..."}]
            temperature: 温度（0.0~1.0）
            max_tokens: 最大token数（可选）
            response_format: 响应格式（"json"或None）
            **kwargs: 其他模型特定参数
            
        Returns:
            str: 模型生成的文本
            
        Raises:
            APIError: API调用失败
        """
        # 根据模型类型构建请求
        if self.model_type == "openai" or self.model_type == "deepseek":
            return self._openai_chat(messages, temperature, max_tokens, response_format, **kwargs)
        elif self.model_type == "anthropic":
            return self._anthropic_chat(messages, temperature, max_tokens, **kwargs)
        elif self.model_type == "qwen":
            return self._qwen_chat(messages, temperature, max_tokens, response_format, **kwargs)
        else:
            raise APIError(f"不支持的模型类型：{self.model_type}")
    
    def _openai_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        response_format: Optional[str],
        **kwargs
    ) -> str:
        """
        OpenAI格式的对话补全（兼容GPT-4o、DeepSeek等）
        """
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        # JSON响应格式
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}
        
        # 添加额外参数
        payload.update(kwargs)
        
        try:
            response = self.client.send_post_request(self.endpoint, payload)
            
            # 提取生成文本
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0]["message"]["content"]
                return content.strip()
            else:
                raise APIError("响应格式异常：缺少choices字段")
        except Exception as e:
            raise APIError(f"OpenAI API调用失败：{str(e)}") from e
    
    def _anthropic_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        **kwargs
    ) -> str:
        """
        Anthropic格式的对话补全（Claude系列）
        """
        # Claude需要特殊的请求头
        custom_headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096
        }
        
        payload.update(kwargs)
        
        try:
            response = self.client.send_post_request(self.endpoint, payload, custom_headers)
            
            # Claude响应格式
            if "content" in response and len(response["content"]) > 0:
                return response["content"][0]["text"].strip()
            else:
                raise APIError("响应格式异常：缺少content字段")
        except Exception as e:
            raise APIError(f"Claude API调用失败：{str(e)}") from e
    
    def _qwen_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        response_format: Optional[str],
        **kwargs
    ) -> str:
        """
        通义千问格式的对话补全
        """
        # 通义千问API特殊格式
        payload = {
            "model": self.model_name,
            "input": {
                "messages": messages
            },
            "parameters": {
                "temperature": temperature
            }
        }
        
        if max_tokens:
            payload["parameters"]["max_tokens"] = max_tokens
        
        if response_format == "json":
            payload["parameters"]["result_format"] = "json"
        
        payload.update(kwargs)
        
        try:
            response = self.client.send_post_request(self.endpoint, payload)
            
            # 通义千问响应格式
            if "output" in response and "text" in response["output"]:
                return response["output"]["text"].strip()
            else:
                raise APIError("响应格式异常：缺少output.text字段")
        except Exception as e:
            raise APIError(f"通义千问API调用失败：{str(e)}") from e
    
    def parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """
        解析JSON格式的响应
        
        Args:
            response_text: 模型返回的文本
            
        Returns:
            Dict[str, Any]: 解析后的JSON对象
            
        Raises:
            APIError: JSON解析失败
        """
        try:
            # 尝试直接解析
            return json.loads(response_text)
        except json.JSONDecodeError:
            # 尝试提取JSON代码块
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                json_str = response_text[json_start:json_end].strip()
                return json.loads(json_str)
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                json_str = response_text[json_start:json_end].strip()
                return json.loads(json_str)
            else:
                raise APIError(f"无法解析JSON响应：{response_text}")
    
    def generate_structured_output(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        生成结构化输出（自动解析JSON）
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            temperature: 温度
            max_tokens: 最大token数
            
        Returns:
            Dict[str, Any]: 结构化数据
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response_text = self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format="json"
        )
        
        return self.parse_json_response(response_text)
    
    def close(self):
        """关闭客户端"""
        self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def __repr__(self) -> str:
        return f"<LLMClient(model={self.model_name}, type={self.model_type})>"
