# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - BGM音乐生成API客户端
支持AI音乐生成服务（Suno、MusicGen等）
"""
import requests
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, Literal


class MusicGenClient:
    """
    AI音乐生成客户端
    支持Suno4.cn代理和其他音乐生成服务
    """
    
    def __init__(
        self,
        provider: Literal["suno", "musicgen", "custom"] = "suno",
        api_key: str = "",
        user_id: str = "default_user",
        base_url: Optional[str] = None,
        timeout: int = 300
    ):
        """
        初始化音乐生成客户端
        
        Args:
            provider: 音乐生成服务提供商
            api_key: API密钥（Suno代理的x-token）
            user_id: 用户ID（Suno代理的x-userId）
            base_url: 自定义API地址
            timeout: 请求超时时间（音乐生成较慢）
        """
        self.provider = provider
        self.api_key = api_key
        self.user_id = user_id
        self.timeout = timeout
        
        if base_url:
            self.base_url = base_url
        else:
            self.base_url = self._get_default_base_url()
        
        # Suno代理使用特殊的请求头
        if provider == "suno" and "suno4.cn" in self.base_url or "dzwlai.com" in self.base_url or "linlongai.com" in self.base_url:
            self.headers = {
                "x-token": api_key,
                "x-userId": user_id,
                "Content-Type": "application/json",
                "Accept-Language": "zh_CN"
            }
        else:
            self.headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
    
    def _get_default_base_url(self) -> str:
        """获取默认API地址"""
        urls = {
            "suno": "https://dzwlai.com/apiuser",  # Suno4.cn国内代理
            "musicgen": "https://api.replicate.com/v1",
            "custom": ""
        }
        return urls.get(self.provider, "")
    
    def generate_music(
        self,
        prompt: str,
        duration: int = 30,
        style: Optional[str] = None,
        mood: Optional[str] = None,
        tempo: Optional[str] = "medium",
        instrumental: bool = True,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        生成音乐
        
        Args:
            prompt: 音乐描述提示词
            duration: 音乐时长（秒）
            style: 音乐风格（如"classical", "electronic", "ambient"）
            mood: 情绪氛围（如"calm", "energetic", "melancholic"）
            tempo: 节奏速度（slow/medium/fast）
            instrumental: 是否为纯音乐（无人声）
            output_path: 输出文件路径
            
        Returns:
            str: 音频文件路径，失败返回None
        """
        if self.provider == "suno":
            return self._generate_suno(
                prompt, duration, style, mood, tempo, instrumental, output_path
            )
        elif self.provider == "musicgen":
            return self._generate_musicgen(
                prompt, duration, style, mood, tempo, output_path
            )
        else:
            raise ValueError(f"不支持的音乐生成服务: {self.provider}")
    
    def _generate_suno(
        self,
        prompt: str,
        duration: int,
        style: Optional[str],
        mood: Optional[str],
        tempo: str,
        instrumental: bool,
        output_path: Optional[str]
    ) -> Optional[str]:
        """使用Suno生成音乐"""
        # 构建完整提示词
        full_prompt = self._build_music_prompt(prompt, style, mood, tempo, instrumental)
        
        # 提交生成任务
        url = f"{self.base_url}/generate"
        payload = {
            "prompt": full_prompt,
            "duration": duration,
            "make_instrumental": instrumental,
            "wait_audio": False  # 异步生成
        }
        
        try:
            # 提交任务
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            task_id = result.get("id")
            
            if not task_id:
                raise Exception("未获取到任务ID")
            
            print(f"音乐生成任务已提交，ID: {task_id}")
            
            # 等待生成完成
            audio_url = self._wait_for_music_completion(task_id)
            
            if not audio_url:
                raise Exception("音乐生成超时")
            
            # 下载音频
            return self._download_audio(audio_url, output_path)
        
        except Exception as e:
            print(f"Suno音乐生成失败: {str(e)}")
            return None
    
    def _generate_musicgen(
        self,
        prompt: str,
        duration: int,
        style: Optional[str],
        mood: Optional[str],
        tempo: str,
        output_path: Optional[str]
    ) -> Optional[str]:
        """使用MusicGen生成音乐"""
        # MusicGen通过Replicate API
        full_prompt = self._build_music_prompt(prompt, style, mood, tempo, True)
        
        url = f"{self.base_url}/predictions"
        payload = {
            "version": "facebook/musicgen-large",
            "input": {
                "prompt": full_prompt,
                "duration": duration,
                "temperature": 1.0,
                "top_k": 250,
                "top_p": 0.0
            }
        }
        
        try:
            # 提交任务
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            prediction_id = result.get("id")
            
            if not prediction_id:
                raise Exception("未获取到预测ID")
            
            print(f"MusicGen生成任务已提交，ID: {prediction_id}")
            
            # 等待生成完成
            audio_url = self._wait_for_musicgen_completion(prediction_id)
            
            if not audio_url:
                raise Exception("音乐生成超时")
            
            # 下载音频
            return self._download_audio(audio_url, output_path)
        
        except Exception as e:
            print(f"MusicGen生成失败: {str(e)}")
            return None
    
    def _build_music_prompt(
        self,
        prompt: str,
        style: Optional[str],
        mood: Optional[str],
        tempo: str,
        instrumental: bool
    ) -> str:
        """构建音乐生成提示词"""
        components = []
        
        if style:
            components.append(f"{style} style")
        
        if mood:
            components.append(f"{mood} mood")
        
        components.append(f"{tempo} tempo")
        
        if instrumental:
            components.append("instrumental")
        
        components.append(prompt)
        
        return ", ".join(components)
    
    def _wait_for_music_completion(
        self,
        task_id: str,
        poll_interval: int = 10,
        max_wait_time: int = 300
    ) -> Optional[str]:
        """等待Suno音乐生成完成"""
        url = f"{self.base_url}/generate/{task_id}"
        elapsed_time = 0
        
        while elapsed_time < max_wait_time:
            try:
                response = requests.get(url, headers=self.headers, timeout=30)
                response.raise_for_status()
                
                result = response.json()
                status = result.get("status")
                
                if status == "complete":
                    audio_url = result.get("audio_url")
                    return audio_url
                elif status == "failed":
                    print(f"音乐生成失败: {result.get('error')}")
                    return None
                
                # 继续等待
                print(f"生成中... 已等待 {elapsed_time}秒")
                time.sleep(poll_interval)
                elapsed_time += poll_interval
            
            except Exception as e:
                print(f"查询任务状态失败: {str(e)}")
                time.sleep(poll_interval)
                elapsed_time += poll_interval
        
        return None
    
    def _wait_for_musicgen_completion(
        self,
        prediction_id: str,
        poll_interval: int = 10,
        max_wait_time: int = 300
    ) -> Optional[str]:
        """等待MusicGen生成完成"""
        url = f"{self.base_url}/predictions/{prediction_id}"
        elapsed_time = 0
        
        while elapsed_time < max_wait_time:
            try:
                response = requests.get(url, headers=self.headers, timeout=30)
                response.raise_for_status()
                
                result = response.json()
                status = result.get("status")
                
                if status == "succeeded":
                    output = result.get("output")
                    if output and isinstance(output, str):
                        return output
                    elif output and isinstance(output, list) and len(output) > 0:
                        return output[0]
                elif status == "failed":
                    print(f"音乐生成失败: {result.get('error')}")
                    return None
                
                # 继续等待
                print(f"生成中... 已等待 {elapsed_time}秒")
                time.sleep(poll_interval)
                elapsed_time += poll_interval
            
            except Exception as e:
                print(f"查询任务状态失败: {str(e)}")
                time.sleep(poll_interval)
                elapsed_time += poll_interval
        
        return None
    
    def _download_audio(
        self,
        audio_url: str,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """下载音频文件"""
        if output_path is None:
            output_path = f"bgm_output_{int(time.time())}.mp3"
        
        try:
            response = requests.get(audio_url, timeout=60)
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            print(f"音频已下载: {output_path}")
            return output_path
        
        except Exception as e:
            print(f"音频下载失败: {str(e)}")
            return None
    
    def batch_generate(
        self,
        prompts: list[Dict[str, Any]],
        output_dir: str = "."
    ) -> list[str]:
        """
        批量生成音乐
        
        Args:
            prompts: 提示词列表
            output_dir: 输出目录
            
        Returns:
            list: 生成的音频文件路径列表
        """
        output_paths = []
        output_path_obj = Path(output_dir)
        output_path_obj.mkdir(parents=True, exist_ok=True)
        
        for idx, prompt_data in enumerate(prompts):
            prompt = prompt_data.get("prompt", "")
            duration = prompt_data.get("duration", 30)
            style = prompt_data.get("style")
            mood = prompt_data.get("mood")
            
            output_file = output_path_obj / f"bgm_{idx+1:03d}.mp3"
            
            result = self.generate_music(
                prompt=prompt,
                duration=duration,
                style=style,
                mood=mood,
                output_path=str(output_file)
            )
            
            if result:
                output_paths.append(result)
            
            # 避免请求过快
            time.sleep(2)
        
        return output_paths
    
    def close(self):
        """关闭客户端"""
        pass


# 音乐风格预设
MUSIC_STYLES = {
    "古典": "classical",
    "电子": "electronic",
    "环境音": "ambient",
    "钢琴": "piano",
    "管弦乐": "orchestral",
    "爵士": "jazz",
    "摇滚": "rock",
    "流行": "pop",
    "民谣": "folk",
    "电影配乐": "cinematic"
}

# 情绪映射
MOOD_MAPPING = {
    "平静": "calm",
    "紧张": "tense",
    "激动": "energetic",
    "悲伤": "melancholic",
    "欢乐": "joyful",
    "神秘": "mysterious",
    "浪漫": "romantic",
    "史诗": "epic",
    "温暖": "warm",
    "黑暗": "dark"
}

# 节奏映射
TEMPO_MAPPING = {
    "缓慢": "slow",
    "中速": "medium",
    "快速": "fast"
}
