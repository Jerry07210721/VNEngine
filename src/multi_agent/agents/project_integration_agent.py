# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - 工程集成Agent
将生成的所有资源整合到VNEngine工程文件中
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
import yaml
from src.multi_agent.core.agent_base import BaseAgent
from src.multi_agent.core.data_models import (
    TaskResultSchema, CharacterSchema, ScriptNodeSchema, 
    ResourceMetaSchema, ProjectIntegrationSchema
)
from src.multi_agent.utils.logger import LoggerFactory
from src.multi_agent.utils.yaml_adapter import YAMLAdapter
from src.multi_agent.utils.resource_processor import ResourceProcessor
from datetime import datetime


class ProjectIntegrationAgent(BaseAgent):
    """
    工程集成Agent
    将AI生成的内容整合到VNEngine工程文件
    """
    
    def __init__(
        self,
        agent_id: str = "integration_001",
        agent_name: str = "工程集成Agent"
    ):
        """
        初始化工程集成Agent
        
        Args:
            agent_id: Agent唯一标识
            agent_name: Agent名称
        """
        super().__init__(agent_id, agent_name)
        self.logger = LoggerFactory.get_logger(agent_name)
        self.yaml_adapter = YAMLAdapter()
    
    def run(self, task_params: Dict[str, Any]) -> TaskResultSchema:
        """
        执行工程集成任务
        
        Args:
            task_params: 任务参数
                - project_root: 工程根目录
                - project_name: 工程名称
                - characters: 角色列表
                - script_nodes: 剧本节点列表
                - connections: 节点连接关系
                - resources: 资源元数据列表
                - game_theme: 游戏主题（可选）
                - game_description: 游戏简介（可选）
                
        Returns:
            TaskResultSchema: 集成结果
        """
        self.logger.log_task_start("工程集成", task_params)
        
        # 校验参数
        required_fields = ["project_root", "project_name", "characters", "script_nodes", "connections"]
        is_valid, error_msg = self.validate_params(task_params, required_fields)
        if not is_valid:
            return self.create_error_result(error_msg)
        
        try:
            project_root = Path(task_params["project_root"])
            project_name = task_params["project_name"]
            characters = [CharacterSchema(**c) for c in task_params["characters"]]
            script_nodes = [ScriptNodeSchema(**n) for n in task_params["script_nodes"]]
            connections = task_params["connections"]
            resources = [ResourceMetaSchema(**r) for r in task_params.get("resources", [])]
            
            # 确保工程目录存在
            project_root.mkdir(parents=True, exist_ok=True)
            
            # 创建资源目录结构
            self.report_progress(0.1, "创建目录结构")
            ResourceProcessor.create_resource_directories(str(project_root))
            
            # 1. 生成角色配置
            self.report_progress(0.2, "生成角色配置")
            char_file = self._create_character_config(project_root, characters, resources)
            
            # 2. 生成剧本节点和连接
            self.report_progress(0.4, "生成剧本节点")
            flow_data = self.yaml_adapter.convert_script_nodes_to_flow_nodes(
                [n.model_dump() for n in script_nodes],
                connections
            )
            
            # 3. 绑定资源到节点
            self.report_progress(0.6, "绑定资源")
            flow_nodes = self._bind_resources_to_nodes(flow_data["nodes"], resources)
            flow_connections = flow_data["connections"]
            
            # 4. 生成主工程文件
            self.report_progress(0.7, "生成工程文件")
            project_file = self._create_project_file(
                project_root,
                project_name,
                task_params.get("game_theme", ""),
                task_params.get("game_description", ""),
                {"nodes": flow_nodes, "connections": flow_connections}
            )
            
            # 5. 生成资源清单
            self.report_progress(0.9, "生成资源清单")
            resource_manifest = self._create_resource_manifest(project_root, resources)
            
            self.report_progress(1.0, "工程集成完成")
            
            result_data = {
                "project_file": str(project_file),
                "character_file": str(char_file),
                "resource_manifest": str(resource_manifest),
                "node_count": len(flow_nodes),
                "resource_count": len(resources),
                "character_count": len(characters)
            }
            
            self.logger.log_task_end(
                "工程集成",
                True,
                f"成功集成{len(characters)}个角色、{len(flow_nodes)}个节点、{len(resources)}个资源"
            )
            
            return self.create_success_result(data=result_data, message="工程集成成功")
        
        except Exception as e:
            return self.create_error_result("工程集成失败", exception=e)
    
    def _create_character_config(
        self,
        project_root: Path,
        characters: List[CharacterSchema],
        resources: List[ResourceMetaSchema]
    ) -> Path:
        """
        生成角色配置文件
        
        Args:
            project_root: 工程根目录
            characters: 角色列表
            resources: 资源列表
            
        Returns:
            Path: 角色配置文件路径
        """
        config_dir = project_root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        char_config = []
        
        for char in characters:
            # 查找角色的立绘资源
            portraits = [
                r for r in resources
                if r.res_type == "portrait" and r.prompt and char.char_id in str(r.prompt)
            ]
            
            # 构建角色配置
            char_data = {
                "id": char.char_id,
                "name": char.name,
                "gender": char.gender,
                "age": getattr(char, "age", None),
                "description": getattr(char, "description", ""),
                "portraits": {}
            }
            
            # 添加立绘路径
            for portrait in portraits:
                # 从文件名提取姿势和表情
                filename = Path(portrait.path).stem
                parts = filename.split("_")
                if len(parts) >= 3:
                    pose = parts[-2]
                    expression = parts[-1]
                    if pose not in char_data["portraits"]:
                        char_data["portraits"][pose] = {}
                    char_data["portraits"][pose][expression] = portrait.path
            
            char_config.append(char_data)
        
        # 保存配置
        char_file = config_dir / "characters.yaml"
        with open(char_file, 'w', encoding='utf-8') as f:
            yaml.dump(
                {"characters": char_config},
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False
            )
        
        self.logger.info(f"角色配置已保存: {char_file}")
        return char_file
    
    def _bind_resources_to_nodes(
        self,
        flow_nodes: List[Dict[str, Any]],
        resources: List[ResourceMetaSchema]
    ) -> List[Dict[str, Any]]:
        """
        将资源绑定到对应节点
        
        Args:
            flow_nodes: 流程节点列表
            resources: 资源列表
            
        Returns:
            List: 更新后的节点列表
        """
        # 创建背景场景映射
        backgrounds = [r for r in resources if r.res_type == "background"]
        
        # 创建CG映射
        cg_by_node_id = {}
        for res in resources:
            if res.res_type == "cg" and res.related_node_id:
                cg_by_node_id[str(res.related_node_id)] = res.path
        
        # 创建角色立绘映射
        portrait_by_char = {}
        for res in resources:
            if res.res_type == "portrait" and res.related_char_id:
                if res.related_char_id not in portrait_by_char:
                    portrait_by_char[res.related_char_id] = {}
                # 从文件名提取姿势和表情
                filename = Path(res.path).stem
                if "_base" in filename:
                    portrait_by_char[res.related_char_id]["base"] = res.path
                else:
                    parts = filename.split("_")
                    if len(parts) >= 3:
                        pose = parts[-2]
                        expression = parts[-1]
                        key = f"{pose}_{expression}"
                        portrait_by_char[res.related_char_id][key] = res.path
        
        # 为每个节点分配背景
        self._assign_backgrounds_to_nodes(flow_nodes, backgrounds)
        
        # 绑定资源到节点
        for node in flow_nodes:
            node_type = node.get("node_type")
            node_id = str(node.get("id", ""))
            
            # 1. 添加CG（如果有）
            if node_id in cg_by_node_id:
                node["video"] = cg_by_node_id[node_id]  # CG作为视频节点使用
            
            # 2. 为text节点的sub_dialogues添加立绘
            if node_type == "text":
                sub_dialogues = node.get("sub_dialogues", [])
                for sub_dlg in sub_dialogues:
                    speaker = sub_dlg.get("speaker", "")
                    if not speaker:
                        continue
                    
                    # 查找对应角色的立绘（按角色ID或名称匹配）
                    for char_id, portraits in portrait_by_char.items():
                        # 尝试匹配角色名称
                        if speaker.lower() in char_id.lower() or char_id.lower() in speaker.lower():
                            # 使用base立绘
                            if "base" in portraits:
                                sub_dlg["portrait"] = portraits["base"]
                            # TODO: 后续可根据对话情绪匹配表情差分
                            break
        
        return flow_nodes
    
    def _assign_backgrounds_to_nodes(
        self,
        flow_nodes: List[Dict[str, Any]],
        backgrounds: List[ResourceMetaSchema]
    ):
        """
        为节点分配背景（智能匹配）
        
        Args:
            flow_nodes: 流程节点列表
            backgrounds: 背景资源列表
        """
        if not backgrounds:
            return
        
        # 如果只有一个背景，所有text节点使用同一背景
        if len(backgrounds) == 1:
            bg_path = backgrounds[0].path
            for node in flow_nodes:
                if node.get("node_type") == "text":
                    node["background"] = bg_path
            return
        
        # 多背景情况：简单轮换策略
        # TODO: 后续可基于节点的scene_description进行语义匹配
        text_nodes = [n for n in flow_nodes if n.get("node_type") == "text"]
        for idx, node in enumerate(text_nodes):
            bg_idx = idx % len(backgrounds)
            node["background"] = backgrounds[bg_idx].path
    
    def _create_project_file(
        self,
        project_root: Path,
        project_name: str,
        game_theme: str,
        game_description: str,
        flow_data: Dict[str, Any]
    ) -> Path:
        """
        生成主工程文件
        
        Args:
            project_root: 工程根目录
            project_name: 工程名称
            game_theme: 游戏主题
            game_description: 游戏简介
            flow_data: 流程数据（包含nodes和connections）
            
        Returns:
            Path: 工程文件路径
        """
        flow_nodes = flow_data.get("nodes", [])
        flow_connections = flow_data.get("connections", [])
        
        project_data = {
            "project_info": {
                "name": project_name,
                "version": "1.0.0",
                "engine_version": "VNEngine V0.1",
                "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_modify_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            "game_config": {
                "window_width": 1280,
                "window_height": 720,
                "game_title": project_name,
                "branch_strategy": "first",
                "menu_title": "",
                "menu_background": "",
                "menu_bgm": "",
                "menu_bgm_loop": True,
                "menu_video": "",
                "menu_video_loop": False,
                "menu_overlay_alpha": 0,
                "menu_title_pos": [60, 60],
                "menu_title_color": [240, 240, 255],
                "menu_option_pos": [80, 140],
                "menu_option_color": [255, 255, 255],
                "menu_title_image": "",
                "menu_title_image_pos": [400, 80],
                "menu_title_scale": 1.0,
                "menu_title_image_scale": 1.0,
                "menu_option_scale": 1.0
            },
            "resources": {
                "images": [],
                "audios": [],
                "portraits": [],
                "voices": [],
                "videos": []
            },
            "global_variables": [],
            "flow_nodes": {
                "nodes": flow_nodes,
                "connections": flow_connections
            }
        }
        
        # 保存工程文件
        project_file = project_root / f"{project_name}.vngproj"
        with open(project_file, 'w', encoding='utf-8') as f:
            yaml.dump(
                project_data,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False
            )
        
        self.logger.info(f"工程文件已保存: {project_file}")
        return project_file
    
    def _create_resource_manifest(
        self,
        project_root: Path,
        resources: List[ResourceMetaSchema]
    ) -> Path:
        """
        生成资源清单
        
        Args:
            project_root: 工程根目录
            resources: 资源列表
            
        Returns:
            Path: 资源清单路径
        """
        manifest = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_count": len(resources),
            "resources": []
        }
        
        for res in resources:
            manifest["resources"].append({
                "id": res.res_id,
                "type": res.res_type,
                "path": res.path,
                "name": res.name,
                "model": res.model_name,
                "generated_at": res.generated_at.strftime("%Y-%m-%d %H:%M:%S") if res.generated_at else None
            })
        
        # 保存清单
        manifest_file = project_root / "resources" / "manifest.yaml"
        with open(manifest_file, 'w', encoding='utf-8') as f:
            yaml.dump(
                manifest,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False
            )
        
        self.logger.info(f"资源清单已保存: {manifest_file}")
        return manifest_file
    
    def validate_project(self, project_file: str) -> Dict[str, Any]:
        """
        验证工程文件完整性
        
        Args:
            project_file: 工程文件路径
            
        Returns:
            Dict: 验证结果
        """
        try:
            with open(project_file, 'r', encoding='utf-8') as f:
                project_data = yaml.safe_load(f)
            
            errors = []
            warnings = []
            
            # 检查必要字段
            if "project" not in project_data:
                errors.append("缺少project字段")
            if "flow" not in project_data:
                errors.append("缺少flow字段")
            
            # 检查节点连接
            if "flow" in project_data:
                nodes = project_data["flow"].get("nodes", [])
                start_node = project_data["flow"].get("start_node")
                
                node_ids = {n["id"] for n in nodes}
                
                if start_node not in node_ids:
                    errors.append(f"起始节点{start_node}不存在")
                
                # 检查连接有效性
                for node in nodes:
                    if "next" in node and node["next"]:
                        if node["next"] not in node_ids:
                            warnings.append(f"节点{node['id']}的next指向不存在的节点{node['next']}")
            
            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings
            }
        
        except Exception as e:
            return {
                "valid": False,
                "errors": [f"验证失败: {str(e)}"],
                "warnings": []
            }
