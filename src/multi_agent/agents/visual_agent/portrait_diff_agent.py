# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - 立绘与差分生成Agent
基于SDXL生成角色立绘基准图，并使用ControlNet生成动作与表情差分
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
from src.multi_agent.core.agent_base import BaseAgent
from src.multi_agent.core.data_models import (
    TaskResultSchema, CharacterSchema, ResourceMetaSchema
)
from src.multi_agent.api_clients.sdxl_client import SDXLClient
from src.multi_agent.api_clients.tongyi_wanxiang_client import TongyiWanxiangClient
from src.multi_agent.api_clients.flux_client import FLUXClient
from src.multi_agent.utils.logger import LoggerFactory
from src.multi_agent.utils.prompt_templates import PromptTemplates
from src.multi_agent.utils.resource_processor import ResourceProcessor
from datetime import datetime


class PortraitDiffAgent(BaseAgent):
    """
    立绘与差分生成Agent
    核心流程：基准立绘 → 3种动作 × 3种表情 = 9张差分图
    """
    
    def __init__(
        self,
        agent_id: str = "portrait_diff_001",
        agent_name: str = "立绘与差分生成Agent",
        image_provider: str = "sdxl",
        api_key: str = "",
        app_id: Optional[str] = None,
        base_url: str = None
    ):
        """
        初始化立绘差分Agent
        
        Args:
            agent_id: Agent唯一标识
            agent_name: Agent名称
            image_provider: 图像生成服务（sdxl/tongyi/flux）
            api_key: API密钥
            app_id: App ID（FLUX需要）
            base_url: 自定义API地址
        """
        super().__init__(agent_id, agent_name)
        
        # 设置日志工具
        self.logger = LoggerFactory.get_logger(agent_name)
        
        # 初始化图像生成客户端
        self.image_client = None
        self.image_provider = image_provider
        
        if api_key:
            if image_provider == "midjourney":
                # MidJourney不适合立绘生成，自动降级为FLUX
                self.logger.warning("MidJourney不适合立绘生成，自动使用FLUX")
                self.image_provider = "flux"
                self.image_client = FLUXClient(
                    api_key=api_key,
                    app_id=app_id,
                    base_url=base_url or "https://api.mmchat.xyz/open/v1",
                    timeout=180
                )
            elif image_provider == "flux":
                self.image_client = FLUXClient(
                    api_key=api_key,
                    app_id=app_id,
                    base_url=base_url or "https://api.mmchat.xyz/open/v1",
                    timeout=180
                )
            elif image_provider == "tongyi":
                self.image_client = TongyiWanxiangClient(
                    api_key=api_key,
                    base_url=base_url,
                    timeout=180
                )
            else:  # 默认使用SDXL
                self.image_client = SDXLClient(
                    api_key=api_key,
                    base_url=base_url or "https://api.stability.ai/v1",
                    timeout=120
                )
        
        # 默认生成配置
        self.default_poses = ["站立", "坐姿", "挥手"]
        self.default_expressions = ["开心", "生气", "哭"]
    
    def run(self, task_params: Dict[str, Any]) -> TaskResultSchema:
        """
        执行立绘与差分生成任务
        
        Args:
            task_params: 任务参数
                - characters: 角色列表（CharacterSchema）
                - project_root: 工程根目录
                - portrait_resolution: 立绘分辨率（可选）
                - poses: 动作列表（可选）
                - expressions: 表情列表（可选）
                
        Returns:
            TaskResultSchema: 生成的立绘资源元数据列表
        """
        self.logger.log_task_start("立绘与差分生成", task_params)
        
        # 校验参数
        required_fields = ["characters", "project_root"]
        is_valid, error_msg = self.validate_params(task_params, required_fields)
        if not is_valid:
            return self.create_error_result(error_msg)
        
        if not self.image_client:
            return self.create_error_result("图像生成客户端未初始化，请检查API配置")
        
        try:
            characters = [CharacterSchema(**char) for char in task_params["characters"]]
            project_root = task_params["project_root"]
            resolution = task_params.get("portrait_resolution", [896, 1408])
            poses = task_params.get("poses", self.default_poses)
            expressions = task_params.get("expressions", self.default_expressions)
            
            # 创建资源目录
            portraits_dir = Path(project_root) / "resources" / "portraits"
            portraits_dir.mkdir(parents=True, exist_ok=True)
            
            all_resources = []
            total_images = len(characters) * (1 + len(poses) * len(expressions))  # 基准图 + 差分
            current_progress = 0
            
            # 为每个角色生成立绘
            for char in characters:
                self.logger.info(f"开始生成角色【{char.name}】的立绘")
                
                # 1. 生成基准立绘
                self.report_progress(
                    current_progress / total_images,
                    f"生成角色【{char.name}】基准立绘"
                )
                
                base_portrait_path, base_resource = self._generate_base_portrait(
                    character=char,
                    output_dir=portraits_dir,
                    resolution=resolution
                )
                
                if base_portrait_path:
                    all_resources.append(base_resource)
                    current_progress += 1
                else:
                    self.logger.error(f"角色【{char.name}】基准立绘生成失败")
                    continue
                
                # 2. 生成差分（动作 × 表情）
                for pose in poses:
                    for expression in expressions:
                        self.report_progress(
                            current_progress / total_images,
                            f"生成角色【{char.name}】{pose}-{expression}差分"
                        )
                        
                        diff_path, diff_resource = self._generate_portrait_diff(
                            character=char,
                            base_portrait_path=base_portrait_path,
                            pose=pose,
                            expression=expression,
                            output_dir=portraits_dir,
                            resolution=resolution
                        )
                        
                        if diff_path:
                            all_resources.append(diff_resource)
                        
                        current_progress += 1
            
            self.report_progress(1.0, "立绘与差分生成完成")
            
            result_data = {
                "resources": [res.model_dump() for res in all_resources],
                "character_count": len(characters),
                "total_images": len(all_resources)
            }
            
            self.logger.log_task_end(
                "立绘与差分生成",
                True,
                f"成功生成{len(all_resources)}张立绘图片"
            )
            
            return self.create_success_result(data=result_data, message="立绘与差分生成成功")
        
        except Exception as e:
            return self.create_error_result("立绘与差分生成失败", exception=e)
    
    def _generate_base_portrait(
        self,
        character: CharacterSchema,
        output_dir: Path,
        resolution: List[int]
    ) -> tuple[Optional[str], Optional[ResourceMetaSchema]]:
        """
        生成角色基准立绘
        
        Args:
            character: 角色数据
            output_dir: 输出目录
            resolution: 分辨率[宽, 高]
            
        Returns:
            tuple: (立绘路径, 资源元数据)
        """
        try:
            # 构建提示词
            prompt = PromptTemplates.get_portrait_base_prompt(
                appearance=character.appearance,
                personality=character.personality
            )
            
            negative_prompt = "nsfw, lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry, multiple views, background"
            
            self.logger.info(f"基准立绘Prompt：{prompt[:200]}...")
            
            # 根据提供商选择生成方法
            if self.image_provider == "flux":
                image_data = self.image_client.text_to_image(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    width=resolution[0],
                    height=resolution[1],
                    style="anime",
                    steps=28,
                    guidance=3.5
                )
            elif self.image_provider == "tongyi":
                image_data = self.image_client.text_to_image(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    width=resolution[0],
                    height=resolution[1],
                    style="anime"
                )
            else:  # SDXL
                image_data = self.image_client.text_to_image(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    width=resolution[0],
                    height=resolution[1],
                    steps=30,
                    cfg_scale=7.5,
                    style_preset="anime"
                )
            
            # 保存图像
            output_path = output_dir / f"{character.char_id}_base.png"
            self.image_client.save_image(image_data, str(output_path))
            
            # 处理透明背景
            ResourceProcessor.ensure_png_transparent(str(output_path))
            
            # 创建资源元数据
            resource = ResourceMetaSchema(
                res_id=f"{character.char_id}_base",
                res_type="portrait",
                path=f"resources/portraits/{output_path.name}",
                name=f"{character.name}_基准立绘",
                related_char_id=character.char_id,
                pose="站立",
                expression="平静",
                prompt=prompt,
                model_name=self.image_provider,
                generated_at=datetime.now()
            )
            
            self.logger.info(f"基准立绘已保存：{output_path}")
            return str(output_path), resource
        
        except Exception as e:
            self.logger.error(f"基准立绘生成失败：{str(e)}")
            return None, None
    
    def _generate_portrait_diff(
        self,
        character: CharacterSchema,
        base_portrait_path: str,
        pose: str,
        expression: str,
        output_dir: Path,
        resolution: List[int]
    ) -> tuple[Optional[str], Optional[ResourceMetaSchema]]:
        """
        生成立绘差分（基于基准图）
        
        Args:
            character: 角色数据
            base_portrait_path: 基准立绘路径
            pose: 动作类型
            expression: 表情类型
            output_dir: 输出目录
            resolution: 分辨率
            
        Returns:
            tuple: (差分路径, 资源元数据)
        """
        try:
            # 构建差分提示词
            prompt = PromptTemplates.get_portrait_diff_prompt(
                pose=pose,
                expression=expression
            )
            
            # 添加角色外貌保持一致的描述
            prompt = f"{character.appearance}, {prompt}"
            
            negative_prompt = "nsfw, lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry, different character, inconsistent appearance"
            
            self.logger.info(f"差分Prompt：{prompt[:150]}...")
            
            # 使用图生图模式（基于基准立绘）
            if self.image_provider == "flux":
                # FLUX支持参考图模式
                image_data = self.image_client.image_to_image(
                    init_image_path=base_portrait_path,
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    strength=0.6
                )
            elif self.image_provider == "tongyi":
                image_data = self.image_client.image_to_image(
                    init_image_path=base_portrait_path,
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    strength=0.6
                )
            else:  # SDXL
                image_data = self.image_client.image_to_image(
                    init_image_path=base_portrait_path,
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    strength=0.6,
                    steps=25,
                    cfg_scale=7.5
                )
            
            # 保存图像
            output_path = output_dir / f"{character.char_id}_{pose}_{expression}.png"
            self.image_client.save_image(image_data, str(output_path))
            
            # 处理透明背景
            ResourceProcessor.ensure_png_transparent(str(output_path))
            
            # 创建资源元数据
            resource = ResourceMetaSchema(
                res_id=f"{character.char_id}_{pose}_{expression}",
                res_type="portrait",
                path=f"resources/portraits/{output_path.name}",
                name=f"{character.name}_{pose}_{expression}",
                related_char_id=character.char_id,
                pose=pose,
                expression=expression,
                prompt=prompt,
                model_name="sdxl",
                generated_at=datetime.now()
            )
            
            self.logger.info(f"差分立绘已保存：{output_path}")
            return str(output_path), resource
        
        except Exception as e:
            self.logger.error(f"差分生成失败（{pose}-{expression}）：{str(e)}")
            return None, None
    
    def close(self):
        """关闭资源"""
        if self.image_client:
            self.image_client.close()
