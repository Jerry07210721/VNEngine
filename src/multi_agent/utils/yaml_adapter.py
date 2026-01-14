# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - YAML适配器
提供工程YAML格式的读取、写入、适配工具
"""
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


class YAMLAdapter:
    """
    YAML适配器
    处理VNEngine工程文件的YAML格式读写与数据适配
    """
    
    @staticmethod
    def load_project(project_path: str) -> Dict[str, Any]:
        """
        加载VNEngine工程文件
        
        Args:
            project_path: .vngproj文件路径
            
        Returns:
            Dict[str, Any]: 工程数据字典
        """
        path = Path(project_path)
        if not path.exists():
            raise FileNotFoundError(f"工程文件不存在：{project_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        return data if data else {}
    
    @staticmethod
    def save_project(project_path: str, project_data: Dict[str, Any]):
        """
        保存VNEngine工程文件
        
        Args:
            project_path: .vngproj文件路径
            project_data: 工程数据字典
        """
        path = Path(project_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(project_data, f, allow_unicode=True, sort_keys=False)
    
    @staticmethod
    def create_empty_project_data(
        project_name: str,
        window_size: tuple[int, int] = (1280, 720)
    ) -> Dict[str, Any]:
        """
        创建空工程数据结构
        
        Args:
            project_name: 工程名称
            window_size: 窗口尺寸
            
        Returns:
            Dict[str, Any]: 空工程数据
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return {
            "project_info": {
                "name": project_name,
                "version": "1.0.0",
                "engine_version": "1.0.0",
                "create_time": now,
                "last_modify_time": now
            },
            "game_config": {
                "window_width": window_size[0],
                "window_height": window_size[1],
                "title": project_name,
                "branch_strategy": "first",
                "main_menu": {
                    "background": "",
                    "background_video": "",
                    "bgm": "",
                    "title_text": project_name,
                    "title_position": [0.5, 0.3],
                    "title_color": [255, 255, 255],
                    "title_image": "",
                    "overlay_alpha": 100
                }
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
                "nodes": [],
                "connections": []
            }
        }
    
    @staticmethod
    def fill_project_info(
        project_data: Dict[str, Any],
        name: Optional[str] = None,
        version: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        填充工程信息
        
        Args:
            project_data: 工程数据
            name: 工程名称（可选）
            version: 工程版本（可选）
            
        Returns:
            Dict[str, Any]: 更新后的工程数据
        """
        if name:
            project_data["project_info"]["name"] = name
        if version:
            project_data["project_info"]["version"] = version
        
        # 更新修改时间
        project_data["project_info"]["last_modify_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return project_data
    
    @staticmethod
    def add_resources(
        project_data: Dict[str, Any],
        resource_type: str,
        resource_paths: List[str]
    ) -> Dict[str, Any]:
        """
        添加资源路径
        
        Args:
            project_data: 工程数据
            resource_type: 资源类型（images/audios/portraits/voices/videos）
            resource_paths: 资源路径列表（相对工程目录）
            
        Returns:
            Dict[str, Any]: 更新后的工程数据
        """
        if resource_type not in project_data["resources"]:
            project_data["resources"][resource_type] = []
        
        # 去重添加
        existing = set(project_data["resources"][resource_type])
        for path in resource_paths:
            if path not in existing:
                project_data["resources"][resource_type].append(path)
        
        return project_data
    
    @staticmethod
    def add_global_variables(
        project_data: Dict[str, Any],
        variables: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        添加全局变量
        
        Args:
            project_data: 工程数据
            variables: 变量列表，每个变量包含name和initial字段
            
        Returns:
            Dict[str, Any]: 更新后的工程数据
        """
        existing_names = {var["name"] for var in project_data["global_variables"]}
        
        for var in variables:
            if var["name"] not in existing_names:
                project_data["global_variables"].append(var)
        
        return project_data
    
    @staticmethod
    def set_flow_nodes(
        project_data: Dict[str, Any],
        nodes: List[Dict[str, Any]],
        connections: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        设置流程图节点
        
        Args:
            project_data: 工程数据
            nodes: 节点列表
            connections: 连接列表
            
        Returns:
            Dict[str, Any]: 更新后的工程数据
        """
        project_data["flow_nodes"]["nodes"] = nodes
        project_data["flow_nodes"]["connections"] = connections
        
        return project_data
    
    @staticmethod
    def validate_project_data(project_data: Dict[str, Any]) -> tuple[bool, str]:
        """
        校验工程数据完整性
        
        Args:
            project_data: 工程数据
            
        Returns:
            tuple[bool, str]: (校验结果, 错误消息)
        """
        required_keys = ["project_info", "game_config", "resources", "global_variables", "flow_nodes"]
        
        for key in required_keys:
            if key not in project_data:
                return False, f"工程数据缺少必需字段：{key}"
        
        # 校验flow_nodes结构
        if "nodes" not in project_data["flow_nodes"]:
            return False, "flow_nodes缺少nodes字段"
        if "connections" not in project_data["flow_nodes"]:
            return False, "flow_nodes缺少connections字段"
        
        # 校验是否至少有一个起始节点
        nodes = project_data["flow_nodes"]["nodes"]
        if nodes:
            has_start = any(node.get("is_start", False) for node in nodes)
            if not has_start:
                return False, "流程图缺少起始节点"
        
        return True, ""
    
    @staticmethod
    def convert_script_nodes_to_flow_nodes(
        script_nodes: List[Dict[str, Any]],
        connections: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        将AI生成的剧本节点转换为VNEngine的flow_nodes格式
        
        Args:
            script_nodes: 剧本节点列表（来自CharacterPlotAgent）
            connections: 连接列表
            
        Returns:
            Dict[str, Any]: VNEngine的flow_nodes数据
        """
        flow_nodes = []
        node_id_map = {}  # node_id字符串 -> id整数的映射
        
        for idx, node in enumerate(script_nodes, start=1):
            node_id_str = node.get("node_id")
            node_id_map[node_id_str] = idx
            
            # 修正node_type：select -> choice
            node_type = node.get("node_type")
            if node_type == "select":
                node_type = "choice"
            
            # 转换节点格式（确保字段对齐）
            flow_node = {
                "id": idx,  # 使用整数id而不node_id
                "title": node.get("title"),
                "node_type": node_type,
                "is_start": node.get("is_start", False),
                "x": node.get("x", 0.0),
                "y": node.get("y", 0.0),
                # 文本节点字段
                "speaker": node.get("speaker"),
                "content": node.get("content"),
                # 选择节点字段
                "options": node.get("options"),
                # 条件节点字段
                "condition_var": node.get("condition_var"),
                "condition_op": node.get("condition_op"),
                "condition_value": node.get("condition_value"),
                "condition_const": node.get("condition_const", True),
                # 媒体字段
                "background": node.get("background"),
                "portrait": node.get("portrait"),
                "voice": node.get("voice"),
                "bgm": node.get("bgm"),
                "video": node.get("video"),
                # 媒体控制字段
                "bgm_loop": node.get("bgm_loop", True),
                "stop_bgm": node.get("stop_bgm", False),
                "bg_fade_in": node.get("bg_fade_in", False),
                "video_loop": node.get("video_loop", False),
                "hide_textbox": node.get("hide_textbox", False),
                "portrait_fade": node.get("portrait_fade", False),
                "portrait_fade_out": node.get("portrait_fade_out", False),
                # UI字段
                "ui_file": node.get("ui_file"),
                # 变量操作
                "var_ops": node.get("var_ops"),
                # 子对话
                "sub_dialogues": node.get("sub_dialogues")
            }
            
            # 为text节点自动生成sub_dialogues（如果没有）
            if node_type == "text" and not flow_node["sub_dialogues"]:
                content = flow_node.get("content")
                speaker = flow_node.get("speaker")
                if content:  # 只有当content不为空时才生成
                    flow_node["sub_dialogues"] = [
                        {
                            "speaker": speaker or "",
                            "text": content,
                            "portrait": flow_node.get("portrait") or "",
                            "voice": flow_node.get("voice") or "",
                            "portrait_fade": flow_node.get("portrait_fade", False),
                            "portrait_fade_out": flow_node.get("portrait_fade_out", False),
                            "hide_textbox": flow_node.get("hide_textbox", False)
                        }
                    ]
            
            # 移除值为None的字段（保持干净）
            flow_node = {k: v for k, v in flow_node.items() if v is not None}
            
            flow_nodes.append(flow_node)
        
        # 转换连接格式（将node_id字符串转为id整数）
        flow_connections = []
        for conn in connections:
            source_str = conn.get("source")
            target_str = conn.get("target")
            
            # 将node_id字符串转换为id整数
            source_id = node_id_map.get(source_str)
            target_id = node_id_map.get(target_str)
            
            if source_id is None or target_id is None:
                continue  # 跳过无效连接
            
            flow_conn = {
                "source": source_id,
                "target": target_id
            }
            if conn.get("option_index") is not None:
                flow_conn["option_index"] = conn["option_index"]
            if conn.get("condition_result") is not None:
                flow_conn["condition_result"] = conn["condition_result"]
            
            flow_connections.append(flow_conn)
        
        return {
            "nodes": flow_nodes,
            "connections": flow_connections
        }
