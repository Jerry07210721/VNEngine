# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - FLUX API客户端
支持FLUX.2 Pro/Max, FLUX.1 Kontext图像生成，基于MetaChat API
"""

import requests
from typing import Dict, Any, List, Optional
from pathlib import Path
from .base_client import BaseAPIClient, APIError


class FluxClient(BaseAPIClient):
    """FLUX API客户端"""
    
    def __init__(
        self,
        app_id: str,
        api_key: str,
        base_url: str = "https://api.mmchat.xyz",
        model: str = "flux-kontext",
        timeout: int = 1800,
        poll_interval: float = 5.0
    ):
        """
        初始化FLUX客户端
        
        Args:
            app_id: MetaChat App ID
            api_key: MetaChat API Key
            base_url: API基础URL
            model: 模型版本（flux-kontext/flux-2-pro/flux-2-max）
            timeout: 超时时间（秒）
            poll_interval: 轮询间隔（秒）
        """
        super().__init__(base_url, api_key, timeout, logger_name="FluxClient")
        self.app_id = app_id
        self.model = model
        self.poll_interval = poll_interval
        
        self.logger.info(f"FLUX客户端初始化: model={model}, poll_interval={poll_interval}s")
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "Content-Type": "application/json",
            "X-App-ID": self.app_id,
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def generate(
        self,
        prompt: str,
        params: Optional[Dict[str, Any]] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        图像生成
        
        Args:
            prompt: 提示词（支持中英文，不超过5000字）
            params: 绘图参数（aspect/num/mode）
            images: 参考图列表（最多3张）
            model: 模型版本（可选）
        
        Returns:
            任务信息 {"id": 任务ID, "prompt": 最终提示词, "model": 模型版本}
        """
        payload = {
            "prompt": prompt,
            "model": model or self.model
        }

        # 确保 params 至少包含 mode，避免后端 null 报错
        params = params or {}
        if "mode" not in params or not params.get("mode"):
            params["mode"] = "pro"
        if "aspect" not in params:
            params["aspect"] = "1:1"
        payload["params"] = params
        
        if images:
            if len(images) > 3:
                raise ValueError(f"参考图最多3张，当前为: {len(images)}")
            payload["images"] = images
        
        self.logger.info(f"发起FLUX图像生成: prompt='{prompt[:50]}...', model={payload['model']}")
        
        response = self.post("/open/v1/image/generate", data=payload)
        
        if response.get("status") == "Success":
            task_data = response.get("data", {})
            task_id = task_data.get("id")
            self.logger.info(f"图像生成任务创建成功: task_id={task_id}")
            return task_data
        else:
            raise APIError(f"图像生成失败: {response.get('message')}")
    
    def query_result(self, task_id: str) -> Dict[str, Any]:
        """
        查询任务结果
        
        Args:
            task_id: 任务ID
        
        Returns:
            任务详情
        """
        response = self.get(f"/open/v1/image/result/{task_id}")
        
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
            timeout: 超时时间（秒）
            poll_interval: 轮询间隔（秒）
        
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
            
            # 任务状态: submitted=排队中, in_progress=执行中, success=成功, failure=失败
            if status == "success":
                self.logger.info(f"任务成功完成: task_id={task_id}")
                return True
            elif status == "failure":
                fail_reason = result.get("fail_reason", "未知错误")
                raise APIError(f"任务失败: {fail_reason}", response_data=result)
            
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
        save_dir: str,
        params: Optional[Dict[str, Any]] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        timeout: Optional[float] = None,
        model: Optional[str] = None,
    ) -> tuple[bool, List[str], List[str]]:
        """
        生成图像并下载（一站式接口）
        
        Returns:
            (是否成功, 本地文件路径列表, 图像URL列表)
        """
        try:
            task_info = self.generate(prompt, params, images, model=model)
            task_id = task_info["id"]

            result = self.wait_for_completion(task_id, timeout)

            image_urls = result.get("image_urls", [])
            if not image_urls:
                self.logger.error("任务完成但未获取到图像URL")
                return False, [], []

            save_dir_obj = Path(save_dir)
            save_dir_obj.mkdir(parents=True, exist_ok=True)

            local_paths: List[str] = []
            for idx, image_url in enumerate(image_urls):
                save_path = save_dir_obj / f"{task_id}_{idx+1}.png"
                if self.download_image(image_url, str(save_path)):
                    local_paths.append(str(save_path))

            return len(local_paths) == len(image_urls), local_paths, image_urls

        except Exception as e:
            self.logger.error(f"生成并下载图像失败: {e}")
            return False, [], []
    
    def batch_generate(
        self,
        prompts: List[str],
        save_dir: str,
        params: Optional[Dict[str, Any]] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        timeout: Optional[float] = None,
        model: Optional[str] = None,
    ) -> List[tuple[bool, str, List[str]]]:
        """
        批量生成图像
        
        Args:
            prompts: 提示词列表
            save_dir: 保存目录
            params: 绘图参数
            images: 参考图列表
            timeout: 每个任务的超时时间
        
        Returns:
            结果列表: [(是否成功, 提示词, 图像URL列表), ...]
        """
        results = []
        
        for idx, prompt in enumerate(prompts):
            self.logger.info(f"批量生成进度: {idx+1}/{len(prompts)}")
            
            success, image_urls = self.generate_and_download(
                prompt=prompt,
                save_dir=save_dir,
                params=params,
                images=images,
                timeout=timeout,
                model=model,
            )
            
            results.append((success, prompt, image_urls))
        
        successful_count = sum(1 for success, _, _ in results if success)
        self.logger.info(f"批量生成完成: 成功{successful_count}/{len(prompts)}")
        
        return results
