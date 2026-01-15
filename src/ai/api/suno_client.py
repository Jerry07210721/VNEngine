# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - Suno AI API客户端
支持AI音乐生成（自定义/灵感模式），基于代理API
"""

import requests
from typing import Dict, Any, List, Optional
from pathlib import Path
from .base_client import BaseAPIClient, APIError


class SunoClient(BaseAPIClient):
    """Suno AI API客户端"""
    
    def __init__(
        self,
        token: str,
        user_id: str,
        base_url: str = "https://dzwlai.com/apiuser",
        model: str = "chirp-v5",
        timeout: int = 600,
        poll_interval: float = 10.0
    ):
        """
        初始化Suno AI客户端
        
        Args:
            token: API Token（x-token）
            user_id: 用户ID（x-userId）
            base_url: API基础URL
            model: 模型版本（chirp-v5/chirp-v4-5+/chirp-v4-5/chirp-v4/chirp-v3-5）
            timeout: 超时时间（秒）
            poll_interval: 轮询间隔（秒）
        """
        super().__init__(base_url, token, timeout, logger_name="SunoClient")
        self.token = token
        self.user_id = user_id
        self.model = model
        self.poll_interval = poll_interval
        
        self.logger.info(f"Suno AI客户端初始化: model={model}, poll_interval={poll_interval}s")
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "Content-Type": "application/json",
            "x-token": self.token,
            "x-userId": self.user_id
        }
    
    def generate_music(
        self,
        input_type: str = "20",
        prompt: str = "",
        tags: str = "",
        title: str = "",
        make_instrumental: bool = False,
        mv_version: Optional[str] = None,
        callback_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        音乐创作（自定义模式/歌词模式）
        
        Args:
            input_type: 输入类型（10=灵感模式, 20=自定义模式）
            prompt: 歌词内容（纯音乐时填空字符串）
            tags: 音乐风格标签
            title: 音乐标题
            make_instrumental: 是否为纯音乐
            mv_version: 模型版本（可选，默认使用初始化时的值）
            callback_url: 回调URL（可选）
        
        Returns:
            任务信息 {"taskBatchId": 任务批次ID, "items": [...]}
        """
        payload = {
            "inputType": input_type,
            "makeInstrumental": make_instrumental,
            "prompt": prompt,
            "tags": tags,
            "title": title,
            "mvVersion": mv_version or self.model
        }
        
        if callback_url:
            payload["callbackUrl"] = callback_url
        
        # 纯音乐模式
        if make_instrumental:
            payload["prompt"] = ""
        
        self.logger.info(
            f"发起音乐生成: title='{title}', tags='{tags}', "
            f"instrumental={make_instrumental}, model={payload['mvVersion']}"
        )
        
        response = self.post("/_open/suno/music/generate", data=payload)
        
        if response.get("code") == 200:
            task_data = response.get("data", {})
            task_batch_id = task_data.get("taskBatchId")
            self.logger.info(f"音乐生成任务创建成功: task_batch_id={task_batch_id}")
            return task_data
        else:
            raise APIError(f"音乐生成失败: {response.get('msg')}")
    
    def query_state(self, task_batch_id: str) -> Dict[str, Any]:
        """
        获取音乐生成状态
        
        Args:
            task_batch_id: 任务批次ID
        
        Returns:
            任务状态详情
        """
        params = {"taskBatchId": task_batch_id}
        
        response = self.get("/_open/suno/music/getState", params=params)
        
        if response.get("code") == 200:
            return response.get("data", {})
        else:
            raise APIError(f"查询状态失败: {response.get('msg')}")
    
    def wait_for_completion(
        self,
        task_batch_id: str,
        timeout: Optional[float] = None,
        poll_interval: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        等待任务完成（轮询）
        
        Args:
            task_batch_id: 任务批次ID
            timeout: 超时时间（秒）
            poll_interval: 轮询间隔（秒）
        
        Returns:
            完成后的任务详情
        """
        timeout = timeout or self.timeout
        poll_interval = poll_interval or self.poll_interval
        
        self.logger.info(f"开始等待任务完成: task_batch_id={task_batch_id}, timeout={timeout}s")
        
        def check_status():
            return self.query_state(task_batch_id)
        
        def is_complete(result):
            task_status = result.get("taskStatus")
            items = result.get("items", [])
            
            self.logger.debug(f"任务状态: taskStatus={task_status}")
            
            # 任务状态: create=创建中, processing=处理中, finished=完成（包括成功和失败）
            if task_status == "finished":
                # 检查所有子任务是否完成
                all_complete = True
                for item in items:
                    status = item.get("status")
                    # 状态: 10=排队, 20=执行中, 30=成功, 40=失败
                    if status not in [30, 40]:
                        all_complete = False
                        break
                
                if all_complete:
                    successful_count = sum(1 for item in items if item.get("status") == 30)
                    failed_count = sum(1 for item in items if item.get("status") == 40)
                    
                    self.logger.info(
                        f"任务批次完成: task_batch_id={task_batch_id}, "
                        f"成功={successful_count}, 失败={failed_count}"
                    )
                    
                    if failed_count == len(items):
                        raise APIError("所有音乐生成任务均失败", response_data=result)
                    
                    return True
            
            return False
        
        return self.poll_until_complete(
            check_func=check_status,
            is_complete_func=is_complete,
            interval=poll_interval,
            max_wait=timeout
        )
    
    def download_audio(self, audio_url: str, save_path: str) -> bool:
        """
        下载音频文件
        
        Args:
            audio_url: 音频URL
            save_path: 保存路径
        
        Returns:
            是否下载成功
        """
        try:
            self.logger.info(f"开始下载音频: {audio_url}")
            
            response = requests.get(audio_url, timeout=60)
            response.raise_for_status()
            
            # 确保目录存在
            save_path_obj = Path(save_path)
            save_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存音频
            with open(save_path, 'wb') as f:
                f.write(response.content)
            
            self.logger.info(f"音频下载成功: {save_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"音频下载失败: {e}")
            return False
    
    def generate_and_download(
        self,
        save_dir: str,
        input_type: str = "20",
        prompt: str = "",
        tags: str = "",
        title: str = "",
        make_instrumental: bool = False,
        timeout: Optional[float] = None
    ) -> tuple[bool, List[Dict[str, str]]]:
        """
        生成音乐并下载（一站式接口）
        
        Args:
            save_dir: 保存目录
            input_type: 输入类型
            prompt: 歌词内容
            tags: 音乐风格
            title: 音乐标题
            make_instrumental: 是否纯音乐
            timeout: 超时时间
        
        Returns:
            (是否成功, 音乐信息列表[{"id": "...", "title": "...", "url": "...", "path": "..."}, ...])
        """
        try:
            # 1. 创建任务
            task_info = self.generate_music(
                input_type=input_type,
                prompt=prompt,
                tags=tags,
                title=title,
                make_instrumental=make_instrumental
            )
            task_batch_id = task_info["taskBatchId"]
            
            # 2. 等待完成
            result = self.wait_for_completion(task_batch_id, timeout)
            
            # 3. 下载所有音乐
            items = result.get("items", [])
            music_list = []
            save_dir_obj = Path(save_dir)
            save_dir_obj.mkdir(parents=True, exist_ok=True)
            
            for item in items:
                if item.get("status") == 30:  # 成功的任务
                    music_id = item.get("id")
                    music_title = item.get("title", "untitled")
                    audio_url = item.get("cld2AudioUrl")
                    
                    if audio_url:
                        # 文件名: taskBatchId_id_title.mp3
                        safe_title = "".join(c for c in music_title if c.isalnum() or c in (' ', '-', '_')).strip()
                        filename = f"{task_batch_id}_{music_id}_{safe_title}.mp3"
                        save_path = save_dir_obj / filename
                        
                        if self.download_audio(audio_url, str(save_path)):
                            music_list.append({
                                "id": music_id,
                                "title": music_title,
                                "url": audio_url,
                                "path": str(save_path)
                            })
            
            success = len(music_list) > 0
            self.logger.info(f"音乐生成完成: 成功下载{len(music_list)}首")
            
            return success, music_list
            
        except Exception as e:
            self.logger.error(f"生成并下载音乐失败: {e}")
            return False, []
    
    def batch_generate(
        self,
        tasks: List[Dict[str, Any]],
        save_dir: str,
        timeout: Optional[float] = None
    ) -> List[tuple[bool, str, List[Dict[str, str]]]]:
        """
        批量生成音乐
        
        Args:
            tasks: 任务列表，格式: [{"title": "...", "tags": "...", "prompt": "...", ...}, ...]
            save_dir: 保存目录
            timeout: 每个任务的超时时间
        
        Returns:
            结果列表: [(是否成功, 标题, 音乐信息列表), ...]
        """
        results = []
        
        for idx, task in enumerate(tasks):
            self.logger.info(f"批量生成进度: {idx+1}/{len(tasks)}")
            
            success, music_list = self.generate_and_download(
                save_dir=save_dir,
                input_type=task.get("input_type", "20"),
                prompt=task.get("prompt", ""),
                tags=task.get("tags", ""),
                title=task.get("title", ""),
                make_instrumental=task.get("make_instrumental", False),
                timeout=timeout
            )
            
            results.append((success, task.get("title", ""), music_list))
        
        successful_count = sum(1 for success, _, _ in results if success)
        self.logger.info(f"批量生成完成: 成功{successful_count}/{len(tasks)}")
        
        return results
