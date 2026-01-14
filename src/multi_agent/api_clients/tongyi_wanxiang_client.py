# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - 通义万相API客户端
阿里云通义万相图像生成服务
"""
import requests
import json
import base64
from pathlib import Path
from typing import Optional, Dict, Any, Literal
import time


class TongyiWanxiangClient:
    """
    通义万相图像生成客户端
    支持文生图、图生图功能
    """
    
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis",
        timeout: int = 180
    ):
        """
        初始化通义万相客户端
        
        Args:
            api_key: 阿里云API Key
            base_url: API地址
            timeout: 请求超时时间
        """
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable"  # 启用异步模式
        }
    
    def text_to_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        style: str = "anime",
        n: int = 1
    ) -> Optional[bytes]:
        """
        文本生成图像
        
        Args:
            prompt: 正向提示词
            negative_prompt: 负向提示词
            width: 图像宽度
            height: 图像高度
            style: 风格（anime/realistic/portrait等）
            n: 生成数量
            
        Returns:
            bytes: 图像数据（PNG格式），失败返回None
        """
        payload = {
            "model": "wanx-v1",
            "input": {
                "prompt": prompt,
                "negative_prompt": negative_prompt
            },
            "parameters": {
                "style": f"<{style}>",
                "size": f"{width}*{height}",
                "n": n
            }
        }
        
        try:
            # 提交任务
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            task_id = result.get("output", {}).get("task_id")
            
            if not task_id:
                print(f"未获取到任务ID: {result}")
                return None
            
            # 等待任务完成
            image_url = self._wait_for_task(task_id)
            
            if not image_url:
                return None
            
            # 下载图像
            return self._download_image(image_url)
        
        except Exception as e:
            print(f"通义万相生成失败: {str(e)}")
            return None
    
    def image_to_image(
        self,
        prompt: str,
        init_image_path: str,
        negative_prompt: str = "",
        strength: float = 0.5
    ) -> Optional[bytes]:
        """
        图像生成图像（图像编辑）
        
        Args:
            prompt: 提示词
            init_image_path: 初始图像路径
            negative_prompt: 负向提示词
            strength: 变化强度（0.0-1.0）
            
        Returns:
            bytes: 图像数据，失败返回None
        """
        # 读取并编码图像
        try:
            with open(init_image_path, 'rb') as f:
                init_image_data = base64.b64encode(f.read()).decode()
        except Exception as e:
            print(f"读取初始图像失败: {str(e)}")
            return None
        
        # 使用图生图接口
        payload = {
            "model": "wanx-v1",
            "input": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "ref_img": init_image_data
            },
            "parameters": {
                "ref_strength": strength
            }
        }
        
        try:
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            task_id = result.get("output", {}).get("task_id")
            
            if not task_id:
                return None
            
            # 等待任务完成
            image_url = self._wait_for_task(task_id)
            
            if not image_url:
                return None
            
            return self._download_image(image_url)
        
        except Exception as e:
            print(f"通义万相图生图失败: {str(e)}")
            return None
    
    def _wait_for_task(
        self,
        task_id: str,
        poll_interval: int = 5,
        max_wait_time: int = 180
    ) -> Optional[str]:
        """
        等待任务完成
        
        Args:
            task_id: 任务ID
            poll_interval: 轮询间隔（秒）
            max_wait_time: 最大等待时间（秒）
            
        Returns:
            str: 图像URL，失败返回None
        """
        query_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
        elapsed_time = 0
        
        while elapsed_time < max_wait_time:
            try:
                response = requests.get(query_url, headers=self.headers, timeout=30)
                response.raise_for_status()
                
                result = response.json()
                task_status = result.get("output", {}).get("task_status")
                
                if task_status == "SUCCEEDED":
                    results = result.get("output", {}).get("results", [])
                    if results and len(results) > 0:
                        return results[0].get("url")
                    return None
                elif task_status == "FAILED":
                    print(f"任务失败: {result.get('output', {}).get('message')}")
                    return None
                
                # 继续等待
                print(f"生成中... 已等待 {elapsed_time}秒")
                time.sleep(poll_interval)
                elapsed_time += poll_interval
            
            except Exception as e:
                print(f"查询任务状态失败: {str(e)}")
                time.sleep(poll_interval)
                elapsed_time += poll_interval
        
        print("任务超时")
        return None
    
    def _download_image(self, image_url: str) -> Optional[bytes]:
        """
        下载图像
        
        Args:
            image_url: 图像URL
            
        Returns:
            bytes: 图像数据
        """
        try:
            response = requests.get(image_url, timeout=60)
            response.raise_for_status()
            return response.content
        except Exception as e:
            print(f"下载图像失败: {str(e)}")
            return None
    
    def save_image(self, image_data: bytes, output_path: str):
        """
        保存图像到文件
        
        Args:
            image_data: 图像数据
            output_path: 输出路径
        """
        with open(output_path, 'wb') as f:
            f.write(image_data)
    
    def batch_generate(
        self,
        prompts: list[str],
        output_dir: str = ".",
        width: int = 1024,
        height: int = 1024,
        style: str = "anime"
    ) -> list[str]:
        """
        批量生成图像
        
        Args:
            prompts: 提示词列表
            output_dir: 输出目录
            width: 图像宽度
            height: 图像高度
            style: 风格
            
        Returns:
            list: 生成的图像路径列表
        """
        output_paths = []
        output_path_obj = Path(output_dir)
        output_path_obj.mkdir(parents=True, exist_ok=True)
        
        for idx, prompt in enumerate(prompts):
            print(f"生成图像 {idx+1}/{len(prompts)}: {prompt[:50]}...")
            
            image_data = self.text_to_image(
                prompt=prompt,
                width=width,
                height=height,
                style=style
            )
            
            if image_data:
                output_file = output_path_obj / f"tongyi_{idx+1:03d}.png"
                self.save_image(image_data, str(output_file))
                output_paths.append(str(output_file))
            
            # 避免请求过快
            time.sleep(2)
        
        return output_paths
    
    def close(self):
        """关闭客户端"""
        pass


# 风格预设
STYLE_PRESETS = {
    "anime": "<anime>",
    "二次元": "<anime>",
    "写实": "<realistic>",
    "3D": "<3d cartoon>",
    "油画": "<oil painting>",
    "水彩": "<watercolor>",
    "素描": "<sketch>",
    "赛博朋克": "<cyberpunk>"
}
