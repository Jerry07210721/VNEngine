# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - FLUX API客户端
通过MetaChat代理调用FLUX图像生成服务
"""
from typing import Dict, Any, Optional
import time
from src.multi_agent.api_clients.common_client import CommonAPIClient, APIError


class FLUXClient:
    """
    FLUX API客户端（MetaChat代理）
    支持文生图和图生图
    """
    
    def __init__(
        self,
        api_key: str,
        app_id: Optional[str] = None,
        base_url: str = "https://api.mmchat.xyz/open/v1",
        timeout: int = 180,
        max_retries: int = 3
    ):
        """
        初始化FLUX客户端
        
        Args:
            api_key: API密钥
            app_id: App ID（MetaChat鉴权需要）
            base_url: API基础URL（MetaChat代理）
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
            model_name="flux-2-pro",
            timeout=timeout,
            max_retries=max_retries
        )
    
    def _get_headers(self) -> Dict[str, str]:
        """构建MetaChat代理所需的请求头"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        # 添加X-App-ID头（如果提供）
        if self.app_id:
            headers["X-App-ID"] = self.app_id
        return headers
    
    def text_to_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        style: str = "anime",
        steps: int = 28,
        guidance: float = 3.5,
        seed: Optional[int] = None,
        **kwargs
    ) -> bytes:
        """
        文生图
        
        Args:
            prompt: 正向提示词
            negative_prompt: 负向提示词（注：FLUX API不支持，仅保留接口兼容性）
            width: 图像宽度
            height: 图像高度
            style: 风格预设（anime/realistic/artistic）
            steps: 生成步数（注：FLUX API不支持，仅保留接口兼容性）
            guidance: 引导系数（注：FLUX API不支持，仅保留接口兼容性）
            seed: 随机种子
            **kwargs: 其他参数
            
        Returns:
            bytes: 图像数据
        """
        endpoint = "/image/generate"
        
        # 添加风格预设到prompt
        style_prompts = {
            "anime": "anime style, manga art, Japanese animation, ",
            "realistic": "photorealistic, highly detailed, 8k resolution, ",
            "artistic": "digital art, trending on artstation, masterpiece, "
        }
        final_prompt = prompt
        if style in style_prompts:
            final_prompt = style_prompts[style] + prompt
        
        # 计算适合的aspect ratio
        aspect = self._calculate_aspect_ratio(width, height)
        
        # 构建请求载荷（按照MetaChat API文档格式）
        payload = {
            "prompt": final_prompt,
            "model": "flux-2-pro",  # 使用FLUX.2 Pro模型
            "params": {
                "aspect": aspect,
                "num": 1
            }
        }
        
        try:
            response = self.client.send_post_request(
                endpoint,
                payload,
                custom_headers=self._get_headers()
            )
            
            # MetaChat代理返回格式：{"status": "Success", "data": {"id": "..."}}
            if isinstance(response, dict):
                if response.get("status") == "Success":
                    task_id = response.get("data", {}).get("id")
                    if task_id:
                        return self._wait_for_result(task_id)
                    else:
                        raise APIError("响应中未找到task_id")
                elif response.get("status") == "Fail":
                    raise APIError(f"FLUX错误：{response.get('message', '未知错误')}")
            
            raise APIError("FLUX响应格式错误")
        
        except Exception as e:
            raise APIError(f"FLUX文生图失败：{str(e)}") from e
    
    def _calculate_aspect_ratio(self, width: int, height: int) -> str:
        """
        根据width/height计算最接近的aspect ratio
        
        Args:
            width: 宽度
            height: 高度
            
        Returns:
            str: aspect ratio（如"16:9", "1:1"等）
        """
        ratio = width / height
        
        # 支持的aspect ratio列表（按照比例排序）
        aspects = [
            ("9:21", 9/21),
            ("2:3", 2/3),
            ("3:4", 3/4),
            ("9:16", 9/16),
            ("1:1", 1),
            ("16:9", 16/9),
            ("4:3", 4/3),
            ("3:2", 3/2),
            ("21:9", 21/9)
        ]
        
        # 找到最接近的aspect ratio
        closest_aspect = "1:1"
        min_diff = float('inf')
        
        for aspect_name, aspect_ratio in aspects:
            diff = abs(ratio - aspect_ratio)
            if diff < min_diff:
                min_diff = diff
                closest_aspect = aspect_name
        
        return closest_aspect
    
    def _wait_for_result(
        self,
        task_id: str,
        poll_interval: int = 5,
        max_wait: int = 180
    ) -> bytes:
        """
        等待任务完成并获取结果
        
        Args:
            task_id: 任务ID
            poll_interval: 轮询间隔（秒）
            max_wait: 最大等待时间（秒）
            
        Returns:
            bytes: 图像数据
        """
        # 使用官方API: GET /open/v1/image/result/{id}
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                # 使用正确的endpoint: /image/result/{id}
                endpoint = f"/image/result/{task_id}"
                response = self.client.send_get_request(
                    endpoint,
                    custom_headers=self._get_headers()
                )
                
                if isinstance(response, dict):
                    if response.get("status") == "Success":
                        data = response.get("data", {})
                        task_status = data.get("status")
                        
                        # 任务状态：submitted（排队中）、in_progress（执行中）、failure（失败）、success（成功）
                        if task_status == "success":
                            # 获取图像URL列表
                            image_urls = data.get("image_urls", [])
                            if image_urls and len(image_urls) > 0:
                                image_url = image_urls[0]
                                # 下载图像
                                import requests
                                img_response = requests.get(image_url, timeout=30)
                                img_response.raise_for_status()
                                return img_response.content
                            else:
                                raise APIError("结果中未找到image_urls")
                        
                        elif task_status == "failure":
                            fail_reason = data.get("fail_reason", "未知错误")
                            raise APIError(f"FLUX任务失败：{fail_reason}")
                        
                        elif task_status in ["submitted", "in_progress"]:
                            # 任务进行中，继续等待
                            progress = data.get("progress", 0)
                            print(f"FLUX任务进度：{progress}%")
                            time.sleep(poll_interval)
                        else:
                            raise APIError(f"未知任务状态：{task_status}")
                    
                    elif response.get("status") == "Fail":
                        raise APIError(f"查询失败：{response.get('message', '未知错误')}")
            
            except APIError:
                raise
            except Exception as e:
                raise APIError(f"查询任务状态失败：{str(e)}") from e
        
        raise APIError(f"等待任务完成超时（{max_wait}秒）")
    
    def image_to_image(
        self,
        init_image_path: str,
        prompt: str,
        negative_prompt: str = "",
        strength: float = 0.6,
        steps: int = 25,
        cfg_scale: float = 7.5,
        **kwargs
    ) -> bytes:
        """
        图生图（基于参考图生成）
        
        Args:
            init_image_path: 初始图像路径
            prompt: 提示词
            negative_prompt: 负向提示词（不支持）
            strength: 变化强度（0-1）
            steps: 生成步数（不支持）
            cfg_scale: 引导系数（不支持）
            **kwargs: 其他参数
            
        Returns:
            bytes: 图像数据
        """
        import base64
        from PIL import Image
        import io
        
        endpoint = "/image/generate"
        
        try:
            # 加载并处理参考图
            img = Image.open(init_image_path)
            
            # 转换为bytes并编码为base64
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='PNG')
            img_bytes = img_buffer.getvalue()
            b64_data = base64.b64encode(img_bytes).decode('utf-8')
            data_url = f"data:image/png;base64,{b64_data}"
            
            # 获取图片尺寸
            width, height = img.size
            aspect = self._calculate_aspect_ratio(width, height)
            
            # 构建请求（包含参考图）
            payload = {
                "prompt": prompt,
                "model": "flux-2-pro",
                "params": {
                    "aspect": aspect,
                    "num": 1
                },
                "images": [
                    {
                        "b64": data_url,
                        "type": "image/png",
                        "size": len(img_bytes),
                        "w": width,
                        "h": height
                    }
                ]
            }
            
            response = self.client.send_post_request(
                endpoint,
                payload,
                custom_headers=self._get_headers()
            )
            
            # 处理响应
            if isinstance(response, dict):
                if response.get("status") == "Success":
                    task_id = response.get("data", {}).get("id")
                    if task_id:
                        return self._wait_for_result(task_id)
                    else:
                        raise APIError("响应中未找到task_id")
                elif response.get("status") == "Fail":
                    raise APIError(f"FLUX错误：{response.get('message', '未知错误')}")
            
            raise APIError("FLUX响应格式错误")
        
        except Exception as e:
            raise APIError(f"FLUX图生图失败：{str(e)}") from e
    
    def save_image(self, image_data: bytes, output_path: str) -> bool:
        """
        保存图像到文件
        
        Args:
            image_data: 图像数据
            output_path: 输出路径
            
        Returns:
            bool: 是否成功
        """
        try:
            with open(output_path, 'wb') as f:
                f.write(image_data)
            return True
        except Exception as e:
            raise APIError(f"保存图像失败：{str(e)}") from e
    
    def close(self):
        """关闭HTTP会话"""
        if self.client:
            self.client.close()
