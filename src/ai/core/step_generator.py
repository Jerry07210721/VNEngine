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

    # UI 侧要求 max_tokens 最大 64000；这里也做一次兜底裁剪
    MAX_TOKENS_HARD_CAP = 64000

    # 各步骤默认 max_tokens（用于长篇故事生成，仍可在主控面板覆盖）
    DEFAULT_STEP_MAX_TOKENS = {
        "step1": 32000,
        "step2": 48000,
        "step3": 48000,
        "step4": 64000,
    }
    
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
            lower = candidate.lower()

            def _strip_fence_payload(payload: str) -> str:
                payload = (payload or "").strip("\n\r \t")
                # 兼容 ```JSON / ```Json / ```json5 等：若第一行像语言标识，则去掉
                first_line, _, rest = payload.partition("\n")
                lang = first_line.strip().lower()
                if lang in {"json", "json5", "javascript", "js"}:
                    return rest.strip("\n\r \t")
                return payload

            if "```json" in lower:
                pos = lower.find("```json")
                payload = candidate[pos + len("```json") :]
                payload = payload.split("```", 1)[0]
                payload = _strip_fence_payload(payload)
                return json.loads(payload)
            if candidate.startswith("```"):
                payload = candidate.split("```", 1)[1].split("```", 1)[0]
                payload = _strip_fence_payload(payload)
                return json.loads(payload)
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

    def _resolve_max_tokens(self, parameters: Dict[str, Any] | None, *, step_key: str, default: int) -> int:
        """从 parameters 读取 max_tokens，并做类型转换与范围裁剪。"""
        value = default
        if isinstance(parameters, dict):
            candidate = parameters.get("max_tokens")
            if candidate is not None:
                try:
                    value = int(candidate)
                except Exception:
                    value = default

        # 兜底裁剪
        if value <= 0:
            value = default
        hard_cap = int(getattr(self, "MAX_TOKENS_HARD_CAP", 64000) or 64000)
        if value > hard_cap:
            value = hard_cap
        return value
    
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
            max_tokens = self._resolve_max_tokens(
                parameters,
                step_key="step1",
                default=int(self.DEFAULT_STEP_MAX_TOKENS.get("step1", 32000)),
            )
            text, structured = self._call_llm(
                instruction,
                system="你是资深的视觉小说角色设定专家，擅长给出结构化、可落地的人设。",
                max_tokens=max_tokens,
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

        enable_single_route = bool(story_config.get("enable_single_route", False))
        enable_multi_branch = bool(story_config.get("enable_multi_branch", False))

        # 互斥纠偏：单线叙事优先
        if enable_single_route and enable_multi_branch:
            enable_multi_branch = False

        # 只有开启多分支，才允许 choice/condition
        enable_choice = bool(story_config.get("enable_choice_node", False))
        enable_condition = bool(story_config.get("enable_condition_node", False))
        if not enable_multi_branch:
            enable_choice = False
            enable_condition = False

        single_route_note = ""
        if enable_single_route:
            single_route_note = """
    - 启用【单线叙事】：全故事必须保持章节级线性推进，不允许并行路线/章节级分支
      - 不允许出现 4A/4B 这种分支章节编号
      - 不允许出现 A线/B线 这种并行路线设计
      - 不需要设计选择节点/条件节点（本模式下强制关闭）
    """

        node_note = ""
        if enable_multi_branch and (enable_choice or enable_condition):
                        node_note = """必须在大纲中**明确规划**选择/条件节点：
    1) 在对应章节的段落里明确写出：此处出现 choice/condition（位置：章末/场景名/剧情节点）。
    2) 在大纲末尾额外输出一个【分支控制计划】小节（供 Step3 直接对齐），逐条列出每个控制节点：
         - at_chapter：发生在第几章（用数字章序，不用 chapter_id）
         - type：choice / condition
         - prompt：节点提示语
         - choice.options：每个选项的 text + 进入的下游路线（可用 4A/4B 这类占位章节编号）
             - 若是“延迟分支”（选择后先回共通线）：必须给出 var_ops（设置变量）以及后续在哪一章用 condition 分流。
         - condition：给出条件表达式（var/op/value/const）以及 true/false 分别进入的下游章节（或路线）。
    3) 一致性：分支控制计划中的 prompt/选项文案应与章节段落中保持一致，避免后续 Step3/Step4 跑偏。
"""
        else:
            node_note = "不要设计选择节点/条件节点，不要引入分支走向"
        
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
- {node_note}
{single_route_note}
"""
        
        parameters = {
            "chapter_count": story_config.get('chapter_count', 5),
            "text_volume": story_config.get('text_volume', 5000),
            "enable_choice": enable_choice,
            "enable_condition": enable_condition,
            "enable_multi_branch": enable_multi_branch,
            "enable_single_route": enable_single_route,
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
            max_tokens = self._resolve_max_tokens(
                parameters,
                step_key="step2",
                default=int(self.DEFAULT_STEP_MAX_TOKENS.get("step2", 48000)),
            )
            text, structured = self._call_llm(
                instruction,
                system="你是专业的视觉小说主编，擅长输出清晰的章节大纲。",
                max_tokens=max_tokens,
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
        enable_choice = bool(story_config.get("enable_choice_node", False))
        enable_condition = bool(story_config.get("enable_condition_node", False))
        enable_multi_branch = bool(story_config.get("enable_multi_branch", False))
        enable_single_route = bool(story_config.get("enable_single_route", False))
        text_volume = int(story_config.get("text_volume", 5000) or 5000)

        # 互斥纠偏：单线叙事优先
        if enable_single_route and enable_multi_branch:
            enable_multi_branch = False

        # 只有开启多分支，才允许 choice/condition
        if not enable_multi_branch:
            enable_choice = False
            enable_condition = False

        branch_note = ""
        if enable_single_route:
            branch_note = """

单线叙事要求（非常重要）：
- 必须严格章节级单线推进：chapter_id 只能使用 "1" "2" ... 这种线性编号，不允许 4A/4B。
- 不允许规划并行路线（route 字段必须省略；by_route 只允许 common）。
- 不要输出 branch_plan 字段（或输出 []）。
- 不需要设计选择节点/条件节点（本模式下强制关闭）。
"""
        elif enable_multi_branch:
            if enable_choice or enable_condition:
                branch_note = """

多分支章节规划要求（非常重要）：
- 章节数量（chapter_count）按“主线/共通线章节数”计数：共通线约为 chapter_count 章；分支章可额外增加。
- 分支章的预计字数通常应短于共通章（例如共通章的 40%-80%），总字数整体接近 text_volume。
- 允许多结局：某些路线可以后期进入不同结局，不要求一定汇聚回同一章。
- 你需要在章节列表阶段就明确“关键选择/条件”会如何影响后续章节走向，并用 branch_plan 明确表达。
- route 字段用于标记章节归属（common/A/B/ending_A/ending_B...）。
"""
            else:
                branch_note = """

重要限制：你开启了多分支，但本次未启用选择/条件节点。
- 因此：不要设计章节级分支，不允许 4A/4B，不允许并行路线，不要输出 branch_plan。
- 请输出严格线性的章节列表（chapter_id 为 "1".."N"）。
"""
        else:
            branch_note = """

线性章节规划要求（非常重要）：
- 未开启多分支：必须严格输出线性章节列表（chapter_id 为 "1".."N"），不允许 4A/4B。
- 不允许规划并行路线（route 字段必须省略；by_route 只允许 common）。
- 不要输出 branch_plan 字段（或输出 []）。
- 不需要设计选择节点/条件节点（本模式下强制关闭）。
"""

        branch_plan_rules = """

branch_plan 字段语义与组合优先级（非常重要，严格遵守）：

【choice 节点】
- 在 at_chapter_id 章末出现选择节点。
- options[i].text：第 i 个选项显示文本。
- options[i].var_ops（可选）：该选项被选择后立刻执行的变量运算列表（用于“延迟分支”）。
  - var_ops 的字段必须是：dest/left/right/op/left_const/right_const
  - op 支持：= + - * /

【选项跳转优先级】（从高到低）：
1) options[i].leads_to：若提供，为路线上的章节 ID 列表。
   - 进入该选项后，首先进入 leads_to[0]；并且可把 leads_to 内部按顺序理解为线性推进。
