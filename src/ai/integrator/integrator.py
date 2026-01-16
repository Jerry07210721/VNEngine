# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - 资源整合器
负责将AI生成的素材整合到VNEngine工程格式
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import json
import shutil
from datetime import datetime

from ..core.config_manager import ConfigManager
from ..core.models import (
    UserConfig,
    FlowNodeData,
    ConnectionData,
    GlobalVariable,
    MaterialRequirement,
)
from ..log.logger import get_logger


class Integrator:
    """资源整合器 - 将AI生成内容整合为VNEngine工程"""
    
    def __init__(self, config_manager: Optional[ConfigManager] = None):
        """
        初始化整合器
        
        Args:
            config_manager: 配置管理器
        """
        self.config_manager = config_manager or ConfigManager()
        self.logger = get_logger("Integrator")
        
        # 当前工程信息
        self.project_path: Optional[Path] = None
        self.project_name: str = ""
        
        # 资源路径
        self.resources_dir: Optional[Path] = None
        self.portraits_dir: Optional[Path] = None
        self.backgrounds_dir: Optional[Path] = None
        self.cg_dir: Optional[Path] = None
        self.voice_dir: Optional[Path] = None
        self.bgm_dir: Optional[Path] = None
        
        # 节点和连接
        self.flow_nodes: List[FlowNodeData] = []
        self.connections: List[ConnectionData] = []
        self.global_vars: List[GlobalVariable] = []
        self.material_reqs: List[MaterialRequirement] = []
        
        self.logger.info("Integrator初始化完成")

    def _safe_copy(self, source: Path, dest: Path) -> bool:
        """复制文件，若源和目标相同则跳过，返回是否实际复制。"""

        if not source.exists():
            return False
        try:
            if source.resolve() == dest.resolve():
                return False
        except Exception:
            # resolve 失败时继续尝试复制
            pass
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        return True
    
    def create_project(
        self,
        project_name: str,
        output_dir: str = "output/projects",
        project_path: Optional[str] = None,
    ) -> Path:
        """
        创建新工程
        
        Args:
            project_name: 工程名称
            output_dir: 输出目录
        
        Returns:
            工程路径
        """
        self.logger.info(f"创建工程: {project_name}")

        self.project_name = project_name
        base_path = Path(project_path).expanduser().resolve() if project_path else None
        # 如果用户提供了绝对工程路径，则直接使用该路径，否则回退到默认输出目录
        self.project_path = base_path if base_path else (Path(output_dir) / project_name)
        
        # 创建工程目录结构
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        self.resources_dir = self.project_path / "resources"
        self.resources_dir.mkdir(exist_ok=True)
        
        # 创建资源子目录
        self.portraits_dir = self.resources_dir / "portraits"
        self.backgrounds_dir = self.resources_dir / "backgrounds"
        self.cg_dir = self.resources_dir / "cg"
        self.voice_dir = self.resources_dir / "voices"
        self.bgm_dir = self.resources_dir / "bgm"
        
        for dir_path in [self.portraits_dir, self.backgrounds_dir, 
                         self.cg_dir, self.voice_dir, self.bgm_dir]:
            dir_path.mkdir(exist_ok=True)
        
        self.logger.info(f"工程目录已创建: {self.project_path}")
        
        return self.project_path
    
    def integrate_plot(self, plot_data_path: str) -> int:
        """
        整合剧情数据
        
        Args:
            plot_data_path: 剧情数据文件路径
        
        Returns:
            生成的节点数量
        """
        self.logger.info(f"整合剧情数据: {plot_data_path}")
        
        plot_file = Path(plot_data_path)
        
        if not plot_file.exists():
            self.logger.error(f"剧情文件不存在: {plot_data_path}")
            return 0
        
        # 读取剧情数据
        with open(plot_file, 'r', encoding='utf-8') as f:
            plot_data = json.load(f)

        # 支持直接使用预生成的流程图数据（flow_nodes / connections）
        node_count = self._load_flow_graph(plot_data)
        if node_count == 0:
            node_count = self._convert_plot_to_nodes(plot_data)
        
        self.logger.info(f"剧情整合完成，生成 {node_count} 个节点")
        
        return node_count

    def _load_flow_graph(self, plot_data: Dict[str, Any]) -> int:
        """如果剧情数据包含 flow_nodes / connections，则直接载入。"""

        flow_nodes = plot_data.get("flow_nodes")
        connections = plot_data.get("connections")
        global_vars = plot_data.get("global_variables") or []
        material_reqs = plot_data.get("material_requirements") or []

        # 兼容 flow_data 格式
        if not flow_nodes and "flow_data" in plot_data:
            flow_data = plot_data.get("flow_data") or {}
            flow_nodes = flow_data.get("nodes")
            connections = flow_data.get("connections")
            global_vars = flow_data.get("global_variables") or global_vars
            material_reqs = flow_data.get("material_requirements") or material_reqs

        if not flow_nodes or not connections:
            return 0

        try:
            self.flow_nodes = [FlowNodeData(**n) for n in flow_nodes]
            self.connections = [ConnectionData(**c) for c in connections]
            self.global_vars = [GlobalVariable(**g) for g in global_vars]
            self.material_reqs = [MaterialRequirement(**m) for m in material_reqs]
        except Exception as exc:
            self.logger.warning(f"预载入流程图数据失败，回退到传统转换: {exc}")
            self.flow_nodes = []
            self.connections = []
            self.global_vars = []
            self.material_reqs = []
            return 0

        return len(self.flow_nodes)
    
    def _convert_plot_to_nodes(self, plot_data: Dict[str, Any]) -> int:
        """
        将剧情数据转换为FlowNode节点
        
        Args:
            plot_data: 剧情数据
        
        Returns:
            节点数量
        """
        self.flow_nodes.clear()
        self.connections.clear()
        self.global_vars.clear()
        self.material_reqs.clear()
        
        node_id = 1
        x_pos = 100
        y_pos = 100
        
        # 获取章节数据
        chapters = plot_data.get("chapters", [])
        
        if not chapters:
            self.logger.warning("剧情数据中没有章节信息")
            return 0
        
        prev_node_id = None
        
        for chapter_idx, chapter in enumerate(chapters):
            scenes = chapter.get("scenes", [])
            
            for scene_idx, scene in enumerate(scenes):
                location = scene.get("location", "未知地点")
                scene_desc = scene.get("description", "")
                dialogues = scene.get("dialogues", [])
                
                # 为每条对话创建一个节点
                for dialogue_idx, dialogue in enumerate(dialogues):
                    speaker = dialogue.get("speaker", "")
                    content = dialogue.get("content", "")
                    emotion = dialogue.get("emotion", "neutral")
                    action = dialogue.get("action", "")
                    
                    # 组合节点内容
                    full_content = content
                    if action:
                        full_content = f"{action}\n{content}"
                    
                    # 创建节点
                    node = FlowNodeData(
                        id=node_id,
                        node_type="text",
                        title=f"{speaker}的对话",
                        content=full_content,
                        speaker=speaker,
                        portrait="",  # 后续填充
                        background="",  # 后续填充
                        voice="",  # 后续填充
                        bgm="",  # 后续填充
                        x=x_pos,
                        y=y_pos
                    )
                    
                    self.flow_nodes.append(node)
                    
                    # 创建连接
                    if prev_node_id is not None:
                        connection = ConnectionData(
                            source=prev_node_id,
                            target=node_id
                        )
                        self.connections.append(connection)
                    
                    prev_node_id = node_id
                    node_id += 1
                    y_pos += 150
                
                # 场景切换时增加x坐标
                x_pos += 200
                y_pos = 100
        
        return len(self.flow_nodes)
    
    def integrate_portraits(self, portraits_dir: str, character_mapping: Dict[str, str]):
        """
        整合立绘资源
        
        Args:
            portraits_dir: 立绘源目录
            character_mapping: 角色名到目录的映射
        """
        self.logger.info(f"整合立绘资源: {portraits_dir}")
        
        source_dir = Path(portraits_dir)
        
        if not source_dir.exists():
            self.logger.warning(f"立绘目录不存在: {portraits_dir}")
            return
        
        copied_count = 0
        
        for char_name, char_dir in character_mapping.items():
            char_source = source_dir / char_dir
            
            if not char_source.exists():
                self.logger.warning(f"角色立绘目录不存在: {char_source}")
                continue
            
            # 复制所有立绘文件
            for img_file in char_source.glob("*.png"):
                dest_file = self.portraits_dir / f"{char_name}_{img_file.name}"
                if self._safe_copy(img_file, dest_file):
                    copied_count += 1
                    self.logger.info(f"  复制立绘: {img_file.name} -> {dest_file.name}")
        
        # 更新节点中的立绘路径
        self._update_node_portraits(character_mapping)
        
        self.logger.info(f"立绘整合完成，复制 {copied_count} 个文件")
    
    def _update_node_portraits(self, character_mapping: Dict[str, str]):
        """更新节点中的立绘路径"""
        
        for node in self.flow_nodes:
            speaker = node.speaker
            
            if speaker in character_mapping:
                # 默认使用neutral表情
                portrait_file = f"{speaker}_{speaker}_neutral.png"
                portrait_path = f"resources/portraits/{portrait_file}"
                
                # 检查文件是否存在
                if (self.portraits_dir / portrait_file).exists():
                    node.portrait = portrait_path
                else:
                    # 尝试查找其他表情
                    portrait_files = list(self.portraits_dir.glob(f"{speaker}_*.png"))
                    if portrait_files:
                        node.portrait = f"resources/portraits/{portrait_files[0].name}"
    
    def integrate_backgrounds(self, backgrounds_dir: str):
        """
        整合背景资源
        
        Args:
            backgrounds_dir: 背景源目录
        """
        self.logger.info(f"整合背景资源: {backgrounds_dir}")
        
        source_dir = Path(backgrounds_dir)
        
        if not source_dir.exists():
            self.logger.warning(f"背景目录不存在: {backgrounds_dir}")
            return
        
        copied_count = 0
        
        # 复制所有背景文件（支持常见图片后缀）
        for pattern in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
            for bg_file in source_dir.glob(pattern):
                dest_file = self.backgrounds_dir / bg_file.name
                if self._safe_copy(bg_file, dest_file):
                    copied_count += 1
                    self.logger.info(f"  复制背景: {bg_file.name}")
        
        # 简单分配背景（可以根据场景描述智能匹配）
        self._assign_backgrounds()
        
        self.logger.info(f"背景整合完成，复制 {copied_count} 个文件")
    
    def _assign_backgrounds(self):
        """为节点分配背景"""
        
        bg_files: List[Path] = []
        for pattern in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
            bg_files.extend(self.backgrounds_dir.glob(pattern))
        
        if not bg_files:
            return
        
        # 简单策略：循环使用背景
        bg_index = 0
        current_bg = None
        
        for node in self.flow_nodes:
            if not node.background:
                # 每10个节点切换一次背景
                if bg_index < len(bg_files):
                    current_bg = f"resources/backgrounds/{bg_files[bg_index].name}"
                    bg_index = (bg_index + 1) % len(bg_files)
                
                node.background = current_bg or ""
    
    def integrate_voice(self, voice_dir: str):
        """
        整合语音资源
        
        Args:
            voice_dir: 语音源目录
        """
        self.logger.info(f"整合语音资源: {voice_dir}")
        
        source_dir = Path(voice_dir)
        
        if not source_dir.exists():
            self.logger.warning(f"语音目录不存在: {voice_dir}")
            return
        
        copied_count = 0
        
        # 复制所有语音文件（按角色分组）
        for char_dir in source_dir.iterdir():
            if char_dir.is_dir():
                target_char_dir = self.voice_dir / char_dir.name
                target_char_dir.mkdir(exist_ok=True)
                for voice_file in char_dir.glob("*.mp3"):
                    dest_file = target_char_dir / voice_file.name
                    if self._safe_copy(voice_file, dest_file):
                        copied_count += 1
        
        # 根据角色顺序为节点分配语音（若已有引用缺失则回填）
        self._assign_voice_from_files()
        self.logger.info(f"语音整合完成，复制 {copied_count} 个文件")
    
    def integrate_bgm(self, bgm_dir: str):
        """
        整合BGM资源
        
        Args:
            bgm_dir: BGM源目录
        """
        self.logger.info(f"整合BGM资源: {bgm_dir}")
        
        source_dir = Path(bgm_dir)
        
        if not source_dir.exists():
            self.logger.warning(f"BGM目录不存在: {bgm_dir}")
            return
        
        copied_count = 0
        
        # 复制所有BGM文件
        for bgm_file in source_dir.glob("*.mp3"):
            dest_file = self.bgm_dir / bgm_file.name
            if self._safe_copy(bgm_file, dest_file):
                copied_count += 1
                self.logger.info(f"  复制BGM: {bgm_file.name}")
        
        # 为节点分配BGM
        self._assign_bgm()
        
        self.logger.info(f"BGM整合完成，复制 {copied_count} 个文件")
    
    def _assign_bgm(self):
        """为节点分配BGM"""
        
        bgm_files = list(self.bgm_dir.glob("*.mp3"))
        
        if not bgm_files:
            return
        
        # 简单策略：使用第一首BGM作为主题曲
        if bgm_files:
            main_bgm = f"resources/bgm/{bgm_files[0].name}"
            
            # 第一个节点播放BGM
            if self.flow_nodes:
                self.flow_nodes[0].bgm = main_bgm
                self.flow_nodes[0].bgm_loop = True

    def _validate_node_resources(self) -> Dict[str, int]:
        """校验节点引用的资源文件是否存在，返回缺失计数。"""

        if not self.project_path:
            return {}

        missing = {"portrait": 0, "background": 0, "voice": 0, "bgm": 0}
        for node in self.flow_nodes:
            checks = {
                "portrait": node.portrait,
                "background": node.background,
                "voice": node.voice,
                "bgm": node.bgm,
            }
            for key, rel_path in checks.items():
                if not rel_path:
                    continue
                full_path = self.project_path / rel_path
                if not full_path.exists():
                    missing[key] += 1
        return missing
    
    def generate_project_file(self, user_config: UserConfig) -> str:
        """
        生成VNGProj工程文件
        
        Args:
            user_config: 用户配置
        
        Returns:
            工程文件路径
        """
        self.logger.info("生成工程文件...")
        
        if not self.project_path:
            raise RuntimeError("工程路径未设置")

        flow_nodes_payload = {
            "nodes": [node.model_dump() for node in self.flow_nodes],
            "connections": [conn.model_dump() for conn in self.connections],
            "material_requirements": [mr.model_dump() for mr in self.material_reqs],
        }

        resources_payload = self._collect_resources()
        
        # 构建工程数据
        project_data = {
            "project_info": {
                "name": self.project_name,
                "version": "0.1",
                "engine_version": user_config.project_info.engine_version,
                "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_modify_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "story_title": user_config.story_config.title,
                "story_style": user_config.story_config.style,
            },
            "game_config": {
                "window_width": user_config.project_info.window_width,
                "window_height": user_config.project_info.window_height,
                "game_title": user_config.story_config.title,
                "branch_strategy": "first",
                "menu_title": user_config.story_config.title,
                "menu_background": "",
                "menu_bgm": resources_payload.get("audios", [""])[0] if resources_payload.get("audios") else "",
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
            "resources": resources_payload,
            "global_variables": [var.model_dump() for var in self.global_vars],
            "flow_nodes": flow_nodes_payload,
            # 向后兼容旧字段
            "flow_data": flow_nodes_payload,
            "characters": [
                {
                    "char_id": char.char_id,
                    "char_name": char.char_name,
                    "persona_keywords": char.persona_keywords,
                }
                for char in user_config.character_config
            ],
        }
        
        # 保存工程文件
        project_file = self.project_path / f"{self.project_name}.vngproj"
        
        with open(project_file, 'w', encoding='utf-8') as f:
            json.dump(project_data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"工程文件已生成: {project_file}")
        
        return str(project_file)

    def _collect_resources(self) -> Dict[str, List[str]]:
        """扫描资源目录，生成资源列表供 Designer/Runtime 读取。"""

        if not self.project_path:
            return {"images": [], "audios": [], "portraits": [], "voices": [], "videos": []}

        def _rel(path: Path) -> str:
            try:
                return path.relative_to(self.project_path).as_posix()
            except Exception:
                return path.as_posix()

        images: List[str] = []
        for folder in [self.backgrounds_dir, self.cg_dir]:
            if not folder:
                continue
            for pattern in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
                images.extend([_rel(p) for p in folder.glob(pattern)])

        portraits = []
        if self.portraits_dir:
            portraits = [_rel(p) for p in self.portraits_dir.glob("*.png")]

        voices = []
        if self.voice_dir:
            voices = [_rel(p) for p in self.voice_dir.glob("**/*.mp3")]

        audios = []
        if self.bgm_dir:
            audios = [_rel(p) for p in self.bgm_dir.glob("*.mp3")]

        return {
            "images": images,
            "audios": audios,
            "portraits": portraits,
            "voices": voices,
            "videos": [],
        }

    def _assign_voice_from_files(self):
        """为节点按角色顺序分配语音文件，避免路径不匹配。"""

        if not self.voice_dir or not self.flow_nodes:
            return

        # 为每个角色预取文件列表
        voice_pool: Dict[str, List[Path]] = {}
        for speaker_dir in self.voice_dir.iterdir():
            if speaker_dir.is_dir():
                files = sorted(speaker_dir.glob("*.mp3"))
                if files:
                    voice_pool[speaker_dir.name] = files

        usage_counter: Dict[str, int] = {k: 0 for k in voice_pool}

        for node in self.flow_nodes:
            speaker = node.speaker or ""
            if not speaker or speaker not in voice_pool:
                continue

            # 如果已有路径且文件存在则保留
            if node.voice:
                full = (self.project_path / node.voice) if self.project_path else None
                if full and full.exists():
                    continue

            idx = usage_counter[speaker]
            files = voice_pool[speaker]
            if idx >= len(files):
                idx = len(files) - 1
            chosen = files[idx]
            usage_counter[speaker] += 1
            rel = chosen.relative_to(self.project_path) if self.project_path else chosen
            node.voice = rel.as_posix()
    
    def integrate_all(
        self,
        user_config: UserConfig,
        plot_file: str,
        portraits_dir: Optional[str] = None,
        backgrounds_dir: Optional[str] = None,
        voice_dir: Optional[str] = None,
        bgm_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        一键整合所有资源
        
        Args:
            user_config: 用户配置
            plot_file: 剧情文件路径
            portraits_dir: 立绘目录
            backgrounds_dir: 背景目录
            voice_dir: 语音目录
            bgm_dir: BGM目录
        
        Returns:
            整合结果
        """
        self.logger.info("=" * 80)
        self.logger.info("开始一键整合")
        self.logger.info("=" * 80)
        
        # 创建工程（尊重用户指定的工程路径）
        project_name = user_config.project_info.project_name
        self.create_project(project_name, project_path=user_config.project_info.project_path)
        
        # 整合剧情
        node_count = self.integrate_plot(plot_file)
        
        # 整合素材
        if portraits_dir:
            char_mapping = {
                char.char_name: char.char_name
                for char in user_config.character_config
            }
            self.integrate_portraits(portraits_dir, char_mapping)
        
        if backgrounds_dir:
            self.integrate_backgrounds(backgrounds_dir)
        
        if voice_dir:
            self.integrate_voice(voice_dir)
        
        if bgm_dir:
            self.integrate_bgm(bgm_dir)
        
        # 生成工程文件
        project_file = self.generate_project_file(user_config)

        missing = self._validate_node_resources()
        for key, cnt in missing.items():
            if cnt:
                self.logger.warning(f"资源缺失: {key} -> {cnt} 个节点引用不存在的文件")
        
        result = {
            "project_path": str(self.project_path),
            "project_file": project_file,
            "node_count": node_count,
            "connection_count": len(self.connections),
            "success": True
        }
        
        self.logger.info("=" * 80)
        self.logger.info("整合完成")
        self.logger.info(f"  工程路径: {self.project_path}")
        self.logger.info(f"  节点数: {node_count}")
        self.logger.info(f"  连接数: {len(self.connections)}")
        self.logger.info("=" * 80)
        
        return result
    
    def get_statistics(self) -> Dict[str, int]:
        """
        获取整合统计信息
        
        Returns:
            统计信息
        """
        return {
            "node_count": len(self.flow_nodes),
            "connection_count": len(self.connections),
            "portrait_count": len(list(self.portraits_dir.glob("*.png"))) if self.portraits_dir else 0,
            "background_count": len(list(self.backgrounds_dir.glob("*.png"))) if self.backgrounds_dir else 0,
            "voice_count": len(list(self.voice_dir.glob("**/*.mp3"))) if self.voice_dir else 0,
            "bgm_count": len(list(self.bgm_dir.glob("*.mp3"))) if self.bgm_dir else 0
        }

    def integrate_from_data(
        self,
        user_config: UserConfig,
        flow_nodes: List[FlowNodeData],
        connections: List[ConnectionData],
        global_variables: Optional[List[GlobalVariable]] = None,
        material_requirements: Optional[List[MaterialRequirement]] = None,
        resources_dir: Optional[str] = None
    ) -> str:
        """基于现有数据直接生成.vngproj（无需中间复制）。"""

        self.project_name = user_config.project_info.project_name
        self.project_path = Path(user_config.project_info.project_path).expanduser().resolve()
        self.resources_dir = Path(resources_dir) if resources_dir else self.project_path / "resources"
        self.resources_dir.mkdir(parents=True, exist_ok=True)
        self.portraits_dir = self.resources_dir / "portraits"
        self.backgrounds_dir = self.resources_dir / "backgrounds"
        self.cg_dir = self.resources_dir / "cg"
        self.voice_dir = self.resources_dir / "voices"
        self.bgm_dir = self.resources_dir / "bgm"

        # 记录数据
        self.flow_nodes = flow_nodes
        self.connections = connections
        self.global_vars = global_variables or []
        self.material_reqs = material_requirements or []

        # 若存在语音文件，尝试根据文件填充节点引用
        self._assign_voice_from_files()

        # 预置常见资源子目录
        for sub in ["portraits", "backgrounds", "cg", "voices", "bgm", "plot"]:
            (self.resources_dir / sub).mkdir(parents=True, exist_ok=True)

        return self.generate_project_file(user_config)
