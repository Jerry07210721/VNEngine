# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - Prompt模板库
存储各类Agent的标准化提示词模板
"""
from typing import Dict, Any


class PromptTemplates:
    """
    提示词模板库
    包含人设、剧情、立绘、背景、CG、语音、BGM等各类生成的提示词模板
    """
    
    # ==================== 人设与剧情生成模板 ====================
    
    CHARACTER_PLOT_SYSTEM_PROMPT = """你是一位经验丰富的Galgame编剧与人设设计师。
你的任务是根据用户提供的游戏主题、风格偏好，生成符合Galgame标准的角色人设与剧本。

核心要求：
1. 人设必须包含：角色ID、姓名、性别、外貌（详细描述供立绘生成）、性格（详细描述供对白生成）、声线风格（供语音生成）、默认动作、默认表情。
2. 剧本必须采用节点化结构，兼容VNEngine的节点类型（text/select/condition）。
3. 剧本节点必须包含：node_id、node_type、title、speaker、content、options（选择节点）、condition_var/condition_op/condition_value（条件节点）、scene_description、atmosphere等字段。
4. 剧本必须有明确的起始节点（is_start=True）。
5. 剧本必须包含分支与汇合，支持多结局。
6. 对白必须生动、符合角色性格，避免机械化对话。

输出格式：严格按JSON格式输出，包含以下两个顶层字段：
{
  "characters": [角色对象列表],
  "script_nodes": [剧本节点对象列表]
}

禁止输出任何额外文字，只返回JSON。"""

    CHARACTER_PLOT_USER_PROMPT_TEMPLATE = """请根据以下要求生成Galgame人设与剧本：

【游戏主题】：{game_theme}
【角色数量】：{char_count}个主要角色
【剧情长度】：约{script_length}字
【分支数量】：{branch_count}个主要分支
【剧情风格】：{script_style}
【额外要求】：{extra_requirements}

【角色人设要求】：
每个角色必须包含以下字段：
- char_id: 唯一标识（如char_001）
- name: 姓名
- gender: 性别（男/女/其他）
- appearance: 外貌详细描述（供立绘生成，需包含发型、发色、眼睛颜色、服装细节、身材特征等，至少50字）
- personality: 性格详细描述（供对白生成，需包含性格特点、说话习惯、行为方式等，至少50字）
- voice_style: 声线风格（如萝莉音、御姐音、少年音、温柔男声等）
- default_pose: 默认动作（如站立、坐姿、挥手）
- default_expression: 默认表情（如平静、微笑、严肃）

【剧本节点要求】：
1. 起始节点：必须有一个is_start=True的文本节点，作为游戏开场。
2. 文本节点示例：
{{
  "node_id": "node_001",
  "node_type": "text",
  "title": "开场白",
  "is_start": true,
  "speaker": "旁白",
  "content": "这是一个普通的夏日午后...",
  "scene_description": "教室，阳光透过窗户照进来，温暖明亮",
  "atmosphere": "温馨",
  "x": 100,
  "y": 100
}}
3. 选择节点示例：
{{
  "node_id": "node_005",
  "node_type": "select",
  "title": "关键选择",
  "options": ["选项1：帮助她", "选项2：离开"],
  "x": 300,
  "y": 200
}}
4. 条件节点示例：
{{
  "node_id": "node_010",
  "node_type": "condition",
  "title": "好感度判断",
  "condition_var": "affinity",
  "condition_op": ">=",
  "condition_value": 80,
  "condition_const": true,
  "x": 500,
  "y": 300
}}

【节点连接要求】：
- 文本节点通常连接到下一个节点（单出口）
- 选择节点必须为每个选项创建一条连接（多出口）
- 条件节点必须有True和False两条连接

现在开始生成，只返回JSON，不要任何额外文字。"""

    # ==================== 立绘生成模板 ====================
    
    PORTRAIT_BASE_PROMPT_TEMPLATE = """(masterpiece, best quality, ultra-detailed, 8k), anime girl, solo, Galgame character sheet, clean line art, transparent background, 
{appearance}, {personality}_expression, 
sharp focus, perfect anatomy, detailed hair strands, detailed eyes, soft lighting, consistent color scheme, fit for Galgame portrait display"""

    PORTRAIT_DIFF_PROMPT_TEMPLATE = """(masterpiece, best quality, same character as reference, consistent appearance with base portrait), 
