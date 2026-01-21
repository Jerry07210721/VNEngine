# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - CG Agent
负责生成事件CG图
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
import time
from datetime import datetime
import base64
import io

from ..utils.flux_reference_images import prepare_flux_reference_images

from ..api.api_manager import APIManager
from ..core.config_manager import ConfigManager
from ..core.models import TaskAssignment, AgentResponse
from ..log.logger import get_logger


class CGAgent:
    """CG生成Agent"""

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        api_manager: Optional[APIManager] = None,
        prefer_midjourney: bool = False,
    ):
        self.config_manager = config_manager or ConfigManager()
        self.api_manager = api_manager or APIManager(self.config_manager)
        self.logger = get_logger("CGAgent")
        self.prefer_midjourney = prefer_midjourney

        self.image_client = self.api_manager.get_image_client(prefer_midjourney=self.prefer_midjourney)

        if not self.image_client:
            raise RuntimeError("无法获取图像生成客户端")

        self.logger.info(f"CGAgent初始化完成 (图像: {type(self.image_client).__name__})")

    def execute(self, task: TaskAssignment) -> AgentResponse:
        start_time = time.time()

        try:
            if task.task_type in {"generate_cg_item", "generate_cg_single"}:
                result = self._generate_single_cg(task.parameters)
            elif task.task_type == "generate_cg":
                result = self._generate_cg_batch(task.parameters)
            else:
                raise ValueError(f"不支持的任务类型: {task.task_type}")

            return AgentResponse(
                agent_name="cg_agent",
                task_type=task.task_type,
                status="success",
                output_files=result["files"],
                metadata=result["metadata"],
                time_cost=time.time() - start_time,
            )
        except Exception as e:
            self.logger.error(f"CG生成失败: {e}")
            return AgentResponse(
                agent_name="cg_agent",
                task_type=task.task_type,
                status="failure",
                output_files=[],
                metadata={},
                error_message=str(e),
                time_cost=time.time() - start_time,
            )

    def build_prompt(
        self,
        scene_description: str,
        characters: List[str],
        atmosphere: str,
        use_reference_images: bool = False,
    ) -> str:
        chars = ", ".join([c for c in (characters or []) if c])
        atmos = (atmosphere or "").strip()
        role_part = f"characters: {chars}" if chars else "characters: (not specified)"
        scene_desc = (scene_description or "").strip() or "(please describe the scene in detail)"
        consistency = (
            "STRICT consistency with provided reference character images: same face, same hairstyle, same outfit, same proportions, same color palette. "
            "Do NOT redesign the character. "
            if use_reference_images
            else ""
        )

        # 预留“用户可编辑的画面描述”段，便于 UI 直接展示并让用户修改
        return (
            "visual novel event CG, anime style, cinematic lighting, dramatic composition, depth of field, highly detailed illustration, high quality game art. "
            f"{role_part}. "
            f"atmosphere: {atmos}. "
            f"SCENE DESCRIPTION (user editable): {scene_desc}. "
            f"{consistency}"
            "clean background (if appropriate), no subtitles, no on-screen text, no watermark, no logo"
        )

    def _generate_single_cg(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        cg_id = parameters.get("cg_id") or "cg"
        # 画面详细描述（建议在 UI 中暴露给用户编辑）
        description = parameters.get("scene_description") or parameters.get("description", "")
        characters = parameters.get("characters", []) or []
        atmosphere = parameters.get("atmosphere", "")
        prompt = parameters.get("prompt")
        aspect = parameters.get("aspect", "16:9")
        model_choice = parameters.get("model") or "flux"
        flux_model = parameters.get("flux_model")
        flux_mode = parameters.get("flux_mode")
        flux_num = parameters.get("flux_num")
        flux_size = parameters.get("flux_size")
        ref_image_paths = parameters.get("reference_images") or []
        project_root = self._project_root(parameters)

        output_path = self._resolve_output_path(parameters, project_root, default_rel=f"resources/images/cg/{cg_id}.png")
        self._ensure_image_client(model_choice)

        # 用户显式上传参考图优先，否则回退到自动搜立绘参考
        ref_images: List[Dict[str, Any]] = []
        if isinstance(ref_image_paths, list) and ref_image_paths:
            paths = [Path(p) for p in ref_image_paths if p]
            ref_images = prepare_flux_reference_images(paths, limit=3)
        else:
            ref_images = self._load_reference_portraits(project_root, characters)

        if not (isinstance(prompt, str) and prompt.strip()):
            prompt = self.build_prompt(description, characters, atmosphere, use_reference_images=bool(ref_images))

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
            raise RuntimeError("CG生成失败")

        rel_path = self._to_relative(file_path, project_root)
        metadata = {
            "cg_id": cg_id,
            "model": type(self.image_client).__name__,
            "aspect": aspect,
            "generation_time": datetime.now().isoformat(),
        }
        return {"files": [rel_path], "metadata": metadata}

    def _generate_cg_batch(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        cg_count = parameters.get("cg_count", 3)
        style = parameters.get("style", "anime")
        project_root = self._project_root(parameters)
        aspect = parameters.get("aspect", "16:9")
        model_choice = parameters.get("model")
        self._ensure_image_client(model_choice or "flux")

        self.logger.info(f"生成CG: 数量={cg_count}, 风格={style}")

        cg_scenes = [
            ("confession", "romantic confession scene, two characters, cherry blossoms falling, sunset background, emotional moment"),
            ("first_meeting", "first meeting scene, characters surprised, school hallway, dramatic lighting"),
            ("happy_ending", "happy ending scene, characters smiling together, bright sunny day, hopeful atmosphere"),
            ("dramatic_moment", "dramatic confrontation scene, intense emotions, dynamic composition"),
            ("peaceful_moment", "peaceful moment, characters relaxing together, gentle atmosphere"),
        ]

        output_dir = project_root / "resources" / "images" / "cg"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_files = []

        reference_images = self._load_reference_portraits(project_root, [])

        for i in range(min(cg_count, len(cg_scenes))):
            cg_name, cg_desc = cg_scenes[i]

            self.logger.info(f"生成CG {i+1}/{cg_count}: {cg_name}")

            prompt = (
                f"{cg_desc}, {style} art style, visual novel CG, cinematic composition, "
                "detailed illustration, high quality artwork, professional game art"
            )
            params = {"aspect": aspect}

            target_path = output_dir / f"cg_{cg_name}.png"
            file_path = self._generate_and_download(
                prompt=prompt,
                output_path=target_path,
                params=params,
                images=reference_images,
            )
            if file_path:
                output_files.append(self._to_relative(file_path, project_root))

        metadata = {
            "cg_count": len(output_files),
            "style": style,
            "aspect": aspect,
            "generation_time": datetime.now().isoformat(),
            "model": type(self.image_client).__name__,
        }

        return {"files": output_files, "metadata": metadata}

    def _load_reference_portraits(self, project_root: Path, preferred_chars: List[str]) -> List[Dict[str, Any]]:
        portraits_dir = project_root / "resources" / "portraits"
        refs: List[Dict[str, Any]] = []
        if not portraits_dir.exists():
            return refs

        def iter_candidates():
            ordered = []
            if preferred_chars:
                for char in preferred_chars:
                    ordered.append(portraits_dir / char)
            ordered.extend(sorted([p for p in portraits_dir.iterdir() if p.is_dir()]))
            for path in ordered:
                if path.exists() and path.is_dir():
                    yield path

        candidate_paths: List[Path] = []
        for char_dir in iter_candidates():
            candidates = list(char_dir.glob("*_neutral.png")) or list(char_dir.glob("*.png"))
            if candidates:
                candidate_paths.append(candidates[0])
            if len(candidate_paths) >= 3:
                break

        if candidate_paths:
            refs = prepare_flux_reference_images(candidate_paths, limit=3)

        return refs

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
                images=images,
            )
            return Path(local_path) if success and local_path else None

        # FluxClient 支持 per-call model 覆盖
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
                images=images,
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
        self.logger.info("CGAgent资源清理完成")