2) options[i].next_chapter_id：若提供，为该选项选择后“立刻进入”的下一章。
   - 典型用法：两条选项都 next_chapter_id="4"（先合并回共通线继续），但 var_ops 设置不同变量。
3) options[i].merge_to：该选项分支结束后汇聚回的共通章节（用于路线图说明）。
4) options[i].ends_to：该选项路线直接结束时进入的结局章节（用于路线图说明）。

一致性要求：
- 如果同时提供 leads_to 与 next_chapter_id：next_chapter_id 必须等于 leads_to[0]。
- 至少提供 leads_to 或 next_chapter_id 之一；merge_to/ends_to 可选（用于说明后续汇聚/结局）。

【condition 节点】
- 在 at_chapter_id 章末出现条件判断节点。
- condition.var/op/value/const：条件表达式。
- true_leads_to / false_leads_to：分别表示 true/false 分支的路线章节 ID 列表，进入时先进入列表第一个。
- 如果只想跳到单章，也可以只写一个元素列表，例如 true_leads_to=["6A"].
"""

        if not (enable_multi_branch and (enable_choice or enable_condition)):
            branch_plan_rules = ""

        allow_branch_plan = bool(enable_multi_branch and (enable_choice or enable_condition))
        branch_plan_output_rule = ""
        if not allow_branch_plan:
            branch_plan_output_rule = """

重要输出约束（非常重要）：
- 本次不允许设计章节级分支：chapter_id 必须是线性编号 "1".."N"。
- 不要输出 branch_plan 对象结构：branch_plan 必须为 [] 或完全省略。
- 不要输出 route 字段（或仅使用 common，但更推荐省略）。
"""

        # 用动态生成的 JSON 示例避免 f-string 花括号转义问题
        example_immediate_branch = json.dumps(
            {
                "word_budget": {"total_target": text_volume, "by_route": {"common": int(text_volume * 0.6), "A": int(text_volume * 0.2), "B": int(text_volume * 0.2)}},
                "chapters": [
                    {"chapter_id": "1", "title": "第1章", "summary": "...", "main_scenes": ["..."], "characters": ["..."], "estimated_words": 900, "route": "common"},
                    {"chapter_id": "2", "title": "第2章", "summary": "...", "main_scenes": ["..."], "characters": ["..."], "estimated_words": 900, "route": "common"},
                    {"chapter_id": "3", "title": "第3章-关键选择", "summary": "...", "main_scenes": ["..."], "characters": ["..."], "estimated_words": 900, "route": "common"},
                    {"chapter_id": "4A", "title": "第4A章", "summary": "...", "main_scenes": ["..."], "characters": ["..."], "estimated_words": 700, "route": "A"},
                    {"chapter_id": "5A", "title": "第5A章", "summary": "...", "main_scenes": ["..."], "characters": ["..."], "estimated_words": 700, "route": "A"},
                    {"chapter_id": "4B", "title": "第4B章", "summary": "...", "main_scenes": ["..."], "characters": ["..."], "estimated_words": 700, "route": "B"},
                    {"chapter_id": "5B", "title": "第5B章", "summary": "...", "main_scenes": ["..."], "characters": ["..."], "estimated_words": 700, "route": "B"},
                    {"chapter_id": "6", "title": "第6章-汇聚", "summary": "...", "main_scenes": ["..."], "characters": ["..."], "estimated_words": 900, "route": "common"},
                ],
                "branch_plan": [
                    {
                        "type": "choice",
                        "at_chapter_id": "3",
                        "prompt": "选择路线",
                        "options": [
                            {"text": "走A线", "leads_to": ["4A", "5A"], "merge_to": "6"},
                            {"text": "走B线", "leads_to": ["4B", "5B"], "merge_to": "6"},
                        ],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

        example_delayed_branch = json.dumps(
            {
                "chapters": [
                    {"chapter_id": "1", "title": "第1章", "summary": "...", "main_scenes": ["..."], "characters": ["..."], "estimated_words": 900, "route": "common"},
                    {"chapter_id": "2", "title": "第2章", "summary": "...", "main_scenes": ["..."], "characters": ["..."], "estimated_words": 900, "route": "common"},
                    {"chapter_id": "3", "title": "第3章-早期选择", "summary": "做选择但先继续共通线", "main_scenes": ["..."], "characters": ["..."], "estimated_words": 900, "route": "common"},
                    {"chapter_id": "4", "title": "第4章-共通", "summary": "共通线继续", "main_scenes": ["..."], "characters": ["..."], "estimated_words": 900, "route": "common"},
                    {"chapter_id": "5", "title": "第5章-分流判断", "summary": "根据变量进入不同路线", "main_scenes": ["..."], "characters": ["..."], "estimated_words": 900, "route": "common"},
                    {"chapter_id": "6A", "title": "第6A章", "summary": "A线开始", "main_scenes": ["..."], "characters": ["..."], "estimated_words": 700, "route": "A"},
                    {"chapter_id": "6B", "title": "第6B章", "summary": "B线开始", "main_scenes": ["..."], "characters": ["..."], "estimated_words": 700, "route": "B"},
                ],
                "branch_plan": [
                    {
                        "type": "choice",
                        "at_chapter_id": "3",
                        "prompt": "选择倾向（先继续共通线）",
                        "options": [
                            {
                                "text": "偏向A",
                                "next_chapter_id": "4",
                                "var_ops": [
                                    {"dest": "route_flag", "op": "=", "right": 1, "right_const": True, "left": 0, "left_const": True}
                                ],
                            },
                            {
                                "text": "偏向B",
                                "next_chapter_id": "4",
                                "var_ops": [
                                    {"dest": "route_flag", "op": "=", "right": 0, "right_const": True, "left": 0, "left_const": True}
                                ],
                            },
                        ],
                    },
                    {
                        "type": "condition",
                        "at_chapter_id": "5",
                        "prompt": "根据 route_flag 进入不同路线",
                        "condition": {"var": "route_flag", "op": "==", "value": 1, "const": True, "true_leads_to": ["6A"], "false_leads_to": ["6B"]},
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

        instruction = f"""请根据故事大纲，生成详细的章节列表（用于后续逐章详稿与自动生成流程图）。

