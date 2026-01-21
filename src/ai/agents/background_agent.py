# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - 背景Agent
负责生成场景背景图
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import time
from datetime import datetime

from ..utils.flux_reference_images import prepare_flux_reference_images

from ..api.api_manager import APIManager
from ..core.config_manager import ConfigManager
from ..core.models import TaskAssignment, AgentResponse
from ..log.logger import get_logger


class BackgroundAgent:
    """背景生成Agent"""

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        api_manager: Optional[APIManager] = None,
        prefer_midjourney: bool = False,
    ):
        self.config_manager = config_manager or ConfigManager()
        self.api_manager = api_manager or APIManager(self.config_manager)
        self.logger = get_logger("BackgroundAgent")
        self.prefer_midjourney = prefer_midjourney

        self.image_client = self.api_manager.get_image_client(prefer_midjourney=self.prefer_midjourney)

        if not self.image_client:
            raise RuntimeError("无法获取图像生成客户端")

        self.logger.info(f"BackgroundAgent初始化完成 (图像: {type(self.image_client).__name__})")

    def execute(self, task: TaskAssignment) -> AgentResponse:
        start_time = time.time()

        try:
            if task.task_type in {"generate_background_item", "generate_background_single"}:
                result = self._generate_single_background(task.parameters)
            elif task.task_type == "generate_backgrounds":
                result = self._generate_background_batch(task.parameters)
            else:
                raise ValueError(f"不支持的任务类型: {task.task_type}")

            return AgentResponse(
                agent_name="background_agent",
                task_type=task.task_type,
                status="success",
                output_files=result["files"],
                metadata=result["metadata"],
                time_cost=time.time() - start_time,
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
                time_cost=time.time() - start_time,
            )

    def build_prompt(self, description: str, atmosphere: str, time_weather: str) -> str:
        atmos = atmosphere or ""
        tw = time_weather or ""
        return (
            f"visual novel background (establishing shot), {description}, {atmos}, {tw}, "
            "anime style environment concept art, wide shot, strong depth, detailed lighting, "
            "high quality background art, clean composition, "
            "no characters, no subtitles, no text, no watermark, no logo"
        )

    def _generate_single_background(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        bg_id = parameters.get("bg_id") or "bg"
        description = parameters.get("description", "")
        atmosphere = parameters.get("atmosphere", "")
        time_weather = parameters.get("time_weather", "")
        prompt = parameters.get("prompt") or self.build_prompt(description, atmosphere, time_weather)
        aspect = parameters.get("aspect", "16:9")
        model_choice = parameters.get("model") or "flux"
        flux_model = parameters.get("flux_model")
        flux_mode = parameters.get("flux_mode")
        flux_num = parameters.get("flux_num")
        flux_size = parameters.get("flux_size")
        ref_image_paths = parameters.get("reference_images") or []
        project_root = self._project_root(parameters)

        output_path = self._resolve_output_path(parameters, project_root, default_rel=f"resources/images/{bg_id}.png")
        self._ensure_image_client(model_choice)

        ref_images: List[Dict[str, Any]] = []
        if isinstance(ref_image_paths, list) and ref_image_paths:
            paths = [Path(p) for p in ref_image_paths if p]
            ref_images = prepare_flux_reference_images(paths, limit=3)

        flux_params: Dict[str, Any] = {"aspect": aspect}
        if flux_num is not None:
            try:
                flux_params["num"] = int(flux_num)
            except Exception:
                pass
        if flux_mode:
            flux_params["mode"] = str(flux_mode)
        if flux_size is not None and str(flux_size).strip():
            size_str = str(flux_size).strip().upper()
            if size_str in {"1MP", "2MP", "4MP"}:
                flux_params["size"] = size_str

        file_path = self._generate_and_download(
            prompt=prompt,
            output_path=output_path,
            params=flux_params,
            images=ref_images if ref_images else None,
            flux_model=flux_model,
        )
        if not file_path:
            raise RuntimeError("背景生成失败")

        rel_path = self._to_relative(file_path, project_root)
        metadata = {
            "bg_id": bg_id,
            "model": type(self.image_client).__name__,
            "aspect": aspect,
            "generation_time": datetime.now().isoformat(),
        }
        return {"files": [rel_path], "metadata": metadata}

    def _generate_background_batch(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        scene_count = parameters.get("scene_count", 5)
        style = parameters.get("style", "anime")
        project_root = self._project_root(parameters)
        aspect = parameters.get("aspect", "16:9")
        model_choice = parameters.get("model") or "flux"

        self._ensure_image_client(model_choice)

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

        output_dir = project_root / "resources" / "images"
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
                params=params,
            )
            if file_path:
                output_files.append(self._to_relative(file_path, project_root))

        metadata = {
            "scene_count": len(output_files),
            "style": style,
            "aspect": aspect,
            "generation_time": datetime.now().isoformat(),
            "model": type(self.image_client).__name__,
        }

        return {"files": output_files, "metadata": metadata}

    def _generate_and_download(
        self,
        prompt: str,
        output_path: Path,
        params: Optional[Dict[str, Any]] = None,
        images: Optional[list] = None,
        flux_model: Optional[str] = None,
    ) -> Optional[Path]:
        client_type = type(self.image_client).__name__

        if "MidjourneyClient" in client_type:
            success, local_path, _url = self.image_client.generate_and_download(
                prompt=prompt,
                save_path=str(output_path),
                params=params,
            )
            return Path(local_path) if success and local_path else None

        if "FluxClient" in client_type:
            success, local_paths, _urls = self.image_client.generate_and_download(
                prompt=prompt,
                save_dir=str(output_path.parent),
                params=params,
                images=images,
                model=flux_model,
            )
        else:
            success, local_paths, _urls = self.image_client.generate_and_download(
                prompt=prompt,
                save_dir=str(output_path.parent),
                params=params,
            )
        if success and local_paths:
            downloaded = Path(local_paths[0])
            if downloaded != output_path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                downloaded.replace(output_path)
            return output_path
        return None

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

    def _ensure_image_client(self, model_choice: Optional[str]):
        target_midjourney = None
        if model_choice:
            target_midjourney = model_choice.lower() == "midjourney"

        if target_midjourney is None:
            return

        current_is_mj = "MidjourneyClient" in type(self.image_client).__name__
        if current_is_mj == target_midjourney and self.image_client:
            return

        client = self.api_manager.get_image_client(prefer_midjourney=target_midjourney)
        if client:
            self.image_client = client
            self.logger.info(f"已切换图像客户端: {type(client).__name__}")

    def cleanup(self):
        self.logger.info("BackgroundAgent资源清理完成")
