# -*- coding: utf-8 -*-
"""Project manager handles create/open/save of VN projects."""
import os
import yaml
from datetime import datetime
from .common_utils import ensure_dir_exists, validate_project_path


class VNProjectManager:
    """视觉小说工程管理器，负责工程的新建、保存、打开"""

    def __init__(self):
        self.project_data = {
            "project_info": {
                "name": "未命名工程",
                "version": "0.1",
                "engine_version": "VNEngine V0.1",
                "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_modify_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "game_config": {
                "window_width": 800,
                "window_height": 600,
                "game_title": "我的视觉小说",
                "branch_strategy": "first",  # first | random | longest (预留)
                "menu_title": "",
                "menu_background": "",
                "menu_bgm": "",
                "menu_bgm_loop": True,
                "menu_video": "",
                "menu_video_loop": False,
                    "menu_overlay_alpha": 0,
            },
            "resources": {
                "images": [],
                "audios": [],
                "portraits": [],
                "voices": [],
                "videos": [],
            },
            "global_variables": [],
            "flow_nodes": {"nodes": [], "connections": []},
        }

    def new_project(self, project_name: str = "未命名工程"):
        """新建空工程"""
        self.project_data["project_info"]["name"] = project_name
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.project_data["project_info"]["create_time"] = now
        self.project_data["project_info"]["last_modify_time"] = now
        self.project_data["flow_nodes"] = {"nodes": [], "connections": []}
        return self.project_data

    def save_project(self, file_path: str) -> bool:
        """保存工程到指定路径（YAML格式）"""
        validate_result = validate_project_path(file_path)
        if validate_result is not None:
            raise ValueError(validate_result)

        self.project_data["project_info"]["last_modify_time"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        try:
            ensure_dir_exists(os.path.dirname(file_path))
            with open(file_path, "w", encoding="utf-8") as file:
                yaml.dump(self.project_data, file, allow_unicode=True, indent=4)
            return True
        except Exception as exc:
            raise Exception(f"保存工程失败：{str(exc)}")

    def open_project(self, file_path: str):
        """从指定路径打开工程"""
        validate_result = validate_project_path(file_path)
        if validate_result is not None:
            raise ValueError(validate_result)

        try:
            with open(file_path, "r", encoding="utf-8") as file:
                self.project_data = yaml.safe_load(file)
            return self.project_data
        except Exception as exc:
            raise Exception(f"打开工程失败：{str(exc)}")