故事大纲：
{outline.get('raw_response', '')}

字数预算要求（非常重要）：
1) 目标总文本量约为 {text_volume} 字（对白+叙述合计）。
2) 你必须在章节列表阶段完成“每一章 estimated_words”的字数分配，并确保所有章节的 estimated_words 总和接近目标总文本量（允许 ±10% 浮动）。
3) 若存在分支路线（route=A/B/...）：请同时给出每条路线的总字数预算（by_route），用于后续逐章写作时控制篇幅。

基础要求：
1) 生成约 {story_config.get('chapter_count', 5)} 个章节：
    - 未开启多分支时：必须严格生成该数量的线性章节（chapter_id 为 "1".."N"），不允许 4A/4B。
    - 开启多分支时：该数字按主线/共通线计数，分支章可额外增加（仅在启用 choice/condition 时允许）。
2) 每个章节包含：
- chapter_id：字符串（唯一、稳定；线性模式为 "1".."N"；多分支模式允许 4A/4B）
- title：章节标题
- summary：章节摘要（150-200字）
- main_scenes：主要场景（列表）
- characters：涉及角色（列表）
- estimated_words：预计字数（整数）
- route：可选，"common" / "A" / "B" ...（仅多分支模式使用；线性模式请省略）
{branch_note}

{branch_plan_output_rule}

{branch_plan_rules}

请严格以结构化 JSON 输出（仅输出 JSON，不要解释文字）。

推荐 JSON Schema：
{{
    "word_budget": {{
        "total_target": 5000,
        "by_route": {{
            "common": 3000,
            "A": 1000,
            "B": 1000
        }}
    }},
    "chapters": [
        {{
            "chapter_id": "1",
            "title": "...",
            "summary": "...",
            "main_scenes": ["..."],
            "characters": ["..."],
            "estimated_words": 1200,
            "route": "common"
        }}
    ],
    "branch_plan": [
        {{
            "type": "choice|condition",
            "at_chapter_id": "3",
            "prompt": "玩家需要做出关键选择...",
            "options": [
                {{
                    "text": "选项A...",
                    "leads_to": ["4A", "5A"],
                    "merge_to": "6",
                    "ends_to": "ending_A",
                    "var_ops": [
                        {{"dest": "route_flag", "op": "=", "right": 1, "right_const": true, "left": 0, "left_const": true}}
                    ]
                }},
                {{
                    "text": "选项B...",
                    "leads_to": ["4B", "5B"],
                    "merge_to": "6",
                    "ends_to": "ending_B",
                    "var_ops": [
                        {{"dest": "route_flag", "op": "=", "right": 0, "right_const": true, "left": 0, "left_const": true}}
                    ]
                }}
            ],
            "condition": {{"var": "A", "op": "==", "value": "1", "const": true, "true_leads_to": ["4A"], "false_leads_to": ["4B"], "merge_to": "6", "true_ends_to": "ending_A", "false_ends_to": "ending_B"}}
        }}
    ]
}}

补充：允许“延迟分支”的常见写法（推荐）：
- 在较早章节（例如第3章）使用 choice，但两个选项都先回到共通章节（例如 merge_to="4" 或 next_chapter_id="4"），同时每个选项通过 var_ops 设置不同变量值；
- 在较晚章节（例如第5章）再放置 condition（at_chapter_id="5"），根据上述变量值决定进入 A/B 路线（true_leads_to/false_leads_to）。

完整示例模板 1（立即分支 + 可汇聚）：
```json
{example_immediate_branch}
```

