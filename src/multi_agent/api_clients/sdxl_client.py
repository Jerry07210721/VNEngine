# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - SDXL API客户端
支持Stable Diffusion XL模型的图像生成
支持ControlNet（用于立绘差分生成）
"""
from typing import Dict, Any, Optional, List, Tuple
import time
import base64
from pathlib import Path
from src.multi_agent.api_clients.common_client import CommonAPIClient, APIError


class SDXLClient:
    """
    SDXL API客户端
    支持文生图、图生图、ControlNet等功能
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.stability.ai/v1",
        timeout: int = 120,
        max_retries: int = 3
    ):
        """
        初始化SDXL客户端
        
        Args:
            api_key: API密钥
            base_url: API基础URL
            timeout: 超时时间（秒）
            max_retries: 最大重试次数
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        
        # 创建通用客户端
        self.client = CommonAPIClient(
            api_key=api_key,
            base_url=base_url,
            model_name="sdxl",
            timeout=timeout,
            max_retries=max_retries
        )
    
    def text_to_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 30,
        cfg_scale: float = 7.0,
        sampler: str = "DPM++ 2M Karras",
        seed: Optional[int] = None,
        style_preset: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """
        文本生成图像
        
        Args:
            prompt: 正向提示词
            negative_prompt: 负向提示词
            width: 图像宽度
            height: 图像高度
            steps: 采样步数
            cfg_scale: CFG引导强度
            sampler: 采样器
            seed: 随机种子
            style_preset: 风格预设（anime/photographic等）
            **kwargs: 其他参数
            
        Returns:
            bytes: 图像二进制数据
        """
        endpoint = "/generation/stable-diffusion-xl-1024-v1-0/text-to-image"
        
        payload = {
            "text_prompts": [
                {"text": prompt, "weight": 1.0}
            ],
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "sampler": sampler
        }
        
        if negative_prompt:
            payload["text_prompts"].append({"text": negative_prompt, "weight": -1.0})
        
        if seed is not None:
            payload["seed"] = seed
        
        if style_preset:
            payload["style_preset"] = style_preset
        
        payload.update(kwargs)
        
        try:
            response = self.client.send_post_request(endpoint, payload)
            
            # 提取图像数据
            if "artifacts" in response and len(response["artifacts"]) > 0:
                image_base64 = response["artifacts"][0]["base64"]
                return base64.b64decode(image_base64)
            else:
                raise APIError("响应中未找到图像数据")
        
        except Exception as e:
            raise APIError(f"SDXL文生图失败：{str(e)}") from e
    
    def image_to_image(
        self,
        init_image_path: str,
        prompt: str,
        negative_prompt: str = "",
        strength: float = 0.5,
        steps: int = 30,
        cfg_scale: float = 7.0,
        seed: Optional[int] = None,
        **kwargs
    ) -> bytes:
        """
        图像生成图像（基于参考图）
        
        Args:
            init_image_path: 初始图像路径
            prompt: 提示词
            negative_prompt: 负向提示词
            strength: 变化强度（0.0-1.0）
            steps: 采样步数
            cfg_scale: CFG引导强度
            seed: 随机种子
            **kwargs: 其他参数
            
        Returns:
            bytes: 图像二进制数据
        """
        endpoint = "/generation/stable-diffusion-xl-1024-v1-0/image-to-image"
        
        # 读取初始图像并转为base64
        with open(init_image_path, 'rb') as f:
            init_image_base64 = base64.b64encode(f.read()).decode()
        
        payload = {
            "text_prompts": [
                {"text": prompt, "weight": 1.0}
            ],
            "init_image": init_image_base64,
            "image_strength": strength,
            "steps": steps,
            "cfg_scale": cfg_scale
        }
        
        if negative_prompt:
            payload["text_prompts"].append({"text": negative_prompt, "weight": -1.0})
        
        if seed is not None:
            payload["seed"] = seed
        
        payload.update(kwargs)
        
        try:
            response = self.client.send_post_request(endpoint, payload)
            
            if "artifacts" in response and len(response["artifacts"]) > 0:
                image_base64 = response["artifacts"][0]["base64"]
                return base64.b64decode(image_base64)
            else:
                raise APIError("响应中未找到图像数据")
        
        except Exception as e:
            raise APIError(f"SDXL图生图失败：{str(e)}") from e
    
    def controlnet_generate(
        self,
        prompt: str,
        control_image_path: str,
        controlnet_type: str = "openpose",
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 30,
        cfg_scale: float = 7.0,
        control_strength: float = 1.0,
        seed: Optional[int] = None,
        **kwargs
    ) -> bytes:
        """
        ControlNet生成图像（用于立绘差分）
        
        Args:
            prompt: 提示词
            control_image_path: 控制图像路径（骨骼图/深度图等）
            controlnet_type: ControlNet类型（openpose/depth/canny等）
            negative_prompt: 负向提示词
            width: 图像宽度
            height: 图像高度
            steps: 采样步数
            cfg_scale: CFG引导强度
            control_strength: 控制强度（0.0-2.0）
            seed: 随机种子
            **kwargs: 其他参数
            
        Returns:
            bytes: 图像二进制数据
        """
        # 注：此处为通用ControlNet接口，实际API端点需根据服务商调整
        # Stability AI官方API暂不直接支持ControlNet，需使用自托管或第三方服务
        
        endpoint = "/generation/stable-diffusion-xl-1024-v1-0/image-to-image/control"
        
        # 读取控制图像
        with open(control_image_path, 'rb') as f:
            control_image_base64 = base64.b64encode(f.read()).decode()
        
        payload = {
            "text_prompts": [
                {"text": prompt, "weight": 1.0}
            ],
            "control_image": control_image_base64,
            "control_type": controlnet_type,
            "control_strength": control_strength,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg_scale
        }
        
        if negative_prompt:
            payload["text_prompts"].append({"text": negative_prompt, "weight": -1.0})
        
        if seed is not None:
            payload["seed"] = seed
        
        payload.update(kwargs)
        
        try:
            response = self.client.send_post_request(endpoint, payload)
            
            if "artifacts" in response and len(response["artifacts"]) > 0:
                image_base64 = response["artifacts"][0]["base64"]
                return base64.b64decode(image_base64)
            else:
                raise APIError("响应中未找到图像数据")
        
        except Exception as e:
            raise APIError(f"ControlNet生成失败：{str(e)}") from e
    
    def save_image(self, image_data: bytes, output_path: str):
        """
        保存图像到文件
        
        Args:
            image_data: 图像二进制数据
            output_path: 输出路径
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'wb') as f:
            f.write(image_data)
    
    def batch_generate(
        self,
        prompts: List[str],
        output_dir: str,
        **common_params
    ) -> List[str]:
        """
        批量生成图像
        
        Args:
            prompts: 提示词列表
            output_dir: 输出目录
            **common_params: 通用参数（width/height/steps等）
            
        Returns:
            List[str]: 生成的图像路径列表
        """
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        
        generated_paths = []
        
        for idx, prompt in enumerate(prompts):
            try:
                image_data = self.text_to_image(prompt=prompt, **common_params)
                output_path = output_dir_path / f"image_{idx+1:03d}.png"
                self.save_image(image_data, str(output_path))
                generated_paths.append(str(output_path))
                
                # 避免API限流
                time.sleep(1)
            
            except Exception as e:
                print(f"生成第{idx+1}张图像失败：{str(e)}")
                continue
        
        return generated_paths
    
    def close(self):
        """关闭客户端"""
        self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def __repr__(self) -> str:
        return f"<SDXLClient(base_url={self.base_url})>"
