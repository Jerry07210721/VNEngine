# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - Midjourney API客户端
支持图像生成、图像拆分、任务查询，基于MetaChat API
"""

import time
import requests
from typing import Dict, Any, List, Optional
from pathlib import Path
from .base_client import BaseAPIClient, APIError, APITimeoutError


class MidjourneyClient(BaseAPIClient):
    """Midjourney API客户端"""
    
    def __init__(
        self,
        app_id: str,
        api_key: str,
        base_url: str = "https://api.mmchat.xyz",
        model: str = "mj-v7",
        timeout: int = 1800,
        poll_interval: float = 5.0
    ):
        """
        初始化Midjourney客户端
        
        Args:
            app_id: MetaChat App ID
            api_key: MetaChat API Key
            base_url: API基础URL
            model: 模型版本（mj-v7/mj-v61/mj-niji-6）
            timeout: 超时时间（秒）
            poll_interval: 轮询间隔（秒）
        """
        super().__init__(base_url, api_key, timeout, logger_name="MidjourneyClient")
        self.app_id = app_id
        self.model = model
        self.poll_interval = poll_interval
        
        self.logger.info(f"Midjourney客户端初始化: model={model}, poll_interval={poll_interval}s")
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "Content-Type": "application/json",
            "X-App-ID": self.app_id,
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def imagine(
        self,
        prompt: str,
        params: Optional[Dict[str, Any]] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        图像生成（创建四宫格图像）
        
        Args:
            prompt: 提示词（支持中英文）
            params: 绘图参数（aspect/stylize/quality/chaos/style/seed等）
            images: 参考图列表
            model: 模型版本（可选，默认使用初始化时的值）
        
        Returns:
            任务信息 {"id": 任务ID, "prompt": 最终提示词, "model": 模型版本}
        """
        payload = {
            "prompt": prompt,
            "model": model or self.model
        }
        
        if params:
            payload["params"] = params
        
        if images:
            payload["images"] = images
        
        self.logger.info(f"发起Midjourney图像生成: prompt='{prompt[:50]}...', model={payload['model']}")
        
        response = self.post("/open/v1/midjourney/imagine", data=payload)
        
        if response.get("status") == "Success":
            task_data = response.get("data", {})
            task_id = task_data.get("id")
            self.logger.info(f"图像生成任务创建成功: task_id={task_id}")
            return task_data
        else:
            raise APIError(f"图像生成失败: {response.get('message')}")
    
    def separate(self, task_id: str, index: int) -> Dict[str, Any]:
        """
        图像拆分（从四宫格中提取单张图像）
        
        Args:
            task_id: 原始任务ID
            index: 图像索引（1=左上U1, 2=右上U2, 3=左下U3, 4=右下U4）
        
        Returns:
            新任务信息
        """
        if index not in [1, 2, 3, 4]:
            raise ValueError(f"图像索引必须为1-4，当前为: {index}")
        
        payload = {
            "id": task_id,
            "index": index
        }
        
        self.logger.info(f"发起图像拆分: task_id={task_id}, index={index}")
        
        response = self.post("/open/v1/midjourney/separate", data=payload)
        
        if response.get("status") == "Success":
            task_data = response.get("data", {})
            new_task_id = task_data.get("id")
            self.logger.info(f"图像拆分任务创建成功: new_task_id={new_task_id}")
            return task_data
        else:
            raise APIError(f"图像拆分失败: {response.get('message')}")
    
    def query_result(self, task_id: str) -> Dict[str, Any]:
        """
        查询任务结果
        
        Args:
            task_id: 任务ID
        
        Returns:
            任务详情
        """
        response = self.get(f"/open/v1/midjourney/result/{task_id}")
        
        if response.get("status") == "Success":
            return response.get("data", {})
        else:
            raise APIError(f"查询任务失败: {response.get('message')}")
    
    def wait_for_completion(
        self,
        task_id: str,
        timeout: Optional[float] = None,
        poll_interval: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        等待任务完成（轮询）
        
        Args:
            task_id: 任务ID
            timeout: 超时时间（秒），默认使用初始化时的值
            poll_interval: 轮询间隔（秒），默认使用初始化时的值
        
        Returns:
            完成后的任务详情
        """
        timeout = timeout or self.timeout
        poll_interval = poll_interval or self.poll_interval
        
        self.logger.info(f"开始等待任务完成: task_id={task_id}, timeout={timeout}s")
        
        def check_status():
            return self.query_result(task_id)
        
        def is_complete(result):
            status = result.get("status")
            progress = result.get("progress", 0)
            
            self.logger.debug(f"任务状态: status={status}, progress={progress}%")
            
            # 支持数字(10/20/30/40)与字符串(submitted/in_progress/success/failure)
            if status in (30, "success"):
                self.logger.info(f"任务成功完成: task_id={task_id}")
                return True
            elif status in (40, "failure"):
                fail_reason = result.get("fail_reason", "未知错误")
                raise APIError(f"任务失败: {fail_reason}", response_data=result)
            elif status in (10, 20, "submitted", "in_progress"):
                return False
            else:
                # 未知状态，继续轮询但输出告警
                self.logger.warning(f"未知任务状态: {status}, 继续轮询")
            
            return False
        
        return self.poll_until_complete(
            check_func=check_status,
            is_complete_func=is_complete,
            interval=poll_interval,
            max_wait=timeout
        )
    
    def download_image(self, image_url: str, save_path: str) -> bool:
        """
        下载图像
        
        Args:
            image_url: 图像URL
            save_path: 保存路径
        
        Returns:
            是否下载成功
        """
        try:
            self.logger.info(f"开始下载图像: {image_url}")
            
            response = requests.get(image_url, timeout=60)
            response.raise_for_status()
            
            # 确保目录存在
            save_path_obj = Path(save_path)
            save_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存图像
            with open(save_path, 'wb') as f:
                f.write(response.content)
            
            self.logger.info(f"图像下载成功: {save_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"图像下载失败: {e}")
            return False
    
    def generate_and_download(
        self,
        prompt: str,
        save_path: str,
        params: Optional[Dict[str, Any]] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        timeout: Optional[float] = None
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        生成图像并下载（一站式接口）
        
        Returns:
            (是否成功, 本地路径, 图像URL)
        """
        try:
            task_info = self.imagine(prompt, params, images)
            task_id = task_info["id"]

            result = self.wait_for_completion(task_id, timeout)

            image_url = result.get("image_url")
            if not image_url:
                self.logger.error("任务完成但未获取到图像URL")
                return False, None, None

            success = self.download_image(image_url, save_path)
            return success, save_path if success else None, image_url

        except Exception as e:
            self.logger.error(f"生成并下载图像失败: {e}")
            return False, None, None
    
    def generate_with_separate(
        self,
        prompt: str,
        save_dir: str,
        index: int = 1,
        params: Optional[Dict[str, Any]] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        timeout: Optional[float] = None
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        生成四宫格并拆分指定图像（完整流程）
        
        Args:
            prompt: 提示词
            save_dir: 保存目录
            index: 要拆分的图像索引（1-4）
            params: 绘图参数
            images: 参考图列表
            timeout: 超时时间
        
        Returns:
            (是否成功, 四宫格URL, 拆分后图像URL)
        """
        try:
            # 1. 生成四宫格
            task_info = self.imagine(prompt, params, images)
            task_id = task_info["id"]
            
            # 2. 等待四宫格完成
            result = self.wait_for_completion(task_id, timeout)
            grid_url = result.get("image_url")
            
            # 3. 拆分图像
            separate_info = self.separate(task_id, index)
            separate_task_id = separate_info["id"]
            
            # 4. 等待拆分完成
            separate_result = self.wait_for_completion(separate_task_id, timeout)
            single_url = separate_result.get("image_url")
            
            # 5. 下载拆分后的图像
            save_path = Path(save_dir) / f"{task_id}_U{index}.png"
            self.download_image(single_url, str(save_path))
            
            self.logger.info(f"完整流程成功: grid={grid_url}, single={single_url}")
            return True, grid_url, single_url
            
        except Exception as e:
            self.logger.error(f"完整流程失败: {e}")
            return False, None, None
