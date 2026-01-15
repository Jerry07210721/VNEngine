# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - 整合Agent
负责调用 Integrator 将剧情节点和素材打包生成 .vngproj
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, List

from ..core.models import TaskAssignment, AgentResponse, UserConfig
from ..integrator.integrator import Integrator
from ..core.config_manager import ConfigManager
from ..log.logger import get_logger


class IntegratorAgent:
    """封装 Integrator 的 Agent 外观，便于调度。"""

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        self.config_manager = config_manager or ConfigManager()
        self.logger = get_logger("IntegratorAgent")
        self.integrator = Integrator(self.config_manager)

    def execute(self, task: TaskAssignment) -> AgentResponse:
        """根据 task.parameters 调用 Integrator。

        期望参数：
        - user_config: dict，可直接构造 UserConfig
        - plot_file: 剧情/流程图 json 路径
        - portraits_dir/backgrounds_dir/voice_dir/bgm_dir: 可选资源目录
        - resources_dir: 可选已有资源根目录（若走 integrate_from_data）
        - flow_nodes/connections/global_variables/material_requirements: 可选直接传入数据
        """
        params = task.parameters or {}
        try:
            user_cfg_dict: Dict[str, Any] = params.get("user_config") or {}
            user_config = UserConfig(**user_cfg_dict)
        except Exception as exc:
            return AgentResponse(
                agent_name="integrator_agent",
                task_type=task.task_type,
                status="failure",
                message="user_config 解析失败",
                error_detail=str(exc),
            )

        plot_file = params.get("plot_file")
        resources_dir = params.get("resources_dir")
        flow_nodes = params.get("flow_nodes")
        connections = params.get("connections")
        global_vars = params.get("global_variables")
        material_reqs = params.get("material_requirements")

        if not plot_file and not flow_nodes:
            plot_file = self._find_latest_flow(Path(user_config.project_info.project_path))

        try:
            if flow_nodes and connections:
                project_file = self.integrator.integrate_from_data(
                    user_config=user_config,
                    flow_nodes=flow_nodes,
                    connections=connections,
                    global_variables=global_vars,
                    material_requirements=material_reqs,
                    resources_dir=resources_dir,
                )
                node_count = len(flow_nodes)
            else:
                if not plot_file:
                    raise ValueError("缺少 plot_file 或 flow_nodes 数据")
                project_file = self.integrator.integrate_all(
                    user_config=user_config,
                    plot_file=plot_file,
                    portraits_dir=params.get("portraits_dir"),
                    backgrounds_dir=params.get("backgrounds_dir"),
                    voice_dir=params.get("voice_dir"),
                    bgm_dir=params.get("bgm_dir"),
                )["project_file"]
                node_count = len(self.integrator.flow_nodes)

            output_files = [project_file]
            metadata = {
                "node_count": node_count,
                "connection_count": len(self.integrator.connections),
                "project_path": str(self.integrator.project_path) if self.integrator.project_path else "",
            }

            return AgentResponse(
                agent_name="integrator_agent",
                task_type=task.task_type,
                status="success",
                message="工程整合完成",
                output_files=output_files,
                metadata=metadata,
            )
        except Exception as exc:
            return AgentResponse(
                agent_name="integrator_agent",
                task_type=task.task_type,
                status="failure",
                message="整合失败",
                error_detail=str(exc),
            )

    def _find_latest_flow(self, project_root: Path) -> Optional[str]:
        plot_dir = project_root / "resources" / "plot"
        if not plot_dir.exists():
            return None
        candidates: List[Path] = list(plot_dir.glob("flow_graph_*.json"))
        if not candidates:
            return None
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        return str(latest)
