# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - 角色配音生成Agent
基于剧本对白和角色设定生成语音文件
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
from src.multi_agent.core.agent_base import BaseAgent
from src.multi_agent.core.data_models import (
    TaskResultSchema, ScriptNodeSchema, CharacterSchema, ResourceMetaSchema
)
from src.multi_agent.api_clients.tts_client import TTSClient, COMMON_VOICES, EMOTION_STYLES
from src.multi_agent.api_clients.gpt_sovits_client import GPTSoVITSClient, BertVITS2Client, EMOTION_MAPPING
from src.multi_agent.utils.logger import LoggerFactory
from src.multi_agent.utils.resource_processor import AudioProcessor
from datetime import datetime


class VoiceActingAgent(BaseAgent):
    """
    角色配音生成Agent
    根据剧本对白和角色声线设定生成语音文件
    """
    
    def __init__(
        self,
        agent_id: str = "voice_001",
        agent_name: str = "角色配音Agent",
        tts_provider: str = "gpt_sovits",
        api_key: str = "",
        region: str = "eastus",
        base_url: str = None
    ):
        """
        初始化配音Agent
        
        Args:
            agent_id: Agent唯一标识
            agent_name: Agent名称
            tts_provider: TTS服务提供商（gpt_sovits/bert_vits2/azure/openai/aliyun）
            api_key: TTS API密钥
            region: 服务区域（Azure需要）
            base_url: 自定义API地址
        """
        super().__init__(agent_id, agent_name)
        
        # 设置日志工具
        self.logger = LoggerFactory.get_logger(agent_name)
        
        # 初始化TTS客户端
        self.tts_client = None
        self.tts_provider = tts_provider
        
        if api_key or tts_provider in ["gpt_sovits", "bert_vits2"]:
            if tts_provider == "gpt_sovits":
                self.tts_client = GPTSoVITSClient(
                    api_key=api_key,
                    base_url=base_url or "http://127.0.0.1:9880",
                    timeout=120
                )
            elif tts_provider == "bert_vits2":
                self.tts_client = BertVITS2Client(
                    api_key=api_key,
                    base_url=base_url or "http://127.0.0.1:5000",
                    timeout=120
                )
            else:
                self.tts_client = TTSClient(
                    provider=tts_provider,
                    api_key=api_key,
                    region=region,
                    base_url=base_url,
                    timeout=90
                )
    
    def run(self, task_params: Dict[str, Any]) -> TaskResultSchema:
        """
        执行配音生成任务
        
        Args:
            task_params: 任务参数
                - script_nodes: 剧本节点列表
                - characters: 角色列表
                - project_root: 工程根目录
                - voice_mapping: 角色ID到语音名称的映射（可选）
                - convert_to_ogg: 是否转换为OGG格式（可选，默认True）
                
        Returns:
            TaskResultSchema: 生成的语音资源元数据列表
        """
        self.logger.log_task_start("角色配音生成", task_params)
        
        # 校验参数
        required_fields = ["script_nodes", "characters", "project_root"]
        is_valid, error_msg = self.validate_params(task_params, required_fields)
        if not is_valid:
            return self.create_error_result(error_msg)
        
        if not self.tts_client:
            return self.create_error_result("TTS客户端未初始化，请检查API配置")
        
        try:
            script_nodes = [ScriptNodeSchema(**node) for node in task_params["script_nodes"]]
            characters = [CharacterSchema(**char) for char in task_params["characters"]]
            project_root = task_params["project_root"]
            voice_mapping = task_params.get("voice_mapping", {})
            convert_to_ogg = task_params.get("convert_to_ogg", True)
            
            # 创建资源目录
            voices_dir = Path(project_root) / "resources" / "audios" / "voices"
            voices_dir.mkdir(parents=True, exist_ok=True)
            
            # 如果没有提供语音映射，自动生成
            if not voice_mapping:
                voice_mapping = self._auto_generate_voice_mapping(characters)
            
            # 提取需要配音的对白节点
            dialogue_nodes = self._extract_dialogue_nodes(script_nodes)
            
            self.logger.info(f"共提取到{len(dialogue_nodes)}条对白需要配音")
            
            all_resources = []
            
            for idx, node in enumerate(dialogue_nodes):
                self.report_progress(
                    idx / len(dialogue_nodes),
                    f"生成配音：{node.content[:20]}..."
                )
                
                voice_path, voice_resource = self._generate_voice(
                    node=node,
                    characters=characters,
                    voice_mapping=voice_mapping,
                    output_dir=voices_dir,
                    convert_to_ogg=convert_to_ogg,
                    voice_index=idx
                )
                
                if voice_path:
                    all_resources.append(voice_resource)
            
            self.report_progress(1.0, "配音生成完成")
            
            result_data = {
                "resources": [res.model_dump() for res in all_resources],
                "voice_count": len(all_resources),
                "dialogue_nodes": [node.node_id for node in dialogue_nodes]
            }
            
            self.logger.log_task_end(
                "角色配音生成",
                True,
                f"成功生成{len(all_resources)}条语音"
            )
            
            return self.create_success_result(data=result_data, message="配音生成成功")
        
        except Exception as e:
            return self.create_error_result("配音生成失败", exception=e)
    
    def _auto_generate_voice_mapping(
        self,
        characters: List[CharacterSchema]
    ) -> Dict[str, str]:
        """
        自动生成角色到语音的映射
        
        Args:
            characters: 角色列表
            
        Returns:
            Dict: {角色ID: 语音名称}
        """
        voice_mapping = {}
        voice_presets = COMMON_VOICES.get(self.tts_provider, {})
        
        for char in characters:
            # 根据角色性别和年龄选择语音
            gender = char.gender
            age = getattr(char, "age", None)
            
            if gender == "女":
                if age and age < 18:
                    voice_mapping[char.char_id] = voice_presets.get("child", "zh-CN-XiaochenNeural")
                elif age and age > 30:
                    voice_mapping[char.char_id] = voice_presets.get("female_mature", "zh-CN-XiaoyanNeural")
                else:
                    voice_mapping[char.char_id] = voice_presets.get("female_young", "zh-CN-XiaoxiaoNeural")
            else:  # 男性
                if age and age > 30:
                    voice_mapping[char.char_id] = voice_presets.get("male_mature", "zh-CN-YunyangNeural")
                else:
                    voice_mapping[char.char_id] = voice_presets.get("male_young", "zh-CN-YunxiNeural")
            
            # 如果有声线描述，记录到日志
            if hasattr(char, "voice_description"):
                self.logger.info(f"角色{char.name}声线描述：{char.voice_description}")
        
        return voice_mapping
    
    def _extract_dialogue_nodes(
        self,
        script_nodes: List[ScriptNodeSchema]
    ) -> List[ScriptNodeSchema]:
        """
        提取需要配音的对白节点
        
        Args:
            script_nodes: 剧本节点列表
            
        Returns:
            List: 对白节点列表
        """
        dialogue_nodes = []
        
        for node in script_nodes:
            # 只处理文本节点且有角色对白的节点
            if node.node_type == "text" and node.character and node.content:
                # 过滤掉旁白（character为空或"narrator"）
                if node.character != "narrator":
                    dialogue_nodes.append(node)
        
        return dialogue_nodes
    
    def _generate_voice(
        self,
        node: ScriptNodeSchema,
        characters: List[CharacterSchema],
        voice_mapping: Dict[str, str],
        output_dir: Path,
        convert_to_ogg: bool,
        voice_index: int
    ) -> tuple[Optional[str], Optional[ResourceMetaSchema]]:
        """
        生成单条语音
        
        Args:
            node: 剧本节点
            characters: 角色列表
            voice_mapping: 语音映射
            output_dir: 输出目录
            convert_to_ogg: 是否转换为OGG
            voice_index: 语音索引
            
        Returns:
            tuple: (语音路径, 资源元数据)
        """
        try:
            char_id = node.character
            text = node.content
            
            # 获取角色语音
            voice_name = voice_mapping.get(char_id, "zh-CN-XiaoxiaoNeural")
            
            # 获取情感风格
            emotion = node.atmosphere or "平静"
            style = EMOTION_STYLES.get(emotion, "calm")
            
            # 获取角色信息（用于日志）
            char_info = None
            for char in characters:
                if char.char_id == char_id:
                    char_info = char
                    break
            
            self.logger.info(
                f"生成语音 - 角色：{char_info.name if char_info else char_id}, "
                f"情感：{emotion}, 文本：{text[:30]}..."
            )
            
            # 生成临时MP3文件
            temp_mp3 = output_dir / f"voice_{voice_index+1:04d}_temp.mp3"
            
            # 调用TTS合成
            result_path = self.tts_client.synthesize(
                text=text,
                voice=voice_name,
                output_path=str(temp_mp3),
                rate="0%",
                pitch="0%",
                style=style if self.tts_provider == "azure" else None,
                style_degree=1.2
            )
            
            if not result_path:
                raise Exception("TTS合成失败")
            
            # 转换为OGG格式（VNEngine运行时支持）
            final_path = temp_mp3
            if convert_to_ogg:
                ogg_path = output_dir / f"voice_{char_id}_{voice_index+1:04d}.ogg"
                try:
                    AudioProcessor.convert_wav_to_ogg(
                        str(temp_mp3),
                        str(ogg_path),
                        bitrate="128k"
                    )
                    final_path = ogg_path
                    # 删除临时MP3
                    temp_mp3.unlink()
                except Exception as e:
                    self.logger.warning(f"OGG转换失败，保留MP3格式: {str(e)}")
                    final_path = output_dir / f"voice_{char_id}_{voice_index+1:04d}.mp3"
                    temp_mp3.rename(final_path)
            else:
                final_path = output_dir / f"voice_{char_id}_{voice_index+1:04d}.mp3"
                temp_mp3.rename(final_path)
            
            # 创建资源元数据
            resource = ResourceMetaSchema(
                res_id=f"voice_{char_id}_{voice_index+1:04d}",
                res_type="voice",
                path=f"resources/audios/voices/{final_path.name}",
                name=f"{char_info.name if char_info else char_id}_{text[:15]}",
                related_node_id=node.node_id,
                prompt=text,
                model_name=f"tts_{self.tts_provider}",
                generated_at=datetime.now()
            )
            
            self.logger.info(f"语音已保存：{final_path}")
            return str(final_path), resource
        
        except Exception as e:
            self.logger.error(f"语音生成失败：{str(e)}")
            return None, None
    
    def close(self):
        """关闭资源"""
        if self.tts_client:
            self.tts_client.close()
