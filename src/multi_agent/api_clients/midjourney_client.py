# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - MidJourney API客户端
通过第三方MidJourney API服务生成高质量CG
"""
from typing import Dict, Any, Optional, List
import time
from src.multi_agent.api_clients.common_client import CommonAPIClient, APIError


class MidJourneyClient:
    """
    MidJourney API客户端
    支持MetaChat代理服务，需要API Key和App ID双重认证
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.mmchat.xyz/open/v1",
        app_id: str = "",
        timeout: int = 300,  # MidJourney生成较慢，默认5分钟
        max_retries: int = 3
    ):
        """
        初始化MidJourney客户端
        
        Args:
            api_key: API密钥（x-token）
            base_url: API基础URL（MetaChat代理）
            app_id: App ID（MetaChat需要）
            timeout: 超时时间（秒）
            max_retries: 最大重试次数
        """
        self.api_key = api_key
        self.app_id = app_id
        self.base_url = base_url.rstrip('/')
        
        # 创建通用客户端
        self.client = CommonAPIClient(
            api_key=api_key,
            base_url=base_url,
            model_name="midjourney-v6",
            timeout=timeout,
            max_retries=max_retries
        )
    
    def _get_headers(self) -> Dict[str, str]:
        """构建MetaChat代理所需的请求头"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        if self.app_id:
            headers["X-App-ID"] = self.app_id
        return headers
    
    def imagine(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        version: str = "6",
        quality: str = "1",
        stylize: int = 100,
        chaos: int = 0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成图像（异步任务）
        
        Args:
            prompt: 提示词
            aspect_ratio: 宽高比（1:1/4:3/16:9/9:16等）
            version: MidJourney版本（5.2/6等）
            quality: 质量（0.25/0.5/1/2）
            stylize: 风格化强度（0-1000）
            chaos: 多样性（0-100）
            **kwargs: 其他参数
            
        Returns:
            Dict[str, Any]: 任务信息（包含task_id）
        """
        endpoint = "/imagine"
        
        # 构建完整提示词（包含参数）
        full_prompt = prompt
        full_prompt += f" --ar {aspect_ratio}"
        full_prompt += f" --v {version}"
        full_prompt += f" --q {quality}"
        full_prompt += f" --s {stylize}"
        if chaos > 0:
            full_prompt += f" --c {chaos}"
        
        payload = {
            "prompt": full_prompt,
            **kwargs
        }
        
        try:
            response = self.client.send_post_request(
                endpoint, 
                payload,
                custom_headers=self._get_headers()
            )
            
            # MetaChat代理返回格式：{"status": "Success", "data": {...}}
            if isinstance(response, dict):
                if response.get("status") == "Success":
                    return response.get("data", response)
                elif response.get("status") == "Fail":
                    raise APIError(f"MidJourney错误：{response.get('message', '未知错误')}")
            
            # 兼容其他格式
            if "task_id" in response or "id" in response:
                return response
            else:
                raise APIError("响应中未找到任务ID")
        
        except Exception as e:
            raise APIError(f"MidJourney任务提交失败：{str(e)}") from e
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        查询任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict[str, Any]: 任务状态信息
        """
        endpoint = f"/task/{task_id}"
        
        try:
            response = self.client.send_get_request(endpoint)
            return response
        
        except Exception as e:
            raise APIError(f"查询任务状态失败：{str(e)}") from e
    
    def wait_for_completion(
        self,
        task_id: str,
        poll_interval: int = 10,
        max_wait_time: int = 600
    ) -> Dict[str, Any]:
        """
        等待任务完成
        
        Args:
            task_id: 任务ID
            poll_interval: 轮询间隔（秒）
            max_wait_time: 最大等待时间（秒）
            
        Returns:
            Dict[str, Any]: 完成后的任务信息
        """
        elapsed = 0
        
        while elapsed < max_wait_time:
            status = self.get_task_status(task_id)
            
            task_status = status.get("status", "").lower()
            
            if task_status == "completed" or task_status == "success":
                return status
            elif task_status == "failed" or task_status == "error":
                error_msg = status.get("error", "未知错误")
                raise APIError(f"任务失败：{error_msg}")
            
            # 继续等待
            time.sleep(poll_interval)
            elapsed += poll_interval
        
        raise APIError(f"任务超时（{max_wait_time}秒）")
    
    def download_image(self, image_url: str, output_path: str):
        """
        下载生成的图像
        
        Args:
            image_url: 图像URL
            output_path: 保存路径
        """
        try:
            self.client.download_file(image_url, output_path)
        except Exception as e:
            raise APIError(f"下载图像失败：{str(e)}") from e
    
    def generate_and_download(
        self,
        prompt: str,
        output_path: str,
        aspect_ratio: str = "1:1",
        version: str = "6",
        quality: str = "1",
        stylize: int = 100,
        **kwargs
    ) -> str:
        """
        生成图像并自动下载（同步方法）
        
        Args:
            prompt: 提示词
            output_path: 输出路径
            aspect_ratio: 宽高比
            version: MidJourney版本
            quality: 质量
            stylize: 风格化强度
            **kwargs: 其他参数
            
        Returns:
            str: 保存的图像路径
        """
        # 1. 提交任务
        task_info = self.imagine(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            version=version,
            quality=quality,
            stylize=stylize,
            **kwargs
        )
        
        task_id = task_info.get("task_id") or task_info.get("id")
        if not task_id:
            raise APIError("未获取到任务ID")
        
        # 2. 等待完成
        result = self.wait_for_completion(task_id)
        
        # 3. 下载图像
        image_url = result.get("image_url") or result.get("url")
        if not image_url:
            raise APIError("未获取到图像URL")
        
        self.download_image(image_url, output_path)
        
        return output_path
    
    def upscale(
        self,
        task_id: str,
        index: int = 1
    ) -> Dict[str, Any]:
        """
        放大指定图像（MidJourney生成4张图后可选择放大）
        
        Args:
            task_id: 原始任务ID
            index: 图像索引（1-4）
            
        Returns:
            Dict[str, Any]: 放大任务信息
        """
        endpoint = "/upscale"
        
        payload = {
            "task_id": task_id,
            "index": index
        }
        
        try:
            response = self.client.send_post_request(endpoint, payload)
            return response
        
        except Exception as e:
            raise APIError(f"图像放大失败：{str(e)}") from e
    
    def vary(
        self,
        task_id: str,
        index: int = 1,
        strength: str = "strong"
    ) -> Dict[str, Any]:
        """
        变体生成（基于已生成的图像）
        
        Args:
            task_id: 原始任务ID
            index: 图像索引（1-4）
            strength: 变化强度（subtle/strong）
            
        Returns:
            Dict[str, Any]: 变体任务信息
        """
        endpoint = "/vary"
        
        payload = {
            "task_id": task_id,
            "index": index,
            "strength": strength
        }
        
        try:
            response = self.client.send_post_request(endpoint, payload)
            return response
        
        except Exception as e:
            raise APIError(f"变体生成失败：{str(e)}") from e
    
    def close(self):
        """关闭客户端"""
        self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def __repr__(self) -> str:
        return f"<MidJourneyClient(base_url={self.base_url})>"
