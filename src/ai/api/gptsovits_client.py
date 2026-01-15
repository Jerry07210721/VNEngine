# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - GPT-SoVITS API客户端
支持异步语音合成，8种情绪控制，基于sovits.cn代理
"""

import requests
from typing import Dict, Any, Optional, List
from pathlib import Path
from .base_client import BaseAPIClient, APIError


class GPTSoVITSClient(BaseAPIClient):
    """GPT-SoVITS API客户端"""
    
    def __init__(
        self,
        sign: str,
        base_url: str = "https://openapi.lipvoice.cn",
        style: str = "2",
        genre: int = 1,
        timeout: int = 300,
        poll_interval: float = 5.0
    ):
        """
        初始化GPT-SoVITS客户端
        
        Args:
            sign: API签名密钥
            base_url: API基础URL
            style: 模型版本（1=普遍模型, 2=专业模型, 3=多语言模型）
            genre: 模型类别（0=参考原音频, 1=语气参考模式）
            timeout: 超时时间（秒）
            poll_interval: 轮询间隔（秒）
        """
        super().__init__(base_url, sign, timeout, logger_name="GPTSoVITSClient")
        self.sign = sign
        self.style = style
        self.genre = genre
        self.poll_interval = poll_interval
        
        self.logger.info(f"GPT-SoVITS客户端初始化: style={style}, genre={genre}")
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "Content-Type": "application/json",
            "sign": self.sign
        }
    
    def create_tts(
        self,
        content: str,
        audio_id: str,
        ext: Optional[Dict[str, float]] = None,
        style: Optional[str] = None,
        genre: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        异步语音合成
        
        Args:
            content: 文本内容（最大5000字符）
            audio_id: 模型ID（克隆声音使用）
            ext: 语音控制参数（8种情绪：happy/angry/sad/afraid/disgusted/melancholic/surprised/calm）
            style: 模型版本（可选）
            genre: 模型类别（可选）
        
        Returns:
            任务信息 {"taskId": 任务ID, "status": 状态, "voiceUrl": 语音地址}
        """
        if len(content) > 5000:
            raise ValueError(f"文本内容过长，最大5000字符，当前{len(content)}字符")
        
        payload = {
            "content": content,
            "audioId": audio_id,
            "style": style or self.style,
            "genre": genre if genre is not None else self.genre
        }
        
        # 添加语气参数
        if ext:
            payload["ext"] = ext
        elif self.genre == 1:
            # 如果是语气参考模式，提供默认值
            payload["ext"] = {
                "happy": 0.0,
                "angry": 0.0,
                "sad": 0.0,
                "afraid": 0.0,
                "disgusted": 0.0,
                "melancholic": 0.0,
                "surprised": 0.0,
                "calm": 0.0
            }
        
        self.logger.info(f"发起语音合成: content='{content[:30]}...', audio_id={audio_id}")
        
        response = self.post("/api/third/tts/create", data=payload)
        
        if response.get("code") == 0:
            task_data = response.get("data", {})
            task_id = task_data.get("taskId")
            self.logger.info(f"语音合成任务创建成功: task_id={task_id}")
            return task_data
        else:
            raise APIError(f"语音合成失败: {response.get('msg')}")

    def list_reference_models(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """查询克隆模型列表，用于选择 audioId。"""

        params = {
            "page": str(page),
            "pageSize": str(page_size),
        }

        response = self.get("/api/third/reference/list", params=params)

        if response.get("code") == 0:
            return response.get("data", {})

        raise APIError(f"获取模型列表失败: {response.get('msg')}")

    def upload_reference_model(self, file_path: str, name: str, describe: str = "") -> Dict[str, Any]:
        """上传语音样本创建克隆模型。"""

        file_p = Path(file_path)
        if not file_p.exists():
            raise FileNotFoundError(f"找不到文件: {file_path}")

        url = f"{self.base_url}/api/third/reference/upload"
        headers = {"sign": self.sign}
        files = {"file": (file_p.name, open(file_p, "rb"), "application/octet-stream")}
        data = {"name": name, "describe": describe or ""}

        try:
            response = self.session.post(url, headers=headers, files=files, data=data, timeout=self.timeout)
            result = self._handle_response(response)
        finally:
            files["file"][1].close()

        if result.get("code") == 0:
            return result.get("data", {})

        raise APIError(f"创建模型失败: {result.get('msg')}")

    def delete_reference_model(self, audio_id: str) -> bool:
        """删除克隆模型。"""

        params = {"audioId": audio_id}
        headers = {"sign": self.sign}
        result = self._request(
            method="DELETE",
            endpoint="/api/third/reference/delete",
            params=params,
            headers=headers
        )

        if result.get("code") == 0:
            return True

        raise APIError(f"删除模型失败: {result.get('msg')}")
    
    def query_result(self, task_id: str) -> Dict[str, Any]:
        """
        查询任务结果
        
        Args:
            task_id: 任务ID
        
        Returns:
            任务详情
        """
        params = {"taskId": task_id}
        headers = {"sign": self.sign}
        
        response = self.get("/api/third/tts/result", params=params, headers=headers)
        
        if response.get("code") == 0:
            return response.get("data", {})
        else:
            raise APIError(f"查询任务失败: {response.get('msg')}")
    
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
            
            self.logger.debug(f"任务状态: status={status}")
            
            # 任务状态: 1=合成中, 2=合成成功, 3=合成失败
            if status == 2:
                self.logger.info(f"任务成功完成: task_id={task_id}")
                return True
            elif status == 3:
                raise APIError(f"任务失败: 语音合成失败", response_data=result)
            
            return False
        
        return self.poll_until_complete(
            check_func=check_status,
            is_complete_func=is_complete,
            interval=poll_interval,
            max_wait=timeout
        )
    
    def download_voice(self, voice_url: str, save_path: str) -> bool:
        """
        下载语音文件
        
        Args:
            voice_url: 语音URL（需在header或参数中携带sign）
            save_path: 保存路径
        
        Returns:
            是否下载成功
        """
        try:
            self.logger.info(f"开始下载语音: {voice_url}")
            
            # URL参数中添加sign
            url_with_sign = f"{voice_url}{'&' if '?' in voice_url else '?'}sign={self.sign}"
            
            response = requests.get(url_with_sign, timeout=60)
            response.raise_for_status()
            
            # 确保目录存在
            save_path_obj = Path(save_path)
            save_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存语音
            with open(save_path, 'wb') as f:
                f.write(response.content)
            
            self.logger.info(f"语音下载成功: {save_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"语音下载失败: {e}")
            return False
    
    def synthesize_and_download(
        self,
        content: str,
        audio_id: str,
        save_path: str,
        ext: Optional[Dict[str, float]] = None,
        timeout: Optional[float] = None
    ) -> tuple[bool, Optional[str]]:
        """
        合成语音并下载（一站式接口）
        
        Args:
            content: 文本内容
            audio_id: 模型ID
            save_path: 保存路径
            ext: 语气参数
            timeout: 超时时间
        
        Returns:
            (是否成功, 语音URL)
        """
        try:
            # 1. 创建任务
            task_info = self.create_tts(content, audio_id, ext)
            task_id = task_info["taskId"]
            
            # 2. 等待完成
            result = self.wait_for_completion(task_id, timeout)
            
            # 3. 下载语音
            voice_url = result.get("voiceUrl")
            if not voice_url:
                self.logger.error("任务完成但未获取到语音URL")
                return False, None
            
            success = self.download_voice(voice_url, save_path)
            
            return success, voice_url
            
        except Exception as e:
            self.logger.error(f"合成并下载语音失败: {e}")
            return False, None
    
    def batch_synthesize(
        self,
        dialogues: List[Dict[str, Any]],
        save_dir: str,
        timeout: Optional[float] = None
    ) -> List[tuple[bool, str, Optional[str]]]:
        """
        批量合成语音
        
        Args:
            dialogues: 对白列表，格式: [{"content": "...", "audio_id": "...", "ext": {...}, "filename": "..."}, ...]
            save_dir: 保存目录
            timeout: 每个任务的超时时间
        
        Returns:
            结果列表: [(是否成功, 文本内容, 语音URL), ...]
        """
        results = []
        save_dir_obj = Path(save_dir)
        save_dir_obj.mkdir(parents=True, exist_ok=True)
        
        for idx, dialogue in enumerate(dialogues):
            self.logger.info(f"批量合成进度: {idx+1}/{len(dialogues)}")
            
            content = dialogue["content"]
            audio_id = dialogue["audio_id"]
            ext = dialogue.get("ext")
            filename = dialogue.get("filename", f"{idx+1}.mp3")
            
            save_path = save_dir_obj / filename
            
            success, voice_url = self.synthesize_and_download(
                content=content,
                audio_id=audio_id,
                save_path=str(save_path),
                ext=ext,
                timeout=timeout
            )
            
            results.append((success, content, voice_url))
        
        successful_count = sum(1 for success, _, _ in results if success)
        self.logger.info(f"批量合成完成: 成功{successful_count}/{len(dialogues)}")
        
        return results
