# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - BGM Agent
负责生成背景音乐
"""

from typing import Dict, Any, Optional, List
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
        api_manager: Optional[APIManager] = None,
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
            if task.task_type in {"generate_bgm_item", "generate_bgm_single"}:
                result = self._generate_bgm_item(task.parameters)
            elif task.task_type == "generate_bgm":
                result = self._generate_bgm_batch(task.parameters)
            else:
                raise ValueError(f"不支持的任务类型: {task.task_type}")

            return AgentResponse(
                agent_name="bgm_agent",
                task_type=task.task_type,
                status="success",
                output_files=result["files"],
                metadata=result["metadata"],
                time_cost=time.time() - start_time,
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
                time_cost=time.time() - start_time,
            )

    def build_prompt(self, description: str, mood: str, style: str) -> str:
        desc = description or "visual novel background music"
        mood_text = mood or ""
        style_text = style or ""
        return f"{desc}, {mood_text}, {style_text}, instrumental score, clean mix, loop friendly"

    def _generate_bgm_item(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        bgm_id = parameters.get("bgm_id") or "bgm"
        description = parameters.get("description", "")
        mood = parameters.get("mood", "")
        style = parameters.get("style", "")
        prompt = parameters.get("prompt") or self.build_prompt(description, mood, style)
        tags = parameters.get("tags") or style or mood
        project_root = self._project_root(parameters)
        output_path = self._resolve_output_path(parameters, project_root, default_rel=f"resources/bgm/{bgm_id}.mp3")

        success, music_list = self.music_client.generate_and_download(
            save_dir=str(output_path.parent),
            input_type=parameters.get("input_type", "20"),
            prompt=prompt,
            tags=tags,
            title=parameters.get("title", bgm_id),
            make_instrumental=parameters.get("make_instrumental", True),
            timeout=parameters.get("timeout"),
        )

        if not success or not music_list:
            raise RuntimeError("未生成有效的BGM")

        first = music_list[0]
        downloaded_path = Path(first.get("path", ""))
        if not downloaded_path.exists():
            raise RuntimeError("生成文件不存在")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if downloaded_path != output_path:
            if output_path.exists():
                output_path.unlink()
            downloaded_path.replace(output_path)

        rel_path = self._to_relative(output_path, project_root)
        metadata = {
            "bgm_id": bgm_id,
            "mood": mood,
            "style": style,
            "duration": parameters.get("duration", 120),
            "loop": parameters.get("loop", True),
            "source_title": first.get("title", ""),
            "generation_time": datetime.now().isoformat(),
            "provider": "suno",
        }

        return {"files": [rel_path], "metadata": metadata}

    def _generate_bgm_batch(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        bgm_count = parameters.get("bgm_count", 3)
        music_style = parameters.get("music_style", "piano")
        project_root = self._project_root(parameters)

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

        output_files: List[str] = []

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
                    make_instrumental=True,
                )
                if success and music_list:
                    first = music_list[0]
                    local_path = first.get("path", "")
                    if local_path:
                        output_files.append(self._to_relative(Path(local_path), project_root))
                    self.logger.info(f"  完成: {bgm_name}")
            except Exception as e:
                self.logger.warning(f"  跳过 {bgm_name}: {e}")

        metadata = {
            "bgm_count": len(output_files),
            "style": music_style,
            "generation_time": datetime.now().isoformat(),
        }

        return {"files": output_files, "metadata": metadata}

    def _project_root(self, parameters: Dict[str, Any]) -> Path:
        root = parameters.get("project_root")
        if root:
            return Path(root).expanduser().resolve()
        output_path = parameters.get("output_path") or parameters.get("file_path")
        if output_path:
            p = Path(output_path).expanduser().resolve()
            for candidate in p.parents:
                if candidate.name == "resources" and candidate.parent.exists():
                    return candidate.parent
            return p.parent
        return Path.cwd() / "output" / "project"

    def _resolve_output_path(self, parameters: Dict[str, Any], project_root: Path, default_rel: str) -> Path:
        output_path = parameters.get("output_path") or parameters.get("file_path")
        if output_path:
            p = Path(output_path)
            return p if p.is_absolute() else (project_root / p).resolve()
        return (project_root / default_rel).resolve()

    def _to_relative(self, path: Path, project_root: Path) -> str:
        try:
            return path.resolve().relative_to(project_root).as_posix()
        except Exception:
            return path.as_posix()

    def cleanup(self):
        self.logger.info("BGMAgent资源清理完成")