based on the base portrait, {pose}_pose, {expression}_expression, 
consistent with the base portrait's clothing, hair, and facial features, same pose as reference skeleton, transparent background, clean line art, detailed expression, fit for Galgame portrait difference"""

    # 表情详细描述映射
    EXPRESSION_DETAILS = {
        "开心": "happy expression, bright smile, eyes curved into crescents, slight blush, cheerful mood",
        "生气": "angry expression, frown, sharp eyes, furrowed brows, clenched teeth, tense mood",
        "哭": "crying expression, tears streaming down cheeks, puffy red eyes, quivering lips, sad mood",
        "害羞": "shy expression, blushing cheeks, looking away, embarrassed smile, nervous mood",
        "惊讶": "surprised expression, wide open eyes, raised eyebrows, open mouth, shocked mood",
        "平静": "calm expression, gentle gaze, neutral mouth, serene mood"
    }

    # ==================== 背景生成模板 ====================
    
    BACKGROUND_PROMPT_TEMPLATE = """(masterpiece, best quality, ultra-detailed), anime background, Galgame scene, 
{scene_description}, {atmosphere} atmosphere, 
no characters, clean background, detailed textures, soft lighting, fit for Galgame scene rendering"""

    # ==================== CG生成模板 ====================
    
    CG_PROMPT_TEMPLATE = """Galgame CG, masterpiece, best quality, ultra-detailed, 8k, cinematic lighting, 
{plot_description}, {character_appearance}, {atmosphere} atmosphere, 
detailed background, perfect anatomy, emotional expression, high contrast, fit for Galgame key scene display"""

    # ==================== 语音生成模板 ====================
    
    VOICE_GENERATION_PARAMS_TEMPLATE = """Voice style: {voice_style}
Emotion: {emotion}
Text: {dialogue_content}
Output format: OGG, 44100Hz
Tone requirements: Match the character's personality, natural intonation, no mechanical sound"""

    # ==================== BGM生成模板 ====================
    
    BGM_GENERATION_PARAMS_TEMPLATE = """Genre: Anime BGM
Atmosphere: {atmosphere}
Instrument: {instrument}
Duration: {duration} seconds
Loop requirement: {loop_flag}
Sound quality: Clear, no noise, balanced volume
Fit scenario: Galgame {scene_type}"""

    @classmethod
    def get_character_plot_prompt(
        cls,
        game_theme: str,
        char_count: int,
        script_length: int,
        branch_count: int,
        script_style: str,
        extra_requirements: str = "无"
    ) -> tuple[str, str]:
        """
        获取人设与剧情生成的提示词
        
        Returns:
            tuple[str, str]: (系统提示词, 用户提示词)
        """
        user_prompt = cls.CHARACTER_PLOT_USER_PROMPT_TEMPLATE.format(
            game_theme=game_theme,
            char_count=char_count,
            script_length=script_length,
            branch_count=branch_count,
            script_style=script_style,
            extra_requirements=extra_requirements
        )
        return cls.CHARACTER_PLOT_SYSTEM_PROMPT, user_prompt
    
    @classmethod
    def get_portrait_base_prompt(cls, appearance: str, personality: str) -> str:
        """
        获取立绘基准图提示词
        
        Args:
            appearance: 角色外貌描述
            personality: 角色性格描述
            
        Returns:
            str: 立绘基准图Prompt
        """
        return cls.PORTRAIT_BASE_PROMPT_TEMPLATE.format(
            appearance=appearance,
            personality=personality
        )
    
    @classmethod
    def get_portrait_diff_prompt(cls, pose: str, expression: str) -> str:
        """
        获取立绘差分提示词
        
        Args:
            pose: 动作类型
            expression: 表情类型
            
        Returns:
            str: 立绘差分Prompt
        """
        expression_detail = cls.EXPRESSION_DETAILS.get(expression, expression)
        return cls.PORTRAIT_DIFF_PROMPT_TEMPLATE.format(
            pose=pose,
            expression=expression_detail
        )
    
    @classmethod
    def get_background_prompt(cls, scene_description: str, atmosphere: str) -> str:
        """
        获取背景图提示词
        
        Args:
            scene_description: 场景描述
            atmosphere: 氛围标签
            
        Returns:
            str: 背景图Prompt
        """
        return cls.BACKGROUND_PROMPT_TEMPLATE.format(
            scene_description=scene_description,
            atmosphere=atmosphere
        )
    
    @classmethod
    def get_cg_prompt(
        cls,
        plot_description: str,
        character_appearance: str,
        atmosphere: str
    ) -> str:
        """
        获取CG提示词
        
        Args:
            plot_description: 剧情描述
            character_appearance: 角色外貌
            atmosphere: 氛围标签
            
        Returns:
            str: CG Prompt
        """
        return cls.CG_PROMPT_TEMPLATE.format(
            plot_description=plot_description,
            character_appearance=character_appearance,
            atmosphere=atmosphere
        )
