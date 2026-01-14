# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - BGM生成Agent
基于剧情氛围生成背景音乐
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
from src.multi_agent.core.agent_base import BaseAgent
from src.multi_agent.core.data_models import (
    TaskResultSchema, ScriptNodeSchema, ResourceMetaSchema
)
from src.multi_agent.api_clients.music_client import (
    MusicGenClient, MUSIC_STYLES, MOOD_MAPPING, TEMPO_MAPPING
)
from src.multi_agent.utils.logger import LoggerFactory
from src.multi_agent.utils.resource_processor import AudioProcessor
from datetime import datetime


class BGMAgent(BaseAgent):
    """
    BGM生成Agent
    根据剧情氛围生成背景音乐
    """
    
    def __init__(
        self,
        agent_id: str = "bgm_001",
        agent_name: str = "BGM生成Agent",
        music_provider: str = "suno",
        api_key: str = "",
        user_id: str = "default_user",
        base_url: str = None
    ):
        """
        初始化BGM Agent
        
        Args:
            agent_id: Agent唯一标识
            agent_name: Agent名称
            music_provider: 音乐生成服务提供商
            api_key: API密钥（Suno代理的x-token）
            user_id: 用户ID（Suno代理的x-userId）
            base_url: 自定义API地址
        """
        super().__init__(agent_id, agent_name)
        
        # 设置日志工具
        self.logger = LoggerFactory.get_logger(agent_name)
        
        # 初始化音乐生成客户端
        self.music_client = None
        if api_key:
            self.music_client = MusicGenClient(
                provider=music_provider,
                api_key=api_key,
                user_id=user_id,
                base_url=base_url,
                timeout=300
            )
    
    def run(self, task_params: Dict[str, Any]) -> TaskResultSchema:
        """
        执行BGM生成任务
        
        Args:
            task_params: 任务参数
                - script_nodes: 剧本节点列表
                - project_root: 工程根目录
                - bgm_duration: BGM时长（可选，默认60秒）
                - bgm_count: BGM数量（可选，自动识别）
                - convert_to_ogg: 是否转换为OGG格式（可选，默认True）
                
        Returns:
            TaskResultSchema: 生成的BGM资源元数据列表
        """
        self.logger.log_task_start("BGM生成", task_params)
        
        # 校验参数
        required_fields = ["script_nodes", "project_root"]
        is_valid, error_msg = self.validate_params(task_params, required_fields)
        if not is_valid:
            return self.create_error_result(error_msg)
        
        if not self.music_client:
            return self.create_error_result("音乐生成客户端未初始化，请检查API配置")
        
        try:
            script_nodes = [ScriptNodeSchema(**node) for node in task_params["script_nodes"]]
            project_root = task_params["project_root"]
            bgm_duration = task_params.get("bgm_duration", 60)
            convert_to_ogg = task_params.get("convert_to_ogg", True)
            
            # 创建资源目录
            bgm_dir = Path(project_root) / "resources" / "audios" / "bgm"
            bgm_dir.mkdir(parents=True, exist_ok=True)
            
            # 分析剧情氛围，生成BGM需求
            bgm_requirements = self._analyze_atmosphere_requirements(
                script_nodes,
                task_params.get("bgm_count")
            )
            
            self.logger.info(f"识别到{len(bgm_requirements)}种不同氛围需要生成BGM")
            
            all_resources = []
            
            for idx, req in enumerate(bgm_requirements):
                self.report_progress(
                    idx / len(bgm_requirements),
                    f"生成BGM：{req['atmosphere']}"
                )
                
                bgm_path, bgm_resource = self._generate_bgm(
                    atmosphere=req["atmosphere"],
                    scene_descriptions=req["scenes"],
                    related_node_ids=req["node_ids"],
                    output_dir=bgm_dir,
                    duration=bgm_duration,
                    convert_to_ogg=convert_to_ogg,
                    bgm_index=idx
                )
                
                if bgm_path:
                    all_resources.append(bgm_resource)
            
            self.report_progress(1.0, "BGM生成完成")
            
            result_data = {
                "resources": [res.model_dump() for res in all_resources],
                "bgm_count": len(all_resources),
                "atmospheres": [req["atmosphere"] for req in bgm_requirements]
            }
            
            self.logger.log_task_end(
                "BGM生成",
                True,
                f"成功生成{len(all_resources)}首BGM"
            )
            
            return self.create_success_result(data=result_data, message="BGM生成成功")
        
        except Exception as e:
            return self.create_error_result("BGM生成失败", exception=e)
    
    def _analyze_atmosphere_requirements(
        self,
        script_nodes: List[ScriptNodeSchema],
        target_count: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        分析剧本氛围需求
        
        Args:
            script_nodes: 剧本节点列表
            target_count: 目标BGM数量（None则自动识别）
            
        Returns:
            List: BGM需求列表
        """
        # 统计不同氛围的场景
        atmosphere_map = {}
        
        for node in script_nodes:
            atmosphere = node.atmosphere or "平静"
            scene = node.scene_description or "默认场景"
            
            if atmosphere not in atmosphere_map:
                atmosphere_map[atmosphere] = {
                    "atmosphere": atmosphere,
                    "scenes": set(),
                    "node_ids": []
                }
            
            atmosphere_map[atmosphere]["scenes"].add(scene)
            atmosphere_map[atmosphere]["node_ids"].append(node.node_id)
        
        # 转换为列表
        requirements = []
        for atm_data in atmosphere_map.values():
            requirements.append({
                "atmosphere": atm_data["atmosphere"],
                "scenes": list(atm_data["scenes"]),
                "node_ids": atm_data["node_ids"]
            })
        
        # 如果指定了数量，按使用频次排序取前N个
        if target_count and len(requirements) > target_count:
            requirements.sort(
                key=lambda x: len(x["node_ids"]),
                reverse=True
            )
            requirements = requirements[:target_count]
        
        self.logger.info(f"氛围分析完成：{[r['atmosphere'] for r in requirements]}")
        return requirements
    
    def _generate_bgm(
        self,
        atmosphere: str,
        scene_descriptions: List[str],
        related_node_ids: List[str],
        output_dir: Path,
        duration: int,
        convert_to_ogg: bool,
        bgm_index: int
    ) -> tuple[Optional[str], Optional[ResourceMetaSchema]]:
        """
        生成单首BGM
        
        Args:
            atmosphere: 氛围标签
            scene_descriptions: 场景描述列表
            related_node_ids: 关联节点ID列表
            output_dir: 输出目录
            duration: BGM时长
            convert_to_ogg: 是否转换为OGG
            bgm_index: BGM索引
            
        Returns:
            tuple: (BGM路径, 资源元数据)
        """
        try:
            # 构建音乐生成提示词
            prompt = self._build_bgm_prompt(atmosphere, scene_descriptions)
            
            # 确定音乐风格和情绪
            style = self._determine_music_style(atmosphere)
            mood = MOOD_MAPPING.get(atmosphere, "calm")
            tempo = self._determine_tempo(atmosphere)
            
            self.logger.info(
                f"生成BGM - 氛围：{atmosphere}, 风格：{style}, "
                f"情绪：{mood}, 节奏：{tempo}"
            )
            self.logger.info(f"Prompt: {prompt}")
            
            # 生成临时MP3文件
            temp_mp3 = output_dir / f"bgm_{bgm_index+1:03d}_temp.mp3"
            
            # 调用音乐生成
            result_path = self.music_client.generate_music(
                prompt=prompt,
                duration=duration,
                style=style,
                mood=mood,
                tempo=tempo,
                instrumental=True,
                output_path=str(temp_mp3)
            )
            
            if not result_path:
                raise Exception("音乐生成失败")
            
            # 转换为OGG格式
            final_path = temp_mp3
            if convert_to_ogg:
                ogg_path = output_dir / f"bgm_{atmosphere}_{bgm_index+1:03d}.ogg"
                try:
                    AudioProcessor.convert_wav_to_ogg(
                        str(temp_mp3),
                        str(ogg_path),
                        bitrate="192k"  # BGM使用更高码率
                    )
                    final_path = ogg_path
                    # 删除临时MP3
                    temp_mp3.unlink()
                except Exception as e:
                    self.logger.warning(f"OGG转换失败，保留MP3格式: {str(e)}")
                    final_path = output_dir / f"bgm_{atmosphere}_{bgm_index+1:03d}.mp3"
                    temp_mp3.rename(final_path)
            else:
                final_path = output_dir / f"bgm_{atmosphere}_{bgm_index+1:03d}.mp3"
                temp_mp3.rename(final_path)
            
            # 创建资源元数据
            resource = ResourceMetaSchema(
                res_id=f"bgm_{bgm_index+1:03d}",
                res_type="bgm",
                path=f"resources/audios/bgm/{final_path.name}",
                name=f"BGM_{atmosphere}",
                related_node_id=related_node_ids[0] if related_node_ids else None,
                prompt=prompt,
                model_name="music_ai",
                generated_at=datetime.now()
            )
            
            self.logger.info(f"BGM已保存：{final_path}")
            return str(final_path), resource
        
        except Exception as e:
            self.logger.error(f"BGM生成失败：{str(e)}")
            return None, None
    
    def _build_bgm_prompt(
        self,
        atmosphere: str,
        scene_descriptions: List[str]
    ) -> str:
        """
        构建BGM生成提示词
        
        Args:
            atmosphere: 氛围
            scene_descriptions: 场景描述
            
        Returns:
            str: 提示词
        """
        # 基础描述
        base = f"{atmosphere}的氛围背景音乐"
        
        # 添加场景元素（取前3个场景）
        if scene_descriptions:
            scenes = ", ".join(scene_descriptions[:3])
            return f"{base}, 适合{scenes}等场景"
        
        return base
    
    def _determine_music_style(self, atmosphere: str) -> str:
        """根据氛围确定音乐风格"""
        style_map = {
            "平静": "ambient",
            "紧张": "electronic",
            "激动": "orchestral",
            "悲伤": "piano",
            "欢乐": "pop",
            "神秘": "ambient",
            "浪漫": "piano",
            "战斗": "rock",
            "温馨": "folk",
            "恐怖": "cinematic"
        }
        return style_map.get(atmosphere, "ambient")
    
    def _determine_tempo(self, atmosphere: str) -> str:
        """根据氛围确定节奏"""
        tempo_map = {
            "平静": "slow",
            "紧张": "fast",
            "激动": "fast",
            "悲伤": "slow",
            "欢乐": "medium",
            "神秘": "slow",
            "浪漫": "slow",
            "战斗": "fast",
            "温馨": "medium",
            "恐怖": "medium"
        }
        return tempo_map.get(atmosphere, "medium")
    
    def close(self):
        """关闭资源"""
        if self.music_client:
            self.music_client.close()
