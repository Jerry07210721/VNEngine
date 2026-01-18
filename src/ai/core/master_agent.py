# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - 主控制Agent
负责任务分配、流程控制、进度追踪、多Agent协调
"""

from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
import json
from datetime import datetime
from math import gcd

from ..api.api_manager import APIManager
from ..log.logger import get_logger
from .config_manager import ConfigManager
from .models import (
    UserConfig, TaskAssignment, ProgressTrack, 
    MaterialRequirement, AgentResponse, FlowNodeData, TaskDetail
)
from .task_scheduler import TaskScheduler
from .progress_monitor import ProgressMonitor
from .quality_validator import QualityValidator
from .result_aggregator import ResultAggregator


class MasterAgent:
    """主控制Agent - 协调所有子Agent的工作"""
    
    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        api_manager: Optional[APIManager] = None
    ):
        """
        初始化主控制Agent
        
        Args:
            config_manager: 配置管理器
            api_manager: API管理器
        """
        self.config_manager = config_manager or ConfigManager()
        self.api_manager = api_manager or APIManager(self.config_manager)
        self.logger = get_logger("MasterAgent")
        
        # 当前任务状态
        self.current_task: Optional[UserConfig] = None
        self.progress: Optional[ProgressTrack] = None
        self.project_root: Optional[Path] = None
        
        # 子Agent注册表
        self.agents: Dict[str, Any] = {}
        
        # 任务历史
        self.task_history: List[Dict[str, Any]] = []
        
        # 协同模块
        self.scheduler = TaskScheduler(max_concurrent=1)
        self.progress_monitor = ProgressMonitor()
        self.quality_validator = QualityValidator()
        self.result_aggregator = ResultAggregator()
        
        self.logger.info("MasterAgent初始化完成")
    
    def register_agent(self, agent_name: str, agent_instance: Any):
        """
        注册子Agent
        
        Args:
            agent_name: Agent名称
            agent_instance: Agent实例
        """
        self.agents[agent_name] = agent_instance
        self.logger.info(f"注册Agent: {agent_name}")
    
    def start_task(self, user_config: UserConfig) -> ProgressTrack:
        """
        启动新任务
        
        Args:
            user_config: 用户配置
        
        Returns:
            进度追踪对象
        """
        self.logger.info("=" * 80)
        self.logger.info("启动新的GalGame创作任务")
        self.logger.info("=" * 80)
        
        # 保存当前任务
        self.current_task = user_config
        self.project_root = Path(user_config.project_info.project_path).expanduser().resolve()
        self._prepare_project_directories()
        
        # 初始化进度追踪
        self.progress = ProgressTrack(
            total_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
            processing_tasks=0,
            pending_tasks=0,
            task_details=[],
            current_stage="planning",
            progress_percentage=0.0
        )
        self.pending_task_list = []
        self.scheduler.reset()
        self.progress_monitor.bind(self.progress)
        
        # 记录任务配置
        self.logger.info(f"项目名称: {user_config.project_info.project_name}")
        self.logger.info(f"故事标题: {user_config.story_config.title}")
        self.logger.info(f"故事风格: {user_config.story_config.style}")
        self.logger.info(f"角色数量: {len(user_config.character_config)}")
        
        # 生成任务列表
        self._plan_tasks(user_config)
        
        return self.progress
    
    def _plan_tasks(self, config: UserConfig):
        """
        根据用户配置规划任务
        
        Args:
            config: 用户配置
        """
        self.logger.info("\n开始任务规划...")
        
        tasks = []
        task_id_counter = 1
        
        # 计算项目长宽比，供背景等使用
        aspect_ratio = self._calc_aspect_ratio(
            config.project_info.window_width,
            config.project_info.window_height
        )

        # 第一人称信息（用于跳过立绘/语音生成）
        fp_enabled = config.story_config.narrative_pov == "first"
        fp_name = (config.story_config.first_person_name or "").strip().lower()

        # 1. 剧情生成任务
        if config.enable_agents.plot_agent:
            tasks.append(TaskAssignment(
                task_id=f"task_{task_id_counter:03d}",
                agent_type="plot",
                task_type="generate_plot",
                agent_name="plot_agent",
                task_content="生成剧情大纲和章节内容",
                parameters={
                    "title": config.story_config.title,
                    "style": config.story_config.style,
                    "plot_outline": config.story_config.plot_outline,
                    "text_volume": config.story_config.text_volume,
                    "project_root": str(self.project_root),
                    "character_hint_weight": config.story_config.character_hint_weight,
                    "narrative_pov": config.story_config.narrative_pov,
                    "first_person_name": config.story_config.first_person_name,
                    "first_person_has_portrait": config.story_config.first_person_has_portrait,
                    "first_person_has_voice": config.story_config.first_person_has_voice,
                    "first_person_cg_presence": config.story_config.first_person_cg_presence,
                    "first_person_cg_notes": config.story_config.first_person_cg_notes,
                    "characters": [
                        {
                            "name": c.char_name,
                            "role": c.role,
                            "persona": c.persona_keywords,
                            "description": c.persona_keywords,
                        }
                        for c in config.character_config
                    ],
                },
                priority=1
            ))
            task_id_counter += 1
        
        # 2. 角色立绘任务
        if config.enable_agents.portrait_agent:
            for char in config.character_config:
                is_first_person = fp_enabled and (char.is_first_person or char.char_name.strip().lower() == fp_name)
                if is_first_person and not config.story_config.first_person_has_portrait:
                    self.logger.info(f"跳过第一人称立绘生成: {char.char_name}")
                    continue
                tasks.append(TaskAssignment(
                    task_id=f"task_{task_id_counter:03d}",
                    agent_type="portrait",
                    task_type="generate_portrait",
                    agent_name="portrait_agent",
                    task_content=f"生成角色 {char.char_name} 的立绘",
                    parameters={
                        "character_name": char.char_name,
                        "persona": char.persona_keywords,
                        "reference_image": char.reference_image,
                        "project_root": str(self.project_root),
                        "aspect": "2:3"
                    },
                    priority=2
                ))
                task_id_counter += 1
        
        # 3. 背景图任务
        if config.enable_agents.background_agent:
            tasks.append(TaskAssignment(
                task_id=f"task_{task_id_counter:03d}",
                agent_type="background",
                task_type="generate_backgrounds",
                agent_name="background_agent",
                task_content="生成场景背景图",
                parameters={
                    "scene_count": 5,
                    "style": config.story_config.style,
                    "project_root": str(self.project_root),
                    "aspect": aspect_ratio,
                },
                priority=2
            ))
            task_id_counter += 1
        
        # 4. CG任务
        if config.enable_agents.cg_agent:
            cg_count = int(getattr(config.story_config, "cg_count", 0) or 0)
            if cg_count <= 0:
                cg_count = 3
            tasks.append(TaskAssignment(
                task_id=f"task_{task_id_counter:03d}",
                agent_type="cg",
                task_type="generate_cg",
                agent_name="cg_agent",
                task_content="生成事件CG图",
                parameters={
                    "cg_count": cg_count,
                    "style": config.story_config.style,
                    "project_root": str(self.project_root)
                },
                priority=3
            ))
            task_id_counter += 1
        
        # 5. 语音合成任务
        if config.enable_agents.voice_api:
            tasks.append(TaskAssignment(
                task_id=f"task_{task_id_counter:03d}",
                agent_type="voice",
                task_type="synthesize_voice",
                agent_name="voice_agent",
                task_content="合成角色语音",
                parameters={
                    "characters": [
                        {"name": c.char_name, "voice_model_id": c.voice_model_id}
                        for c in config.character_config
                        if not (fp_enabled and (c.is_first_person or c.char_name.strip().lower() == fp_name) and not config.story_config.first_person_has_voice)
                    ],
                    "project_root": str(self.project_root)
                },
                priority=4
            ))
            task_id_counter += 1
        
        # 6. BGM生成任务
        if config.enable_agents.bgm_api:
            tasks.append(TaskAssignment(
                task_id=f"task_{task_id_counter:03d}",
                agent_type="bgm",
                task_type="generate_bgm",
                agent_name="bgm_agent",
                task_content="生成背景音乐",
                parameters={
                    "bgm_count": 3,
                    "music_style": config.story_config.style,
                    "project_root": str(self.project_root)
                },
                priority=4
            ))
            task_id_counter += 1

        # 7. 资源整合任务（串行最后一步）
        latest_plot = self._find_latest_plot_file(self.project_root)
        tasks.append(TaskAssignment(
            task_id=f"task_{task_id_counter:03d}",
            agent_type="integrator",
            task_type="integrate_project",
            agent_name="integrator_agent",
            task_content="整合剧情与素材，生成工程文件",
            parameters={
                "user_config": config.model_dump(),
                "plot_file": latest_plot,
                "portraits_dir": str(self.project_root / "resources" / "portraits"),
                "backgrounds_dir": str(self.project_root / "resources" / "backgrounds"),
                "voice_dir": str(self.project_root / "resources" / "voice"),
                "bgm_dir": str(self.project_root / "resources" / "bgm"),
            },
            priority=5
        ))
        task_id_counter += 1
        
        self.pending_task_list = tasks
        self.progress.total_tasks = len(tasks)
        self.progress.pending_tasks = len(tasks)
        self.logger.info(f"共规划 {len(tasks)} 个任务")
        
        # 按优先级排序并放入调度器
        self.pending_task_list.sort(key=lambda t: t.priority)
        self.scheduler.add_tasks(self.pending_task_list)

    def _find_latest_plot_file(self, project_root: Path) -> Optional[str]:
        """寻找最新的 flow_graph_*.json 作为整合输入。"""
        plot_dir = project_root / "resources" / "plot"
        if not plot_dir.exists():
            return None
        candidates = list(plot_dir.glob("flow_graph_*.json"))
        if not candidates:
            return None
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        return str(latest)

    def _calc_aspect_ratio(self, width: int, height: int) -> str:
        """根据窗口尺寸计算简化后的宽高比字符串。"""
        try:
            w = max(1, int(width))
            h = max(1, int(height))
            g = gcd(w, h)
            return f"{w // g}:{h // g}"
        except Exception:
            return "16:9"
    
    def execute_next_task(self, callback: Optional[Callable] = None) -> Optional[AgentResponse]:
        """
        执行下一个待处理任务
        
        Args:
            callback: 进度回调函数
        
        Returns:
            Agent响应结果
        """
        if not self.progress or not self.scheduler.has_pending():
            self.logger.info("没有待处理的任务")
            return None
        
        # 获取下一个可执行的任务（检查依赖）
        task = self._get_next_executable_task()
        
        if not task:
            self.logger.warning("所有待处理任务都有未满足的依赖")
            return None
        
        self.progress.pending_tasks = max(0, self.progress.pending_tasks - 1)
        self.progress.processing_tasks += 1
        self.progress_monitor.on_task_started()
        
        self.logger.info(f"\n执行任务: {task.task_type or task.agent_type} (Agent: {task.agent_key})")
        
        # 获取对应的Agent
        agent = self.agents.get(task.agent_key)
        
        if not agent:
            self.logger.error(f"Agent {task.agent_name} 未注册")
            return None
        
        # 执行任务
        try:
            response = agent.execute(task)
            
            # 更新进度
            self.scheduler.mark_complete(task)

            if response.status == "success":
                self._update_progress(task)
                self.progress_monitor.on_task_finished(success=True)

                output_files = response.output_files or []
                if not output_files and response.data:
                    output_files = response.data.get("output_files", [])

                # 质量校验（存在性/后缀）
                abs_files = [str(self.project_root / f) if self.project_root else f for f in output_files]
                valid, missing = self.quality_validator.validate_files(abs_files)
                if not valid:
                    self.logger.warning(f"输出文件缺失: {missing}")

                task_detail = TaskDetail(
                    task_id=task.task_id,
                    task_content=task.task_content,
                    status="completed",
                    result_path=str(output_files[0]) if output_files else "",
                    message=response.message or "任务完成"
                )
                self.progress.task_details.append(task_detail)

                self.logger.info(f"✓ 任务完成: {task.task_content}")
                if response.message:
                    self.logger.info(f"  消息: {response.message}")
            else:
                self.progress.failed_tasks += 1
                self.progress.processing_tasks = max(0, self.progress.processing_tasks - 1)
                self.progress_monitor.on_task_finished(success=False)

                task_detail = TaskDetail(
                    task_id=task.task_id,
                    task_content=task.task_content,
                    status="failed",
                    message=response.message or "任务失败",
                    error_info=response.error_detail or response.error_message or "未知错误"
                )
                self.progress.task_details.append(task_detail)
                
                self.logger.error(f"✗ 任务失败: {response.message}")
            
            # 调用回调
            if callback:
                callback(self.progress)
            
            return response
            
        except Exception as e:
            self.logger.error(f"执行任务时发生错误: {e}")
            self.scheduler.mark_complete(task)
            if self.progress:
                self.progress.failed_tasks += 1
                self.progress.processing_tasks = max(0, self.progress.processing_tasks - 1)
                self.progress_monitor.on_task_finished(success=False)
                task_detail = TaskDetail(
                    task_id=task.task_id,
                    task_content=task.task_content,
                    status="failed",
                    message="任务异常失败",
                    error_info=str(e)
                )
                self.progress.task_details.append(task_detail)
            return AgentResponse(
                agent_name=task.agent_key,
                task_type=task.task_type,
                status="failure",
                output_files=[],
                metadata={},
                error_message=str(e)
            )
    
    def _get_next_executable_task(self) -> Optional[TaskAssignment]:
        """
        获取下一个可执行的任务（依赖已满足）
        
        Returns:
            可执行的任务，如果没有则返回None
        """
        if not self.scheduler.queue:
            return None

        completed_contents = [t.task_content for t in self.progress.task_details if t.status == "completed"]

        for idx, task in enumerate(list(self.scheduler.queue)):
            dependencies_met = all(
                dep in completed_contents for dep in task.parameters.get("dependencies", [])
            )

            if not dependencies_met:
                continue

            # check concurrency slots
            if self.scheduler.active_count >= self.scheduler.max_concurrent:
                return None
            active_for_type = self.scheduler.active_by_type.get(task.agent_type, 0)
            type_limit = self.scheduler.per_type_limits.get(task.agent_type, self.scheduler.max_concurrent)
            if active_for_type >= type_limit:
                continue

            # allocate slot and pop from queue
            self.scheduler.active_by_type[task.agent_type] = active_for_type + 1
            self.scheduler.active_count += 1
            self.scheduler.queue.pop(idx)
            self.pending_task_list = [t for t in self.pending_task_list if t.task_id != task.task_id]
            return task

        return None
    
    def _update_progress(self, completed_task: TaskAssignment):
        """
        更新整体进度
        
        Args:
            completed_task: 已完成的任务
        """
        # 更新计数
        self.progress.completed_tasks += 1
        self.progress.processing_tasks = max(0, self.progress.processing_tasks - 1)
        
        # 计算整体进度百分比
        if self.progress.total_tasks > 0:
            self.progress.progress_percentage = (
                self.progress.completed_tasks / self.progress.total_tasks
            ) * 100.0
        
        # 更新当前阶段
        if completed_task.agent_type == "plot":
            self.progress.current_stage = "portraits_and_backgrounds"
        elif completed_task.agent_type in ["portrait", "background"]:
            self.progress.current_stage = "cg_generation"
        elif completed_task.agent_type == "cg":
            self.progress.current_stage = "voice_and_music"
        elif completed_task.agent_type in ["voice", "bgm"]:
            if self.progress.completed_tasks == self.progress.total_tasks:
                self.progress.current_stage = "completed"
        
        self.logger.info(f"整体进度: {self.progress.progress_percentage:.1f}%")
    
    def execute_all_tasks(self, callback: Optional[Callable] = None) -> List[AgentResponse]:
        """
        执行所有待处理任务
        
        Args:
            callback: 进度回调函数
        
        Returns:
            所有任务的响应列表
        """
        self.logger.info("\n开始批量执行所有任务...")
        
        responses = []
        
        while self.progress and self.pending_task_list:
            response = self.execute_next_task(callback)
            
            if response:
                responses.append(response)
            else:
                # 没有可执行的任务，可能是依赖未满足或出错
                break
        
        # 任务完成统计
        success_count = sum(1 for r in responses if r.status == "success")
        total_count = len(responses)
        
        self.logger.info("\n" + "=" * 80)
        self.logger.info(f"任务批量执行完成: {success_count}/{total_count} 成功")
        self.logger.info("=" * 80)
        
        return responses
    
    def get_progress(self) -> Optional[ProgressTrack]:
        """获取当前进度"""
        return self.progress
    
    def save_progress(self, output_path: Path):
        """
        保存进度到文件
        
        Args:
            output_path: 输出文件路径
        """
        if not self.progress:
            self.logger.warning("没有进度信息可保存")
            return
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        progress_data = self.progress.model_dump()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"进度已保存到: {output_path}")
    
    def load_progress(self, input_path: Path) -> ProgressTrack:
        """
        从文件加载进度
        
        Args:
            input_path: 输入文件路径
        
        Returns:
            进度追踪对象
        """
        input_path = Path(input_path)
        
        with open(input_path, 'r', encoding='utf-8') as f:
            progress_data = json.load(f)
        
        self.progress = ProgressTrack(**progress_data)
        
        self.logger.info(f"进度已从 {input_path} 加载")
        return self.progress
    
    def cleanup(self):
        """清理资源"""
        self.logger.info("清理MasterAgent资源...")
        
        # 关闭所有子Agent
        for agent_name, agent in self.agents.items():
            try:
                if hasattr(agent, 'cleanup'):
                    agent.cleanup()
                self.logger.info(f"  {agent_name} 已清理")
            except Exception as e:
                self.logger.warning(f"  清理 {agent_name} 时出错: {e}")
        
        # 关闭API管理器
        self.api_manager.close_all()
        
        self.logger.info("MasterAgent清理完成")

    def _prepare_project_directories(self):
        """确保工程资源目录存在。"""
        if not self.project_root:
            return
        self.project_root.mkdir(parents=True, exist_ok=True)
        resources = [
            self.project_root / "resources" / "portraits",
            self.project_root / "resources" / "backgrounds",
            self.project_root / "resources" / "cg",
            self.project_root / "resources" / "voice",
            self.project_root / "resources" / "bgm",
            self.project_root / "resources" / "plot",
        ]
        for path in resources:
            path.mkdir(parents=True, exist_ok=True)
