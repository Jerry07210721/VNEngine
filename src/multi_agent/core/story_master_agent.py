# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - 故事总控Agent
多智能体体系的核心协调者，负责任务分发、一致性校验、异常处理
"""
from typing import Dict, Any, List, Optional
from src.multi_agent.core.agent_base import BaseAgent
from src.multi_agent.core.data_models import (
    TaskResultSchema, GenerationConfigSchema, 
    CharacterSchema, ScriptNodeSchema, ConnectionSchema,
    ResourceMetaSchema, ProjectIntegrationSchema
)
from src.multi_agent.utils.logger import LoggerFactory
from src.multi_agent.agents.character_plot_agent import CharacterPlotAgent
from src.multi_agent.agents.prompt_optimizer_agent import PromptOptimizerAgent
from src.multi_agent.agents.visual_agent.portrait_diff_agent import PortraitDiffAgent
from src.multi_agent.agents.visual_agent.background_agent import BackgroundAgent
from src.multi_agent.agents.visual_agent.cg_agent import CGAgent
from src.multi_agent.agents.audio_agent.voice_acting_agent import VoiceActingAgent
from src.multi_agent.agents.audio_agent.bgm_agent import BGMAgent
from src.multi_agent.agents.project_integration_agent import ProjectIntegrationAgent
import time


class StoryMasterAgent(BaseAgent):
    """
    故事总控Agent
    统筹整个Galgame生成流程，协调各专项Agent
    """
    
    def __init__(
        self,
        agent_id: str = "story_master_001",
        agent_name: str = "故事总控Agent"
    ):
        """
        初始化故事总控Agent
        
        Args:
            agent_id: Agent唯一标识
            agent_name: Agent名称
        """
        super().__init__(agent_id, agent_name)
        
        # 设置日志工具
        self.logger = LoggerFactory.get_logger(agent_name)
        
        # 子Agent实例（延迟初始化）
        self.char_plot_agent: Optional[CharacterPlotAgent] = None
        self.prompt_optimizer_agent: Optional[PromptOptimizerAgent] = None
        self.portrait_agent: Optional[PortraitDiffAgent] = None
        self.background_agent: Optional[BackgroundAgent] = None
        self.cg_agent: Optional[CGAgent] = None
        self.voice_agent: Optional[VoiceActingAgent] = None
        self.bgm_agent: Optional[BGMAgent] = None
        self.integration_agent: Optional[ProjectIntegrationAgent] = None
        
        # 生成结果缓存
        self.characters: List[CharacterSchema] = []
        self.script_nodes: List[ScriptNodeSchema] = []
        self.connections: List[ConnectionSchema] = []
        self.resources: List[ResourceMetaSchema] = []
    
    def run(self, task_params: Dict[str, Any]) -> TaskResultSchema:
        """
        执行完整的Galgame生成流程
        
        Args:
            task_params: 任务参数（GenerationConfigSchema的字典形式）
                - game_name: 游戏名称
                - game_theme: 游戏主题
                - char_count: 角色数量
                - script_length: 剧情长度
                - branch_count: 分支数量
                - script_style: 剧情风格
                - api_configs: API配置字典
                - save_path: 保存路径
                
        Returns:
            TaskResultSchema: 完整工程数据
        """
        self.logger.log_task_start("AI游戏生成", task_params)
        
        # 校验参数
        required_fields = ["game_name", "game_theme", "char_count", "script_length", "api_configs", "save_path"]
        is_valid, error_msg = self.validate_params(task_params, required_fields)
        if not is_valid:
            return self.create_error_result(error_msg)
        
        try:
            # 阶段1：初始化子Agent
            self.report_progress(0.05, "初始化Agent体系")
            self._initialize_agents(task_params["api_configs"])
            
            # 阶段2：生成人设与剧情
            self.report_progress(0.1, "开始生成人设与剧情")
            char_plot_result = self._generate_characters_and_plot(task_params)
            if not char_plot_result.success:
                return char_plot_result
            
            # 阶段3：生成视觉资源（可选）
            if self.portrait_agent or self.background_agent or self.cg_agent:
                self.report_progress(0.4, "开始生成视觉资源")
                visual_result = self._generate_visual_resources(task_params)
                if not visual_result.success:
                    self.logger.warning(f"视觉资源生成失败：{visual_result.error_msg}")
            else:
                self.logger.info("跳过视觉资源生成（未配置图像生成API）")
            
            # 阶段4：生成音频资源（可选）
            if self.voice_agent or self.bgm_agent:
                self.report_progress(0.6, "开始生成音频资源")
                audio_result = self._generate_audio_resources(task_params)
                if not audio_result.success:
                    self.logger.warning(f"音频资源生成失败：{audio_result.error_msg}")
            else:
                self.logger.info("跳过音频资源生成（未配置TTS/音乐生成API）")
            
            # 阶段5：工程整合
            self.report_progress(0.8, "开始工程整合")
            integration_result = self._integrate_project(task_params)
            if not integration_result.success:
                return integration_result
            
            # 阶段6：完成
            self.report_progress(1.0, "AI游戏生成完成")
            
            result_data = {
                "characters": [char.model_dump() for char in self.characters],
                "script_nodes": [node.model_dump() for node in self.script_nodes],
                "connections": [conn.model_dump() for conn in self.connections],
                "resources": [res.model_dump() for res in self.resources],
                "project_path": task_params["save_path"],
                "project_file": integration_result.data.get("project_file") if integration_result.success else None
            }
            
            self.logger.log_task_end("AI游戏生成", True, "完整游戏生成完成")
            return self.create_success_result(data=result_data, message="AI游戏生成成功")
        
        except Exception as e:
            return self.create_error_result("AI游戏生成失败", exception=e)
    
    def _initialize_agents(self, api_configs: Dict[str, Dict[str, str]]):
        """
        初始化所有子Agent（支持可选Agent）
        
        Args:
            api_configs: API配置字典
                {
                    "llm": {"model": "gpt-4o", "api_key": "xxx", "base_url": "xxx"},
                    "portrait": {"provider": "flux", "api_key": "xxx", "app_id": "xxx", "base_url": "xxx"},
                    "background": {"provider": "midjourney", "api_key": "xxx", "app_id": "xxx", "base_url": "xxx"},
                    "tts": {"provider": "gpt_sovits", "api_key": "xxx", "base_url": "xxx"},
                    "music": {"provider": "suno", "api_key": "xxx", "user_id": "xxx", "base_url": "xxx"}
                }
        """
        self.logger.info("开始初始化子Agent")
        
        # 初始化人设剧情Agent（必需）
        if "llm" in api_configs:
            llm_config = api_configs["llm"]
            self.char_plot_agent = CharacterPlotAgent(
                model_name=llm_config.get("model", "gpt-4o"),
                api_key=llm_config.get("api_key", ""),
                base_url=llm_config.get("base_url")
            )
            self.logger.info(f"人设剧情Agent已初始化，模型：{llm_config.get('model')}")
        else:
            raise ValueError("缺少LLM API配置，这是必需的")
        
        # 初始化Prompt优化Agent（可选）
        if "prompt_optimizer" in api_configs:
            opt_config = api_configs["prompt_optimizer"]
            self.prompt_optimizer_agent = PromptOptimizerAgent(
                model_name=opt_config.get("model", "gpt-4o"),
                api_key=opt_config.get("api_key", ""),
                base_url=opt_config.get("base_url")
            )
            self.logger.info("Prompt优化Agent已初始化")
        
        # 初始化视觉Agent（可选）
        # 立绘Agent
        if "portrait" in api_configs:
            portrait_config = api_configs["portrait"]
            portrait_provider = portrait_config.get("provider", "flux")
            
            # MidJourney不适合立绘批量生成，自动降级为FLUX
            if portrait_provider == "midjourney":
                self.logger.warning("MidJourney不适合立绘批量生成（耗时且成本高），建议使用FLUX生成立绘")
                portrait_provider = "flux"
            
            self.portrait_agent = PortraitDiffAgent(
                api_key=portrait_config.get("api_key", ""),
                app_id=portrait_config.get("app_id"),
                base_url=portrait_config.get("base_url"),
                image_provider=portrait_provider
            )
            self.logger.info(f"立绘生成Agent已初始化，模型：{portrait_provider}")
        else:
            self.logger.warning("未配置立绘生成API，将跳过立绘生成")
        
        # 背景/CG Agent
        if "background" in api_configs:
            bg_config = api_configs["background"]
            bg_provider = bg_config.get("provider", "flux")
            
            # 背景Agent
            self.background_agent = BackgroundAgent(
                api_key=bg_config.get("api_key", ""),
                app_id=bg_config.get("app_id"),
                base_url=bg_config.get("base_url"),
                image_provider=bg_provider
            )
            self.logger.info(f"背景生成Agent已初始化，模型：{bg_provider}")
            
            # CG Agent（仅MidJourney）
            if bg_provider == "midjourney":
                self.cg_agent = CGAgent(
                    api_key=bg_config.get("api_key", ""),
                    app_id=bg_config.get("app_id", ""),
                    base_url=bg_config.get("base_url")
                )
                self.logger.info("CG生成Agent已初始化（MidJourney高质量模式）")
            else:
                self.logger.info(f"CG将使用背景模型生成：{bg_provider}")
        else:
            self.logger.warning("未配置背景/CG生成API，将跳过背景/CG生成")
        
        # 初始化音频Agent（可选）
        if "tts" in api_configs:
            tts_config = api_configs["tts"]
            self.voice_agent = VoiceActingAgent(
                tts_provider=tts_config.get("provider", "gpt_sovits"),
                api_key=tts_config.get("api_key", ""),
                region=tts_config.get("region", "eastus"),
                base_url=tts_config.get("base_url")
            )
            self.logger.info(f"语音合成Agent已初始化，服务商：{tts_config.get('provider', 'gpt_sovits')}")
        else:
            self.logger.warning("未配置TTS API，将跳过语音生成")
        
        if "music" in api_configs:
            music_config = api_configs["music"]
            self.bgm_agent = BGMAgent(
                music_provider=music_config.get("provider", "suno"),
                api_key=music_config.get("api_key", ""),
                user_id=music_config.get("user_id", "default_user"),
                base_url=music_config.get("base_url")
            )
            self.logger.info(f"BGM生成Agent已初始化，服务商：{music_config.get('provider', 'suno')}")
        else:
            self.logger.warning("未配置音乐生成API，将跳过BGM生成")
        
        # 初始化工程集成Agent
        self.integration_agent = ProjectIntegrationAgent()
        self.logger.info("工程集成Agent已初始化")
    
    def _generate_characters_and_plot(self, task_params: Dict[str, Any]) -> TaskResultSchema:
        """
        生成人设与剧情
        
        Args:
            task_params: 任务参数
            
        Returns:
            TaskResultSchema: 生成结果
        """
        self.logger.info("调用人设剧情Agent")
        
        if not self.char_plot_agent:
            return self.create_error_result("人设剧情Agent未初始化")
        
        # 调用人设剧情Agent
        result = self.char_plot_agent.safe_run(task_params)
        
        if not result.success:
            self.logger.error(f"人设剧情生成失败：{result.error_msg}")
            return result
        
        # 提取结果
        if result.data:
            self.characters = [CharacterSchema(**char) for char in result.data.get("characters", [])]
            self.script_nodes = [ScriptNodeSchema(**node) for node in result.data.get("script_nodes", [])]
            self.connections = [ConnectionSchema(**conn) for conn in result.data.get("connections", [])]
            
            self.logger.info(f"人设剧情生成成功：{len(self.characters)}个角色，{len(self.script_nodes)}个节点")
        
        return result
    
    def _validate_consistency(self) -> tuple[bool, str]:
        """
        校验生成结果的一致性
        
        Returns:
            tuple[bool, str]: (校验结果, 错误消息)
        """
        # 校验1：至少有一个角色
        if not self.characters:
            return False, "未生成任何角色"
        
        # 校验2：至少有一个起始节点
        has_start = any(node.is_start for node in self.script_nodes)
        if not has_start:
            return False, "剧本缺少起始节点"
        
        # 校验3：节点ID唯一性
        node_ids = [node.node_id for node in self.script_nodes]
        if len(node_ids) != len(set(node_ids)):
            return False, "节点ID存在重复"
        
        # 校验4：连接的源和目标节点必须存在
        node_id_set = set(node_ids)
        for conn in self.connections:
            if conn.source not in node_id_set:
                return False, f"连接源节点不存在：{conn.source}"
            if conn.target not in node_id_set:
                return False, f"连接目标节点不存在：{conn.target}"
        
        return True, ""
    
    def _generate_visual_resources(self, task_params: Dict[str, Any]) -> TaskResultSchema:
        """
        生成视觉资源（立绘、背景、CG）
        
        Args:
            task_params: 任务参数
            
        Returns:
            TaskResultSchema: 生成结果
        """
        all_resources = []
        
        try:
            # 1. 生成角色立绘
            if self.portrait_agent and self.characters:
                self.logger.info("开始生成角色立绘")
                portrait_result = self.portrait_agent.safe_run({
                    "characters": [char.model_dump() for char in self.characters],
                    "project_root": task_params["save_path"]
                })
                
                if portrait_result.success and portrait_result.data:
                    resources = portrait_result.data.get("resources", [])
                    all_resources.extend([ResourceMetaSchema(**r) for r in resources])
                    self.logger.info(f"立绘生成完成：{len(resources)}个资源")
            
            # 2. 生成背景图
            if self.background_agent and self.script_nodes:
                self.logger.info("开始生成背景图")
                bg_result = self.background_agent.safe_run({
                    "script_nodes": [node.model_dump() for node in self.script_nodes],
                    "project_root": task_params["save_path"]
                })
                
                if bg_result.success and bg_result.data:
                    resources = bg_result.data.get("resources", [])
                    all_resources.extend([ResourceMetaSchema(**r) for r in resources])
                    self.logger.info(f"背景生成完成：{len(resources)}个资源")
            
            # 3. 生成CG
            if self.cg_agent and self.script_nodes and self.characters:
                self.logger.info("开始生成CG")
                cg_result = self.cg_agent.safe_run({
                    "script_nodes": [node.model_dump() for node in self.script_nodes],
                    "characters": [char.model_dump() for char in self.characters],
                    "project_root": task_params["save_path"]
                })
                
                if cg_result.success and cg_result.data:
                    resources = cg_result.data.get("resources", [])
                    all_resources.extend([ResourceMetaSchema(**r) for r in resources])
                    self.logger.info(f"CG生成完成：{len(resources)}个资源")
            
            # 更新资源列表
            self.resources.extend(all_resources)
            
            return self.create_success_result(
                data={"resources": [r.model_dump() for r in all_resources]},
                message=f"视觉资源生成完成，共{len(all_resources)}个"
            )
        
        except Exception as e:
            self.logger.error(f"视觉资源生成异常：{str(e)}")
            return self.create_error_result("视觉资源生成失败", exception=e)
    
    def _generate_audio_resources(self, task_params: Dict[str, Any]) -> TaskResultSchema:
        """
        生成音频资源（语音、BGM）
        
        Args:
            task_params: 任务参数
            
        Returns:
            TaskResultSchema: 生成结果
        """
        all_resources = []
        
        try:
            # 1. 生成角色配音
            if self.voice_agent and self.script_nodes and self.characters:
                self.logger.info("开始生成角色配音")
                voice_result = self.voice_agent.safe_run({
                    "script_nodes": [node.model_dump() for node in self.script_nodes],
                    "characters": [char.model_dump() for char in self.characters],
                    "project_root": task_params["save_path"]
                })
                
                if voice_result.success and voice_result.data:
                    resources = voice_result.data.get("resources", [])
                    all_resources.extend([ResourceMetaSchema(**r) for r in resources])
                    self.logger.info(f"配音生成完成：{len(resources)}个资源")
            
            # 2. 生成BGM
            if self.bgm_agent and self.script_nodes:
                self.logger.info("开始生成BGM")
                bgm_result = self.bgm_agent.safe_run({
                    "script_nodes": [node.model_dump() for node in self.script_nodes],
                    "project_root": task_params["save_path"]
                })
                
                if bgm_result.success and bgm_result.data:
                    resources = bgm_result.data.get("resources", [])
                    all_resources.extend([ResourceMetaSchema(**r) for r in resources])
                    self.logger.info(f"BGM生成完成：{len(resources)}个资源")
            
            # 更新资源列表
            self.resources.extend(all_resources)
            
            return self.create_success_result(
                data={"resources": [r.model_dump() for r in all_resources]},
                message=f"音频资源生成完成，共{len(all_resources)}个"
            )
        
        except Exception as e:
            self.logger.error(f"音频资源生成异常：{str(e)}")
            return self.create_error_result("音频资源生成失败", exception=e)
    
    def _integrate_project(self, task_params: Dict[str, Any]) -> TaskResultSchema:
        """
        整合工程文件
        
        Args:
            task_params: 任务参数
            
        Returns:
            TaskResultSchema: 集成结果
        """
        if not self.integration_agent:
            return self.create_error_result("工程集成Agent未初始化")
        
        try:
            self.logger.info("开始工程集成")
            
            integration_result = self.integration_agent.safe_run({
                "project_root": task_params["save_path"],
                "project_name": task_params["game_name"],
                "characters": [char.model_dump() for char in self.characters],
                "script_nodes": [node.model_dump() for node in self.script_nodes],
                "connections": [conn.model_dump() for conn in self.connections],
                "resources": [res.model_dump() for res in self.resources],
                "game_theme": task_params.get("game_theme", ""),
                "game_description": task_params.get("game_description", "")
            })
            
            if integration_result.success:
                self.logger.info("工程集成完成")
            else:
                self.logger.error(f"工程集成失败：{integration_result.error_msg}")
            
            return integration_result
        
        except Exception as e:
            self.logger.error(f"工程集成异常：{str(e)}")
            return self.create_error_result("工程集成失败", exception=e)
    
    def get_generation_summary(self) -> Dict[str, Any]:
        """
        获取生成结果摘要
        
        Returns:
            Dict[str, Any]: 摘要信息
        """
        return {
            "character_count": len(self.characters),
            "node_count": len(self.script_nodes),
            "connection_count": len(self.connections),
            "resource_count": len(self.resources),
            "character_names": [char.name for char in self.characters],
            "node_types": {
                "text": sum(1 for node in self.script_nodes if node.node_type == "text"),
                "select": sum(1 for node in self.script_nodes if node.node_type == "select"),
                "condition": sum(1 for node in self.script_nodes if node.node_type == "condition")
            }
        }
    
    def close(self):
        """关闭所有子Agent资源"""
        if self.char_plot_agent:
            self.char_plot_agent.close()
        if self.prompt_optimizer_agent:
            self.prompt_optimizer_agent.close()
        if self.portrait_agent:
            self.portrait_agent.close()
        if self.background_agent:
            self.background_agent.close()
        if self.cg_agent:
            self.cg_agent.close()
        if self.voice_agent:
            self.voice_agent.close()
        if self.bgm_agent:
            self.bgm_agent.close()