完整示例模板 2（延迟分支：先 choice 设变量并回到共通线，后续再 condition 分流）：
```json
{example_delayed_branch}
```
"""

        parameters = {
            "chapter_count": story_config.get("chapter_count", 5),
            "text_volume": text_volume,
            "enable_choice": enable_choice,
            "enable_condition": enable_condition,
            "enable_multi_branch": enable_multi_branch,
            "enable_single_route": enable_single_route,
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
            max_tokens = self._resolve_max_tokens(
                parameters,
                step_key="step3",
                default=int(self.DEFAULT_STEP_MAX_TOKENS.get("step3", 48000)),
            )
            text, structured = self._call_llm(
                instruction,
                system="你是视觉小说剧本统筹，请输出可直接拆分的章节计划。",
                max_tokens=max_tokens,
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
        chapters_plan: Optional[Dict[str, Any]] = None,
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
        enable_multi_branch = bool(story_cfg.get("enable_multi_branch", False))
        enable_choice = bool(story_cfg.get("enable_choice_node", False)) if enable_multi_branch else False
        enable_condition = bool(story_cfg.get("enable_condition_node", False)) if enable_multi_branch else False
        target_words = int(
            chapter_info.get("estimated_words")
            or chapter_info.get("target_words")
            or 0
        )
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

        # Step3 章节规划（只读）用于减少模型跑偏：提供全局章节序与本章相关的 branch_plan 片段。
        chapter_plan_context = ""
        try:
            if isinstance(chapters_plan, dict) and isinstance(chapters_plan.get("chapters"), list):
                chap_id = str(
                    chapter_info.get("chapter_id")
                    or chapter_info.get("id")
                    or (chapter_info.get("parameters", {}) or {}).get("chapter_id")
                    or str(chapter_index + 1)
                ).strip()

                compact_chapters = []
                for c in chapters_plan.get("chapters") or []:
                    if not isinstance(c, dict):
                        continue
                    compact_chapters.append(
                        {
                            "chapter_id": c.get("chapter_id"),
                            "title": c.get("title"),
                            "route": c.get("route"),
                            "estimated_words": c.get("estimated_words"),
                            "summary": (str(c.get("summary") or "")[:220] + "...") if isinstance(c.get("summary"), str) and len(c.get("summary")) > 220 else c.get("summary"),
                        }
                    )

                # 只取与本章相关的 branch_plan（at_chapter_id 匹配），降低 token。
                related_branch_plan = []
                raw_bp = chapters_plan.get("branch_plan")
                if isinstance(raw_bp, list) and chap_id:
                    for item in raw_bp:
                        if not isinstance(item, dict):
                            continue
                        if str(item.get("at_chapter_id") or "").strip() == chap_id:
                            related_branch_plan.append(item)

                plan_payload = {
                    "word_budget": chapters_plan.get("word_budget"),
                    "chapters": compact_chapters,
                }
                if related_branch_plan:
                    plan_payload["branch_plan_for_this_chapter"] = related_branch_plan

                chapter_plan_context = f"""

Step3 章节规划（只读，必须严格对齐，不要擅自改动/偏离）：
- 当前要生成的章节：chapter_index={chapter_index}，chapter_id={chap_id}
- 你只能生成该章节的具体内容，不要把后续章节的关键事件提前写进来。

{json.dumps(plan_payload, ensure_ascii=False, indent=2)}
"""
        except Exception:
            chapter_plan_context = ""

        instruction = f"""你正在为 VNEngine 生成“逐章详稿”（将用于后续自动生成 flow_nodes 与 pending_lists）。

