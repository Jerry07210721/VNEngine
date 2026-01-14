# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - GPT-SoVITS API客户端
支持GPT-SoVITS v2语音克隆与合成
"""
import requests
import json
import base64
from pathlib import Path
from typing import Optional, Dict, Any
import time


class GPTSoVITSClient:
    """
    GPT-SoVITS语音合成客户端
    支持高质量的二次元声线克隆与合成
    """
    
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "http://127.0.0.1:9880",
        timeout: int = 120
    ):
        """
        初始化GPT-SoVITS客户端
        
        Args:
            api_key: API密钥（本地部署可留空）
            base_url: API地址（默认本地部署地址）
            timeout: 请求超时时间
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        
        self.headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
    
    def synthesize(
        self,
        text: str,
        ref_audio_path: Optional[str] = None,
        ref_text: Optional[str] = None,
        language: str = "zh",
        output_path: Optional[str] = None,
        speed: float = 1.0,
        emotion: str = "neutral"
    ) -> Optional[str]:
        """
        合成语音
        
        Args:
            text: 要合成的文本
            ref_audio_path: 参考音频路径（用于声线克隆）
            ref_text: 参考音频对应的文本
            language: 语言（zh/en/ja）
            output_path: 输出音频文件路径
            speed: 语速（0.5-2.0）
            emotion: 情感标签
            
        Returns:
            str: 音频文件路径，失败返回None
        """
        # API endpoint
        url = f"{self.base_url}/tts"
        
        # 构建请求
        payload = {
            "text": text,
            "text_language": language,
            "speed": speed
        }
        
        # 添加参考音频（如果提供）
        if ref_audio_path and ref_text:
            # 读取参考音频并编码
            try:
                with open(ref_audio_path, 'rb') as f:
                    ref_audio_data = base64.b64encode(f.read()).decode()
                payload["ref_audio_base64"] = ref_audio_data
                payload["prompt_text"] = ref_text
                payload["prompt_language"] = language
            except Exception as e:
                print(f"读取参考音频失败: {str(e)}")
                return None
        
        try:
            # 发送请求
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            
            # 保存音频
            if output_path is None:
                output_path = f"gpt_sovits_output_{int(time.time())}.wav"
            
            # 检查响应类型
            content_type = response.headers.get('Content-Type', '')
            if 'audio' in content_type:
                # 直接返回音频数据
                with open(output_path, 'wb') as f:
                    f.write(response.content)
            else:
                # JSON响应，包含base64编码的音频
                result = response.json()
                if 'audio' in result:
                    audio_data = base64.b64decode(result['audio'])
                    with open(output_path, 'wb') as f:
                        f.write(audio_data)
                else:
                    print(f"响应中未找到音频数据: {result}")
                    return None
            
            return output_path
        
        except Exception as e:
            print(f"GPT-SoVITS合成失败: {str(e)}")
            return None
    
    def batch_synthesize(
        self,
        texts: list[Dict[str, str]],
        output_dir: str = ".",
        ref_audio_path: Optional[str] = None,
        ref_text: Optional[str] = None,
        language: str = "zh"
    ) -> list[str]:
        """
        批量合成语音
        
        Args:
            texts: 文本列表 [{"char_id": "char1", "text": "对白内容"}, ...]
            output_dir: 输出目录
            ref_audio_path: 参考音频路径
            ref_text: 参考音频文本
            language: 语言
            
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
            
            # 生成输出文件名
            output_file = output_path_obj / f"{char_id}_{idx+1:04d}.wav"
            
            # 合成语音
            result = self.synthesize(
                text=text,
                ref_audio_path=ref_audio_path,
                ref_text=ref_text,
                language=language,
                output_path=str(output_file)
            )
            
            if result:
                output_paths.append(result)
                print(f"已生成: {output_file.name}")
            
            # 添加短暂延迟
            time.sleep(0.3)
        
        return output_paths
    
    def get_available_speakers(self) -> Dict[str, Any]:
        """
        获取可用的说话人列表（如果API支持）
        
        Returns:
            Dict: 说话人列表信息
        """
        url = f"{self.base_url}/speakers"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"获取说话人列表失败: {str(e)}")
            return {"speakers": []}
    
    def close(self):
        """关闭客户端"""
        pass


class BertVITS2Client:
    """
    Bert-VITS2语音合成客户端
    作为GPT-SoVITS的备选方案
    """
    
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "http://127.0.0.1:5000",
        timeout: int = 120
    ):
        """
        初始化Bert-VITS2客户端
        
        Args:
            api_key: API密钥
            base_url: API地址
            timeout: 请求超时时间
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        
        self.headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
    
    def synthesize(
        self,
        text: str,
        speaker_id: int = 0,
        language: str = "ZH",
        output_path: Optional[str] = None,
        speed: float = 1.0,
        emotion: str = "neutral"
    ) -> Optional[str]:
        """
        合成语音
        
        Args:
            text: 要合成的文本
            speaker_id: 说话人ID
            language: 语言（ZH/EN/JP）
            output_path: 输出音频文件路径
            speed: 语速
            emotion: 情感标签
            
        Returns:
            str: 音频文件路径，失败返回None
        """
        url = f"{self.base_url}/voice"
        
        payload = {
            "text": text,
            "speaker_id": speaker_id,
            "language": language,
            "speed": speed,
            "emotion": emotion
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
                output_path = f"bert_vits2_output_{int(time.time())}.wav"
            
            # 保存音频
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            return output_path
        
        except Exception as e:
            print(f"Bert-VITS2合成失败: {str(e)}")
            return None
    
    def close(self):
        """关闭客户端"""
        pass


# 情感标签映射
EMOTION_MAPPING = {
    "开心": "happy",
    "悲伤": "sad",
    "愤怒": "angry",
    "害怕": "fearful",
    "惊讶": "surprised",
    "平静": "neutral",
    "温柔": "gentle",
    "兴奋": "excited"
}
