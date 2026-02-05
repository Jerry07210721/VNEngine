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
                "version": "2.6",
                "engine_version": "VNEngine V2.6",
                "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_modify_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "game_config": {
                "window_width": 800,
                "window_height": 600,
                "game_title": "我的视觉小说",
                "branch_strategy": "first",  # first | random | longest (预留)
                "text_styles": {
                    "dialogue": {
                        "font_family": "SimHei",
                        "font_path": "",
                        "size": 22,
                        "color": [235, 235, 240],
                        "bold": False,
                        "outline_color": [0, 0, 0],
                        "outline_width": 0,
                    },
                    "name": {
                        "font_family": "SimHei",
                        "font_path": "",
                        "size": 24,
                        "color": [220, 220, 220],
                        "bold": True,
                        "outline_color": [0, 0, 0],
                        "outline_width": 0,
                    },
                },
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
                "menu_option_scale": 1.0,
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

    def new_project(self, project_name: str = "未命名工程", window_width: int = 800, window_height: int = 600):
        """新建空工程并固定窗口分辨率。"""
        self.project_data["project_info"]["name"] = project_name
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.project_data["project_info"]["create_time"] = now
        self.project_data["project_info"]["last_modify_time"] = now
        # 记录用户选择的窗口分辨率（项目创建后不再修改）
        self.project_data["game_config"]["window_width"] = int(max(320, window_width))
        self.project_data["game_config"]["window_height"] = int(max(240, window_height))
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
