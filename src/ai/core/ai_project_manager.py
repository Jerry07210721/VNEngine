# -*- coding: utf-8 -*-
"""
AI辅助工程文件管理器
负责AI工程（.vnai）的创建、保存、加载
"""

import os
import yaml
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from .models import (
    AIProject,
    AIProjectInfo,
    StoryConfig,
    CharacterConfig,
    GenerationHistory,
    PendingLists,
    GenerationStep
)
from ..log.logger import get_logger

logger = get_logger("AIProjectManager")


class AIProjectManager:
    """AI辅助工程管理器"""
    
    EXTENSION = ".vnai"  # AI工程文件扩展名
    
    def __init__(self):
        self.current_project: Optional[AIProject] = None
        self.current_file_path: Optional[str] = None
    
    def create_new_project(
        self,
        project_name: str,
        save_path: str,
        story_title: str = "",
        description: str = ""
    ) -> AIProject:
        """
        创建新的AI辅助工程
        
        Args:
            project_name: 工程名称
            save_path: 保存路径（.vnai文件路径）
            story_title: 故事标题（可选）
            description: 工程描述（可选）
        
        Returns:
            AIProject实例
        """
        logger.info(f"创建新AI工程: {project_name}")
        
        # 确保路径以.vnai结尾
        if not save_path.endswith(self.EXTENSION):
            save_path = save_path + self.EXTENSION
        
        # 创建工程数据
        project_info = AIProjectInfo(
            name=project_name,
            description=description,
            vng_project_path=None
        )
        
        # 初始化故事配置（使用默认值）
        story_config = StoryConfig(
            title=story_title or project_name,
            style="日系校园",
            plot_outline="",
            text_volume=5000
        )
        
        # 创建AI工程对象
        self.current_project = AIProject(
            ai_project_info=project_info,
            story_config=story_config,
            character_config=[],
            generation_history=GenerationHistory(),
            pending_lists=PendingLists()
        )
        
        self.current_file_path = save_path
        
        # 保存到文件
        self.save_project(save_path)
        
        logger.info(f"AI工程创建成功: {save_path}")
        return self.current_project
    
    def save_project(self, file_path: Optional[str] = None) -> bool:
        """
        保存AI工程到文件
        
        Args:
            file_path: 保存路径，为None则使用当前路径
        
        Returns:
            是否保存成功
        """
        if self.current_project is None:
            logger.error("没有加载的AI工程")
            return False
        
        save_path = file_path or self.current_file_path
        if not save_path:
            logger.error("未指定保存路径")
            return False
        
        try:
            # 更新修改时间
            self.current_project.update_modified_time()
            
            # 转换为字典
            project_dict = self.current_project.model_dump(mode='python')
            
            # 确保目录存在
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            
            # 保存为YAML格式
            with open(save_path, 'w', encoding='utf-8') as f:
                yaml.dump(
                    project_dict,
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False
                )
            
            self.current_file_path = save_path
            logger.info(f"AI工程已保存: {save_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存AI工程失败: {e}", exc_info=True)
            return False
    
    def load_project(self, file_path: str) -> Optional[AIProject]:
        """
        加载AI工程文件
        
        Args:
            file_path: .vnai文件路径
        
        Returns:
            加载的AIProject实例，失败返回None
        """
        if not os.path.exists(file_path):
            logger.error(f"AI工程文件不存在: {file_path}")
            return None
        
        try:
            logger.info(f"加载AI工程: {file_path}")
            
            # 读取YAML文件
            with open(file_path, 'r', encoding='utf-8') as f:
                project_dict = yaml.safe_load(f)
            
            # 验证并创建AIProject实例
            self.current_project = AIProject(**project_dict)
            self.current_file_path = file_path
            
            logger.info(f"AI工程加载成功: {self.current_project.ai_project_info.name}")
            return self.current_project
            
        except Exception as e:
            logger.error(f"加载AI工程失败: {e}", exc_info=True)
            return None
    
    def update_story_config(self, story_config: StoryConfig) -> bool:
        """更新剧情配置"""
        if self.current_project is None:
            return False
        
        self.current_project.story_config = story_config
        self.current_project.update_modified_time()
        return True
    
    def update_character_config(self, character_config: list[CharacterConfig]) -> bool:
        """更新角色配置"""
        if self.current_project is None:
            return False
        
        self.current_project.character_config = character_config
        self.current_project.update_modified_time()
        return True
    
    def add_character(self, character: CharacterConfig) -> bool:
        """添加角色"""
        if self.current_project is None:
            return False
        
        self.current_project.character_config.append(character)
        self.current_project.update_modified_time()
        return True
    
    def remove_character(self, char_id: str) -> bool:
        """删除角色"""
        if self.current_project is None:
            return False
        
        self.current_project.character_config = [
            char for char in self.current_project.character_config
            if char.char_id != char_id
        ]
        self.current_project.update_modified_time()
        return True
    
    def update_generation_step(
        self,
        step_key: str,
        data: Dict[str, Any]
    ) -> bool:
        """
        更新生成历史的某个步骤
        
        Args:
            step_key: 步骤键名，如'step1_personas'
            data: 步骤数据
        """
        if self.current_project is None:
            return False
        
        if hasattr(self.current_project.generation_history, step_key):
            setattr(self.current_project.generation_history, step_key, data)
            self.current_project.update_modified_time()
            logger.info(f"更新生成历史: {step_key}")
            return True
        else:
            logger.warning(f"无效的步骤键名: {step_key}")
            return False

    def update_generation_history_field(self, field_key: str, value: Any) -> bool:
        """更新 generation_history 的任意字段（用于保存对话历史等非 stepX 结果字段）。"""
        if self.current_project is None:
            return False

        gh = getattr(self.current_project, "generation_history", None)
        if gh is None:
            return False

        if hasattr(gh, field_key):
            setattr(gh, field_key, value)
            self.current_project.update_modified_time()
            logger.info(f"更新生成历史字段: {field_key}")
            return True

        logger.warning(f"无效的生成历史字段: {field_key}")
        return False
    
    def add_agent_instruction(self, instruction: GenerationStep) -> bool:
        """添加Agent指令记录"""
        if self.current_project is None:
            return False
        
        self.current_project.generation_history.agent_instructions.append(instruction)
        self.current_project.update_modified_time()
        return True
    
    def update_pending_lists(self, pending_lists: PendingLists) -> bool:
        """更新待生成列表"""
        if self.current_project is None:
            return False
        
        self.current_project.pending_lists = pending_lists
        self.current_project.update_modified_time()
        return True
    
    def set_vng_project_path(self, vng_path: str) -> bool:
        """设置关联的VNG工程路径"""
        if self.current_project is None:
            return False
        
        self.current_project.ai_project_info.vng_project_path = vng_path
        self.current_project.update_modified_time()
        logger.info(f"关联VNG工程: {vng_path}")
        return True
    
    def export_to_json(self, json_path: str) -> bool:
        """导出为JSON格式（用于调试或备份）"""
        if self.current_project is None:
            return False
        
        try:
            project_dict = self.current_project.model_dump(mode='python')
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(project_dict, f, ensure_ascii=False, indent=2)
            
            logger.info(f"AI工程已导出为JSON: {json_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出JSON失败: {e}", exc_info=True)
            return False
    
    def get_project_summary(self) -> Dict[str, Any]:
        """获取工程摘要信息"""
        if self.current_project is None:
            return {}
        
        return {
            "name": self.current_project.ai_project_info.name,
            "created_time": self.current_project.ai_project_info.created_time,
            "last_modified_time": self.current_project.ai_project_info.last_modified_time,
            "story_title": self.current_project.story_config.title,
            "character_count": len(self.current_project.character_config),
            "vng_project_path": self.current_project.ai_project_info.vng_project_path,
            "pending_portraits": len(self.current_project.pending_lists.portraits),
            "pending_backgrounds": len(self.current_project.pending_lists.backgrounds),
            "pending_cgs": len(self.current_project.pending_lists.cgs),
            "pending_voices": len(self.current_project.pending_lists.voices),
            "pending_bgms": len(self.current_project.pending_lists.bgms),
        }
    
    @staticmethod
    def is_valid_project_file(file_path: str) -> bool:
        """检查是否为有效的AI工程文件"""
        if not file_path.endswith(AIProjectManager.EXTENSION):
            return False
        
        if not os.path.exists(file_path):
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            # 检查必要字段
            return (
                isinstance(data, dict) and
                'ai_project_info' in data and
                'story_config' in data
            )
        except:
            return False