请严格输出 **仅一个 JSON 对象**（不要输出解释文字），建议放在 ```json 代码块中。

章节信息：
{json.dumps(chapter_info, ensure_ascii=False, indent=2)}
{chapter_plan_context}

故事配置摘要：
- 故事风格：{story_cfg.get('style', '')}
- 启用选择节点：{enable_choice}
- 启用条件节点：{enable_condition}
- 开启多分支：{enable_multi_branch}
- 本章目标字数：{target_words if target_words > 0 else '（未指定，按章节摘要合理控制）'}（对白+叙述合计；若指定请尽量控制在 ±15%）

角色列表：
{char_block}

{prev}
输出 JSON Schema（必须遵守字段名，未用字段可为空/省略）：
{{
    "chapter_id": "string (必须，来自章节列表的 chapter_id)",
    "chapter_title": "string",
    "route": "string (可选：common/A/B/...)",
    "summary": "string",
    "word_target": "int (可选：本章目标字数；建议回填章节列表的 estimated_words)",
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
    ],
    "exit": {{
        "type": "linear|choice|condition|end",
        "next_chapter_id": "string (当 type=linear)",
        "choice": {{
            "prompt": "string",
            "options": [
                {{"text": "选项文本", "next_chapter_id": "4A"}},
                {{"text": "选项文本", "next_chapter_id": "4B"}}
            ]
        }},
        "condition": {{
            "var": "A",
            "op": "==",
            "value": "1",
            "const": true,
            "true_next_chapter_id": "4A",
            "false_next_chapter_id": "4B"
        }}
    }}
}}

关键约束（用于保证 Step5 节点聚合/切分效果）：
1) **同一个 scene(type=text)** 内的对白将被尽量聚合进同一个文本节点的 sub_dialogues。
2) 当需要强制切分为新文本节点时，请在新的 scene 的 directives 中体现变化：
     - background 改变 / bgm 改变 / stop_bgm=true / cg 出现 / video 改变 / ui_file 改变 / hide_textbox 段落变化。
3) choice/condition scene：不要提供 sub_dialogues 的多行对白；
     - choice 必须提供 options 数组（>=2）。
     - condition 必须提供 condition 对象（并隐含 True/False 两条分支）。

分支生成强约束（用于避免“只有占位节点，没有分支剧情”）：
- 当启用选择/条件节点且该章确实存在关键分支时：
    - 请优先把“分支跳转关系”写到顶层 exit（type=choice/condition），并为每个选项/真假分支给出 next_chapter_id。
    - **如果使用了 exit.type=choice/condition：请不要在 scenes 中再重复输出同一个 choice/condition scene（尤其不要作为最后一个 scene）。**
      - 需要“选择前铺垫/情绪推进”请用 text scene 写在前面。
    - 分支的具体剧情请放到对应的分支章节（例如 4A/4B）里生成，而不是在本章里写“分支占位”。
- 如果本章只是共通推进（没有关键分支），exit.type 使用 linear 或 end。

多分支/多结局约束（当开启多分支时必须遵守）：
- chapter_count 按主线/共通线计数；分支章节（route=A/B/...）通常更短，不需要与共通线平均字数。
- 允许多结局：分支章节可 exit.type = end（直接结束）或 linear 指向独立结局章节；不要求强制汇聚。

{fp_rules}
{cg_rules}

内容要求：
- 对白自然、推进剧情，符合章节摘要与人设。
- 每个 scene 的 directives 只在需要变化时写；不写表示沿用上一 scene 的状态。

输出前自检（必须逐条满足）：
1) 输出 JSON 的 chapter_id / chapter_title / route 与“章节信息/章节规划”一致。
2) 本章关键事件必须覆盖 chapter_info.summary 的要点，不要跑题。
3) 若本章存在关键分支：请用顶层 exit 精确表达跳转；且不要在 scenes 末尾重复输出 choice/condition。
"""
        
        parameters = {
            "chapter_index": chapter_index,
            "chapter_title": chapter_info.get('title', f'第{chapter_index+1}章'),
            "chapter_id": chapter_info.get("chapter_id") or chapter_info.get("id") or str(chapter_index + 1),
            "narrative_pov": pov,
            "first_person_name": fp_name,
            "cg_count": cg_count,
            "target_words": target_words,
            "has_chapters_plan": bool(isinstance(chapters_plan, dict) and isinstance(chapters_plan.get("chapters"), list)),
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
            max_tokens = self._resolve_max_tokens(
                parameters,
                step_key="step4",
                default=int(self.DEFAULT_STEP_MAX_TOKENS.get("step4", 64000)),
            )
            text, structured = self._call_llm(
                instruction,
                system="你是GalGame剧本作者，请输出包含对白与资源标注的章节文本。",
                max_tokens=max_tokens,
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
        chapters_plan: Dict[str, Any] | None = None,
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

        # step3 章节列表（可选）：用于在 Step4 未输出 exit 时补齐分支节点与跨章节连线
        plan_structured: Dict[str, Any] = {}
        if isinstance(chapters_plan, dict):
            if isinstance(chapters_plan.get("structured"), dict):
                plan_structured = chapters_plan.get("structured") or {}
            else:
                # 允许直接传入 structured
                plan_structured = chapters_plan

        plan_route_by_chapter_id: Dict[str, str] = {}
        if isinstance(plan_structured.get("chapters"), list):
            for ch in plan_structured.get("chapters") or []:
                if not isinstance(ch, dict):
                    continue
                cid = str(ch.get("chapter_id") or "").strip()
                if not cid:
                    continue
                plan_route_by_chapter_id[cid] = str(ch.get("route") or "").strip()

        # 由 branch_plan 推导“线性下一章”与“章末分支出口”
        forced_next_by_id: Dict[str, str] = {}
        forced_branch_exits: List[Dict[str, Any]] = []
        if isinstance(plan_structured.get("branch_plan"), list):
            for bp in plan_structured.get("branch_plan") or []:
                if not isinstance(bp, dict):
                    continue
                at_cid = str(bp.get("at_chapter_id") or "").strip()
                if not at_cid:
                    continue
                btype = str(bp.get("type") or "").strip().lower()
                if btype in {"choice", "condition"}:
                    forced_branch_exits.append(bp)

                # 推导 route 链路：A线/B线各自顺序连接
                if btype == "choice" and isinstance(bp.get("options"), list):
                    for opt in bp.get("options") or []:
                        if not isinstance(opt, dict):
                            continue
                        leads = opt.get("leads_to")
                        if isinstance(leads, str):
                            leads = [leads]
                        if not isinstance(leads, list):
                            leads = []
                        leads = [str(x).strip() for x in leads if str(x).strip()]
                        for a, b in zip(leads, leads[1:]):
                            forced_next_by_id.setdefault(a, b)
                        last = leads[-1] if leads else ""
                        merge_to = str(opt.get("merge_to") or "").strip()
                        ends_to = str(opt.get("ends_to") or "").strip()
                        if last and merge_to:
                            forced_next_by_id.setdefault(last, merge_to)
                        elif last and ends_to and ends_to != last:
                            forced_next_by_id.setdefault(last, ends_to)

                if btype == "condition" and isinstance(bp.get("condition"), dict):
                    cnd = bp.get("condition") or {}
                    for key_leads, key_merge, key_ends in (
                        ("true_leads_to", "merge_to", "true_ends_to"),
                        ("false_leads_to", "merge_to", "false_ends_to"),
                    ):
                        leads = cnd.get(key_leads)
                        if isinstance(leads, str):
                            leads = [leads]
                        if not isinstance(leads, list):
                            leads = []
                        leads = [str(x).strip() for x in leads if str(x).strip()]
                        for a, b in zip(leads, leads[1:]):
                            forced_next_by_id.setdefault(a, b)
                        last = leads[-1] if leads else ""
                        merge_to = str(cnd.get(key_merge) or "").strip()
                        ends_to = str(cnd.get(key_ends) or "").strip()
                        if last and merge_to:
                            forced_next_by_id.setdefault(last, merge_to)
                        elif last and ends_to and ends_to != last:
                            forced_next_by_id.setdefault(last, ends_to)

        # chapter graph（用于跨章节分支连线）
        chapter_order: List[str] = []
        chapter_start_node_by_id: Dict[str, int] = {}
        chapter_end_sources_by_id: Dict[str, List[int]] = {}
        chapter_next_by_id: Dict[str, List[str]] = {}
        chapter_explicit_routing: Dict[str, bool] = {}
        unresolved_edges: List[Tuple[int, str]] = []  # (source_node_id, target_chapter_id)

        seen_connections: set[tuple[int, int]] = set()

        node_by_id: Dict[int, FlowNodeData] = {}

        def _add_connection(source: int, target: int):
            if not source or not target or source == target:
                return
            key = (int(source), int(target))
            if key in seen_connections:
                return
            seen_connections.add(key)
            connections.append(ConnectionData(source=int(source), target=int(target)))

        def _append_node_with_linear_links(node: FlowNodeData, *, allow_prev_node_link: bool = True):
            """把 node 加入 flow，并从线性来源连到该 node。

            - 若存在 last_linear_sources（分支汇合点），则全部连向 node
            - 否则若已有前一个节点，则从前一个节点连向 node
            - 第一个节点不自动生成连线
            """
            nonlocal last_linear_sources
            sources: List[int] = []
            if last_linear_sources:
                sources = list(last_linear_sources)
            elif allow_prev_node_link and flow_nodes:
                sources = [flow_nodes[-1].id]
            for src in sources:
                _add_connection(src, node.id)
            flow_nodes.append(node)
            node_by_id[node.id] = node
            last_linear_sources = [node.id]

        def _normalize_chapter_id(val: Any, default: str) -> str:
            token = str(val).strip() if val is not None else ""
            return token or default

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

            chap_id = _normalize_chapter_id(
                (structured.get("chapter_id") if isinstance(structured, dict) else None)
                or (chapter.get("chapter_id") if isinstance(chapter, dict) else None)
                or (chapter.get("parameters", {}).get("chapter_id") if isinstance(chapter, dict) and isinstance(chapter.get("parameters"), dict) else None),
                default=str(chap_idx + 1),
            )
            chapter_order.append(chap_id)
            chapter_explicit_routing.setdefault(chap_id, False)

            # 开始新章节：禁止自动从上一章节末尾连到本章首节点
            last_linear_sources = []
            chapter_started = False

            def _append_in_chapter(node: FlowNodeData):
                nonlocal chapter_started
                if not chapter_started:
                    _append_node_with_linear_links(node, allow_prev_node_link=False)
                    chapter_start_node_by_id.setdefault(chap_id, node.id)
                    chapter_started = True
                else:
                    _append_node_with_linear_links(node)

            # 章节默认背景/BGM（作为兜底）。
            # 注意：不要提前写入 pending 列表，只有当节点真正使用它们时才登记，避免出现“未引用的默认项”。
            default_bg = _as_path(f"bg_{chap_idx+1:03d}", kind="background")
            default_bgm = _as_path(f"bgm_{chap_idx+1:02d}", kind="bgm")

            # 需要知道“末尾 scene”，用于去重：若同时存在 scenes 的 choice/condition 与 structured.exit 的 choice/condition，
            # 则优先以 exit 为准，避免生成重复节点与分支占位桩。
            items = list(_iter_items(structured))

            exit_type_for_dedupe = ""
            try:
                if isinstance(structured, dict) and isinstance(structured.get("exit"), dict):
                    exit_type_for_dedupe = str((structured.get("exit") or {}).get("type") or "").strip().lower()
            except Exception:
                exit_type_for_dedupe = ""

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
                _append_in_chapter(current_node)
                current_node = None
                node_state = None
                current_subs = []

            for raw_idx, raw in enumerate(items):
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

                    # 末尾 scene 去重：若 exit 也提供同类出口，则跳过该末尾 scene，避免出现“正确出口 + 占位 choice/condition”重复。
                    is_last_scene = (raw_idx == (len(items) - 1))
                    if is_last_scene and exit_type_for_dedupe in {"choice", "condition"} and kind == exit_type_for_dedupe:
                        continue

                    if kind == "choice":
                        raw_options = raw.get("options") or []
                        if isinstance(raw_options, str):
                            raw_options = [raw_options]
                        if not isinstance(raw_options, list):
                            raw_options = []

                        options: List[str] = []
                        targets: List[str] = []
                        for o in raw_options:
                            if isinstance(o, dict):
                                text_opt = str(o.get("text") or o.get("label") or "").strip()
                                next_ch = str(o.get("next_chapter_id") or o.get("next") or "").strip()
                                if text_opt:
                                    options.append(text_opt)
                                    targets.append(next_ch)
                            else:
                                text_opt = str(o).strip()
                                if text_opt:
                                    options.append(text_opt)
                                    targets.append("")
                        if not options:
                            options = ["选项 1", "选项 2"]
                            targets = ["", ""]

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
                        _append_in_chapter(choice_node)

                        # 若提供 next_chapter_id，则将 choice 作为“章节出口”直接连向目标章节首节点（第二遍解析）
                        has_targets = any(t.strip() for t in targets)
                        if has_targets:
                            chapter_explicit_routing[chap_id] = True
                            for opt_idx, t in enumerate(targets):
                                if t and t.strip():
                                    unresolved_edges.append((choice_node.id, t.strip()))
                            # choice 作为出口：不再创建占位桩，也避免本章后续节点被自动连上
                            last_linear_sources = []
                            continue

                        # 兼容旧格式：没有目标章节时，继续生成分支占位桩（但跨章节将按默认顺序连线）
                        branch_sources: List[int] = []
                        for opt_idx, opt in enumerate(options):
                            stub = _new_text_node(
                                title=f"{choice_node.title}-{opt_idx+1}",
                                state=dict(pending_state),
                                content_hint=f"分支占位：{opt}",
                            )
                            _add_connection(choice_node.id, stub.id)
                            stub.sub_dialogues = []
                            flow_nodes.append(stub)
                            node_by_id[stub.id] = stub
                            branch_sources.append(stub.id)
                        last_linear_sources = branch_sources
                        continue

                    # condition
                    cond = raw.get("condition") or raw
                    var_name = (cond.get("var") or cond.get("condition_var") or "").strip() or "favorability"
                    op = (cond.get("op") or cond.get("condition_op") or ">=").strip() or ">="
                    value = str(cond.get("value") or cond.get("condition_value") or "0")
                    is_const = bool(cond.get("const") if "const" in cond else cond.get("condition_const", True))

                    true_next = str(cond.get("true_next_chapter_id") or cond.get("true_next") or "").strip()
                    false_next = str(cond.get("false_next_chapter_id") or cond.get("false_next") or "").strip()

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
                    _append_in_chapter(cond_node)

                    if true_next or false_next:
                        chapter_explicit_routing[chap_id] = True
                        if true_next:
                            unresolved_edges.append((cond_node.id, true_next))
                        if false_next:
                            unresolved_edges.append((cond_node.id, false_next))
                        last_linear_sources = []
                        continue

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
                    _add_connection(cond_node.id, true_stub.id)
                    _add_connection(cond_node.id, false_stub.id)
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

            # 若本章完全没有生成任何节点，创建一个最小 text 节点，保证可作为分支目标
            if not chapter_started:
                node_state = dict(pending_state)
                current_node = _new_text_node(chap_title, node_state, content_hint=chap_summary or chap_title)
                current_node.sub_dialogues = []
                _append_in_chapter(current_node)
                current_node = None

            # 章节级出口（推荐的分支方式）：structured.exit
            if isinstance(structured, dict) and isinstance(structured.get("exit"), dict):
                exit_obj = structured.get("exit") or {}
                exit_type = str(exit_obj.get("type") or "").strip().lower()
                if exit_type in {"end", "finish", "none"}:
                    chapter_explicit_routing[chap_id] = True
                    chapter_next_by_id[chap_id] = []
                    chapter_end_sources_by_id[chap_id] = list(last_linear_sources)
                    continue

                if exit_type == "linear":
                    nxt = str(exit_obj.get("next_chapter_id") or exit_obj.get("next") or "").strip()
                    if nxt:
                        chapter_explicit_routing[chap_id] = True
                        chapter_next_by_id[chap_id] = [nxt]

                if exit_type == "choice" and isinstance(exit_obj.get("choice"), dict):
                    ch = exit_obj.get("choice") or {}
                    prompt = str(ch.get("prompt") or "请选择：").strip() or "请选择："
                    raw_opts = ch.get("options") or []
                    if isinstance(raw_opts, str):
                        raw_opts = [raw_opts]
                    if not isinstance(raw_opts, list):
                        raw_opts = []
                    opt_texts: List[str] = []
                    opt_targets: List[str] = []
                    for o in raw_opts:
                        if isinstance(o, dict):
                            t = str(o.get("text") or o.get("label") or "").strip()
                            nid = str(o.get("next_chapter_id") or o.get("next") or "").strip()
                            if t:
                                opt_texts.append(t)
                                opt_targets.append(nid)
                        else:
                            t = str(o).strip()
                            if t:
                                opt_texts.append(t)
                                opt_targets.append("")
                    if len(opt_texts) >= 2:
                        chapter_explicit_routing[chap_id] = True
                        choice_node = FlowNodeData(
                            id=node_id,
                            node_type="choice",
                            title=str(exit_obj.get("title") or structured.get("chapter_title") or "选择").strip() or "选择",
                            content=prompt,
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
                            options=opt_texts,
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
                        _append_in_chapter(choice_node)
                        for t in opt_targets:
                            if t and t.strip():
                                unresolved_edges.append((choice_node.id, t.strip()))
                        last_linear_sources = []
                        chapter_end_sources_by_id[chap_id] = []
                        continue

                if exit_type == "condition" and isinstance(exit_obj.get("condition"), dict):
                    cnd = exit_obj.get("condition") or {}
                    var_name = str(cnd.get("var") or "favorability").strip() or "favorability"
                    op = str(cnd.get("op") or ">=").strip() or ">="
                    value = str(cnd.get("value") or "0")
                    is_const = bool(cnd.get("const", True))
                    true_next = str(cnd.get("true_next_chapter_id") or cnd.get("true_next") or "").strip()
                    false_next = str(cnd.get("false_next_chapter_id") or cnd.get("false_next") or "").strip()
                    if true_next or false_next:
                        chapter_explicit_routing[chap_id] = True
                        cond_node = FlowNodeData(
                            id=node_id,
                            node_type="condition",
                            title=str(exit_obj.get("title") or "条件判断").strip() or "条件判断",
                            content=str(exit_obj.get("prompt") or f"判断：{var_name} {op} {value}").strip(),
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
                        _append_in_chapter(cond_node)
                        if true_next:
                            unresolved_edges.append((cond_node.id, true_next))
                        if false_next:
                            unresolved_edges.append((cond_node.id, false_next))
                        last_linear_sources = []
                        chapter_end_sources_by_id[chap_id] = []
                        continue

            # 默认情况下：本章末尾 sources 用于跨章节连线
            chapter_end_sources_by_id[chap_id] = list(last_linear_sources)

        # ---------- 使用 Step3 branch_plan 做兜底：补齐章末分支出口 / route 链路 ----------
        # 1) 先把 forced_next 写入 chapter_next_by_id（仅在本章未显式路由时生效）
        for src_cid, dst_cid in (forced_next_by_id or {}).items():
            if not src_cid or not dst_cid:
                continue
            if chapter_explicit_routing.get(src_cid):
                continue
            # 不覆盖已有显式 next
            if src_cid in chapter_next_by_id and chapter_next_by_id.get(src_cid):
                continue
            chapter_next_by_id[src_cid] = [dst_cid]

        # 2) 若某章在 Step4 未提供 exit，但 Step3 有 branch_plan，则创建 choice/condition 出口节点
        for bp in forced_branch_exits:
            at_cid = str(bp.get("at_chapter_id") or "").strip()
            if not at_cid:
                continue
            if chapter_explicit_routing.get(at_cid):
                # Step4 已有显式路由，避免重复出口
                continue
            end_sources = chapter_end_sources_by_id.get(at_cid) or []
            if not end_sources:
                # 若章内完全没节点或异常，至少尝试挂到该章首节点
                start = chapter_start_node_by_id.get(at_cid)
                if start:
                    end_sources = [start]

            # 取章末节点的媒体状态，让出口节点视觉更连贯
            ref_node = node_by_id.get(end_sources[-1]) if end_sources else None
            bg = (ref_node.background if ref_node else "") or ""
            bgm = (ref_node.bgm if ref_node else "") or ""
            ui_file = (ref_node.ui_file if ref_node else "") or ""
            video = (ref_node.video if ref_node else "") or ""
            hide_tb = bool(ref_node.hide_textbox if ref_node else False)
            stop_bgm = bool(ref_node.stop_bgm if ref_node else False)
            x = float(ref_node.x + 220) if ref_node else 0.0
            y = float(ref_node.y) if ref_node else 0.0

            btype = str(bp.get("type") or "").strip().lower()
            if btype == "choice":
                raw_opts = bp.get("options") or []
                if not isinstance(raw_opts, list):
                    raw_opts = []
                opt_texts: List[str] = []
                opt_targets: List[str] = []
                opt_var_ops: List[List[Dict[str, Any]]] = []
                for o in raw_opts:
                    if not isinstance(o, dict):
                        continue
                    t = str(o.get("text") or "").strip()
                    leads = o.get("leads_to")
                    if isinstance(leads, str):
                        leads = [leads]
                    if isinstance(leads, list) and leads:
                        nxt = str(leads[0]).strip()
                    else:
                        nxt = str(o.get("next_chapter_id") or o.get("next") or o.get("merge_to") or o.get("ends_to") or "").strip()
                    ops = o.get("var_ops")
                    if not isinstance(ops, list):
                        ops = []
                    norm_ops: List[Dict[str, Any]] = []
                    for item in ops[:50]:
                        if not isinstance(item, dict):
                            continue
                        norm_ops.append(
                            {
                                "dest": item.get("dest", ""),
                                "left": item.get("left", ""),
                                "right": item.get("right", ""),
                                "op": item.get("op", "+"),
                                "left_const": bool(item.get("left_const", False)),
                                "right_const": bool(item.get("right_const", False)),
                            }
                        )
                    if t:
                        opt_texts.append(t)
                        opt_targets.append(nxt)
                        opt_var_ops.append(norm_ops)
                if len(opt_texts) >= 2:
                    choice_node = FlowNodeData(
                        id=node_id,
                        node_type="choice",
                        title="选择",
                        content=str(bp.get("prompt") or "请选择：").strip() or "请选择：",
                        speaker="",
                        portrait="",
                        background=bg,
                        voice="",
                        bgm=bgm,
                        bgm_loop=True,
                        stop_bgm=stop_bgm,
                        bg_fade_in=False,
                        portrait_fade=False,
                        portrait_fade_out=False,
                        hide_textbox=hide_tb,
                        ui_file=ui_file,
                        video=video,
                        video_loop=False,
                        options=opt_texts,
                        condition_var="",
                        condition_op="==",
                        condition_value="",
                        condition_const=False,
                        sub_dialogues=[],
                        var_ops=[],
                        x=x,
                        y=y,
                    )
                    node_id += 1
                    # 出口节点追加到 flow（不参与章内自动连线），并手动从章末连入
                    flow_nodes.append(choice_node)
                    node_by_id[choice_node.id] = choice_node
                    for s in end_sources:
                        _add_connection(s, choice_node.id)

                    # 若选项需要执行变量操作，或多选项回到同一目标章，则插入“选项处理节点”以保序/保差异
                    non_empty_targets = [t for t in opt_targets if t]
                    need_option_nodes = any(bool(vops) for vops in opt_var_ops) or (
                        len(non_empty_targets) >= 2 and len(set(non_empty_targets)) < len(non_empty_targets)
                    )

                    if need_option_nodes:
                        for idx, (tgt, vops, opt_text) in enumerate(zip(opt_targets, opt_var_ops, opt_texts)):
                            opt_node = FlowNodeData(
                                id=node_id,
                                node_type="text",
                                title=f"选项：{opt_text}" if opt_text else "选项处理",
                                content="",
                                speaker="",
                                portrait="",
                                background=bg,
                                voice="",
                                bgm=bgm,
                                bgm_loop=True,
                                stop_bgm=stop_bgm,
                                bg_fade_in=False,
                                portrait_fade=False,
                                portrait_fade_out=False,
                                hide_textbox=True,
                                ui_file=ui_file,
                                video=video,
                                video_loop=False,
                                options=[],
                                condition_var="",
                                condition_op="==",
                                condition_value="",
                                condition_const=False,
                                sub_dialogues=[],
                                var_ops=vops or [],
                                x=x + 220,
                                y=y + (idx * 120),
                            )
                            node_id += 1
                            flow_nodes.append(opt_node)
                            node_by_id[opt_node.id] = opt_node
                            _add_connection(choice_node.id, opt_node.id)

                            if tgt:
                                start = chapter_start_node_by_id.get(tgt)
                                if start is None:
                                    unresolved_edges.append((opt_node.id, tgt))
                                else:
                                    _add_connection(opt_node.id, start)
                    else:
                        for tgt in opt_targets:
                            if not tgt:
                                continue
                            start = chapter_start_node_by_id.get(tgt)
                            if start is None:
                                unresolved_edges.append((choice_node.id, tgt))
                            else:
                                _add_connection(choice_node.id, start)
                    chapter_explicit_routing[at_cid] = True

            if btype == "condition" and isinstance(bp.get("condition"), dict):
                cnd = bp.get("condition") or {}
                var_name = str(cnd.get("var") or "favorability").strip() or "favorability"
                op = str(cnd.get("op") or ">=").strip() or ">="
                value = str(cnd.get("value") or "0")
                is_const = bool(cnd.get("const", True))
                true_leads = cnd.get("true_leads_to")
                false_leads = cnd.get("false_leads_to")
                true_next = ""
                false_next = ""
                if isinstance(true_leads, str):
                    true_next = true_leads.strip()
                elif isinstance(true_leads, list) and true_leads:
                    true_next = str(true_leads[0]).strip()
                if isinstance(false_leads, str):
                    false_next = false_leads.strip()
                elif isinstance(false_leads, list) and false_leads:
                    false_next = str(false_leads[0]).strip()
                if not true_next:
                    true_next = str(cnd.get("true_next_chapter_id") or cnd.get("true_next") or cnd.get("merge_to") or cnd.get("true_ends_to") or "").strip()
                if not false_next:
                    false_next = str(cnd.get("false_next_chapter_id") or cnd.get("false_next") or cnd.get("merge_to") or cnd.get("false_ends_to") or "").strip()
                if true_next or false_next:
                    cond_node = FlowNodeData(
                        id=node_id,
                        node_type="condition",
                        title="条件判断",
                        content=str(bp.get("prompt") or f"判断：{var_name} {op} {value}").strip(),
                        speaker="",
                        portrait="",
                        background=bg,
                        voice="",
                        bgm=bgm,
                        bgm_loop=True,
                        stop_bgm=stop_bgm,
                        bg_fade_in=False,
                        portrait_fade=False,
                        portrait_fade_out=False,
                        hide_textbox=hide_tb,
                        ui_file=ui_file,
                        video=video,
                        video_loop=False,
                        options=[],
                        condition_var=var_name,
                        condition_op=op,
                        condition_value=value,
                        condition_const=is_const,
                        sub_dialogues=[],
                        var_ops=[],
                        x=x,
                        y=y,
                    )
                    node_id += 1
                    flow_nodes.append(cond_node)
                    node_by_id[cond_node.id] = cond_node
                    for s in end_sources:
                        _add_connection(s, cond_node.id)
                    if true_next:
                        unresolved_edges.append((cond_node.id, true_next))
                    if false_next:
                        unresolved_edges.append((cond_node.id, false_next))
                    chapter_explicit_routing[at_cid] = True

        # ---------- 跨章节连线：优先显式 next / choice / condition，其次按章节顺序线性连接 ----------
        # 1) 显式 linear next
        for chap_id, next_ids in (chapter_next_by_id or {}).items():
            if not next_ids:
                continue
            sources = chapter_end_sources_by_id.get(chap_id) or []
            for nxt in next_ids:
                start = chapter_start_node_by_id.get(nxt)
                if start is None:
                    continue
                for s in sources:
                    _add_connection(s, start)

        # 2) choice/condition unresolved edges
        for src, target_chap in unresolved_edges:
            start = chapter_start_node_by_id.get(target_chap)
            if start is None:
                continue
            _add_connection(src, start)

        # 3) 默认线性：对“没有显式路由/next”的章节，连接到章节列表中的下一个章节
        for i in range(len(chapter_order) - 1):
            cid = chapter_order[i]
            if chapter_explicit_routing.get(cid):
                continue
            if cid in chapter_next_by_id and chapter_next_by_id.get(cid):
                continue
            next_cid = chapter_order[i + 1]

            # 多分支时：默认线性仅对 common 章节生效，避免把 A/B 分支按列表顺序串错
            if bool(story_config.get("enable_multi_branch", False)) and plan_route_by_chapter_id:
                r1 = (plan_route_by_chapter_id.get(cid) or "common").strip().lower()
                r2 = (plan_route_by_chapter_id.get(next_cid) or "common").strip().lower()
                if r1 != "common" or r2 != "common":
                    continue

            start = chapter_start_node_by_id.get(next_cid)
            if start is None:
                continue
            sources = chapter_end_sources_by_id.get(cid) or []
            for s in sources:
                _add_connection(s, start)

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
