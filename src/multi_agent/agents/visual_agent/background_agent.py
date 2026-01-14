# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - 背景图生成Agent
基于剧本节点的场景描述生成对应背景图
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
from src.multi_agent.core.agent_base import BaseAgent
from src.multi_agent.core.data_models import (
    TaskResultSchema, ScriptNodeSchema, ResourceMetaSchema
)
from src.multi_agent.api_clients.sdxl_client import SDXLClient
from src.multi_agent.api_clients.tongyi_wanxiang_client import TongyiWanxiangClient
from src.multi_agent.api_clients.flux_client import FLUXClient
from src.multi_agent.utils.logger import LoggerFactory
from src.multi_agent.utils.prompt_templates import PromptTemplates
from src.multi_agent.utils.resource_processor import ResourceProcessor
from datetime import datetime


class BackgroundAgent(BaseAgent):
    """
    背景图生成Agent
    从剧本节点提取场景描述，生成对应背景图
    """
    
    def __init__(
        self,
        agent_id: str = "background_001",
        agent_name: str = "背景图生成Agent",
        api_key: str = "",
        app_id: Optional[str] = None,
        base_url: str = None,
        image_provider: str = "sdxl"
    ):
        """
        初始化背景图Agent
        
        Args:
            agent_id: Agent唯一标识
            agent_name: Agent名称
            api_key: 图像生成API密钥
            app_id: App ID（FLUX需要）
            base_url: 自定义API地址
            image_provider: 图像生成服务商 (sdxl/tongyi/flux/midjourney)
        """
        super().__init__(agent_id, agent_name)
        
        # 设置日志工具
        self.logger = LoggerFactory.get_logger(agent_name)
        self.image_provider = image_provider
        
        # 根据provider初始化图像生成客户端
        self.image_client = None
        if api_key:
            if image_provider == "midjourney":
                # MidJourney不适合背景生成，自动降级为FLUX
                self.logger.warning("MidJourney不适合背景生成，自动使用FLUX")
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
                    timeout=120
                )
            else:  # 默认使用SDXL
                self.image_client = SDXLClient(
                    api_key=api_key,
                    base_url=base_url or "https://api.stability.ai/v1",
                    timeout=120
                )
    
    def run(self, task_params: Dict[str, Any]) -> TaskResultSchema:
        """
        执行背景图生成任务
        
        Args:
            task_params: 任务参数
                - script_nodes: 剧本节点列表
                - project_root: 工程根目录
                - background_resolution: 背景分辨率（可选，默认1280×720）
                
        Returns:
            TaskResultSchema: 生成的背景资源元数据列表
        """
        self.logger.log_task_start("背景图生成", task_params)
        
        # 校验参数
        required_fields = ["script_nodes", "project_root"]
        is_valid, error_msg = self.validate_params(task_params, required_fields)
        if not is_valid:
            return self.create_error_result(error_msg)
        
        if not self.image_client:
            return self.create_error_result("图像生成客户端未初始化，请检查API配置")
        
        try:
            script_nodes = [ScriptNodeSchema(**node) for node in task_params["script_nodes"]]
            project_root = task_params["project_root"]
            resolution = task_params.get("background_resolution", [1280, 720])
            
            # 创建资源目录
            backgrounds_dir = Path(project_root) / "resources" / "images" / "backgrounds"
            backgrounds_dir.mkdir(parents=True, exist_ok=True)
            
            # 提取唯一场景描述（去重）
            unique_scenes = self._extract_unique_scenes(script_nodes)
            
            self.logger.info(f"共提取到{len(unique_scenes)}个独特场景")
            
            all_resources = []
            
            for idx, (scene_key, scene_info) in enumerate(unique_scenes.items()):
                self.report_progress(
                    idx / len(unique_scenes),
                    f"生成场景【{scene_info['description'][:20]}】背景"
                )
                
                bg_path, bg_resource = self._generate_background(
                    scene_description=scene_info["description"],
                    atmosphere=scene_info["atmosphere"],
                    related_node_ids=scene_info["node_ids"],
                    output_dir=backgrounds_dir,
                    resolution=resolution,
                    scene_index=idx
                )
                
                if bg_path:
                    all_resources.append(bg_resource)
            
            self.report_progress(1.0, "背景图生成完成")
            
            result_data = {
                "resources": [res.model_dump() for res in all_resources],
                "scene_count": len(unique_scenes),
                "total_backgrounds": len(all_resources)
            }
            
            self.logger.log_task_end(
                "背景图生成",
                True,
                f"成功生成{len(all_resources)}张背景图"
            )
            
            return self.create_success_result(data=result_data, message="背景图生成成功")
        
        except Exception as e:
            return self.create_error_result("背景图生成失败", exception=e)
    
    def _extract_unique_scenes(
        self,
        script_nodes: List[ScriptNodeSchema]
    ) -> Dict[str, Dict[str, Any]]:
        """
        从剧本节点中提取唯一场景
        
        Args:
            script_nodes: 剧本节点列表
            
        Returns:
            Dict: {场景标识: {description, atmosphere, node_ids}}
        """
        unique_scenes = {}
        
        for node in script_nodes:
            # 只处理文本节点且有场景描述的节点
            if node.node_type != "text":
                continue
            
            scene_desc = node.scene_description
            atmosphere = node.atmosphere or "平静"
            
            if not scene_desc:
                # 如果没有场景描述，跳过
                continue
            
            # 使用场景描述作为标识（去重）
            scene_key = f"{scene_desc}_{atmosphere}"
            
            if scene_key not in unique_scenes:
                unique_scenes[scene_key] = {
                    "description": scene_desc,
                    "atmosphere": atmosphere,
                    "node_ids": [node.node_id]
                }
            else:
                # 记录使用该场景的节点ID
                unique_scenes[scene_key]["node_ids"].append(node.node_id)
        
        return unique_scenes
    
    def _generate_background(
        self,
        scene_description: str,
        atmosphere: str,
        related_node_ids: List[str],
        output_dir: Path,
        resolution: List[int],
        scene_index: int
    ) -> tuple[Optional[str], Optional[ResourceMetaSchema]]:
        """
        生成单个背景图
        
        Args:
            scene_description: 场景描述
            atmosphere: 氛围标签
            related_node_ids: 关联的节点ID列表
            output_dir: 输出目录
            resolution: 分辨率
            scene_index: 场景索引
            
        Returns:
            tuple: (背景路径, 资源元数据)
        """
        try:
            # 构建背景生成提示词
            prompt = PromptTemplates.get_background_prompt(
                scene_description=scene_description,
                atmosphere=atmosphere
            )
            
            negative_prompt = "people, characters, humans, animals, text, watermark, signature, logo, lowres, bad quality, blurry, jpeg artifacts"
            
            self.logger.info(f"背景Prompt：{prompt[:200]}...")
            
            # 根据provider调用不同的API
            if self.image_provider == "flux":
                image_data = self.image_client.text_to_image(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    width=resolution[0],
                    height=resolution[1],
                    style="realistic",  # 背景使用写实风格
                    steps=28,
                    guidance=3.5
                )
            elif self.image_provider == "tongyi":
                image_data = self.image_client.text_to_image(
                    prompt=prompt,
                    style="realistic",  # 背景使用写实风格
                    width=resolution[0],
                    height=resolution[1]
                )
            else:  # SDXL
                image_data = self.image_client.text_to_image(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    width=resolution[0],
                    height=resolution[1],
                    steps=25,
                    cfg_scale=7.0,
                    style_preset="anime"
                )
            
            # 保存图像
            output_path = output_dir / f"bg_{scene_index+1:03d}.png"
            self.image_client.save_image(image_data, str(output_path))
            
            # 创建资源元数据
            resource = ResourceMetaSchema(
                res_id=f"bg_{scene_index+1:03d}",
                res_type="background",
                path=f"resources/images/backgrounds/{output_path.name}",
                name=f"背景_{scene_description[:20]}",
                related_node_id=related_node_ids[0] if related_node_ids else None,
                prompt=prompt,
                model_name=self.image_provider,
                generated_at=datetime.now()
            )
            
            self.logger.info(f"背景图已保存：{output_path}")
            return str(output_path), resource
        
        except Exception as e:
            self.logger.error(f"背景生成失败：{str(e)}")
            return None, None
    
    def close(self):
        """关闭资源"""
        if self.image_client:
            self.image_client.close()
