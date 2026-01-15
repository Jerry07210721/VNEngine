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

from ..api.api_manager import APIManager
from ..core.config_manager import ConfigManager
from ..core.models import TaskAssignment, AgentResponse
from ..log.logger import get_logger


class CGAgent:
    """CG生成Agent"""
    
    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        api_manager: Optional[APIManager] = None
    ):
        self.config_manager = config_manager or ConfigManager()
        self.api_manager = api_manager or APIManager(self.config_manager)
        self.logger = get_logger("CGAgent")
        
        self.image_client = self.api_manager.get_image_client(prefer_midjourney=False)
        
        if not self.image_client:
            raise RuntimeError("无法获取图像生成客户端")
        
        self.logger.info(f"CGAgent初始化完成 (图像: {type(self.image_client).__name__})")
    
    def execute(self, task: TaskAssignment) -> AgentResponse:
        start_time = time.time()
        
        try:
            if task.task_type == "generate_cg":
                result = self._generate_cg(task.parameters)
            else:
                raise ValueError(f"不支持的任务类型: {task.task_type}")
            
            return AgentResponse(
                agent_name="cg_agent",
                task_type=task.task_type,
                status="success",
                output_files=result["files"],
                metadata=result["metadata"],
                time_cost=time.time() - start_time
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
                time_cost=time.time() - start_time
            )
    
    def _generate_cg(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        cg_count = parameters.get("cg_count", 3)
        style = parameters.get("style", "anime")
        project_root = Path(parameters.get("project_root", "output/project"))

        self.logger.info(f"生成CG: 数量={cg_count}, 风格={style}")

        cg_scenes = [
            ("confession", "romantic confession scene, two characters, cherry blossoms falling, sunset background, emotional moment"),
            ("first_meeting", "first meeting scene, characters surprised, school hallway, dramatic lighting"),
            ("happy_ending", "happy ending scene, characters smiling together, bright sunny day, hopeful atmosphere"),
            ("dramatic_moment", "dramatic confrontation scene, intense emotions, dynamic composition"),
            ("peaceful_moment", "peaceful moment, characters relaxing together, gentle atmosphere"),
        ]

        output_dir = project_root / "resources" / "cg"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_files = []

        # 尝试加载参考立绘（每个角色一张）
        reference_images = self._load_reference_portraits(project_root)

        for i in range(min(cg_count, len(cg_scenes))):
            cg_name, cg_desc = cg_scenes[i]

            self.logger.info(f"生成CG {i+1}/{cg_count}: {cg_name}")

            prompt = (
                f"{cg_desc}, {style} art style, visual novel CG, cinematic composition, "
                "detailed illustration, high quality artwork, professional game art"
            )
            params = {"aspect": "16:9"}

            target_path = output_dir / f"cg_{cg_name}.png"
            file_path = self._generate_and_download(
                prompt=prompt,
                output_path=target_path,
                params=params,
                images=reference_images
            )
            if file_path:
                rel_path = file_path.relative_to(project_root).as_posix()
                output_files.append(rel_path)

        metadata = {
            "cg_count": len(output_files),
            "style": style,
            "generation_time": datetime.now().isoformat()
        }

        return {"files": output_files, "metadata": metadata}

    def _load_reference_portraits(self, project_root: Path) -> List[Dict[str, Any]]:
        """从已生成的立绘中取少量参考图，压缩后传给FLUX。"""
        portraits_dir = project_root / "resources" / "portraits"
        refs: List[Dict[str, Any]] = []
        if not portraits_dir.exists():
            return refs

        try:
            from PIL import Image
        except Exception:
            Image = None

        for char_dir in sorted(portraits_dir.iterdir()):
            if not char_dir.is_dir():
                continue
            candidates = list(char_dir.glob("*_neutral.png")) or list(char_dir.glob("*.png"))
            if not candidates:
                continue
            img_path = candidates[0]
            try:
                raw = img_path.read_bytes()
                if Image:
                    img = Image.open(io.BytesIO(raw)).convert("RGBA")
                    max_side = max(img.size)
                    if max_side > 1024:
                        scale = 1024 / max_side
                        new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
                        img = img.resize(new_size)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG", optimize=True)
                    data = buf.getvalue()
                else:
                    data = raw

                if len(data) > 500_000:
                    self.logger.warning(f"参考立绘过大，跳过: {img_path.name}")
                    continue
                refs.append({
                    "type": "image/png",
                    "b64": base64.b64encode(data).decode("ascii"),
                })
            except Exception as exc:
                self.logger.warning(f"读取参考立绘失败 {img_path}: {exc}")

            if len(refs) >= 3:
                break

        return refs

    def _generate_and_download(
        self,
        prompt: str,
        output_path: Path,
        params: Optional[Dict[str, Any]] = None,
        images: Optional[list] = None,
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
    
    def cleanup(self):
        self.logger.info("CGAgent资源清理完成")
