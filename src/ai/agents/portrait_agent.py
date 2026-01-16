# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - 立绘Agent
负责生成角色立绘和表情差分图
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import json
import time
from datetime import datetime
import base64
import io
from typing import Tuple

from ..api.api_manager import APIManager
from ..core.config_manager import ConfigManager
from ..core.models import TaskAssignment, AgentResponse
from ..log.logger import get_logger


class PortraitAgent:
    """立绘生成Agent"""
    
    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        api_manager: Optional[APIManager] = None,
        prefer_midjourney: bool = False,
    ):
        """
        初始化立绘Agent
        
        Args:
            config_manager: 配置管理器
            api_manager: API管理器
        """
        self.config_manager = config_manager or ConfigManager()
        self.api_manager = api_manager or APIManager(self.config_manager)
        self.logger = get_logger("PortraitAgent")
        self.prefer_midjourney = prefer_midjourney
        
        # 获取图像生成客户端（优先FLUX）
        self.image_client = self.api_manager.get_image_client(prefer_midjourney=self.prefer_midjourney)
        
        if not self.image_client:
            raise RuntimeError("无法获取图像生成客户端，请检查配置")
        
        self.logger.info(f"PortraitAgent初始化完成 (图像: {type(self.image_client).__name__})")
    
    def execute(self, task: TaskAssignment) -> AgentResponse:
        """
        执行立绘生成任务
        
        Args:
            task: 任务配置
        
        Returns:
            Agent响应
        """
        start_time = time.time()
        
        self.logger.info(f"开始执行立绘生成任务: {task.task_type}")
        
        try:
            if task.task_type == "generate_portrait":
                result = self._generate_portrait(task.parameters)
            elif task.task_type == "generate_design_sheet":
                result = self._generate_design_sheet(task.parameters)
            elif task.task_type == "generate_base_portrait":
                result = self._generate_base_portrait(task.parameters)
            elif task.task_type == "generate_expression_batch":
                result = self._generate_expression_batch(task.parameters)
            else:
                raise ValueError(f"不支持的任务类型: {task.task_type}")
            
            time_cost = time.time() - start_time
            
            return AgentResponse(
                agent_name="portrait_agent",
                task_type=task.task_type,
                status="success",
                output_files=result["files"],
                metadata=result["metadata"],
                time_cost=time_cost
            )
            
        except Exception as e:
            self.logger.error(f"立绘生成失败: {e}")
            
            return AgentResponse(
                agent_name="portrait_agent",
                task_type=task.task_type,
                status="failure",
                output_files=[],
                metadata={},
                error_message=str(e),
                time_cost=time.time() - start_time
            )
    
    def _generate_portrait(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        char_name = parameters.get("character_name", "角色")
        description = parameters.get("description", parameters.get("persona", ""))
        expressions = parameters.get("expressions", ["neutral", "happy", "sad", "angry"])
        project_root = Path(parameters.get("project_root", "output/project"))
        aspect = parameters.get("aspect", "2:3")
        model_choice = parameters.get("model")
        prefer_midjourney = parameters.get("prefer_midjourney")

        self._ensure_image_client(prefer_midjourney, model_choice)

        # 用于一致性生成的参考图列表（基础立绘生成后再填充）
        reference_images: List[Dict[str, Any]] = []
        support_reference = "FluxClient" in type(self.image_client).__name__

        self.logger.info(f"生成立绘: {char_name}, 表情数={len(expressions)}")

        output_dir = project_root / "resources" / "portraits" / char_name
        output_dir.mkdir(parents=True, exist_ok=True)

        output_files = []

        base_prompt = self._build_portrait_prompt(char_name, description, "neutral")
        base_params = {"aspect": aspect}
        self.logger.info("生成基础立绘(全身+透明背景)...")

        base_file = self._generate_and_download(
            prompt=base_prompt,
            output_path=output_dir / f"{char_name}_neutral.png",
            params=base_params,
            postprocess_transparent=False,
        )
        if base_file:
            output_files.append(base_file.relative_to(project_root).as_posix())
            if support_reference:
                ref = self._prepare_reference_image(base_file)
                if ref:
                    reference_images = [ref]
                else:
                    self.logger.warning("参考图过大或处理失败，差分将不使用参考图")
        else:
            raise RuntimeError("基础立绘生成失败，后续差分无法进行")

        for expression in expressions:
            if expression == "neutral":
                continue

            self.logger.info(f"生成表情差分: {expression}")

            expr_prompt = self._build_portrait_prompt(char_name, description, expression, use_reference=support_reference)
            expr_params = {"aspect": aspect}

            expr_file = self._generate_and_download(
                prompt=expr_prompt,
                output_path=output_dir / f"{char_name}_{expression}.png",
                params=expr_params,
                images=reference_images if support_reference else None,
                postprocess_transparent=False,
            )
            if expr_file:
                output_files.append(expr_file.relative_to(project_root).as_posix())

        metadata = {
            "character_name": char_name,
            "expression_count": len(expressions),
            "expressions": expressions,
            "generation_time": datetime.now().isoformat(),
            "model": type(self.image_client).__name__,
        }

        return {
            "files": output_files,
            "metadata": metadata
        }

    def _generate_design_sheet(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """仅生成设定图，不遵循命名规则，保存到指定路径。"""
        char_name = parameters.get("character_name", "角色")
        prompt = parameters.get("prompt") or self.build_design_prompt(char_name, parameters.get("description", ""))
        save_path = Path(parameters.get("save_path", "design.png"))
        aspect = parameters.get("aspect", "3:2")
        model_choice = parameters.get("model") or "midjourney"
        self._ensure_image_client(None, model_choice)

        save_path.parent.mkdir(parents=True, exist_ok=True)
        file_path = self._generate_and_download(prompt=prompt, output_path=save_path, params={"aspect": aspect}, images=None)
        if not file_path:
            raise RuntimeError("设定图生成失败")

        return {
            "files": [file_path.as_posix()],
            "metadata": {"mode": "design_sheet", "model": type(self.image_client).__name__},
        }

    def _generate_base_portrait(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """生成基准立绘（neutral）。"""
        char_id = parameters.get("char_id") or parameters.get("character_name", "role")
        char_name = parameters.get("character_name", char_id)
        prompt = parameters.get("prompt") or self._build_portrait_prompt(char_name, parameters.get("description", ""), "neutral")
        output_path = Path(parameters.get("output_path", "base.png"))
        aspect = parameters.get("aspect", "2:3")
        model_choice = parameters.get("model") or "flux"
        self._ensure_image_client(None, model_choice)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        file_path = self._generate_and_download(prompt=prompt, output_path=output_path, params={"aspect": aspect}, images=None)
        if not file_path:
            raise RuntimeError("基准立绘生成失败")

        return {
            "files": [file_path.as_posix()],
            "metadata": {"mode": "base", "model": type(self.image_client).__name__},
        }

    def _generate_expression_batch(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """基于基准图批量生成表情差分（一次最多4张视具体接口而定）。"""
        char_id = parameters.get("char_id") or parameters.get("character_name", "role")
        char_name = parameters.get("character_name", char_id)
        description = parameters.get("description", "")
        expressions: List[str] = parameters.get("expressions", [])
        aspect = parameters.get("aspect", "2:3")
        model_choice = parameters.get("model") or "flux"
        base_image = parameters.get("base_image_path")
        output_dir = Path(parameters.get("output_dir", "output/portraits"))
        output_dir.mkdir(parents=True, exist_ok=True)

        if not expressions:
            return {"files": [], "metadata": {"mode": "expression_batch", "model": model_choice}}

        self._ensure_image_client(None, model_choice)
        support_reference = "FluxClient" in type(self.image_client).__name__
        if not support_reference:
            raise RuntimeError("表情差分仅支持Flux客户端，请选择Flux")
        ref_images = []
        if base_image and support_reference:
            ref = self._prepare_reference_image(Path(base_image))
            if ref:
                ref_images = [ref]

        output_files: List[str] = []
        for exp in expressions:
            prompt = self._build_portrait_prompt(char_name, description, exp, use_reference=support_reference)
            out_path = output_dir / f"{char_id}_{exp}.png"
            file_path = self._generate_and_download(
                prompt=prompt,
                output_path=out_path,
                params={"aspect": aspect},
                images=ref_images if support_reference else None,
            )
            if file_path:
                output_files.append(file_path.as_posix())

        return {
            "files": output_files,
            "metadata": {"mode": "expression_batch", "model": type(self.image_client).__name__, "count": len(output_files)},
        }
    
    def _build_portrait_prompt(
        self,
        char_name: str,
        description: str,
        expression: str,
        use_reference: bool = False
    ) -> str:
        """构建立绘生成提示词"""
        
        # 表情描述映射
        expression_desc = {
            "neutral": "neutral expression, calm face",
            "happy": "happy smile, cheerful expression",
            "sad": "sad expression, teary eyes",
            "angry": "angry expression, furrowed brows",
            "surprised": "surprised expression, wide eyes",
            "embarrassed": "embarrassed blush, shy expression",
            "thinking": "thoughtful expression, pondering",
            "worried": "worried expression, concerned look"
        }
        
        expr_text = expression_desc.get(expression, f"{expression} expression")
        
        transparent_hint = "transparent background, no background elements, alpha channel"
        consistency_hint = "keep proportions and outfit consistent with reference" if use_reference else ""
        prompt = (
            f"anime character portrait, {char_name}, {description}, {expr_text}, full body standing pose,"
            f" {transparent_hint}, {consistency_hint} high quality anime art style, visual novel character design,"
            " detailed shading, professional illustration"
        )
        
        return prompt

    def build_design_prompt(self, char_name: str, description: str) -> str:
        """生成设定图提示词模板。"""
        desc = description or ""
        return (
            f"anime character design sheet, {char_name}, full body front and side, outfit variants, clear partition layout, "
            f"5 expression close-ups, {desc}, ultra high detail, clean white background, professional reference sheet"
        )
    
    def _prepare_reference_image(self, image_path: Path) -> Optional[Dict[str, Any]]:
        """准备参考图，迭代压缩到安全体积，返回FLUX可接受的b64结构。"""
        try:
            try:
                from PIL import Image
            except Exception:
                Image = None

            raw = image_path.read_bytes()

            if not Image:
                data = raw
            else:
                img = Image.open(io.BytesIO(raw)).convert("RGBA")
                # 多级缩放+压缩，目标 < 420KB
                for max_side in [1024, 900, 768, 640, 512]:
                    scaled = self._resize_with_max_side(img, max_side)
                    data = self._encode_png(scaled, optimize=True)
                    if len(data) <= 420_000:
                        break
                else:
                    self.logger.warning(f"参考图仍过大({len(data)} bytes)，跳过以避免413")
                    return None

            b64 = base64.b64encode(data).decode("ascii")
            return {
                "type": "image/png",
                "b64": f"data:image/png;base64,{b64}",
            }
        except Exception as exc:
            self.logger.warning(f"参考图处理失败: {exc}")
            return None

    def _generate_and_download(
        self,
        prompt: str,
        output_path: Path,
        params: Optional[Dict[str, Any]] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        postprocess_transparent: bool = False,
    ) -> Optional[Path]:
        """生成并下载图像，必要时做透明背景后处理。"""

        client_type = type(self.image_client).__name__

        if "MidjourneyClient" in client_type:
            success, local_path, _url = self.image_client.generate_and_download(
                prompt=prompt,
                save_path=str(output_path),
                params=params,
                images=images,
            )
            final_path = Path(local_path) if success and local_path else None
        else:
            success, local_paths, _urls = self.image_client.generate_and_download(
                prompt=prompt,
                save_dir=str(output_path.parent),
                params=params,
                images=images,
            )
            final_path = None
            if success and local_paths:
                downloaded = Path(local_paths[0])
                if downloaded != output_path:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    downloaded.replace(output_path)
                final_path = output_path

        if final_path and postprocess_transparent:
            self._ensure_transparency(final_path)

        return final_path

    def _ensure_image_client(self, prefer_midjourney: Optional[bool], model_choice: Optional[str]):
        """根据用户选择切换图像客户端。"""
        target_midjourney = None
        if model_choice:
            target_midjourney = model_choice.lower() == "midjourney"
        elif prefer_midjourney is not None:
            target_midjourney = bool(prefer_midjourney)

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
        """清理资源"""
        self.logger.info("PortraitAgent资源清理完成")

    # ----------------- 图像处理辅助 -----------------
    def _resize_with_max_side(self, img, max_side: int):
        w, h = img.size
        scale = min(1.0, float(max_side) / float(max(w, h)))
        if scale >= 0.999:
            return img
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        return img.resize(new_size)

    def _encode_png(self, img, optimize: bool = True) -> bytes:
        buf = io.BytesIO()
        save_kwargs = {"format": "PNG", "optimize": optimize, "compress_level": 9}
        img.save(buf, **save_kwargs)
        return buf.getvalue()

    def _ensure_transparency(self, image_path: Path):
        """若背景接近纯白，自动抠成透明。"""
        try:
            from PIL import Image
        except Exception:
            return

        try:
            img = Image.open(image_path).convert("RGBA")
            data = img.getdata()
            new_data = []
            # 统计白底占比，避免误杀
            white_count = 0
            threshold = 245
            for pixel in data:
                r, g, b, a = pixel
                if r >= threshold and g >= threshold and b >= threshold:
                    white_count += 1
            white_ratio = white_count / max(1, len(data))
            if white_ratio < 0.2:
                return  # 不像纯白背景，保持原样

            for pixel in data:
                r, g, b, a = pixel
                if r >= threshold and g >= threshold and b >= threshold:
                    new_data.append((r, g, b, 0))
                else:
                    new_data.append((r, g, b, a))
            img.putdata(new_data)
            img.save(image_path, format="PNG")
        except Exception:
            return
