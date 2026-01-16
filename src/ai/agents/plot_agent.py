# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - 剧情Agent
负责生成故事大纲、章节内容、角色对白、场景描述
"""

from typing import Dict, Any, List, Optional
import math
from pathlib import Path
import json
import time
from datetime import datetime

from ..api.api_manager import APIManager
from ..core.config_manager import ConfigManager
from ..core.models import (
    TaskAssignment,
    AgentResponse,
    FlowNodeData,
    ConnectionData,
    GlobalVariable,
    MaterialRequirement,
)
from ..utils import image_utils
from ..log.logger import get_logger


class PlotAgent:
    """剧情生成Agent"""
    
    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        api_manager: Optional[APIManager] = None
    ):
        """
        初始化剧情Agent
        
        Args:
            config_manager: 配置管理器
            api_manager: API管理器
        """
        self.config_manager = config_manager or ConfigManager()
        self.api_manager = api_manager or APIManager(self.config_manager)
        self.logger = get_logger("PlotAgent")
        
        # 获取LLM客户端（优先Claude）
        self.llm_client = self.api_manager.get_llm_client(prefer_claude=True)
        
        if not self.llm_client:
            raise RuntimeError("无法获取LLM客户端，请检查配置")
        
        self.logger.info(f"PlotAgent初始化完成 (LLM: {type(self.llm_client).__name__})")
    
    def execute(self, task: TaskAssignment) -> AgentResponse:
        """
        执行剧情生成任务
        
        Args:
            task: 任务配置
        
        Returns:
            Agent响应
        """
        start_time = time.time()
        
        self.logger.info(f"开始执行剧情生成任务: {task.task_type}")
        
        try:
            task_type = task.task_type or "generate_plot"
            if task_type == "generate_plot":
                result = self._generate_plot(task.parameters)
            else:
                raise ValueError(f"不支持的任务类型: {task_type}")
            
            time_cost = time.time() - start_time
            
            return AgentResponse(
                agent_name="plot_agent",
                task_type=task_type,
                status="success",
                output_files=result["files"],
                metadata=result["metadata"],
                time_cost=time_cost,
                message="剧情生成完成"
            )
            
        except Exception as e:
            self.logger.error(f"剧情生成失败: {e}")
            
            return AgentResponse(
                agent_name="plot_agent",
                task_type=task.task_type,
                status="failure",
                output_files=[],
                metadata={},
                error_message=str(e),
                time_cost=time.time() - start_time
            )
    
    def _generate_plot(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成完整剧情
        
        Args:
            parameters: 任务参数
        
        Returns:
            生成结果
        """
        theme = parameters.get("theme", "青春恋爱")
        style = parameters.get("style", "轻松日常")
        project_root = Path(parameters.get("project_root", "output/project"))
        text_volume = int(parameters.get("text_volume", 5000))
        # 根据文本量动态估算章节数：每章目标约 3000-5000 字
        chapter_count = parameters.get("chapter_count")
        if not chapter_count:
            chapter_count = max(3, min(10, math.ceil(text_volume / 4000)))

        self.logger.info(f"生成剧情参数: 章节数={chapter_count}, 文本量={text_volume}, 主题={theme}, 风格={style}")
        
        # 第1步：生成故事大纲
        self.logger.info("步骤 1/3: 生成故事大纲...")
        provided_chars = parameters.get("characters") or []
        char_hint_weight = float(parameters.get("character_hint_weight", 0.7))
        narrative_pov = parameters.get("narrative_pov", "third")
        first_person_name = parameters.get("first_person_name", "我")
        first_person_has_portrait = bool(parameters.get("first_person_has_portrait", False))
        first_person_has_voice = bool(parameters.get("first_person_has_voice", False))
        first_person_cg_presence = bool(parameters.get("first_person_cg_presence", True))

        outline = self._generate_outline(
            theme,
            style,
            chapter_count,
            provided_chars,
            narrative_pov,
            first_person_name,
        )
        
        # 第2步：生成角色设定
        self.logger.info("步骤 2/3: 生成角色设定...")
        if provided_chars:
            characters = self._refine_characters(provided_chars, theme, char_hint_weight)
        else:
            characters = self._generate_characters(outline, theme)
        
        # 第3步：生成章节详细内容
        self.logger.info("步骤 3/3: 生成章节详细内容...")
        chapters = []
        per_chapter_words = max(1500, min(6000, int(text_volume / chapter_count))) if chapter_count else 3000
        dialogues_target = max(12, min(40, int(per_chapter_words / 120)))
        for i in range(chapter_count):
            chapter = self._generate_chapter(
                i + 1,
                outline,
                characters,
                style,
                narrative_pov,
                first_person_name,
                first_person_has_portrait,
                first_person_has_voice,
                first_person_cg_presence,
                per_chapter_words,
                dialogues_target,
            )
            chapters.append(chapter)
            self.logger.info(f"  第 {i+1}/{chapter_count} 章完成 (目标字数≈{per_chapter_words}, 目标对白≈{dialogues_target})")
        
        # 构建可直接用于整合的节点/连接/变量
        flow_nodes, connections, global_vars, material_reqs = self._build_flow_graph(
            chapters=chapters,
            characters=characters,
            style=style,
            project_root=project_root,
            first_person_name=first_person_name,
            first_person_has_portrait=first_person_has_portrait,
            first_person_has_voice=first_person_has_voice,
        )
        
        # 保存结果
        output_files = self._save_plot_data(
            outline,
            characters,
            chapters,
            flow_nodes,
            connections,
            global_vars,
            material_reqs,
            project_root,
        )
        
        metadata = {
            "chapter_count": chapter_count,
            "character_count": len(characters),
            "total_dialogues": sum(len(scene.get("dialogues", [])) for ch in chapters for scene in ch.get("scenes", [])),
            "theme": theme,
            "style": style,
            "node_count": len(flow_nodes),
            "connection_count": len(connections),
            "generation_time": datetime.now().isoformat()
        }
        
        return {
            "files": output_files,
            "metadata": metadata
        }
    
    def _generate_outline(self, theme: str, style: str, chapter_count: int, characters: List[Dict[str, Any]], narrative_pov: str, first_person_name: str) -> Dict[str, Any]:
        """生成故事大纲，若用户预设角色则需纳入大纲。"""

        char_hint = "".join([
            f"- {c.get('name','未命名')} ({c.get('role','角色')}): {c.get('persona','')}\n"
            for c in characters
        ]) if characters else "(无预设角色，可自行设定3-5个角色)"

        pov_text = "第一人称" if narrative_pov == "first" else "第三人称"

        prompt = f"""你是一位专业的视觉小说编剧。请为一个{theme}主题、{style}风格的GalGame创作故事大纲。

叙述视角：{pov_text}。若为第一人称，叙述人名称为“{first_person_name}”。
若下方提供了预设角色，请确保他们出现在大纲与后续章节中并保持人设一致：
{char_hint}

要求：
1. 共{chapter_count}个章节
2. 包含引人入胜的开篇、起承转合的情节发展、令人难忘的结局
3. 设定3-5个主要角色（包括主角）
4. 每个章节有明确的情节目标和转折点
5. 符合{style}的氛围和节奏

请以JSON格式输出，包含：
- title: 作品标题
- summary: 整体简介（200字左右）
- main_conflict: 核心矛盾
- chapter_outlines: 数组，每个章节包含
  - chapter_number: 章节号
  - chapter_title: 章节标题
  - summary: 章节概要
  - key_events: 关键事件列表
  - emotional_tone: 情感基调（如"轻松愉快"、"紧张刺激"等）
"""
        
        response = self.llm_client.create_message(
            messages=[{"role": "user", "content": prompt}],
            system="你是一位专业的视觉小说编剧，擅长创作引人入胜的故事大纲。",
            temperature=0.8
        )

        # 解析JSON响应
        content_blocks = response.get("content", [])
        content = "".join(block.get("text", "") for block in content_blocks if isinstance(block, dict))
        
        # 尝试提取JSON（可能包含在markdown代码块中）
        try:
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()
            
            outline = json.loads(json_str)
            return outline
        except Exception as e:
            self.logger.warning(f"JSON解析失败，返回文本格式: {e}")
            return {
                "title": f"{theme}物语",
                "summary": content[:500],
                "raw_content": content
            }
    
    def _generate_characters(self, outline: Dict[str, Any], theme: str) -> List[Dict[str, Any]]:
        """生成角色设定"""
        
        story_summary = outline.get("summary", "")
        
        prompt = f"""基于以下故事大纲，创建3-5个主要角色的详细设定：

故事大纲：
{story_summary}

请为每个角色创建详细设定，以JSON格式输出数组，每个角色包含：
- name: 角色姓名
- role: 角色定位（如"主角"、"女主角"、"配角"等）
- age: 年龄
- personality: 性格特点（3-5个关键词）
- appearance: 外貌描述（详细，用于后续立绘生成）
- background: 背景故事
- relationships: 与其他角色的关系
- voice_characteristics: 说话方式特点
- expressions: 常用表情列表（如["neutral", "happy", "sad", "angry", "surprised"]）
"""
        
        response = self.llm_client.create_message(
            messages=[{"role": "user", "content": prompt}],
            system="你是专业的角色设计师，擅长创作立体生动的角色形象。",
            temperature=0.7
        )
        
        content = "".join(block.get("text", "") for block in response.get("content", []) if isinstance(block, dict))
        
        try:
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()
            
            characters = json.loads(json_str)
            
            # 确保是列表
            if isinstance(characters, dict):
                characters = [characters]
            
            return characters
        except Exception as e:
            self.logger.warning(f"角色JSON解析失败: {e}")
            return []

    def _prepare_characters_from_config(self, chars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将用户配置的角色转为统一结构，供后续章节引用。"""
        prepared = []
        for c in chars:
            name = c.get("name") or c.get("char_name") or "角色"
            prepared.append({
                "name": name,
                "role": c.get("role", "主角"),
                "personality": c.get("persona", "") or c.get("persona_keywords", ""),
                "appearance": c.get("appearance", "外貌由你发挥"),
                "background": c.get("background", ""),
                "voice_characteristics": c.get("voice_characteristics", ""),
                "expressions": c.get("expressions", ["neutral", "happy", "sad", "angry"]),
            })
        return prepared

    def _refine_characters(self, chars: List[Dict[str, Any]], theme: str, weight: float) -> List[Dict[str, Any]]:
        """基于用户设定进行优化，保持名字与核心人设，允许AI补充细节。"""
        base_chars = self._prepare_characters_from_config(chars)
        try:
            prompt = f"""你是角色设定优化师。请在保持用户提供的名字与核心人设的前提下，补充细节并轻度优化（不要改名）。

主题：{theme}
用户角色设定（保持一致度不低于 {int(weight*100)}%）：
{json.dumps(base_chars, ensure_ascii=False, indent=2)}

输出JSON数组，字段：name, role, age, personality(3-5关键词), appearance, background, relationships, voice_characteristics, expressions。不得改名。"""

            response = self.llm_client.create_message(
                messages=[{"role": "user", "content": prompt}],
                system="你是专业的角色设定优化师，尊重用户角色，不改名，仅补充细节。",
                temperature=0.5
            )
            content = "".join(block.get("text", "") for block in response.get("content", []) if isinstance(block, dict))
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()
            refined = json.loads(json_str)
            if isinstance(refined, dict):
                refined = [refined]
            # 保证顺序与数量不减少，缺失则回填原数据
            merged = []
            for idx, base in enumerate(base_chars):
                if idx < len(refined):
                    r = refined[idx]
                    r["name"] = base.get("name")  # 强制保持名字
                    merged.append({**base, **r})
                else:
                    merged.append(base)
            return merged
        except Exception as exc:
            self.logger.warning(f"角色优化失败，回退原设定: {exc}")
            return base_chars
    
    def _generate_chapter(
        self,
        chapter_num: int,
        outline: Dict[str, Any],
        characters: List[Dict[str, Any]],
        style: str,
        narrative_pov: str,
        first_person_name: str,
        first_person_has_portrait: bool,
        first_person_has_voice: bool,
        first_person_cg_presence: bool,
        target_words: int,
        target_dialogues: int,
    ) -> Dict[str, Any]:
        """生成单个章节的详细内容"""
        
        # 获取章节大纲
        chapter_outlines = outline.get("chapter_outlines", [])
        chapter_outline = None
        
        for ch in chapter_outlines:
            if ch.get("chapter_number") == chapter_num:
                chapter_outline = ch
                break
        
        if not chapter_outline:
            chapter_outline = {
                "chapter_number": chapter_num,
                "chapter_title": f"第{chapter_num}章",
                "summary": "章节内容"
            }
        
        # 角色信息列表
        char_names = [c.get("name", "未知") for c in characters]
        char_info = json.dumps(characters, ensure_ascii=False, indent=2)
        pov_text = "第一人称" if narrative_pov == "first" else "第三人称"
        first_person_note = """
    叙述视角要求：如果是第一人称，请让“{name}”作为叙述者，但对话时使用角色名标注；
    第一人称立绘={has_portrait}，配音={has_voice}，CG出现={cg_presence}。
    只有在需要第一人称出现的CG画面时再描述“我”的外显动作，其他时候避免给第一人称立绘/配音。""".format(
            name=first_person_name,
            has_portrait="是" if first_person_has_portrait else "否",
            has_voice="是" if first_person_has_voice else "否",
            cg_presence="是" if first_person_cg_presence else "否",
        )
        
        prompt = f"""基于以下信息，编写第{chapter_num}章的详细剧本：

章节大纲：
{json.dumps(chapter_outline, ensure_ascii=False, indent=2)}

角色设定（保持设定一致）：
{char_info}

{first_person_note}

要求：
1. 对话条数控制在 {target_dialogues-2} 到 {target_dialogues+2} 条
2. 每条对话标注说话者
3. 包含场景描述、动作描写、心理活动
4. 对话符合{style}风格
5. 控制总字数在 {max(1000, int(target_words*0.7))} 到 {int(target_words*1.2)} 字

以JSON格式输出：
{{
  "chapter_number": {chapter_num},
  "chapter_title": "章节标题",
  "scenes": [
    {{
      "scene_number": 1,
      "location": "场景地点",
      "time": "时间",
      "description": "场景描述",
      "dialogues": [
        {{
          "speaker": "角色名",
          "content": "对话内容",
          "emotion": "情绪",
          "action": "动作描写（可选）"
        }}
      ]
    }}
  ]
}}
"""
        
        response = self.llm_client.create_message(
            messages=[{"role": "user", "content": prompt}],
            system="你是专业的剧本作家，擅长编写生动的对话和场景。",
            temperature=0.7
        )
        
        content = "".join(block.get("text", "") for block in response.get("content", []) if isinstance(block, dict))
        
        try:
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()
            
            chapter_data = json.loads(json_str)
            return chapter_data
        except Exception as e:
            self.logger.warning(f"章节JSON解析失败: {e}")
            return {
                "chapter_number": chapter_num,
                "chapter_title": chapter_outline.get("chapter_title", f"第{chapter_num}章"),
                "raw_content": content
            }

    def _build_flow_graph(
        self,
        chapters: List[Dict[str, Any]],
        characters: List[Dict[str, Any]],
        style: str,
        project_root: Path,
        first_person_name: str,
        first_person_has_portrait: bool,
        first_person_has_voice: bool,
    ) -> tuple[List[FlowNodeData], List[ConnectionData], List[GlobalVariable], List[MaterialRequirement]]:
        """将章节/对白转换为 VNEngine 节点、连接和全局变量。"""

        nodes: List[FlowNodeData] = []
        connections: List[ConnectionData] = []
        material_reqs: List[MaterialRequirement] = []

        node_id = 1
        x, y = 100, 100
        last_id: Optional[int] = None

        # 全局变量：默认好感度
        global_vars = [
            GlobalVariable(name="favorability", initial=0.0, type="float"),
        ]

        for chapter_idx, chapter in enumerate(chapters, start=1):
            scenes = chapter.get("scenes", []) or []
            for scene_idx, scene in enumerate(scenes, start=1):
                location = scene.get("location", f"scene_{chapter_idx}_{scene_idx}")
                bg_slug = image_utils.slugify_name(str(location) or f"scene_{scene_idx}")
                background_path = f"resources/backgrounds/bg_{bg_slug}.png"
                bgm_path = f"resources/bgm/main_theme.mp3"

                dialogues = scene.get("dialogues", []) or []
                for dlg_idx, dialogue in enumerate(dialogues, start=1):
                    speaker = dialogue.get("speaker", "旁白")
                    sp_slug = image_utils.slugify_name(speaker or "narrator")
                    if speaker == first_person_name and not first_person_has_portrait:
                        portrait_path = ""
                    else:
                        portrait_path = f"resources/portraits/{speaker}/{sp_slug}_neutral.png"

                    if speaker == first_person_name and not first_person_has_voice:
                        voice_path = ""
                    else:
                        voice_path = f"resources/voices/{speaker}/{bg_slug}_{dlg_idx}.mp3"

                    content_parts = []
                    if dialogue.get("action"):
                        content_parts.append(dialogue.get("action"))
                    if dialogue.get("content"):
                        content_parts.append(dialogue.get("content"))
                    full_content = "\n".join(content_parts)

                    node = FlowNodeData(
                        id=node_id,
                        node_type="text",
                        title=f"{speaker}的对话",
                        content=full_content,
                        speaker=speaker,
                        portrait=portrait_path,
                        background=background_path,
                        voice=voice_path,
                        bgm=bgm_path,
                        bgm_loop=True,
                        x=x,
                        y=y,
                    )
                    nodes.append(node)

                    # 连接
                    if last_id is not None:
                        connections.append(ConnectionData(source=last_id, target=node_id))
                    last_id = node_id
                    node_id += 1
                    y += 140

                    # 素材需求记录
                    if portrait_path:
                        material_reqs.append(
                            MaterialRequirement(
                                material_type="portrait",
                                material_id=f"portrait_{sp_slug}",
                                description=f"{speaker} 立绘",
                                node_ids=[str(node.id)],
                                parameters={"character": speaker},
                            )
                        )
                    if voice_path:
                        material_reqs.append(
                            MaterialRequirement(
                                material_type="voice",
                                material_id=f"voice_{sp_slug}_{dlg_idx}",
                                description=f"{speaker} 对白",
                                node_ids=[str(node.id)],
                                parameters={"character": speaker, "emotion": dialogue.get("emotion", "neutral")},
                            )
                        )

                # choice 节点
                options = scene.get("options")
                if options:
                    choice_node = FlowNodeData(
                        id=node_id,
                        node_type="choice",
                        title=f"选择 - {location}",
                        content="",
                        speaker="",
                        portrait="",
                        background=background_path,
                        voice="",
                        bgm=bgm_path,
                        bgm_loop=True,
                        options=[opt.get("text", "") for opt in options],
                        x=x + 200,
                        y=y,
                    )
                    nodes.append(choice_node)
                    if last_id is not None:
                        connections.append(ConnectionData(source=last_id, target=node_id))
                    last_id = node_id
                    node_id += 1
                    y += 140

                # condition 节点
                cond = scene.get("condition")
                if cond:
                    cond_node = FlowNodeData(
                        id=node_id,
                        node_type="condition",
                        title=f"条件 - {location}",
                        content="",
                        speaker="",
                        portrait="",
                        background=background_path,
                        voice="",
                        bgm=bgm_path,
                        bgm_loop=True,
                        condition_var=cond.get("var", "favorability"),
                        condition_op=cond.get("op", ">="),
                        condition_value=str(cond.get("value", 0)),
                        condition_const=True,
                        x=x + 200,
                        y=y,
                    )
                    nodes.append(cond_node)
                    if last_id is not None:
                        connections.append(ConnectionData(source=last_id, target=node_id))
                    last_id = node_id
                    node_id += 1
                    y += 140

                # 每个场景后重置 Y 并推进 X
                y = 100
                x += 240

        return nodes, connections, global_vars, material_reqs
    
    def _save_plot_data(
        self,
        outline: Dict[str, Any],
        characters: List[Dict[str, Any]],
        chapters: List[Dict[str, Any]],
        flow_nodes: List[FlowNodeData],
        connections: List[ConnectionData],
        global_vars: List[GlobalVariable],
        material_reqs: List[MaterialRequirement],
        project_root: Path,
    ) -> List[str]:
        """保存剧情与节点数据到工程内 resources/plot"""

        output_dir = project_root / "resources" / "plot"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        output_files: List[str] = []

        outline_file = output_dir / f"outline_{timestamp}.json"
        with open(outline_file, 'w', encoding='utf-8') as f:
            json.dump(outline, f, ensure_ascii=False, indent=2)
        output_files.append(outline_file.relative_to(project_root).as_posix())
        self.logger.info(f"大纲已保存: {outline_file}")

        characters_file = output_dir / f"characters_{timestamp}.json"
        with open(characters_file, 'w', encoding='utf-8') as f:
            json.dump(characters, f, ensure_ascii=False, indent=2)
        output_files.append(characters_file.relative_to(project_root).as_posix())
        self.logger.info(f"角色设定已保存: {characters_file}")

        chapters_file = output_dir / f"chapters_{timestamp}.json"
        with open(chapters_file, 'w', encoding='utf-8') as f:
            json.dump(chapters, f, ensure_ascii=False, indent=2)
        output_files.append(chapters_file.relative_to(project_root).as_posix())
        self.logger.info(f"章节内容已保存: {chapters_file}")

        full_script = {
            "outline": outline,
            "characters": characters,
            "chapters": chapters,
            "metadata": {
                "generation_time": timestamp,
                "chapter_count": len(chapters),
                "character_count": len(characters),
            },
        }

        full_file = output_dir / f"full_script_{timestamp}.json"
        with open(full_file, 'w', encoding='utf-8') as f:
            json.dump(full_script, f, ensure_ascii=False, indent=2)
        output_files.append(full_file.relative_to(project_root).as_posix())
        self.logger.info(f"完整剧本已保存: {full_file}")

        flow_bundle = {
            "flow_nodes": [n.model_dump() for n in flow_nodes],
            "connections": [c.model_dump() for c in connections],
            "global_variables": [g.model_dump() for g in global_vars],
            "material_requirements": [m.model_dump() for m in material_reqs],
        }

        flow_file = output_dir / f"flow_graph_{timestamp}.json"
        with open(flow_file, 'w', encoding='utf-8') as f:
            json.dump(flow_bundle, f, ensure_ascii=False, indent=2)
        output_files.append(flow_file.relative_to(project_root).as_posix())
        self.logger.info(f"节点数据已保存: {flow_file}")

        return output_files
    
    def cleanup(self):
        """清理资源"""
        self.logger.info("PlotAgent资源清理完成")
