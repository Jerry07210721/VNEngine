# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - 背景Agent
负责生成场景背景图
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import time
from datetime import datetime

from ..api.api_manager import APIManager
from ..core.config_manager import ConfigManager
from ..core.models import TaskAssignment, AgentResponse
from ..log.logger import get_logger


class BackgroundAgent:
    """背景生成Agent"""
    
    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        api_manager: Optional[APIManager] = None
    ):
        self.config_manager = config_manager or ConfigManager()
        self.api_manager = api_manager or APIManager(self.config_manager)
        self.logger = get_logger("BackgroundAgent")
        
        self.image_client = self.api_manager.get_image_client(prefer_midjourney=False)
        
        if not self.image_client:
            raise RuntimeError("无法获取图像生成客户端")
        
        self.logger.info(f"BackgroundAgent初始化完成 (图像: {type(self.image_client).__name__})")
    
    def execute(self, task: TaskAssignment) -> AgentResponse:
        start_time = time.time()
        
        try:
            if task.task_type == "generate_backgrounds":
                result = self._generate_backgrounds(task.parameters)
            else:
                raise ValueError(f"不支持的任务类型: {task.task_type}")
            
            return AgentResponse(
                agent_name="background_agent",
                task_type=task.task_type,
                status="success",
                output_files=result["files"],
                metadata=result["metadata"],
                time_cost=time.time() - start_time
            )
        except Exception as e:
            self.logger.error(f"背景生成失败: {e}")
            return AgentResponse(
                agent_name="background_agent",
                task_type=task.task_type,
                status="failure",
                output_files=[],
                metadata={},
                error_message=str(e),
                time_cost=time.time() - start_time
            )
    
    def _generate_backgrounds(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        scene_count = parameters.get("scene_count", 5)
        style = parameters.get("style", "anime")
        project_root = Path(parameters.get("project_root", "output/project"))
        aspect = parameters.get("aspect", "16:9")

        self.logger.info(f"生成背景: 场景数={scene_count}, 风格={style}")

        scenes = [
            ("classroom", "anime style classroom, detailed interior, sunlight through windows"),
            ("school_entrance", "anime school entrance gate, cherry blossoms, blue sky"),
            ("park", "anime style park, green grass, trees, benches, peaceful atmosphere"),
            ("cafe", "cozy anime cafe interior, warm lighting, wooden furniture"),
            ("street", "anime style city street, evening, street lights, shops"),
            ("bedroom", "anime style bedroom, comfortable, moonlight through window"),
            ("rooftop", "school rooftop, blue sky, clouds, fence, cityscape background"),
            ("library", "anime library interior, bookshelves, study desks, quiet atmosphere"),
        ]

        output_dir = project_root / "resources" / "backgrounds"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_files = []

        for i in range(min(scene_count, len(scenes))):
            scene_name, scene_desc = scenes[i]

            self.logger.info(f"生成场景 {i+1}/{scene_count}: {scene_name}")

            prompt = (
                f"{scene_desc}, {style} art style, high quality background art, "
                "visual novel background, detailed environment, professional illustration, no characters"
            )
            params = {"aspect": aspect}

            target_path = output_dir / f"bg_{scene_name}.png"
            file_path = self._generate_and_download(
                prompt=prompt,
                output_path=target_path,
                params=params
            )
            if file_path:
                rel_path = file_path.relative_to(project_root).as_posix()
                output_files.append(rel_path)

        metadata = {
            "scene_count": len(output_files),
            "style": style,
            "generation_time": datetime.now().isoformat()
        }

        return {"files": output_files, "metadata": metadata}

    def _generate_and_download(
        self,
        prompt: str,
        output_path: Path,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Path]:
        client_type = type(self.image_client).__name__

        if "MidjourneyClient" in client_type:
            success, local_path, _url = self.image_client.generate_and_download(
                prompt=prompt,
                save_path=str(output_path),
                params=params
            )
            return Path(local_path) if success and local_path else None

        success, local_paths, _urls = self.image_client.generate_and_download(
            prompt=prompt,
            save_dir=str(output_path.parent),
            params=params
        )
        if success and local_paths:
            downloaded = Path(local_paths[0])
            if downloaded != output_path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                downloaded.replace(output_path)
            return output_path
        return None
    
    def cleanup(self):
        self.logger.info("BackgroundAgent资源清理完成")
