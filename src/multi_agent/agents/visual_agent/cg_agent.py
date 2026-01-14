# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - CG生成Agent
识别关键剧情节点生成精美CG插图
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
from src.multi_agent.core.agent_base import BaseAgent
from src.multi_agent.core.data_models import (
    TaskResultSchema, ScriptNodeSchema, CharacterSchema, ResourceMetaSchema
)
from src.multi_agent.api_clients.midjourney_client import MidJourneyClient
from src.multi_agent.utils.logger import LoggerFactory
from src.multi_agent.utils.prompt_templates import PromptTemplates
from datetime import datetime


class CGAgent(BaseAgent):
    """
    CG生成Agent
    基于剧情关键节点生成高质量CG插图
    """
    
    def __init__(
        self,
        agent_id: str = "cg_001",
        agent_name: str = "CG生成Agent",
        api_key: str = "",
        app_id: str = "",
        base_url: str = None
    ):
        """
        初始化CG Agent
        
        Args:
            agent_id: Agent唯一标识
            agent_name: Agent名称
            api_key: MidJourney API密钥
            app_id: MidJourney App ID（MetaChat代理需要）
            base_url: 自定义API地址
        """
        super().__init__(agent_id, agent_name)
        
        # 设置日志工具
        self.logger = LoggerFactory.get_logger(agent_name)
        
        # 初始化MidJourney客户端
        self.mj_client = None
        if api_key:
            self.mj_client = MidJourneyClient(
                api_key=api_key,
                app_id=app_id,
                base_url=base_url or "https://api.mmchat.xyz/open/v1",
                timeout=180
            )
    
    def run(self, task_params: Dict[str, Any]) -> TaskResultSchema:
        """
        执行CG生成任务
        
        Args:
            task_params: 任务参数
                - script_nodes: 剧本节点列表
                - characters: 角色列表
                - project_root: 工程根目录
                - cg_count: 生成CG数量（可选，默认自动识别）
                - aspect_ratio: 宽高比（可选，默认16:9）
                - quality: 质量等级（可选，默认high）
                
        Returns:
            TaskResultSchema: 生成的CG资源元数据列表
        """
        self.logger.log_task_start("CG生成", task_params)
        
        # 校验参数
        required_fields = ["script_nodes", "characters", "project_root"]
        is_valid, error_msg = self.validate_params(task_params, required_fields)
        if not is_valid:
            return self.create_error_result(error_msg)
        
        if not self.mj_client:
            return self.create_error_result("MidJourney客户端未初始化，请检查API配置")
        
        try:
            script_nodes = [ScriptNodeSchema(**node) for node in task_params["script_nodes"]]
            characters = [CharacterSchema(**char) for char in task_params["characters"]]
            project_root = task_params["project_root"]
            aspect_ratio = task_params.get("aspect_ratio", "16:9")
            quality = task_params.get("quality", "high")
            
            # 创建资源目录
            cg_dir = Path(project_root) / "resources" / "images" / "cg"
            cg_dir.mkdir(parents=True, exist_ok=True)
            
            # 识别关键剧情节点
            key_nodes = self._identify_key_plot_nodes(script_nodes, task_params.get("cg_count"))
            
            self.logger.info(f"识别到{len(key_nodes)}个关键剧情节点需要生成CG")
            
            all_resources = []
            
            for idx, node in enumerate(key_nodes):
                # select节点没有content，跳过
                if not node.content:
                    self.logger.warning(f"跳过节点{node.node_id}：无content字段（可能是select/condition节点）")
                    continue
                
                self.report_progress(
                    idx / len(key_nodes),
                    f"生成CG：{node.content[:30]}..."
                )
                
                cg_path, cg_resource = self._generate_cg(
                    node=node,
                    characters=characters,
                    output_dir=cg_dir,
                    aspect_ratio=aspect_ratio,
                    quality=quality,
                    cg_index=idx
                )
                
                if cg_path:
                    all_resources.append(cg_resource)
            
            self.report_progress(1.0, "CG生成完成")
            
            result_data = {
                "resources": [res.model_dump() for res in all_resources],
                "cg_count": len(all_resources),
                "key_nodes": [node.node_id for node in key_nodes]
            }
            
            self.logger.log_task_end(
                "CG生成",
                True,
                f"成功生成{len(all_resources)}张CG"
            )
            
            return self.create_success_result(data=result_data, message="CG生成成功")
        
        except Exception as e:
            return self.create_error_result("CG生成失败", exception=e)
    
    def _identify_key_plot_nodes(
        self,
        script_nodes: List[ScriptNodeSchema],
        target_count: Optional[int] = None
    ) -> List[ScriptNodeSchema]:
        """
        识别关键剧情节点
        
        Args:
            script_nodes: 剧本节点列表
            target_count: 目标CG数量（None则自动识别）
            
        Returns:
            关键节点列表
        """
        # 关键节点判定规则：
        # 1. 节点类型为 select（玩家选择）
        # 2. 节点有重要标记（importance="high"）
        # 3. 节点包含强烈情感表现（atmosphere in ["紧张", "激动", "悲伤", "欢乐"]）
        # 4. 节点内容长度超过100字（长对话往往是重要剧情）
        
        key_nodes = []
        
        for node in script_nodes:
            # 规则1：选择节点
            if node.node_type == "select":
                key_nodes.append(node)
                continue
            
            # 规则2：重要标记
            if hasattr(node, "importance") and node.importance == "high":
                key_nodes.append(node)
                continue
            
            # 规则3：强烈氛围
            strong_atmospheres = ["紧张", "激动", "悲伤", "欢乐", "感动", "震撼"]
            if node.atmosphere in strong_atmospheres:
                key_nodes.append(node)
                continue
            
            # 规则4：长对话（文本节点）
            if node.node_type == "text" and len(node.content) > 100:
                key_nodes.append(node)
        
        # 如果指定了数量，按权重排序取前N个
        if target_count and len(key_nodes) > target_count:
            # 简单权重：select节点权重3，其他节点权重1
            key_nodes.sort(
                key=lambda n: 3 if n.node_type == "select" else 1,
                reverse=True
            )
            key_nodes = key_nodes[:target_count]
        
        self.logger.info(f"关键节点识别完成：{[n.node_id for n in key_nodes]}")
        return key_nodes
    
    def _generate_cg(
        self,
        node: ScriptNodeSchema,
        characters: List[CharacterSchema],
        output_dir: Path,
        aspect_ratio: str,
        quality: str,
        cg_index: int
    ) -> tuple[Optional[str], Optional[ResourceMetaSchema]]:
        """
        生成单张CG
        
        Args:
            node: 剧情节点
            characters: 角色列表
            output_dir: 输出目录
            aspect_ratio: 宽高比
            quality: 质量等级
            cg_index: CG索引
            
        Returns:
            tuple: (CG路径, 资源元数据)
        """
        try:
            # 获取节点中的角色信息
            char_info = None
            if node.character:
                for char in characters:
                    if char.char_id == node.character:
                        char_info = char
                        break
            
            # 构建CG生成提示词
            prompt = PromptTemplates.get_cg_prompt(
                scene_description=node.scene_description or "室内",
                character_info=char_info.model_dump() if char_info else None,
                dialogue=node.content,
                atmosphere=node.atmosphere or "平静"
            )
            
            self.logger.info(f"CG Prompt：{prompt[:200]}...")
            
            # 根据质量等级设置参数
            quality_map = {
                "low": {"stylize": 50, "version": "6", "quality": 0.5},
                "medium": {"stylize": 100, "version": "6", "quality": 1},
                "high": {"stylize": 150, "version": "6", "quality": 1},
                "ultra": {"stylize": 200, "version": "6", "quality": 2}
            }
            params = quality_map.get(quality, quality_map["high"])
            
            # 调用MidJourney生成
            image_path = self.mj_client.generate_and_download(
                prompt=prompt,
                output_path=str(output_dir / f"cg_{cg_index+1:03d}.png"),
                aspect_ratio=aspect_ratio,
                version=params["version"],
                stylize=params["stylize"],
                quality=params["quality"]
            )
            
            if not image_path:
                raise Exception("MidJourney生成失败")
            
            # 创建资源元数据
            resource = ResourceMetaSchema(
                res_id=f"cg_{cg_index+1:03d}",
                res_type="cg",
                path=f"resources/images/cg/{Path(image_path).name}",
                name=f"CG_{node.content[:20]}",
                related_node_id=node.node_id,
                prompt=prompt,
                model_name="midjourney-v6",
                generated_at=datetime.now()
            )
            
            self.logger.info(f"CG已保存：{image_path}")
            return image_path, resource
        
        except Exception as e:
            self.logger.error(f"CG生成失败：{str(e)}")
            return None, None
    
    def close(self):
        """关闭资源"""
        if self.mj_client:
            self.mj_client.close()
