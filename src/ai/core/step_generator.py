# -*- coding: utf-8 -*-
"""
分步生成管理器
负责管理AI辅助工程的分步生成流程
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
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
            pass

        # 兼容 LLM 在 JSON 前后加解释/提示等噪声：尽量截取最外层 {...} 或 [...] 再解析。
        def _try_span(open_ch: str, close_ch: str):
            if open_ch not in candidate or close_ch not in candidate:
                return None
            start = candidate.find(open_ch)
            end = candidate.rfind(close_ch)
            if start < 0 or end <= start:
                return None
            snippet = candidate[start : end + 1].strip()
            try:
                return json.loads(snippet)
            except Exception:
                return None

        return _try_span("{", "}") or _try_span("[", "]")

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
{personas.get('raw_response', '（已生成）')}

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
        previous_context: Optional[str] = None,
        story_config: Optional[Dict[str, Any]] = None,
        character_config: Optional[List[Dict[str, Any]]] = None,
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

        story_cfg = story_config or {}
        chars = character_config or []
        pov = (story_cfg.get("narrative_pov") or "third").strip().lower()
        fp_name = story_cfg.get("first_person_name") or "我"
        fp_has_portrait = bool(story_cfg.get("first_person_has_portrait", False))
        fp_has_voice = bool(story_cfg.get("first_person_has_voice", False))
        fp_cg_presence = bool(story_cfg.get("first_person_cg_presence", True))
        fp_cg_notes = story_cfg.get("first_person_cg_notes") or ""
        cg_count = int(story_cfg.get("cg_count") or 0)

        char_lines = []
        for c in chars:
            name = c.get("char_name") or c.get("name") or ""
            cid = c.get("char_id") or c.get("id") or ""
            role = c.get("role") or ""
            is_player = bool(c.get("is_player", False))
            is_fp = bool(c.get("is_first_person", False))
            tags = []
            if is_player:
                tags.append("玩家")
            if is_fp:
                tags.append("第一人称")
            tag_text = f" [{', '.join(tags)}]" if tags else ""
            if name or cid:
                char_lines.append(f"- {name} ({cid}) {role}{tag_text}".strip())
        char_block = "\n".join(char_lines) if char_lines else "(未提供角色列表)"

        # Step5 需要可稳定解析的结构化输出，以便按媒体状态变化切分/聚合文本节点。
        # 因此这里强制输出 JSON（建议包在 ```json 代码块中），并约定 scenes + directives。
        prev = f"上一章结尾：{previous_context}\n" if previous_context else ""
        pov_text = "第一人称" if pov == "first" else "第三人称"
        fp_rules = ""
        if pov == "first":
            fp_rules = f"""
POV 规则（必须遵守）：
- 叙述视角：{pov_text}
- 第一人称代称：{fp_name}
- 第一人称立绘：{'有' if fp_has_portrait else '无'}（无则该角色对白不要提供 portrait，且不要暗示需要生成立绘）
- 第一人称配音：{'有' if fp_has_voice else '无'}（无则该角色对白不要提供 voice，且不要暗示需要生成语音）
- 第一人称 CG 出镜：{'会' if fp_cg_presence else '不会'}；说明：{fp_cg_notes}
"""

        cg_rules = ""
        if cg_count > 0:
            cg_rules = f"""
CG 规则（必须遵守）：
- 本章目标 CG 数量：{cg_count}（请尽量使用恰好 {cg_count} 张不同的 CG）
- CG 标注方式：在 scene.directives.cg 填写 CG 的 id（例如 cg_{chapter_index+1:02d}_01、cg_{chapter_index+1:02d}_02 ...），不要写完整路径。
- 当进入/退出 CG 时必须新开一个 scene，并在 directives 中体现 cg/background 的切换：
    - 进入 CG：写 directives.cg
    - 退出 CG：写 directives.background（恢复到某个背景）
"""

        instruction = f"""你正在为 VNEngine 生成“逐章详稿”（将用于后续自动生成 flow_nodes 与 pending_lists）。

