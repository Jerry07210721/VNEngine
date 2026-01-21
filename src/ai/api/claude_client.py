# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - Claude API客户端
支持Claude 4/4.1/4.5系列模型，基于MetaChat API
"""

from typing import Dict, Any, List, Optional, Union
from .base_client import BaseAPIClient


class ClaudeClient(BaseAPIClient):
    """Claude API客户端"""
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://llm-api.mmchat.xyz",
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 64000,
        timeout: int = 300
    ):
        """
        初始化Claude客户端
        
        Args:
            api_key: MetaChat API Key
            base_url: API基础URL
            model: 模型版本
            max_tokens: 最大生成token数
            timeout: 超时时间（秒）
        """
        super().__init__(base_url, api_key, timeout, logger_name="ClaudeClient")
        self.model = model
        self.max_tokens = max_tokens
        
        # Token计数统计
        self.token_stats = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }
        
        self.logger.info(f"Claude客户端初始化: model={model}, max_tokens={max_tokens}")
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }
    
    def create_message(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        temperature: float = 0.7,
        stream: bool = False,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """创建消息（调用Messages API）"""
        payload = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": messages,
            "stream": stream
        }
        if system:
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature
        
        self.logger.info(
            f"发起Claude对话请求: {len(messages)}条消息, max_tokens={payload['max_tokens']}"
        )
        
        response = self.post("/v1/messages", data=payload)
        
        # 更新token统计
        if "usage" in response:
            usage = response["usage"]
            self.token_stats["input_tokens"] += usage.get("input_tokens", 0)
            self.token_stats["output_tokens"] += usage.get("output_tokens", 0)
            self.token_stats["total_tokens"] = (
                self.token_stats["input_tokens"] + self.token_stats["output_tokens"]
            )
            
            self.logger.info(
                f"Token消耗: input={usage.get('input_tokens', 0)}, "
                f"output={usage.get('output_tokens', 0)}"
            )
        
        return response
    
    def generate_text(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        生成文本（简化接口）
        
        Args:
            prompt: 用户提示词
            system: 系统提示词（可选）
            temperature: 温度参数
            max_tokens: 最大生成token数
        
        Returns:
            生成的文本内容
        """
        messages = [{"role": "user", "content": prompt}]
        
        response = self.create_message(
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # 提取文本内容
        content_blocks = response.get("content", [])
        text = "".join(block.get("text", "") for block in content_blocks if isinstance(block, dict))
        return text
    
    def generate_structured_output(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        生成结构化输出（返回完整响应）
        
        Args:
            prompt: 用户提示词
            system: 系统提示词（可选）
            temperature: 温度参数
            max_tokens: 最大生成token数
        
        Returns:
            完整的API响应
        """
        messages = [{"role": "user", "content": prompt}]
        
        return self.create_message(
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens
        )
    
    def multi_turn_conversation(
        self,
        conversation_history: List[Dict[str, str]],
        new_message: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> tuple[str, List[Dict[str, str]]]:
        """
        多轮对话
        
        Args:
            conversation_history: 对话历史
            new_message: 新的用户消息
            system: 系统提示词
            temperature: 温度参数
            max_tokens: 最大生成token数
        
        Returns:
            (助手回复, 更新后的对话历史)
        """
        # 添加新消息到历史
        updated_history = conversation_history.copy()
        updated_history.append({"role": "user", "content": new_message})
        
        response = self.create_message(
            messages=updated_history,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # 提取助手回复
        content = response.get("content", [])
        assistant_reply = ""
        if isinstance(content, list) and len(content) > 0:
            assistant_reply = content[0].get("text", "")
        
        # 添加助手回复到历史
        updated_history.append({"role": "assistant", "content": assistant_reply})
        
        return assistant_reply, updated_history
    
    def get_token_stats(self) -> Dict[str, int]:
        """
        获取token统计信息
        
        Returns:
            token统计字典
        """
        return self.token_stats.copy()
    
    def reset_token_stats(self):
        """重置token统计"""
        self.token_stats = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }
    
    def estimate_cost(self, pricing_per_million: Dict[str, float]) -> float:
        """
        估算API成本
        
        Args:
            pricing_per_million: 价格配置，格式: {"input": 价格, "output": 价格}
        
        Returns:
            估算成本（美元）
        """
        input_cost = (self.token_stats["input_tokens"] / 1_000_000) * pricing_per_million.get("input", 0)
        output_cost = (self.token_stats["output_tokens"] / 1_000_000) * pricing_per_million.get("output", 0)
        
        return input_cost + output_cost
