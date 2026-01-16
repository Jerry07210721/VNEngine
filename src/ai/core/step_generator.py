# -*- coding: utf-8 -*-
"""
分步生成管理器
负责管理AI辅助工程的分步生成流程
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import json
import re

from ..log.logger import get_logger
from .config_manager import ConfigManager
from ..api.api_manager import APIManager
from ..agents.plot_agent import PlotAgent
from .models import (
    PendingLists,
    PortraitPendingItem,
    BackgroundPendingItem,
    CGPendingItem,
    VoicePendingItem,
    BGMPendingItem,
    FlowNodeData,
    ConnectionData,
    GlobalVariable,
)


class StepGenerator:
    """分步生成管理器"""
    
    def __init__(
        self,
        config_manager: ConfigManager,
        api_manager: Optional[APIManager] = None
    ):
        """
        初始化分步生成管理器
        
        Args:
            config_manager: 配置管理器
            api_manager: API管理器（可选）
        """
        self.config_manager = config_manager
        self.api_manager = api_manager or APIManager(config_manager)
        self.logger = get_logger("StepGenerator")
        
        # 初始化剧情Agent
        self.plot_agent = PlotAgent(config_manager, self.api_manager)
        
        self.logger.info("StepGenerator初始化完成")

    # ==================== 通用辅助 ====================

    def _extract_text(self, response: Dict[str, Any]) -> str:
        """从LLM响应中提取纯文本。"""
        content = response.get("content", "")
        if isinstance(content, list):
            return "".join(block.get("text", "") for block in content if isinstance(block, dict))
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)

    def _try_parse_json(self, text: str) -> Optional[Any]:
        """尝试解析JSON或代码块中的JSON，失败则返回None。"""
        if not text:
            return None
        candidate = text.strip()
        try:
            if "```json" in candidate:
                candidate = candidate.split("```json", 1)[1].split("```", 1)[0].strip()
            elif candidate.startswith("```"):
                candidate = candidate.split("```", 1)[1].split("```", 1)[0].strip()
            return json.loads(candidate)
        except Exception:
            return None

    def _call_llm(self, instruction: str, system: str, *, max_tokens: int, temperature: float) -> Tuple[str, Optional[Any]]:
        """统一的LLM调用，返回文本与解析后的结构化数据。"""
        response = self.plot_agent.llm_client.create_message(
            messages=[{"role": "user", "content": instruction}],
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = self._extract_text(response)
        structured = self._try_parse_json(text)
        return text, structured
    
    # ==================== 步骤1：生成角色人设 ====================
    
    def prepare_personas_instruction(
        self,
        story_config: Dict[str, Any],
        character_config: List[Dict[str, Any]]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        准备生成角色人设的指令
        
        Args:
            story_config: 剧情配置
            character_config: 角色配置列表
        
        Returns:
            (指令文本, 参数字典)
        """
        self.logger.info("准备角色人设生成指令")
        
        # 构建指令
        instruction = f"""请根据以下信息，为每个角色生成详细的人设：

故事风格：{story_config.get('style', '未指定')}
剧情概要：{story_config.get('plot_outline', '未指定')}

角色列表：
"""
        
        for i, char in enumerate(character_config, 1):
            instruction += f"\n{i}. {char['char_name']} ({char['char_id']})"
            instruction += f"\n   - 角色定位：{char.get('role', '未指定')}"
            instruction += f"\n   - 人设关键词：{char.get('persona_keywords', '未指定')}"
            if char.get('is_player'):
                instruction += f"\n   - 特殊标识：玩家角色（第一视角）"
        
        instruction += f"""

请为每个角色生成：
1. 详细的性格描述（200-300字）
2. 外貌特征描述（100-150字）
3. 背景故事（150-200字）
4. 语言风格特点
5. 与其他角色的关系

要求：
- 人设需要符合故事风格和剧情
- 角色之间要有明确的关系和互动
- 第一视角角色的人设要符合玩家代入感
- 人设权重：{story_config.get('character_hint_weight', 0.7)}（越接近1.0越严格遵循用户提供的关键词）
"""
        
        # 参数
        parameters = {
            "story_style": story_config.get('style', ''),
            "plot_outline": story_config.get('plot_outline', ''),
            "character_count": len(character_config),
            "character_ids": [c['char_id'] for c in character_config],
            "hint_weight": story_config.get('character_hint_weight', 0.7)
        }
        
        return instruction, parameters
    
    def generate_personas(
        self,
        instruction: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成角色人设
        
        Args:
            instruction: 指令文本
            parameters: 参数字典
        
        Returns:
            生成的角色人设数据
        """
        self.logger.info("开始生成角色人设")
        
        try:
            text, structured = self._call_llm(
                instruction,
                system="你是资深的视觉小说角色设定专家，擅长给出结构化、可落地的人设。",
                max_tokens=8000,
                temperature=0.7,
            )

            personas = {
                "raw_response": text,
                "structured": structured,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "parameters": parameters,
            }
            
            self.logger.info("角色人设生成完成")
            return personas
            
        except Exception as e:
            self.logger.error(f"生成角色人设失败: {e}")
            raise
    
    # ==================== 步骤2：生成故事大纲 ====================
    
    def prepare_outline_instruction(
        self,
        story_config: Dict[str, Any],
        personas: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        准备生成故事大纲的指令
        
        Args:
            story_config: 剧情配置
            personas: 角色人设数据
        
        Returns:
            (指令文本, 参数字典)
        """
        self.logger.info("准备故事大纲生成指令")
        
        instruction = f"""请根据以下信息，生成故事大纲：

故事标题：{story_config.get('title', '未命名')}
故事风格：{story_config.get('style', '')}
剧情概要：{story_config.get('plot_outline', '')}
目标文本量：{story_config.get('text_volume', 5000)}字
章节数量：约{story_config.get('chapter_count', 5)}章

角色人设：
{personas.get('raw_response', '（已生成）')[:500]}...

请生成：
1. 完整的故事大纲（包括开端、发展、高潮、结局）
2. 划分为{story_config.get('chapter_count', 5)}个章节
3. 每个章节的核心剧情（100-150字）
4. 关键剧情转折点
5. 角色成长弧线

要求：
- 大纲要完整连贯
- 符合故事风格
- 预留选择节点和条件节点的位置（如果启用）
"""
        
        parameters = {
            "chapter_count": story_config.get('chapter_count', 5),
            "text_volume": story_config.get('text_volume', 5000),
            "enable_choice": story_config.get('enable_choice_node', True),
            "enable_condition": story_config.get('enable_condition_node', True)
        }
        
        return instruction, parameters
    
    def generate_outline(
        self,
        instruction: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成故事大纲
        
        Args:
            instruction: 指令文本
            parameters: 参数字典
        
        Returns:
            生成的故事大纲数据
        """
        self.logger.info("开始生成故事大纲")
        
        try:
            text, structured = self._call_llm(
                instruction,
                system="你是专业的视觉小说主编，擅长输出清晰的章节大纲。",
                max_tokens=12000,
                temperature=0.7,
            )

            outline = {
                "raw_response": text,
                "structured": structured,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "parameters": parameters,
            }
            
            self.logger.info("故事大纲生成完成")
            return outline
            
        except Exception as e:
            self.logger.error(f"生成故事大纲失败: {e}")
            raise
    
    # ==================== 步骤3：生成章节列表 ====================
    
    def prepare_chapters_instruction(
        self,
        story_config: Dict[str, Any],
        outline: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        准备生成章节列表的指令
        
        Args:
            story_config: 剧情配置
            outline: 故事大纲数据
        
        Returns:
            (指令文本, 参数字典)
        """
        self.logger.info("准备章节列表生成指令")
        
        instruction = f"""请根据故事大纲，生成详细的章节列表：

故事大纲：
{outline.get('raw_response', '')}

要求：
1. 生成{story_config.get('chapter_count', 5)}个章节
2. 每个章节包含：
   - 章节标题
   - 章节摘要（150-200字）
   - 主要场景
   - 涉及角色
   - 预计字数

请以结构化JSON格式输出，便于后续处理。
"""
        
        parameters = {
            "chapter_count": story_config.get('chapter_count', 5)
        }
        
        return instruction, parameters
    
    def generate_chapters(
        self,
        instruction: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成章节列表
        
        Args:
            instruction: 指令文本
            parameters: 参数字典
        
        Returns:
            生成的章节列表数据
        """
        self.logger.info("开始生成章节列表")
        
        try:
            text, structured = self._call_llm(
                instruction,
                system="你是视觉小说剧本统筹，请输出可直接拆分的章节计划。",
                max_tokens=12000,
                temperature=0.7,
            )

            chapters = {
                "raw_response": text,
                "structured": structured,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "parameters": parameters,
            }
            
            self.logger.info("章节列表生成完成")
            return chapters
            
        except Exception as e:
            self.logger.error(f"生成章节列表失败: {e}")
            raise
    
    # ==================== 步骤4：生成章节详细内容 ====================
    
    def prepare_chapter_detail_instruction(
        self,
        chapter_index: int,
        chapter_info: Dict[str, Any],
        previous_context: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        准备生成单个章节详细内容的指令
        
        Args:
            chapter_index: 章节索引（从0开始）
            chapter_info: 章节信息
            previous_context: 上一章的上下文（可选）
        
        Returns:
            (指令文本, 参数字典)
        """
        self.logger.info(f"准备第{chapter_index+1}章详细内容生成指令")
        
        instruction = f"""请生成第{chapter_index+1}章的详细内容：

章节信息：
{json.dumps(chapter_info, ensure_ascii=False, indent=2)}

{"上一章结尾：" + previous_context if previous_context else ""}

要求：
1. 生成完整的对白和场景描述
2. 保持角色人设一致
3. 符合章节摘要
4. 标注所需的立绘、背景、BGM等资源
"""
        
        parameters = {
            "chapter_index": chapter_index,
            "chapter_title": chapter_info.get('title', f'第{chapter_index+1}章')
        }
        
        return instruction, parameters
    
    def generate_chapter_detail(
        self,
        instruction: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成单个章节的详细内容
        
        Args:
            instruction: 指令文本
            parameters: 参数字典
        
        Returns:
            生成的章节详细内容
        """
        chapter_index = parameters.get('chapter_index', 0)
        self.logger.info(f"开始生成第{chapter_index+1}章详细内容")
        
        try:
            text, structured = self._call_llm(
                instruction,
                system="你是GalGame剧本作者，请输出包含对白与资源标注的章节文本。",
                max_tokens=16000,
                temperature=0.7,
            )

            detail = {
                "chapter_index": chapter_index,
                "raw_response": text,
                "structured": structured,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "parameters": parameters,
            }
            
            self.logger.info(f"第{chapter_index+1}章详细内容生成完成")
            return detail
            
        except Exception as e:
            self.logger.error(f"生成第{chapter_index+1}章详细内容失败: {e}")
            raise

    def _normalize_chapter_detail(self, chapter: Any) -> Dict[str, Any]:
        """防止章节详情被重复json序列化，尽量还原为标准dict。"""

        def _try_json(text: Any):
            if not isinstance(text, str):
                return None
            try:
                return json.loads(text)
            except Exception:
                return None

        if chapter is None:
            return {}

        if isinstance(chapter, str):
            parsed = _try_json(chapter)
            if isinstance(parsed, dict):
                chapter = parsed
            else:
                return {"raw_response": chapter}

        if isinstance(chapter, dict):
            normalized = dict(chapter)

            raw_text = normalized.get("raw_response")
            parsed_raw = _try_json(raw_text) if isinstance(raw_text, str) else None
            if isinstance(parsed_raw, dict):
                # 如果raw_response里又包了一层detail/structured，展开合并，同时保留原始文本
                normalized["raw_response"] = raw_text
                normalized.update(parsed_raw)

            structured = normalized.get("structured")
            parsed_struct = _try_json(structured) if isinstance(structured, str) else None
            if parsed_struct is not None:
                normalized["structured"] = parsed_struct

            # 如果structured缺失，尝试从raw_response里提取简单对话，避免语音统计为0
            if not normalized.get("structured") and isinstance(raw_text, str):
                dialogues = []
                patterns = [
                    # **角色名**（可选舞台说明）：对白
                    re.compile(r"^\*\*(?P<speaker>[^*]+?)\*\*\s*(?:（[^）]*）|\([^)]*\))?\s*[：:]\s*[\"“]?(?P<text>.+?)[\"”]?\s*$"),
                    # 角色名（可选舞台说明）：对白（无加粗）
                    re.compile(r"^(?P<speaker>[^：:\s【][^：:]*?)\s*(?:（[^）]*）|\([^)]*\))?\s*[：:]\s*[\"“]?(?P<text>.+?)[\"”]?\s*$"),
                ]
                for line in raw_text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    match = None
                    for pat in patterns:
                        match = pat.match(line)
                        if match:
                            break
                    if not match:
                        continue
                    speaker = (match.group("speaker") or "").strip()
                    text = (match.group("text") or "").strip()
                    if speaker and text:
                        dialogues.append({"speaker": speaker, "text": text})
                if dialogues:
                    normalized["structured"] = {"dialogues": dialogues}

            return normalized

        return {"raw_response": str(chapter)}

    # ==================== 步骤5：生成待生成列表 & 流程骨架 ====================

    def build_pending_and_flow(
        self,
        story_config: Dict[str, Any],
        characters: List[Dict[str, Any]],
        chapter_details: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        根据章节详情生成待生成列表（立绘/背景/CG/语音/BGM）与基础流程节点骨架。

        返回：{
          "pending_lists": PendingLists,
          "flow_nodes": List[FlowNodeData],
          "connections": List[ConnectionData],
          "global_variables": List[GlobalVariable],
          "summary": {...}
        }
        """

        self.logger.info("生成待生成列表与流程骨架")

        normalized_chapters = [self._normalize_chapter_detail(ch) for ch in (chapter_details or [])]

        # ---------- 立绘 ----------
        portrait_items: List[PortraitPendingItem] = []
        default_expressions = ["neutral", "happy", "sad", "angry", "surprised"]
        for char in characters:
            char_id = char.get("char_id") or char.get("id") or "char"
            char_name = char.get("char_name") or char.get("name") or char_id
            portrait_items.append(
                PortraitPendingItem(
                    item_id=f"portrait_{char_id}",
                    char_id=char_id,
                    char_name=char_name,
                    description=char.get("persona_keywords", ""),
                    expressions=default_expressions,
                    poses=["stand"],
                    status="pending",
                    file_paths=[f"resources/portraits/{char_id}_{exp}.png" for exp in default_expressions],
                )
            )

        # ---------- 背景 ----------
        background_items: List[BackgroundPendingItem] = []
        for idx, chapter in enumerate(normalized_chapters):
            desc = ""
            structured = chapter.get("structured") if isinstance(chapter, dict) else None
            if structured and isinstance(structured, dict):
                desc = structured.get("summary") or structured.get("chapter_summary") or ""
            if not desc and isinstance(chapter, dict):
                desc = chapter.get("raw_response", "")[:120]
            bg_id = f"bg_{idx+1:03d}"
            background_items.append(
                BackgroundPendingItem(
                    item_id=f"background_{idx+1:03d}",
                    bg_id=bg_id,
                    description=desc or f"第{idx+1}章背景",
                    atmosphere=story_config.get("style", ""),
                    time_weather="",
                    status="pending",
                    file_path=f"resources/backgrounds/{bg_id}.png",
                )
            )

        # ---------- BGM ----------
        bgm_items: List[BGMPendingItem] = []
        for idx, chapter in enumerate(normalized_chapters):
            desc = ""
            structured = chapter.get("structured") if isinstance(chapter, dict) else None
            if structured and isinstance(structured, dict):
                desc = structured.get("emotional_tone") or structured.get("summary") or ""
            if not desc and isinstance(chapter, dict):
                desc = chapter.get("raw_response", "")[:80]
            bgm_id = f"bgm_{idx+1:02d}"
            bgm_items.append(
                BGMPendingItem(
                    item_id=f"bgm_item_{idx+1:02d}",
                    bgm_id=bgm_id,
                    description=desc or f"第{idx+1}章BGM",
                    mood=desc,
                    style=story_config.get("style", ""),
                    duration=120,
                    loop=True,
                    status="pending",
                    file_path=f"resources/bgm/{bgm_id}.mp3",
                )
            )

        # ---------- CG（此阶段仅占位，待用户后续补充） ----------
        cg_items: List[CGPendingItem] = []

        # ---------- 语音 ----------
        voice_items: List[VoicePendingItem] = []
        char_map = {c.get("char_name") or c.get("name"): c for c in characters}
        for chap_idx, chapter in enumerate(normalized_chapters):
            structured = chapter.get("structured") if isinstance(chapter, dict) else None
            dialogues = []
            if structured:
                # 兼容多种字段名
                if isinstance(structured, dict):
                    dialogues = structured.get("dialogues") or structured.get("dialogue") or []
                elif isinstance(structured, list):
                    dialogues = structured
            for dlg_idx, dlg in enumerate(dialogues):
                if not isinstance(dlg, dict):
                    continue
                speaker = dlg.get("speaker") or dlg.get("role") or ""
                content = dlg.get("text") or dlg.get("content") or ""
                emotion = dlg.get("emotion") or dlg.get("tone") or "平静"
                char_id = "unknown"
                for name, cfg in char_map.items():
                    if name and name == speaker:
                        char_id = cfg.get("char_id") or cfg.get("id") or "unknown"
                        break
                voice_id = f"voice_{chap_idx+1:02d}_{dlg_idx+1:03d}"
                voice_items.append(
                    VoicePendingItem(
                        item_id=f"voice_item_{chap_idx+1:02d}_{dlg_idx+1:03d}",
                        voice_id=voice_id,
                        node_id=str(chap_idx + 1),
                        sub_id=dlg_idx,
                        speaker=speaker,
                        char_id=char_id,
                        text=content,
                        emotion=emotion,
                        voice_model_id=None,
                        status="pending",
                        file_path=f"resources/voices/{char_id}/{voice_id}.mp3",
                    )
                )

        pending_lists = PendingLists(
            portraits=portrait_items,
            backgrounds=background_items,
            cgs=cg_items,
            voices=voice_items,
            bgms=bgm_items,
        )

        # ---------- 流程骨架 ----------
        flow_nodes: List[FlowNodeData] = []
        connections: List[ConnectionData] = []
        node_id = 1
        for idx, chapter in enumerate(normalized_chapters):
            title = f"第{idx+1}章"
            structured = chapter.get("structured") if isinstance(chapter, dict) else None
            if structured and isinstance(structured, dict):
                title = structured.get("chapter_title") or structured.get("title") or title
            content = ""
            if structured and isinstance(structured, dict):
                content = structured.get("summary") or structured.get("chapter_summary") or ""
            if not content and isinstance(chapter, dict):
                content = chapter.get("raw_response", "")[:400]

            bg_path = background_items[idx].file_path if idx < len(background_items) else ""
            bgm_path = bgm_items[idx].file_path if idx < len(bgm_items) else ""

            node = FlowNodeData(
                id=node_id,
                node_type="text",
                title=title,
                content=content,
                speaker="",
                portrait="",
                background=bg_path,
                voice="",
                bgm=bgm_path,
                bgm_loop=True,
                stop_bgm=False,
                bg_fade_in=False,
                portrait_fade=False,
                portrait_fade_out=False,
                hide_textbox=False,
                ui_file="",
                video="",
                video_loop=False,
                options=[],
                condition_var="",
                condition_op="==",
                condition_value="",
                condition_const=False,
                sub_dialogues=[],
                var_ops=[],
                x=120 * (idx % 5),
                y=140 * (idx // 5),
            )
            flow_nodes.append(node)
            if node_id > 1:
                connections.append(ConnectionData(source=node_id - 1, target=node_id))
            node_id += 1

        summary = {
            "portraits": len(portrait_items),
            "backgrounds": len(background_items),
            "cgs": len(cg_items),
            "voices": len(voice_items),
            "bgms": len(bgm_items),
            "nodes": len(flow_nodes),
        }

        return {
            "pending_lists": pending_lists,
            "flow_nodes": flow_nodes,
            "connections": connections,
            "global_variables": [],
            "summary": summary,
        }
