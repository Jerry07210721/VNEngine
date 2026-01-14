# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - 人设与剧情生成Agent
基于大语言模型生成结构化角色人设与节点化剧本
"""
from typing import Dict, Any, List
from src.multi_agent.core.agent_base import BaseAgent
from src.multi_agent.core.data_models import (
    TaskResultSchema, CharacterSchema, ScriptNodeSchema, 
    ConnectionSchema, GenerationConfigSchema
)
from src.multi_agent.api_clients.llm_client import LLMClient
from src.multi_agent.utils.logger import LoggerFactory
from src.multi_agent.utils.prompt_templates import PromptTemplates
import json


class CharacterPlotAgent(BaseAgent):
    """
    人设与剧情生成Agent
    负责生成Galgame的角色人设与节点化剧本
    """
    
    def __init__(
        self,
        agent_id: str = "char_plot_001",
        agent_name: str = "人设与剧情生成Agent",
        model_name: str = "gpt-4o",
        api_key: str = "",
        base_url: str = None
    ):
        """
        初始化人设与剧情Agent
        
        Args:
            agent_id: Agent唯一标识
            agent_name: Agent名称
            model_name: 使用的模型
            api_key: API密钥
            base_url: 自定义API地址
        """
        super().__init__(agent_id, agent_name)
        
        # 设置日志工具
        self.logger = LoggerFactory.get_logger(agent_name)
        
        # 初始化LLM客户端
        self.llm_client = None
        if api_key:
            self.llm_client = LLMClient(
                model_name=model_name,
                api_key=api_key,
                base_url=base_url,
                timeout=120  # 剧本生成可能耗时较长
            )
    
    def run(self, task_params: Dict[str, Any]) -> TaskResultSchema:
        """
        执行人设与剧情生成任务
        
        Args:
            task_params: 任务参数（GenerationConfigSchema的字典形式）
                - game_theme: 游戏主题
                - char_count: 角色数量
                - script_length: 剧情长度
                - branch_count: 分支数量
                - script_style: 剧情风格
                - extra_requirements: 额外要求
                
        Returns:
            TaskResultSchema: 包含人设列表与剧本节点列表
        """
        self.logger.log_task_start("人设与剧情生成", task_params)
        
        # 校验参数
        required_fields = ["game_theme", "char_count", "script_length", "branch_count"]
        is_valid, error_msg = self.validate_params(task_params, required_fields)
        if not is_valid:
            return self.create_error_result(error_msg)
        
        if not self.llm_client:
            return self.create_error_result("LLM客户端未初始化，请检查API配置")
        
        try:
            self.report_progress(0.1, "构建生成提示词")
            
            # 获取提示词模板
            system_prompt, user_prompt = PromptTemplates.get_character_plot_prompt(
                game_theme=task_params["game_theme"],
                char_count=task_params["char_count"],
                script_length=task_params["script_length"],
                branch_count=task_params["branch_count"],
                script_style=task_params.get("script_style", ["温馨"]),
                extra_requirements=task_params.get("extra_requirements", "无")
            )
            
            self.logger.info(f"系统提示词：{system_prompt[:200]}...")
            self.logger.info(f"用户提示词：{user_prompt[:200]}...")
            
            self.report_progress(0.3, "调用LLM生成人设与剧本")
            
            # 调用LLM生成结构化输出
            result_json = self.llm_client.generate_structured_output(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.8,  # 创意性任务，温度稍高
                max_tokens=8000   # 剧本较长，需要足够token
            )
            
            self.report_progress(0.7, "解析生成结果")
            
            # 解析并验证结果
            characters, script_nodes, connections = self._parse_generation_result(result_json)
            
            self.report_progress(0.9, "后处理与优化")
            
            # 后处理：补充缺失字段、生成连接关系
            characters = self._post_process_characters(characters)
            script_nodes = self._post_process_script_nodes(script_nodes)
            connections = self._generate_connections(script_nodes, connections)
            
            self.report_progress(1.0, "人设与剧情生成完成")
            
            result_data = {
                "characters": [char.model_dump() for char in characters],
                "script_nodes": [node.model_dump() for node in script_nodes],
                "connections": [conn.model_dump() for conn in connections]
            }
            
            self.logger.log_task_end(
                "人设与剧情生成", 
                True, 
                f"生成{len(characters)}个角色，{len(script_nodes)}个节点，{len(connections)}个连接"
            )
            
            return self.create_success_result(data=result_data, message="人设与剧情生成成功")
        
        except Exception as e:
            return self.create_error_result("人设与剧情生成失败", exception=e)
    
    def _parse_generation_result(
        self, 
        result_json: Dict[str, Any]
    ) -> tuple[List[CharacterSchema], List[ScriptNodeSchema], List[ConnectionSchema]]:
        """
        解析LLM生成的JSON结果
        
        Args:
            result_json: LLM返回的JSON数据
            
        Returns:
            tuple: (角色列表, 节点列表, 连接列表)
        """
        # 解析角色
        characters = []
        if "characters" in result_json:
            for char_data in result_json["characters"]:
                try:
                    char = CharacterSchema(**char_data)
                    characters.append(char)
                except Exception as e:
                    self.logger.warning(f"角色数据解析失败：{char_data}，错误：{e}")
        
        # 解析节点
        script_nodes = []
        if "script_nodes" in result_json:
            for node_data in result_json["script_nodes"]:
                try:
                    node = ScriptNodeSchema(**node_data)
                    script_nodes.append(node)
                except Exception as e:
                    self.logger.warning(f"节点数据解析失败：{node_data}，错误：{e}")
        
        # 尝试从节点中提取连接关系（如果LLM直接在节点中定义了连接）
        connections = []
        # 注：实际连接关系通常需要根据节点类型自动生成
        
        return characters, script_nodes, connections
    
    def _post_process_characters(self, characters: List[CharacterSchema]) -> List[CharacterSchema]:
        """
        后处理角色数据：补充缺失字段、规范化
        
        Args:
            characters: 角色列表
            
        Returns:
            List[CharacterSchema]: 处理后的角色列表
        """
        processed = []
        for idx, char in enumerate(characters):
            # 确保char_id唯一
            if not char.char_id:
                char.char_id = f"char_{idx+1:03d}"
            
            # 确保默认值
            if not char.default_pose:
                char.default_pose = "站立"
            if not char.default_expression:
                char.default_expression = "平静"
            
            processed.append(char)
        
        return processed
    
    def _post_process_script_nodes(self, script_nodes: List[ScriptNodeSchema]) -> List[ScriptNodeSchema]:
        """
        后处理剧本节点：补充缺失字段、规范化、布局坐标
        
        Args:
            script_nodes: 节点列表
            
        Returns:
            List[ScriptNodeSchema]: 处理后的节点列表
        """
        processed = []
        
        # 自动布局：垂直排列节点
        y_offset = 100
        y_step = 150
        
        for idx, node in enumerate(script_nodes):
            # 确保node_id唯一
            if not node.node_id:
                node.node_id = f"node_{idx+1:03d}"
            
            # 自动布局
            if node.x == 0 and node.y == 0:
                node.x = 200.0
                node.y = y_offset + idx * y_step
            
            # 确保第一个节点为起始节点
            if idx == 0:
                node.is_start = True
            
            processed.append(node)
        
        return processed
    
    def _generate_connections(
        self,
        script_nodes: List[ScriptNodeSchema],
        existing_connections: List[ConnectionSchema]
    ) -> List[ConnectionSchema]:
        """
        生成节点连接关系
        
        Args:
            script_nodes: 节点列表
            existing_connections: 已有的连接（可能为空）
            
        Returns:
            List[ConnectionSchema]: 连接列表
        """
        connections = list(existing_connections)
        
        # 如果已有连接，直接返回
        if connections:
            return connections
        
        # 自动生成简单的线性连接（后续可优化为智能连接）
        for idx in range(len(script_nodes) - 1):
            current_node = script_nodes[idx]
            next_node = script_nodes[idx + 1]
            
            # 文本节点：连接到下一个节点
            if current_node.node_type == "text":
                conn = ConnectionSchema(
                    source=current_node.node_id,
                    target=next_node.node_id
                )
                connections.append(conn)
            
            # 选择节点：为每个选项创建连接（简化处理，连接到后续节点）
            elif current_node.node_type == "select":
                if current_node.options:
                    for option_idx in range(len(current_node.options)):
                        # 连接到下一个节点（实际应根据选项连接到不同分支）
                        target_idx = min(idx + 1 + option_idx, len(script_nodes) - 1)
                        conn = ConnectionSchema(
                            source=current_node.node_id,
                            target=script_nodes[target_idx].node_id,
                            option_index=option_idx
                        )
                        connections.append(conn)
            
            # 条件节点：创建True/False两条连接
            elif current_node.node_type == "condition":
                # True分支
                conn_true = ConnectionSchema(
                    source=current_node.node_id,
                    target=next_node.node_id,
                    condition_result=True
                )
                connections.append(conn_true)
                
                # False分支（连接到再下一个节点）
                false_target_idx = min(idx + 2, len(script_nodes) - 1)
                conn_false = ConnectionSchema(
                    source=current_node.node_id,
                    target=script_nodes[false_target_idx].node_id,
                    condition_result=False
                )
                connections.append(conn_false)
        
        return connections
    
    def close(self):
        """关闭资源"""
        if self.llm_client:
            self.llm_client.close()
