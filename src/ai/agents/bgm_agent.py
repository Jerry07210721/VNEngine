# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - BGM Agent
负责生成背景音乐
"""

from typing import Dict, Any, Optional
from pathlib import Path
import time
from datetime import datetime

from ..api.api_manager import APIManager
from ..core.config_manager import ConfigManager
from ..core.models import TaskAssignment, AgentResponse
from ..log.logger import get_logger


class BGMAgent:
    """BGM生成Agent"""
    
    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        api_manager: Optional[APIManager] = None
    ):
        self.config_manager = config_manager or ConfigManager()
        self.api_manager = api_manager or APIManager(self.config_manager)
        self.logger = get_logger("BGMAgent")
        
        self.music_client = self.api_manager.get_suno_client()
        
        if not self.music_client:
            raise RuntimeError("无法获取音乐生成客户端")
        
        self.logger.info("BGMAgent初始化完成")
    
    def execute(self, task: TaskAssignment) -> AgentResponse:
        start_time = time.time()
        
        try:
            if task.task_type == "generate_bgm":
                result = self._generate_bgm(task.parameters)
            else:
                raise ValueError(f"不支持的任务类型: {task.task_type}")
            
            return AgentResponse(
                agent_name="bgm_agent",
                task_type=task.task_type,
                status="success",
                output_files=result["files"],
                metadata=result["metadata"],
                time_cost=time.time() - start_time
            )
        except Exception as e:
            self.logger.error(f"BGM生成失败: {e}")
            return AgentResponse(
                agent_name="bgm_agent",
                task_type=task.task_type,
                status="failure",
                output_files=[],
                metadata={},
                error_message=str(e),
                time_cost=time.time() - start_time
            )
    
    def _generate_bgm(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        bgm_count = parameters.get("bgm_count", 3)
        music_style = parameters.get("music_style", "piano")
        project_root = Path(parameters.get("project_root", "output/project"))

        self.logger.info(f"生成BGM: 数量={bgm_count}, 风格={music_style}")

        bgm_scenes = [
            ("main_theme", "uplifting piano melody, hopeful atmosphere, visual novel main theme"),
            ("romantic", "romantic piano and strings, gentle emotional piece, love theme"),
            ("tension", "suspenseful orchestral music, building tension, dramatic scene"),
            ("peaceful", "calm ambient piano, peaceful atmosphere, relaxing background music"),
            ("cheerful", "upbeat cheerful melody, happy scene music, lighthearted tune"),
        ]

        output_dir = project_root / "resources" / "bgm"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_files = []

        for i in range(min(bgm_count, len(bgm_scenes))):
            bgm_name, bgm_desc = bgm_scenes[i]

            self.logger.info(f"生成BGM {i+1}/{bgm_count}: {bgm_name}")

            prompt = f"{bgm_desc}, instrumental only, {music_style} style"

            try:
                success, music_list = self.music_client.generate_and_download(
                    save_dir=str(output_dir),
                    input_type="20",
                    prompt=prompt,
                    tags=music_style,
                    title=bgm_name,
                    make_instrumental=True
                )
                if success and music_list:
                    first = music_list[0]
                    local_path = first.get("path", "")
                    if local_path:
                        output_files.append(Path(local_path).relative_to(project_root).as_posix())
                    self.logger.info(f"  完成: {bgm_name}")
            except Exception as e:
                self.logger.warning(f"  跳过 {bgm_name}: {e}")

        metadata = {
            "bgm_count": len(output_files),
            "style": music_style,
            "generation_time": datetime.now().isoformat()
        }

        return {"files": output_files, "metadata": metadata}
    
    def cleanup(self):
        self.logger.info("BGMAgent资源清理完成")