请严格输出 **仅一个 JSON 对象**（不要输出解释文字），建议放在 ```json 代码块中。

章节信息：
{json.dumps(chapter_info, ensure_ascii=False, indent=2)}

故事配置摘要：
- 故事风格：{story_cfg.get('style', '')}
- 启用选择节点：{bool(story_cfg.get('enable_choice_node', True))}
- 启用条件节点：{bool(story_cfg.get('enable_condition_node', True))}

角色列表：
{char_block}

{prev}
输出 JSON Schema（必须遵守字段名，未用字段可为空/省略）：
{{
    "chapter_title": "string",
    "summary": "string",
    "scenes": [
        {{
            "type": "text|choice|condition",
            "title": "string (可选)",

            "directives": {{
                "background": "bg_id_or_path (可选，例 bg_001 或 resources/images/bg_001.png)",
                "cg": "cg_id_or_path (可选，视为背景切换到 resources/images/cg/...)",
                "bgm": "bgm_id_or_path (可选，例 bgm_01 或 resources/audios/bgm_01.mp3)",
                "stop_bgm": false,
                "video": "video_id_or_path (可选)",
                "ui_file": "ui_id_or_path (可选)",
                "hide_textbox": false
            }},

            "dialogues": [
                {{
                    "speaker": "角色名",
                    "text": "对白内容",
                    "emotion": "情绪(可选)",
                    "portrait": "可选：若省略，将由引擎按角色+情绪映射到 resources/portraits/...",
                    "voice": "可选：若省略，将由系统生成虚拟路径 resources/voices/...",
                    "hide_textbox": false,
                    "portrait_fade": false,
                    "portrait_fade_out": false
                }}
            ],

            "options": ["选项1", "选项2"],
            "condition": {{"var": "favorability_char_001", "op": ">=", "value": 10, "const": true}}
        }}
    ]
}}

关键约束（用于保证 Step5 节点聚合/切分效果）：
1) **同一个 scene(type=text)** 内的对白将被尽量聚合进同一个文本节点的 sub_dialogues。
2) 当需要强制切分为新文本节点时，请在新的 scene 的 directives 中体现变化：
     - background 改变 / bgm 改变 / stop_bgm=true / cg 出现 / video 改变 / ui_file 改变 / hide_textbox 段落变化。
3) choice/condition scene：不要提供 sub_dialogues 的多行对白；
     - choice 必须提供 options 数组（>=2）。
     - condition 必须提供 condition 对象（并隐含 True/False 两条分支）。

{fp_rules}
{cg_rules}

内容要求：
- 对白自然、推进剧情，符合章节摘要与人设。
- 每个 scene 的 directives 只在需要变化时写；不写表示沿用上一 scene 的状态。
"""
        
        parameters = {
            "chapter_index": chapter_index,
            "chapter_title": chapter_info.get('title', f'第{chapter_index+1}章'),
            "narrative_pov": pov,
            "first_person_name": fp_name,
            "cg_count": cg_count,
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

            # 如果 structured 缺失，尝试从 raw_response（可能是 ```json 代码块或带噪 JSON）提取
            if not normalized.get("structured") and isinstance(raw_text, str):
                extracted = self._try_parse_json(raw_text)
                if extracted is not None:
                    normalized["structured"] = extracted

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
        personas_data: Any | None = None,
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

        pov = (story_config.get("narrative_pov") or "third").strip().lower()
        first_person_name = (story_config.get("first_person_name") or "我").strip() or "我"
        first_person_has_portrait = bool(story_config.get("first_person_has_portrait", False))
        first_person_has_voice = bool(story_config.get("first_person_has_voice", False))

        def _is_first_person_char(char_dict: Dict[str, Any]) -> bool:
            # 只要用户在角色配置中明确标记 is_player/is_first_person，就视为第一人称角色。
            if char_dict.get("is_player") or char_dict.get("is_first_person"):
                return True
            # 叙事 POV 为第一人称时，允许用名称匹配第一人称代称。
            if pov == "first":
                name = (char_dict.get("char_name") or char_dict.get("name") or "").strip()
                return bool(name) and name == first_person_name
            return False

        # ---------- 立绘（虚拟路径：resources/portraits/...） ----------
        from ..utils.persona_extract import extract_persona_map

        persona_by_char_id = extract_persona_map(personas_data)

        portrait_items: List[PortraitPendingItem] = []
        default_expressions = ["neutral", "happy", "sad", "angry", "surprised"]
        for char in characters:
            char_id = char.get("char_id") or char.get("id") or "char"
            char_name = char.get("char_name") or char.get("name") or char_id
            if _is_first_person_char(char) and (not first_person_has_portrait):
                continue
            persona_text = (persona_by_char_id.get(str(char_id)) or "").strip()
            if not persona_text:
                persona_text = (char.get("persona_keywords", "") or "").strip()
            portrait_items.append(
                PortraitPendingItem(
                    item_id=f"portrait_{char_id}",
                    char_id=char_id,
                    char_name=char_name,
                    description=persona_text,
                    expressions=default_expressions,
                    poses=["stand"],
                    status="pending",
                    file_paths=[f"resources/portraits/{char_id}_stand_{exp}.png" for exp in default_expressions],
                )
            )

        # ---------- 工具：从结构化章节里提取“事件流” ----------
        def _emotion_to_expr(emotion_text: str) -> str:
            t = (emotion_text or "").strip().lower()
            if not t:
                return "neutral"
            mapping = [
                ("angry", ["angry", "生气", "愤怒", "恼", "怒"]),
                ("sad", ["sad", "难过", "悲伤", "委屈", "哭"]),
                ("happy", ["happy", "开心", "高兴", "喜悦", "笑"]),
                ("surprised", ["surprised", "惊讶", "震惊", "诧异"]),
            ]
            for expr, keys in mapping:
                if any(k in t for k in keys):
                    return expr
            return "neutral"

        def _as_path(val: Any, *, kind: str) -> str:
            """把 id 或路径规范为虚拟路径。

            kind: background|cg|bgm|video|ui
            """
            if not val:
                return ""
            if isinstance(val, dict):
                val = val.get("file") or val.get("path") or val.get("id") or ""
            token = str(val).strip()
            if not token:
                return ""
            if token.startswith("resources/"):
                return token

            def _norm_id(s: str) -> str:
                # 仅对“id”做温和归一化：把空白压成下划线，避免生成带空格的资源路径。
                # 若用户传入的是路径（包含分隔符），则保持原样。
                if "/" in s or "\\" in s:
                    return s
                s2 = re.sub(r"\s+", "_", s)
                s2 = re.sub(r"_+", "_", s2).strip("_")
                return s2 or s

            token = _norm_id(token)

            low = token.lower()
            if kind == "bgm":
                # 支持 stop/none 表示停止BGM
                if low in {"stop", "stop_bgm", "none", "null", "off"}:
                    return ""
                # 容许传入不带扩展名的 id
                if not low.endswith(".mp3"):
                    token = f"{token}.mp3"
                return f"resources/audios/{token}".replace("\\", "/")
            if kind == "background":
                if not (low.endswith(".png") or low.endswith(".jpg") or low.endswith(".jpeg") or low.endswith(".webp")):
                    token = f"{token}.png"
                return f"resources/images/{token}".replace("\\", "/")
            if kind == "cg":
                if not (low.endswith(".png") or low.endswith(".jpg") or low.endswith(".jpeg") or low.endswith(".webp")):
                    token = f"{token}.png"
                return f"resources/images/cg/{token}".replace("\\", "/")
            if kind == "video":
                # 不强制扩展名，用户可能给 mp4/webm
                return f"resources/videos/{token}".replace("\\", "/")
            if kind == "ui":
                # UI 资源统一归入 images 子目录，避免额外顶层 resources/ui
                return f"resources/images/ui/{token}".replace("\\", "/")
            return token

        def _iter_items(structured: Any) -> List[Dict[str, Any]]:
            """把章节 structured 统一成 item 列表。

            支持：
            - {scenes:[{type, dialogues/options/condition,...}]}
            - {dialogues:[...]}
            - 直接是 list
            """
            if structured is None or not isinstance(structured, (list, dict)):
                return []
            if isinstance(structured, list):
                return [x for x in structured if isinstance(x, dict)]
            if not isinstance(structured, dict):
                return []
            if isinstance(structured.get("scenes"), list):
                out: List[Dict[str, Any]] = []
                for scene in structured.get("scenes"):
                    if not isinstance(scene, dict):
                        continue
                    st = (scene.get("type") or scene.get("node_type") or "text").strip().lower()
                    directives = scene.get("directives") if isinstance(scene.get("directives"), dict) else {}
                    scene_title = (scene.get("title") or scene.get("scene_title") or "").strip()
                    if st in {"choice", "condition"}:
                        # choice/condition 本身也可能携带媒体指令（用于切换背景/BGM后再进入节点）
                        out.append({"_kind": st, "_directives": directives, "_scene_title": scene_title, **scene})
                        continue
                    dialogues = scene.get("dialogues") or scene.get("dialogue") or []
                    if isinstance(dialogues, list):
                        for d in dialogues:
                            if not isinstance(d, dict):
                                continue
                            # 将 scene 的 directives 合并到每条对白上（对白字段优先）
                            merged = dict(directives)
                            merged.update(d)
                            merged["_directives"] = directives
                            merged["_scene_title"] = scene_title
                            out.append(merged)
                return out
            dialogues = structured.get("dialogues") or structured.get("dialogue") or structured.get("lines") or []
            if isinstance(dialogues, list):
                return [x for x in dialogues if isinstance(x, dict)]
            return []

        # ---------- 流程骨架（文本节点按“媒体状态”聚合；choice/condition 不建 sub_dialogues） ----------
        flow_nodes: List[FlowNodeData] = []
        connections: List[ConnectionData] = []
        global_variables: List[GlobalVariable] = []

        # ---------- 待生成清单（从实际引用推导，支持虚拟路径） ----------
        background_by_path: Dict[str, BackgroundPendingItem] = {}
        bgm_by_path: Dict[str, BGMPendingItem] = {}
        cg_by_path: Dict[str, CGPendingItem] = {}
        voice_items: List[VoicePendingItem] = []

        char_map = {str(c.get("char_name") or c.get("name") or "").strip(): c for c in characters}

        def _ensure_background_item(path: str, *, hint: str) -> str:
            if not path or path.startswith("resources/images/cg/"):
                return path
            if path in background_by_path:
                # 允许用更具体的信息补齐（仅填空字段，避免覆盖用户自定义 prompt）
                try:
                    it = background_by_path[path]
                    if hint and (not it.description):
                        it.description = hint
                except Exception:
                    pass
                return path
            stem = Path(path).stem
            bg_id = stem or f"bg_{len(background_by_path)+1:03d}"
            background_by_path[path] = BackgroundPendingItem(
                item_id=f"background_{len(background_by_path)+1:03d}",
                bg_id=bg_id,
                description=hint or bg_id,
                atmosphere=str(story_config.get("style", "") or ""),
                time_weather="",
                status="pending",
                file_path=path,
            )
            return path

        def _make_bg_hint(chapter_title: str, raw_item: Dict[str, Any]) -> str:
            parts: List[str] = [chapter_title]
            st = (raw_item.get("_scene_title") or "").strip()
            if st:
                parts.append(st)

            # 尝试拼一些更“可用”的结构化字段（若 Step4 输出里带了）
            loc = (raw_item.get("location") or raw_item.get("place") or raw_item.get("scene") or "").strip()
            tw = (raw_item.get("time_weather") or raw_item.get("time") or raw_item.get("weather") or "").strip()
            atmos = (raw_item.get("atmosphere") or raw_item.get("mood") or raw_item.get("tone") or "").strip()
            if loc:
                parts.append(f"地点:{loc}")
            if tw:
                parts.append(f"时间/天气:{tw}")
            if atmos and atmos not in {"平静", "neutral"}:
                parts.append(f"氛围:{atmos}")

            speaker = (raw_item.get("speaker") or raw_item.get("role") or "").strip()
            text = (raw_item.get("text") or raw_item.get("content") or "").strip()
            if speaker and text:
                snippet = text.replace("\n", " ").strip()
                if len(snippet) > 24:
                    snippet = snippet[:24] + "..."
                parts.append(f"{speaker}:{snippet}")
            return " | ".join(parts)

        def _make_bgm_hint(chapter_title: str, raw_item: Dict[str, Any]) -> str:
            parts: List[str] = [chapter_title]
            st = (raw_item.get("_scene_title") or "").strip()
            if st:
                parts.append(st)
            emo = str(raw_item.get("emotion") or raw_item.get("tone") or "").strip()
            if emo and emo not in {"平静", "neutral"}:
                parts.append(f"情绪:{emo}")
            speaker = (raw_item.get("speaker") or raw_item.get("role") or "").strip()
            text = (raw_item.get("text") or raw_item.get("content") or "").strip()
            if speaker and text:
                snippet = text.replace("\n", " ").strip()
                if len(snippet) > 24:
                    snippet = snippet[:24] + "..."
                parts.append(f"{speaker}:{snippet}")
            return " | ".join(parts)

        def _make_cg_hint(chapter_title: str, raw_item: Dict[str, Any], recent_chars: List[str]) -> str:
            parts: List[str] = [chapter_title]
            st = (raw_item.get("_scene_title") or "").strip()
            if st:
                parts.append(st)
            if recent_chars:
                parts.append("人物:" + ",".join(recent_chars[:4]))
            speaker = (raw_item.get("speaker") or raw_item.get("role") or "").strip()
            text = (raw_item.get("text") or raw_item.get("content") or "").strip()
            if speaker and text:
                snippet = text.replace("\n", " ").strip()
                if len(snippet) > 24:
                    snippet = snippet[:24] + "..."
                parts.append(f"{speaker}:{snippet}")
            return " | ".join(parts)

        def _ensure_bgm_item(path: str, *, hint: str, mood: str = "") -> str:
            if not path:
                return path
            if path in bgm_by_path:
                try:
                    it = bgm_by_path[path]
                    if hint and (not it.description):
                        it.description = hint
                    if mood and (not it.mood):
                        it.mood = mood
                except Exception:
                    pass
                return path
            stem = Path(path).stem
            bgm_id = stem or f"bgm_{len(bgm_by_path)+1:02d}"
            bgm_by_path[path] = BGMPendingItem(
                item_id=f"bgm_item_{len(bgm_by_path)+1:02d}",
                bgm_id=bgm_id,
                description=hint or bgm_id,
                mood=(mood or ""),
                style=story_config.get("style", ""),
                duration=120,
                loop=True,
                status="pending",
                file_path=path,
            )
            return path

        def _ensure_cg_item(
            path: str,
            *,
            hint: str,
            node_id_hint: str = "0",
            characters: List[str] | None = None,
        ) -> str:
            if not path:
                return path
            if path in cg_by_path:
                # 若之前没有 node_id（占位 0），后续拿到真实 node_id 则补齐
                try:
                    if cg_by_path[path].node_id in ("", "0") and node_id_hint not in ("", "0"):
                        cg_by_path[path].node_id = str(node_id_hint)
                    if characters and (not cg_by_path[path].characters):
                        cg_by_path[path].characters = [c for c in characters if c]
                except Exception:
                    pass
                return path
            stem = Path(path).stem
            cg_id = stem or f"cg_{len(cg_by_path)+1:03d}"
            cg_by_path[path] = CGPendingItem(
                item_id=f"cg_item_{len(cg_by_path)+1:03d}",
                cg_id=cg_id,
                node_id=str(node_id_hint),
                description=hint or cg_id,
                characters=[c for c in (characters or []) if c],
                atmosphere=story_config.get("style", ""),
                status="pending",
                file_path=path,
            )
            return path

        def _states_equal(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
            keys = ("background", "bgm", "stop_bgm", "video", "ui_file", "hide_textbox")
            return all((a.get(k) or "") == (b.get(k) or "") for k in keys)

        node_id = 1
        last_linear_sources: List[int] = []  # 需要连接到“下一个节点”的源（用于分支汇合）

        def _append_node_with_linear_links(node: FlowNodeData):
            """把 node 加入 flow，并从线性来源连到该 node。

            - 若存在 last_linear_sources（分支汇合点），则全部连向 node
            - 否则若已有前一个节点，则从前一个节点连向 node
            - 第一个节点不自动生成连线
            """
            nonlocal last_linear_sources
            sources: List[int] = []
            if last_linear_sources:
                sources = list(last_linear_sources)
            elif flow_nodes:
                sources = [flow_nodes[-1].id]
            for src in sources:
                if src != node.id:
                    connections.append(ConnectionData(source=src, target=node.id))
            flow_nodes.append(node)
            last_linear_sources = [node.id]

        def _new_text_node(title: str, state: Dict[str, Any], *, content_hint: str) -> FlowNodeData:
            nonlocal node_id
            node = FlowNodeData(
                id=node_id,
                node_type="text",
                title=title,
                content=content_hint,
                speaker="",
                portrait="",
                background=state.get("background") or "",
                voice="",
                bgm=state.get("bgm") or "",
                bgm_loop=True,
                stop_bgm=bool(state.get("stop_bgm", False)),
                bg_fade_in=False,
                portrait_fade=False,
                portrait_fade_out=False,
                hide_textbox=bool(state.get("hide_textbox", False)),
                ui_file=state.get("ui_file") or "",
                video=state.get("video") or "",
                video_loop=False,
                options=[],
                condition_var="",
                condition_op="==",
                condition_value="",
                condition_const=False,
                sub_dialogues=[],
                var_ops=[],
                x=220 * ((node_id - 1) % 5),
                y=180 * ((node_id - 1) // 5),
            )

            # 只有在“节点实际引用”时，才登记默认背景/BGM，避免出现未引用的 bg_001/bgm_01 等兜底项。
            try:
                bg_path = state.get("background") or ""
                if bg_path:
                    if str(bg_path).startswith("resources/images/cg/"):
                        _ensure_cg_item(str(bg_path), hint=f"{title} CG", node_id_hint=str(node_id))
                    else:
                        _ensure_background_item(str(bg_path), hint=f"{title} | 节点背景")
                bgm_path = state.get("bgm") or ""
                if bgm_path:
                    _ensure_bgm_item(str(bgm_path), hint=f"{title} | 节点BGM")
            except Exception:
                pass

            node_id += 1
            return node

        def _is_first_person_line(speaker_name: str, char_cfg: Dict[str, Any]) -> bool:
            # 角色配置标记优先（不依赖 narrative_pov 是否正确保存）。
            if char_cfg and (char_cfg.get("is_player") or char_cfg.get("is_first_person")):
                return True
            if pov == "first" and speaker_name and speaker_name.strip() == first_person_name:
                return True
            return False

        def _add_voice(node_id_for_voice: int, sub_id: int, speaker: str, char_id: str, text: str, emotion: str) -> str:
            cfg = char_map.get(speaker) or {}
            voice_model_id = cfg.get("voice_model_id")
            voice_id = f"voice_{len(voice_items)+1:05d}"
            voice_items.append(
                VoicePendingItem(
                    item_id=f"voice_item_{len(voice_items)+1:05d}",
                    voice_id=voice_id,
                    node_id=str(node_id_for_voice),
                    sub_id=sub_id,
                    speaker=speaker,
                    char_id=char_id,
                    text=text,
                    emotion=emotion,
                    voice_model_id=voice_model_id,
                    status="pending",
                    file_path=f"resources/voices/{char_id}/{voice_id}.mp3",
                )
            )
            return voice_items[-1].file_path
        for chap_idx, chapter in enumerate(normalized_chapters):
            structured = chapter.get("structured") if isinstance(chapter, dict) else None
            chap_title = f"第{chap_idx+1}章"
            chap_summary = ""
            if isinstance(structured, dict):
                chap_title = structured.get("chapter_title") or structured.get("title") or chap_title
                chap_summary = structured.get("summary") or structured.get("chapter_summary") or ""
            if not chap_summary and isinstance(chapter, dict):
                chap_summary = (chapter.get("raw_response", "") or "")[:400]

            # 章节默认背景/BGM（作为兜底）。
            # 注意：不要提前写入 pending 列表，只有当节点真正使用它们时才登记，避免出现“未引用的默认项”。
            default_bg = _as_path(f"bg_{chap_idx+1:03d}", kind="background")
            default_bgm = _as_path(f"bgm_{chap_idx+1:02d}", kind="bgm")

            items = _iter_items(structured)

            # 用于 CG 角色推断：记录最近出现的角色（char_id）
            recent_char_ids: List[str] = []

            pending_state = {
                "background": default_bg,
                "bgm": default_bgm,
                "stop_bgm": False,
                "video": "",
                "ui_file": "",
                "hide_textbox": False,
            }
            current_node: FlowNodeData | None = None
            node_state: Dict[str, Any] | None = None
            current_subs: List[Dict[str, Any]] = []

            def _flush_text_node():
                nonlocal current_node, current_subs, node_state
                if current_node is None:
                    return
                current_node.sub_dialogues = current_subs
                _append_node_with_linear_links(current_node)
                current_node = None
                node_state = None
                current_subs = []

            for raw in items:
                kind = (raw.get("_kind") or raw.get("type") or raw.get("node_type") or "").strip().lower()
                directives = raw.get("_directives") if isinstance(raw.get("_directives"), dict) else {}
                if isinstance(raw.get("directives"), dict):
                    directives = {**directives, **raw.get("directives")}
                if kind in {"choice", "condition"}:
                    # choice/condition 前先应用 scene directives（会触发节点切分）
                    desired_state = dict(pending_state)
                    bg_val = directives.get("background")
                    if bg_val:
                        desired_state["background"] = _as_path(bg_val, kind="background")
                    cg_val = directives.get("cg")
                    if cg_val:
                        desired_state["background"] = _as_path(cg_val, kind="cg")
                    video_val = directives.get("video")
                    if video_val:
                        desired_state["video"] = _as_path(video_val, kind="video")
                    ui_val = directives.get("ui") or directives.get("ui_file")
                    if ui_val:
                        desired_state["ui_file"] = _as_path(ui_val, kind="ui")
                    if directives.get("hide_textbox") is not None:
                        desired_state["hide_textbox"] = bool(directives.get("hide_textbox"))

                    stop_bgm_val = directives.get("stop_bgm")
                    bgm_val = directives.get("bgm")
                    if stop_bgm_val is True or (isinstance(bgm_val, str) and str(bgm_val).strip().lower() in {"stop", "stop_bgm", "off"}):
                        desired_state["stop_bgm"] = True
                        desired_state["bgm"] = ""
                    elif bgm_val:
                        desired_state["stop_bgm"] = False
                        desired_state["bgm"] = _as_path(bgm_val, kind="bgm")

                    # 登记媒体引用
                    if desired_state.get("background"):
                        if str(desired_state["background"]).startswith("resources/images/cg/"):
                            _ensure_cg_item(
                                desired_state["background"],
                                hint=_make_cg_hint(chap_title, raw, recent_char_ids),
                                node_id_hint="0",
                                characters=recent_char_ids,
                            )
                        else:
                            _ensure_background_item(desired_state["background"], hint=_make_bg_hint(chap_title, raw))
                    if desired_state.get("bgm"):
                        bgm_mood = str(raw.get("emotion") or raw.get("tone") or "").strip()
                        _ensure_bgm_item(desired_state["bgm"], hint=_make_bgm_hint(chap_title, raw), mood=bgm_mood)

                    pending_state = desired_state
                    _flush_text_node()

                    if kind == "choice":
                        options = raw.get("options") or []
                        if isinstance(options, str):
                            options = [options]
                        if not isinstance(options, list):
                            options = []
                        options = [str(o.get("text") if isinstance(o, dict) else o) for o in options]
                        options = [o.strip() for o in options if o and str(o).strip()]
                        if not options:
                            options = ["选项 1", "选项 2"]

                        choice_node = FlowNodeData(
                            id=node_id,
                            node_type="choice",
                            title=raw.get("title") or "选择",
                            content=raw.get("prompt") or raw.get("content") or "请选择：",
                            speaker="",
                            portrait="",
                            background=pending_state.get("background") or "",
                            voice="",
                            bgm=pending_state.get("bgm") or "",
                            bgm_loop=True,
                            stop_bgm=bool(pending_state.get("stop_bgm", False)),
                            bg_fade_in=False,
                            portrait_fade=False,
                            portrait_fade_out=False,
                            hide_textbox=bool(pending_state.get("hide_textbox", False)),
                            ui_file=pending_state.get("ui_file") or "",
                            video=pending_state.get("video") or "",
                            video_loop=False,
                            options=options,
                            condition_var="",
                            condition_op="==",
                            condition_value="",
                            condition_const=False,
                            sub_dialogues=[],
                            var_ops=[],
                            x=220 * ((node_id - 1) % 5),
                            y=180 * ((node_id - 1) // 5),
                        )
                        node_id += 1
                        _append_node_with_linear_links(choice_node)

                        branch_sources: List[int] = []
                        for opt_idx, opt in enumerate(options):
                            stub = _new_text_node(
                                title=f"{choice_node.title}-{opt_idx+1}",
                                state=dict(pending_state),
                                content_hint=f"分支占位：{opt}",
                            )
                            # choice 节点连到每个分支桩
                            connections.append(ConnectionData(source=choice_node.id, target=stub.id))
                            stub.sub_dialogues = []
                            flow_nodes.append(stub)
                            branch_sources.append(stub.id)
                        last_linear_sources = branch_sources
                        continue

                    # condition
                    cond = raw.get("condition") or raw
                    var_name = (cond.get("var") or cond.get("condition_var") or "").strip() or "favorability"
                    op = (cond.get("op") or cond.get("condition_op") or ">=").strip() or ">="
                    value = str(cond.get("value") or cond.get("condition_value") or "0")
                    is_const = bool(cond.get("const") if "const" in cond else cond.get("condition_const", True))

                    cond_node = FlowNodeData(
                        id=node_id,
                        node_type="condition",
                        title=raw.get("title") or "条件判断",
                        content=raw.get("prompt") or raw.get("content") or f"判断：{var_name} {op} {value}",
                        speaker="",
                        portrait="",
                        background=pending_state.get("background") or "",
                        voice="",
                        bgm=pending_state.get("bgm") or "",
                        bgm_loop=True,
                        stop_bgm=bool(pending_state.get("stop_bgm", False)),
                        bg_fade_in=False,
                        portrait_fade=False,
                        portrait_fade_out=False,
                        hide_textbox=bool(pending_state.get("hide_textbox", False)),
                        ui_file=pending_state.get("ui_file") or "",
                        video=pending_state.get("video") or "",
                        video_loop=False,
                        options=[],
                        condition_var=var_name,
                        condition_op=op,
                        condition_value=value,
                        condition_const=is_const,
                        sub_dialogues=[],
                        var_ops=[],
                        x=220 * ((node_id - 1) % 5),
                        y=180 * ((node_id - 1) // 5),
                    )
                    node_id += 1
                    _append_node_with_linear_links(cond_node)

                    true_stub = _new_text_node(
                        title=f"{cond_node.title}-True",
                        state=dict(pending_state),
                        content_hint="条件为真分支占位",
                    )
                    false_stub = _new_text_node(
                        title=f"{cond_node.title}-False",
                        state=dict(pending_state),
                        content_hint="条件为假分支占位",
                    )
                    connections.append(ConnectionData(source=cond_node.id, target=true_stub.id))
                    connections.append(ConnectionData(source=cond_node.id, target=false_stub.id))
                    true_stub.sub_dialogues = []
                    false_stub.sub_dialogues = []
                    flow_nodes.extend([true_stub, false_stub])
                    last_linear_sources = [true_stub.id, false_stub.id]
                    continue

                # 普通“对白/指令”项
                desired_state = dict(pending_state)

                # 媒体/显示指令（这些变化会触发新节点）
                bg_val = raw.get("background") or raw.get("bg") or raw.get("bg_id") or directives.get("background")
                if bg_val:
                    desired_state["background"] = _as_path(bg_val, kind="background")
                cg_val = raw.get("cg") or raw.get("cg_id") or raw.get("cg_path") or directives.get("cg")
                if cg_val:
                    # CG 视为背景切换到 resources/images/cg/...
                    desired_state["background"] = _as_path(cg_val, kind="cg")
                video_val = raw.get("video") or raw.get("video_path") or directives.get("video")
                if video_val:
                    desired_state["video"] = _as_path(video_val, kind="video")
                ui_val = raw.get("ui") or raw.get("ui_file") or directives.get("ui") or directives.get("ui_file")
                if ui_val:
                    desired_state["ui_file"] = _as_path(ui_val, kind="ui")

                hide_val = raw.get("hide_textbox")
                if hide_val is None and ("hide_textbox" in directives):
                    hide_val = directives.get("hide_textbox")
                if hide_val is not None:
                    desired_state["hide_textbox"] = bool(hide_val)

                stop_bgm_val = raw.get("stop_bgm")
                if stop_bgm_val is None and ("stop_bgm" in directives):
                    stop_bgm_val = directives.get("stop_bgm")
                bgm_val = raw.get("bgm") or raw.get("bgm_id")
                if not bgm_val and directives.get("bgm"):
                    bgm_val = directives.get("bgm")
                if stop_bgm_val is True or (isinstance(bgm_val, str) and str(bgm_val).strip().lower() in {"stop", "stop_bgm", "off"}):
                    desired_state["stop_bgm"] = True
                    desired_state["bgm"] = ""
                elif bgm_val:
                    desired_state["stop_bgm"] = False
                    desired_state["bgm"] = _as_path(bgm_val, kind="bgm")

                # 这里把“媒体引用”登记到待生成清单（即使文件不存在）
                if desired_state.get("background"):
                    if str(desired_state["background"]).startswith("resources/images/cg/"):
                        _ensure_cg_item(
                            desired_state["background"],
                            hint=_make_cg_hint(chap_title, raw, recent_char_ids),
                            node_id_hint="0",
                            characters=recent_char_ids,
                        )
                    else:
                        _ensure_background_item(desired_state["background"], hint=_make_bg_hint(chap_title, raw))
                if desired_state.get("bgm"):
                    bgm_mood = str(raw.get("emotion") or raw.get("tone") or "").strip()
                    _ensure_bgm_item(desired_state["bgm"], hint=_make_bgm_hint(chap_title, raw), mood=bgm_mood)

                speaker = (raw.get("speaker") or raw.get("role") or "").strip()
                text = (raw.get("text") or raw.get("content") or "").strip()
                emotion = str(raw.get("emotion") or raw.get("tone") or "平静")

                narrator_aliases = {"旁白", "叙述", "narrator", "narration", "Narrator", "Narration"}
                is_narration = (not speaker) or (speaker.strip() in narrator_aliases)

                # 纯指令行（无对白），只更新状态，不创建节点
                if not speaker and not text:
                    pending_state = desired_state
                    continue

                # 节点聚合规则：只要媒体状态不变，就尽量塞进同一 text node
                if current_node is None:
                    pending_state = desired_state
                    node_state = dict(desired_state)
                    current_node = _new_text_node(chap_title, node_state, content_hint=chap_summary)
                else:
                    if node_state is None:
                        node_state = dict(pending_state)
                    if not _states_equal(node_state, desired_state):
                        _flush_text_node()
                        pending_state = desired_state
                        node_state = dict(desired_state)
                        current_node = _new_text_node(chap_title, node_state, content_hint=chap_summary)
                    else:
                        # 同节点内对白：保持 pending_state 跟随最新（便于后续指令继承），但 node_state 不变
                        pending_state = desired_state

                # 若当前媒体状态使用 CG 背景，补齐 CG 的 node_id
                if current_node and desired_state.get("background") and str(desired_state["background"]).startswith("resources/images/cg/"):
                    _ensure_cg_item(
                        desired_state["background"],
                        hint=_make_cg_hint(chap_title, raw, recent_char_ids),
                        node_id_hint=str(current_node.id),
                        characters=recent_char_ids,
                    )

                char_cfg = char_map.get(speaker) or {}
                if _is_first_person_line(speaker, char_cfg) and not char_cfg:
                    char_cfg = {"char_id": "player", "char_name": speaker, "is_player": True}
                char_id = (char_cfg.get("char_id") or char_cfg.get("id") or "unknown")
                expr = _emotion_to_expr(emotion)
                is_fp_line = _is_first_person_line(speaker, char_cfg)
                if is_narration:
                    portrait_path = ""
                elif is_fp_line and (not first_person_has_portrait):
                    portrait_path = ""
                else:
                    portrait_path = f"resources/portraits/{char_id}_stand_{expr}.png" if char_id != "unknown" else ""

                if is_narration:
                    voice_path = ""
                elif is_fp_line and (not first_person_has_voice):
                    voice_path = ""
                else:
                    voice_path = _add_voice(current_node.id, len(current_subs), speaker, char_id, text, emotion)

                # 更新“最近角色”缓存，用于后续 CG 角色推断
                if (not is_narration) and char_id and char_id != "unknown":
                    try:
                        cid = str(char_id)
                        if cid in recent_char_ids:
                            recent_char_ids.remove(cid)
                        recent_char_ids.append(cid)
                        if len(recent_char_ids) > 4:
                            recent_char_ids = recent_char_ids[-4:]
                    except Exception:
                        pass

                # 若当前行更新了 recent_char_ids，且当前背景为 CG，则补齐 CG 的人物信息
                if current_node and desired_state.get("background") and str(desired_state["background"]).startswith("resources/images/cg/"):
                    _ensure_cg_item(
                        desired_state["background"],
                        hint=_make_cg_hint(chap_title, raw, recent_char_ids),
                        node_id_hint=str(current_node.id),
                        characters=recent_char_ids,
                    )

                # 注意：运行时 hide_textbox 从 sub_dialogues 覆盖 node 本体
                current_subs.append(
                    {
                        "speaker": speaker,
                        "text": text,
                        "portrait": portrait_path,
                        "voice": voice_path,
                        "hide_textbox": bool((node_state or desired_state).get("hide_textbox", False)),
                        "portrait_fade": bool(raw.get("portrait_fade", False)),
                        "portrait_fade_out": bool(raw.get("portrait_fade_out", False)),
                    }
                )

            _flush_text_node()

        # ---------- 全局变量（启用条件节点时，预置好感度变量，后续可扩展） ----------
        if story_config.get("enable_condition_node"):
            for char in characters:
                char_id = char.get("char_id") or char.get("id")
                if not char_id:
                    continue
                global_variables.append(GlobalVariable(name=f"favorability_{char_id}", initial=0.0, type="float"))

        pending_lists = PendingLists(
            portraits=portrait_items,
            backgrounds=list(background_by_path.values()),
            cgs=list(cg_by_path.values()),
            voices=voice_items,
            bgms=list(bgm_by_path.values()),
        )

        summary = {
            "portraits": len(portrait_items),
            "backgrounds": len(pending_lists.backgrounds),
            "cgs": len(pending_lists.cgs),
            "voices": len(pending_lists.voices),
            "bgms": len(pending_lists.bgms),
            "nodes": len(flow_nodes),
        }

        return {
            "pending_lists": pending_lists,
            "flow_nodes": flow_nodes,
            "connections": connections,
            "global_variables": global_variables,
            "summary": summary,
        }
