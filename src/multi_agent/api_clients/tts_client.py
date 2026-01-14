# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - TTS语音合成API客户端
支持多种TTS服务提供商（Azure、阿里云、OpenAI等）
"""
import requests
import json
import base64
from pathlib import Path
from typing import Optional, Dict, Any, Literal
import time


class TTSClient:
    """
    语音合成客户端
    支持多种TTS服务商的统一接口
    """
    
    def __init__(
        self,
        provider: Literal["azure", "aliyun", "openai", "edge"] = "azure",
        api_key: str = "",
        region: str = "eastus",
        base_url: Optional[str] = None,
        timeout: int = 60
    ):
        """
        初始化TTS客户端
        
        Args:
            provider: TTS服务提供商（azure/aliyun/openai/edge）
            api_key: API密钥
            region: 服务区域（Azure需要）
            base_url: 自定义API地址
            timeout: 请求超时时间
        """
        self.provider = provider
        self.api_key = api_key
        self.region = region
        self.timeout = timeout
        
        # 根据提供商设置基础URL
        if base_url:
            self.base_url = base_url
        else:
            self.base_url = self._get_default_base_url()
        
        # 设置请求头
        self.headers = self._build_headers()
    
    def _get_default_base_url(self) -> str:
        """获取默认API地址"""
        urls = {
            "azure": f"https://{self.region}.tts.speech.microsoft.com",
            "aliyun": "https://nls-gateway.cn-shanghai.aliyuncs.com",
            "openai": "https://api.openai.com/v1",
            "edge": "https://speech.platform.bing.com"
        }
        return urls.get(self.provider, "")
    
    def _build_headers(self) -> Dict[str, str]:
        """构建请求头"""
        if self.provider == "azure":
            return {
                "Ocp-Apim-Subscription-Key": self.api_key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3"
            }
        elif self.provider == "aliyun":
            return {
                "Content-Type": "application/json"
            }
        elif self.provider == "openai":
            return {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        else:
            return {"Content-Type": "application/json"}
    
    def synthesize(
        self,
        text: str,
        voice: str = "zh-CN-XiaoxiaoNeural",
        output_path: Optional[str] = None,
        rate: str = "0%",
        pitch: str = "0%",
        style: Optional[str] = None,
        style_degree: float = 1.0
    ) -> Optional[str]:
        """
        合成语音
        
        Args:
            text: 要合成的文本
            voice: 语音角色名称
            output_path: 输出音频文件路径（可选）
            rate: 语速调整（-50%到+100%）
            pitch: 音调调整（-50%到+50%）
            style: 情感风格（如"cheerful", "sad", "angry"等）
            style_degree: 风格强度（0.01-2.0）
            
        Returns:
            str: 音频文件路径，失败返回None
        """
        if self.provider == "azure":
            return self._synthesize_azure(
                text, voice, output_path, rate, pitch, style, style_degree
            )
        elif self.provider == "aliyun":
            return self._synthesize_aliyun(text, voice, output_path, rate, pitch)
        elif self.provider == "openai":
            return self._synthesize_openai(text, voice, output_path)
        else:
            raise ValueError(f"不支持的TTS提供商: {self.provider}")
    
    def _synthesize_azure(
        self,
        text: str,
        voice: str,
        output_path: Optional[str],
        rate: str,
        pitch: str,
        style: Optional[str],
        style_degree: float
    ) -> Optional[str]:
        """使用Azure TTS合成语音"""
        # 构建SSML
        ssml = self._build_azure_ssml(text, voice, rate, pitch, style, style_degree)
        
        # 发送请求
        url = f"{self.base_url}/cognitiveservices/v1"
        
        try:
            response = requests.post(
                url,
                headers=self.headers,
                data=ssml.encode('utf-8'),
                timeout=self.timeout
            )
            
            response.raise_for_status()
            
            # 保存音频
            if output_path is None:
                output_path = f"tts_output_{int(time.time())}.mp3"
            
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            return output_path
        
        except Exception as e:
            print(f"Azure TTS合成失败: {str(e)}")
            return None
    
    def _build_azure_ssml(
        self,
        text: str,
        voice: str,
        rate: str,
        pitch: str,
        style: Optional[str],
        style_degree: float
    ) -> str:
        """构建Azure SSML格式"""
        # 基础SSML结构
        ssml = f'''<speak version='1.0' xml:lang='zh-CN'>
    <voice name='{voice}'>'''
        
        # 添加情感风格
        if style:
            ssml += f'''
        <mstts:express-as style="{style}" styledegree="{style_degree}">'''
        
        # 添加韵律控制
        ssml += f'''
            <prosody rate="{rate}" pitch="{pitch}">
                {text}
            </prosody>'''
        
        # 关闭标签
        if style:
            ssml += '''
        </mstts:express-as>'''
        
        ssml += '''
    </voice>
</speak>'''
        
        return ssml
    
    def _synthesize_aliyun(
        self,
        text: str,
        voice: str,
        output_path: Optional[str],
        rate: str,
        pitch: str
    ) -> Optional[str]:
        """使用阿里云TTS合成语音"""
        # 阿里云TTS实现（需要具体API文档）
        # 此处提供框架代码
        url = f"{self.base_url}/stream/v1/tts"
        
        payload = {
            "appkey": self.api_key,
            "text": text,
            "voice": voice,
            "format": "mp3",
            "sample_rate": 16000,
            "speech_rate": int(rate.replace('%', '')) if rate else 0,
            "pitch_rate": int(pitch.replace('%', '')) if pitch else 0
        }
        
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            
            if output_path is None:
                output_path = f"tts_output_{int(time.time())}.mp3"
            
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            return output_path
        
        except Exception as e:
            print(f"阿里云TTS合成失败: {str(e)}")
            return None
    
    def _synthesize_openai(
        self,
        text: str,
        voice: str,
        output_path: Optional[str]
    ) -> Optional[str]:
        """使用OpenAI TTS合成语音"""
        url = f"{self.base_url}/audio/speech"
        
        # OpenAI TTS voices: alloy, echo, fable, onyx, nova, shimmer
        payload = {
            "model": "tts-1",
            "input": text,
            "voice": voice
        }
        
        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            
            if output_path is None:
                output_path = f"tts_output_{int(time.time())}.mp3"
            
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            return output_path
        
        except Exception as e:
            print(f"OpenAI TTS合成失败: {str(e)}")
            return None
    
    def get_available_voices(self) -> Dict[str, Any]:
        """
        获取可用的语音列表
        
        Returns:
            Dict: 语音列表信息
        """
        if self.provider == "azure":
            return self._get_azure_voices()
        elif self.provider == "openai":
            return {
                "voices": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
                "description": "OpenAI TTS 支持的语音"
            }
        else:
            return {"voices": [], "description": "暂不支持获取语音列表"}
    
    def _get_azure_voices(self) -> Dict[str, Any]:
        """获取Azure可用语音列表"""
        url = f"{self.base_url}/cognitiveservices/voices/list"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            return {"voices": response.json()}
        except Exception as e:
            print(f"获取Azure语音列表失败: {str(e)}")
            return {"voices": []}
    
    def batch_synthesize(
        self,
        texts: list[Dict[str, str]],
        output_dir: str = ".",
        voice_mapping: Optional[Dict[str, str]] = None
    ) -> list[str]:
        """
        批量合成语音
        
        Args:
            texts: 文本列表，格式 [{"char_id": "char1", "text": "对白内容"}, ...]
            output_dir: 输出目录
            voice_mapping: 角色ID到语音名称的映射
            
        Returns:
            list: 生成的音频文件路径列表
        """
        output_paths = []
        output_path_obj = Path(output_dir)
        output_path_obj.mkdir(parents=True, exist_ok=True)
        
        for idx, item in enumerate(texts):
            char_id = item.get("char_id", "narrator")
            text = item.get("text", "")
            
            if not text:
                continue
            
            # 获取角色对应的语音
            voice = voice_mapping.get(char_id, "zh-CN-XiaoxiaoNeural") if voice_mapping else "zh-CN-XiaoxiaoNeural"
            
            # 生成输出文件名
            output_file = output_path_obj / f"{char_id}_{idx+1:04d}.mp3"
            
            # 合成语音
            result = self.synthesize(text, voice, str(output_file))
            
            if result:
                output_paths.append(result)
                print(f"已生成: {output_file.name}")
            
            # 添加短暂延迟避免请求过快
            time.sleep(0.5)
        
        return output_paths
    
    def close(self):
        """关闭客户端（预留接口）"""
        pass


# 常用语音预设
COMMON_VOICES = {
    "azure": {
        "female_young": "zh-CN-XiaoxiaoNeural",  # 年轻女声
        "female_mature": "zh-CN-XiaoyanNeural",  # 成熟女声
        "male_young": "zh-CN-YunxiNeural",       # 年轻男声
        "male_mature": "zh-CN-YunyangNeural",    # 成熟男声
        "child": "zh-CN-XiaochenNeural"          # 儿童音
    },
    "openai": {
        "female_young": "nova",
        "female_mature": "shimmer",
        "male_young": "echo",
        "male_mature": "onyx"
    }
}


# 情感风格映射
EMOTION_STYLES = {
    "开心": "cheerful",
    "悲伤": "sad",
    "愤怒": "angry",
    "害怕": "fearful",
    "温柔": "gentle",
    "兴奋": "excited",
    "平静": "calm",
    "严肃": "serious"
}
