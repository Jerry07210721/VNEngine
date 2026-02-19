# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - 数据模型定义
使用 Pydantic 实现数据验证和序列化
"""

from typing import List, Dict, Optional, Any, Literal
from pydantic import BaseModel, Field, validator, model_validator
from datetime import datetime


# ==================== 用户配置相关模型 ====================

class ProjectConfig(BaseModel):
    """工程基础配置"""
    project_path: str = Field(..., description="工程保存路径（绝对路径）")
    project_name: str = Field(..., description="工程名称")
    window_width: int = Field(1280, description="窗口宽度", ge=800, le=3840)
    window_height: int = Field(720, description="窗口高度", ge=600, le=2160)
    engine_version: str = Field("V2.7-AI", description="引擎版本")


class StoryConfig(BaseModel):
    """故事配置"""
    title: str = Field(..., description="故事标题")
    style: str = Field(..., description="故事风格（如：日系校园、纯爱、治愈）")
    plot_outline: str = Field(..., description="剧情梗概")
    # 长篇故事：放宽上限（由 UI/提示词控制实际生成规模）
    text_volume: int = Field(..., description="文本量（字数）", ge=1000, le=500000)
    chapter_count: int = Field(5, description="章节数量", ge=1, le=100)
    enable_choice_node: bool = Field(False, description="是否开启选择节点（仅在开启多分支时可用）")
    enable_condition_node: bool = Field(False, description="是否开启条件节点（仅在开启多分支时可用）")
    enable_multi_branch: bool = Field(False, description="是否开启多分支章节规划（允许并行路线/多结局）")
    allow_loop_story: bool = Field(False, description="允许出现循环剧情（仅多分支；需 choice/condition 提供跳出循环的出口）")
    enable_single_route: bool = Field(False, description="是否启用单线叙事（禁止章节级分支/并行路线）")
    condition_type: str = Field("favorability", description="条件类型（如：好感度）")
    character_hint_weight: float = Field(0.7, ge=0.0, le=1.0, description="角色设定遵循用户配置的权重(0-1)")
    narrative_pov: Literal["first", "third"] = Field("third", description="叙述视角：第一人称/第三人称")
    first_person_name: str = Field("我", description="第一人称的名字/代称")
    first_person_has_portrait: bool = Field(False, description="第一人称是否有立绘")
    first_person_has_voice: bool = Field(False, description="第一人称是否有配音")
    first_person_cg_presence: bool = Field(True, description="第一人称是否会出现在CG中")
    first_person_cg_notes: str = Field("", description="第一人称在CG中的表现说明")
    cg_count: int = Field(0, description="每章目标CG数量（用于章节详稿标注）", ge=0, le=20)

    # Step4（逐章详稿）文本量控制：经验上 LLM 常低估字数/字符数，允许通过倍率放大写作目标
    step4_word_boost_factor: float = Field(
        1.0,
        ge=1.0,
        le=3.0,
        description="Step4 逐章详稿写作目标字数放大倍率（用于抵消模型计数偏差；1.0 表示不放大）",
    )

    @model_validator(mode="after")
    def _enforce_story_mode_constraints(self):
        """强制配置互斥/依赖规则：

        - 单线叙事与多分支互斥：如果同时为 True，优先保留单线叙事并关闭多分支。
        - 只有开启多分支，才能启用选择/条件节点；否则强制关闭。
        - 只有开启多分支，才允许循环剧情；并且循环剧情必须至少启用 choice/condition 之一用于跳出循环。
        """
        if bool(self.enable_single_route) and bool(self.enable_multi_branch):
            self.enable_multi_branch = False

        if not bool(self.enable_multi_branch):
            self.enable_choice_node = False
            self.enable_condition_node = False
            self.allow_loop_story = False

        # 循环剧情依赖 choice/condition 作为“跳出循环”的出口
        if bool(self.enable_multi_branch) and bool(self.allow_loop_story):
            if not (bool(self.enable_choice_node) or bool(self.enable_condition_node)):
                # 默认启用条件节点来保证可跳出循环
                self.enable_condition_node = True

        return self

    # 语音合成（GPT-SoVITS）相关配置
    voice_tts_style: str = Field("2", description="语音模型版本 style：1=普遍模型, 2=专业模型, 3=多语言模型")
    voice_tts_genre: int = Field(1, description="语音模型类别 genre：0=参考原音频, 1=语气参考模式", ge=0, le=1)
    voice_use_emotion_ext: bool = Field(True, description="是否根据对白情绪发送 ext 语气参数")
    voice_emotion_strength: float = Field(1.0, description="情绪强度缩放(0-1)，用于 ext 参数", ge=0.0, le=1.0)


class CharacterConfig(BaseModel):
    """角色配置"""
    char_id: str = Field(..., description="角色ID（唯一标识）")
    char_name: str = Field(..., description="角色名称")
    role: str = Field("主角", description="角色定位，如主角/女主角/配角")
    is_first_person: bool = Field(False, description="是否为第一人称角色")
    is_player: bool = Field(False, description="是否为玩家角色")
    persona_keywords: str = Field(..., description="人设关键词")
    reference_image: Optional[str] = Field(None, description="参考图片路径（可选）")
    voice_tone: Optional[str] = Field(None, description="语音音色描述（如：青年、温和、语速中等）")
    voice_model_id: Optional[str] = Field(None, description="GPT-SoVITS语音模型ID（用于语音生成）")


class MaterialConfig(BaseModel):
    """素材配置"""
    portrait_format: str = Field("png", description="立绘格式")
    background_format: str = Field("jpg", description="背景格式")
    cg_format: str = Field("png", description="CG格式")
    voice_format: str = Field("mp3", description="语音格式")
    bgm_format: str = Field("mp3", description="BGM格式")


class EnableAgentsConfig(BaseModel):
    """Agent启用配置"""
    plot_agent: bool = Field(True, description="剧情对白Agent（必选）")
    portrait_agent: bool = Field(True, description="立绘差分Agent（可选）")
    background_agent: bool = Field(True, description="背景生成Agent（可选）")
    cg_agent: bool = Field(True, description="CG生成Agent（可选）")
    voice_api: bool = Field(True, description="语音生成接口（可选）")
    bgm_api: bool = Field(True, description="BGM生成接口（可选）")


class UserConfig(BaseModel):
    """用户输入参数模型（完整配置）"""
    project_info: ProjectConfig
    story_config: StoryConfig
    character_config: List[CharacterConfig] = Field(..., min_items=1, description="角色配置列表（至少1个）")
    enable_agents: EnableAgentsConfig
    material_config: MaterialConfig


# ==================== 任务调度相关模型 ====================

class TaskAssignment(BaseModel):
    """任务分派模型"""
    task_id: str = Field(..., description="任务ID（唯一标识）")
    agent_type: Literal["plot", "portrait", "background", "cg", "voice", "bgm", "integrator"] = Field(
        ..., description="Agent类型"
    )
    task_type: str = Field("", description="任务类型（便于Agent内部路由）")
    agent_name: Optional[str] = Field(None, description="执行该任务的Agent名称（注册表键）")
    task_content: str = Field(..., description="任务内容描述")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="任务参数")
    target_node_ids: Optional[List[str]] = Field(None, description="目标节点ID列表")
    priority: int = Field(1, description="任务优先级（数字越小优先级越高）", ge=1, le=10)
    timeout: int = Field(300, description="超时时间（秒）", ge=60)
    created_at: datetime = Field(default_factory=datetime.now, description="任务创建时间")

    @property
    def agent_key(self) -> str:
        """返回用于 Agent 注册表的键名。"""
        return self.agent_name or f"{self.agent_type}_agent"


class TaskDetail(BaseModel):
    """任务详情"""
    task_id: str = Field(..., description="任务ID")
    task_content: Optional[str] = Field(None, description="任务内容描述")
    status: Literal["pending", "processing", "completed", "failed"] = Field(
        ..., description="任务状态"
    )
    result_path: Optional[str] = Field(None, description="结果文件路径（相对工程目录）")
    message: str = Field("", description="任务消息")
    error_info: Optional[str] = Field(None, description="错误信息（任务失败时）")


class ProgressTrack(BaseModel):
    """进度跟踪模型"""
    total_tasks: int = Field(0, description="总任务数", ge=0)
    completed_tasks: int = Field(0, description="已完成任务数", ge=0)
    failed_tasks: int = Field(0, description="失败任务数", ge=0)
    processing_tasks: int = Field(0, description="处理中任务数", ge=0)
    pending_tasks: int = Field(0, description="待处理任务数", ge=0)
    task_details: List[TaskDetail] = Field(default_factory=list, description="任务详情列表")
    current_stage: str = Field("", description="当前阶段描述")
    progress_percentage: float = Field(0.0, description="总体进度百分比", ge=0.0, le=100.0)


# ==================== 素材需求相关模型 ====================

class MaterialRequirement(BaseModel):
    """素材需求模型"""
    material_type: Literal["portrait", "background", "cg", "voice", "bgm"] = Field(
        ..., description="素材类型"
    )
    material_id: str = Field(..., description="素材ID（唯一标识）")
    description: str = Field(..., description="素材描述")
    node_ids: List[str] = Field(default_factory=list, description="关联节点ID列表")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="素材生成参数")


# ==================== Agent响应相关模型 ====================

class AgentResponse(BaseModel):
    """Agent响应模型"""
    status: Literal["success", "failure", "processing"] = Field(..., description="响应状态")
    message: str = Field("", description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")
    error_code: Optional[str] = Field(None, description="错误代码（失败时）")
    error_detail: Optional[str] = Field(None, description="错误详情（失败时）")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间")
    # 执行元信息（便于进度跟踪）
    agent_name: Optional[str] = Field(None, description="执行Agent名称")
    task_type: Optional[str] = Field(None, description="任务类型")
    output_files: List[str] = Field(default_factory=list, description="输出文件路径列表")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="附加元数据")
    time_cost: Optional[float] = Field(None, description="耗时（秒）")
    error_message: Optional[str] = Field(None, description="错误消息（失败时）")


# ==================== 工程整合相关模型 ====================
class ConditionRule(BaseModel):
    """条件节点规则（顺序匹配）。

    - exprs: 每行一个 var_expr 表达式
    - logic: 多表达式的连接方式
    """

    name: str = Field("", description="规则名称（可选）")
    logic: Literal["and", "or"] = Field("and", description="多表达式连接方式")
    exprs: List[str] = Field(default_factory=list, description="表达式列表（每行一个）")


class FlowNodeData(BaseModel):
    """流程节点数据（对齐VNEngine格式）"""
    id: int = Field(..., description="节点ID")
    node_type: Literal["text", "choice", "condition", "function"] = Field(..., description="节点类型")
    title: str = Field(..., description="节点标题")
    content: str = Field("", description="节点内容")
    speaker: str = Field("", description="发言者")
    portrait: str = Field("", description="立绘路径")
    portrait2: str = Field("", description="第二立绘路径")
    background: str = Field("", description="背景路径")
    voice: str = Field("", description="语音路径")
    sfx: str = Field("", description="音效路径")
    text_style_enabled: bool = Field(False, description="是否启用该节点的文字样式覆盖")
    text_styles: Dict[str, Any] = Field(default_factory=dict, description="该节点的文字样式覆盖配置")
    bgm: str = Field("", description="BGM路径")
    bgm_loop: bool = Field(True, description="BGM是否循环")
    stop_bgm: bool = Field(False, description="是否停止BGM")
    bg_fade_in: bool = Field(False, description="背景是否淡入")
    bg_fade_duration: float = Field(0.45, description="背景淡入时长（秒）", ge=0.0, le=10.0)
    portrait_fade: bool = Field(False, description="立绘是否淡入")
    portrait_fade_out: bool = Field(False, description="立绘是否淡出")
    portrait2_fade: bool = Field(False, description="第二立绘是否淡入")
    portrait2_fade_out: bool = Field(False, description="第二立绘是否淡出")
    portrait_bounce: bool = Field(False, description="立绘是否弹跳（进入节点时）")
    portrait2_bounce: bool = Field(False, description="第二立绘是否弹跳（进入节点时）")
    hide_textbox: bool = Field(False, description="是否隐藏文本框")
    skip_dialogue: bool = Field(False, description="选择/条件节点：进入节点时是否跳过对白展示并直接执行对应逻辑")
    ui_file: str = Field("", description="UI文件路径")
    video: str = Field("", description="视频路径")
    video_loop: bool = Field(False, description="视频是否循环")
    options: List[str] = Field(default_factory=list, description="选项列表（选择节点）")

    # 条件节点（新规则列表）
    condition_rules: List[ConditionRule] = Field(
        default_factory=list,
        description="条件规则列表（顺序匹配；规则 i 对应第 i 条出边；最后一条出边为否则分支）",
    )

    sub_dialogues: List[Dict[str, Any]] = Field(default_factory=list, description="子对话列表")
    var_ops: List[Dict[str, Any]] = Field(default_factory=list, description="变量运算列表")

    # 功能节点（function）专用字段：绑定到宿主节点并按规则执行脚本
    bound_to: Optional[int] = Field(None, description="功能节点绑定的宿主节点ID")
    bound_offset: List[float] = Field(default_factory=lambda: [0.0, 0.0], description="功能节点相对宿主节点偏移")
    rules: List[Dict[str, Any]] = Field(default_factory=list, description="功能节点规则列表（condition/action 等）")

    x: float = Field(0.0, description="节点X坐标")
    y: float = Field(0.0, description="节点Y坐标")


class ConnectionData(BaseModel):
    """连接数据"""
    source: int = Field(..., description="源节点ID")
    target: int = Field(..., description="目标节点ID")


class GlobalVariable(BaseModel):
    """全局变量"""
    name: str = Field(..., description="变量名")
    initial: float = Field(0.0, description="初始值")
    type: str = Field("float", description="变量类型")


# ==================== AI工程文件专属模型 ====================

class AIProjectInfo(BaseModel):
    """AI辅助工程基础信息"""
    name: str = Field("", description="AI工程名称")
    created_time: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    last_modified_time: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    vng_project_path: Optional[str] = Field(None, description="关联的VNG工程文件路径")
    description: str = Field("", description="工程描述")


class GenerationStep(BaseModel):
    """单个生成步骤记录"""
    step_name: str = Field(..., description="步骤名称，如generate_personas")
    timestamp: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    instruction: str = Field("", description="发送给Agent的指令")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="调用参数")
    result: Optional[Dict[str, Any]] = Field(None, description="生成结果")
    status: Literal["pending", "success", "failed"] = Field(default="pending", description="执行状态")
    error_message: Optional[str] = Field(None, description="错误信息")


class GenerationHistory(BaseModel):
    """生成历史记录（分步存储）"""
    step1_personas: Optional[Dict[str, Any]] = Field(None, description="步骤1：角色人设")
    step2_outline: Optional[Dict[str, Any]] = Field(None, description="步骤2：故事大纲")
    # 章节列表使用结构化字典（包含 raw_response/structured/parameters 等），而非纯列表，便于保存上下文
    step3_chapters: Optional[Dict[str, Any]] = Field(None, description="步骤3：章节列表")

    # 主控面板：每步“已保存指令”（用户可编辑后点按钮持久化保存；发送时强制使用已保存版本）
    # - saved_step_instructions：step1/step2/step3
    # - step4_saved_instructions：按章节索引保存（key 为字符串："0"/"1"...），避免 YAML/JSON 的 int key 兼容问题
    saved_step_instructions: Dict[str, str] = Field(
        default_factory=dict,
        description="主控面板：step1/step2/step3 已保存指令文本（用于发送前校验/持久化）",
    )
    step4_saved_instructions: Dict[str, str] = Field(
        default_factory=dict,
        description="主控面板：step4 按章节索引保存的指令文本（key=章节索引字符串）",
    )
    # 主控面板每步可独立配置的 max_tokens（用于长文本生成）；UI 侧限制最大 64000
    step_max_tokens: Dict[str, int] = Field(
        default_factory=lambda: {
            "step1": 32000,
            "step2": 48000,
            "step3": 48000,
            "step4": 64000,
            "step5_prompts": 8000,
        },
        description="各步骤 LLM max_tokens 上限配置（step1..step5_prompts）",
    )
    step4_chapter_details: Optional[List[Dict[str, Any]]] = Field(None, description="步骤4：章节详细内容")
    step5_full_script: Optional[Dict[str, Any]] = Field(None, description="步骤5：完整剧本")
    step5_flow_nodes: Optional[Dict[str, Any]] = Field(None, description="步骤5：流程节点数据")
    step5_material_prompts: Optional[Dict[str, Any]] = Field(None, description="步骤5：素材提示词生成结果（背景/CG/BGM prompts）")

    # 多轮上下文对话：
    # - master_conversation：历史遗留字段，保留以兼容旧工程/调试（通常会被更新为最近一次 step1~step3 的对话）
    # - master_conversation_after_step{1,2,3}：用于“重新生成某一步时不携带该步历史”的快照字段
    # - step4_conversations：步骤4 按章节索引保存对话历史（key 为字符串："0"/"1"/...），用于字数补偿续写/可复现
    # 说明：对话历史体积可能较大，但这是实现“续写补偿/可复现生成”的核心。
    master_conversation: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="主控面板：兼容字段；最近一次 step1~step3 的 Messages 对话历史（role/content）",
    )
    master_conversation_after_step1: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="主控面板：step1 完成后的对话快照（用于 step2 重新生成的上下文起点）",
    )
    master_conversation_after_step2: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="主控面板：step2 完成后的对话快照（用于 step3 重新生成的上下文起点）",
    )
    master_conversation_after_step3: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="主控面板：step3 完成后的对话快照（用于 step4 重新生成的上下文起点）",
    )
    step4_conversations: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict,
        description="主控面板：步骤4 按章节索引保存的 Messages 对话历史（key=章节索引字符串）",
    )
    
    agent_instructions: List[GenerationStep] = Field(default_factory=list, description="所有Agent调用记录")


class PortraitPendingItem(BaseModel):
    """待生成立绘项"""
    source: Literal["auto", "manual"] = Field(
        default="auto",
        description="来源：auto=系统生成，manual=手动添加",
    )
    item_id: str = Field(..., description="项目ID")
    char_id: str = Field(..., description="角色ID")
    char_name: str = Field(..., description="角色名称")
    description: str = Field("", description="立绘描述")
    expressions: List[str] = Field(default_factory=list, description="表情列表，如['happy', 'sad']")
    poses: List[str] = Field(default_factory=list, description="动作列表，如['stand', 'sit']")
    status: Literal["pending", "generated"] = Field(default="pending", description="生成状态")
    prompt: Optional[str] = Field(None, description="生成提示词")
    model: Optional[str] = Field(None, description="使用的模型，如midjourney/flux")
    file_paths: List[str] = Field(default_factory=list, description="生成的文件路径列表")
    base_image_path: Optional[str] = Field(None, description="基准图路径（Flux多表情生成用）")
    mj_state: Dict[str, Any] = Field(default_factory=dict, description="Midjourney三步工作流状态(任务ID/参数/保存路径等)")
    flux_state: Dict[str, Any] = Field(default_factory=dict, description="FLUX工作流状态(模型/参数/参考图/保存设置等)")


class BackgroundPendingItem(BaseModel):
    """待生成背景项"""
    source: Literal["auto", "manual"] = Field(
        default="auto",
        description="来源：auto=系统生成，manual=手动添加",
    )
    item_id: str = Field(..., description="项目ID")
    bg_id: str = Field(..., description="背景ID")
    description: str = Field(..., description="背景描述")
    atmosphere: str = Field("", description="氛围关键词")
    time_weather: str = Field("", description="时间/天气，如'午后晴天'")
    status: Literal["pending", "generated"] = Field(default="pending")
    prompt: Optional[str] = Field(None, description="生成提示词")
    model: Optional[str] = Field(None, description="使用的模型")
    file_path: str = Field("", description="文件路径，按命名规则")
    mj_state: Dict[str, Any] = Field(default_factory=dict, description="Midjourney三步工作流状态(任务ID/参数/保存路径等)")
    flux_state: Dict[str, Any] = Field(default_factory=dict, description="FLUX工作流状态(模型/参数/参考图/保存设置等)")


class CGPendingItem(BaseModel):
    """待生成CG项"""
    source: Literal["auto", "manual"] = Field(
        default="auto",
        description="来源：auto=系统生成，manual=手动添加",
    )
    item_id: str = Field(..., description="项目ID")
    cg_id: str = Field(..., description="CG ID")
    node_id: str = Field(..., description="关联的流程节点ID")
    description: str = Field(..., description="CG场景描述")
    characters: List[str] = Field(default_factory=list, description="涉及角色ID列表")
    atmosphere: str = Field("", description="氛围关键词")
    status: Literal["pending", "generated"] = Field(default="pending")
    prompt: Optional[str] = Field(None, description="生成提示词")
    model: Optional[str] = Field(None, description="使用的模型")
    file_path: str = Field("", description="文件路径，按命名规则")
    mj_state: Dict[str, Any] = Field(default_factory=dict, description="Midjourney三步工作流状态(任务ID/参数/保存路径等)")
    flux_state: Dict[str, Any] = Field(default_factory=dict, description="FLUX工作流状态(模型/参数/参考图/保存设置等)")


class VoicePendingItem(BaseModel):
    """待生成语音项"""
    source: Literal["auto", "manual"] = Field(
        default="auto",
        description="来源：auto=系统生成，manual=手动添加",
    )
    item_id: str = Field(..., description="项目ID")
    voice_id: str = Field(..., description="语音ID")
    node_id: str = Field(..., description="关联的节点ID")
    sub_id: Optional[int] = Field(None, description="子对话ID（若为子对话）")
    speaker: str = Field(..., description="说话人")
    char_id: str = Field(..., description="角色ID")
    text: str = Field(..., description="对白文本")
    # 第二语言对白：用于批量翻译/多语言语音生成（默认空）
    second_text: Optional[str] = Field(None, description="第二语言对白（翻译后文本，默认空）")
    emotion: str = Field("平静", description="语气情绪")
    voice_model_id: Optional[str] = Field(None, description="音色模型ID")

    # 逐条可覆盖的 TTS 参数（对齐 /api/third/tts/create）
    # - audio_id: 覆盖音色模型ID（audioId）；若为空则使用 voice_model_id
    # - tts_style: 模型版本（style）
    # - tts_genre: 模型类别（genre）
    # - tts_ext: 8维语气参数 ext
    audio_id: Optional[str] = Field(None, description="覆盖 audioId（优先于 voice_model_id）")
    tts_style: Optional[str] = Field(None, description="逐条覆盖 style（1/2/3）")
    tts_genre: Optional[int] = Field(None, description="逐条覆盖 genre（0/1）")
    tts_ext: Optional[Dict[str, float]] = Field(None, description="逐条覆盖 ext（8维情绪参数）")
    use_emotion_ext: Optional[bool] = Field(None, description="逐条覆盖：是否根据对白情绪发送 ext")

    status: Literal["pending", "generated"] = Field(default="pending")
    prompt: Optional[str] = Field(None, description="生成提示/参数")
    file_path: str = Field("", description="文件路径，按命名规则")


class BGMPendingItem(BaseModel):
    """待生成BGM项"""
    source: Literal["auto", "manual"] = Field(
        default="auto",
        description="来源：auto=系统生成，manual=手动添加",
    )
    item_id: str = Field(..., description="项目ID")
    bgm_id: str = Field(..., description="BGM ID")
    description: str = Field(..., description="BGM描述")
    mood: str = Field("", description="情绪关键词，如'欢快、悲伤'")
    style: str = Field("", description="曲风，如'钢琴、管弦乐'")
    duration: int = Field(120, description="时长（秒）")
    loop: bool = Field(True, description="是否循环")

    # Suno 自定义/歌词模式参数（对齐 /_open/suno/music/generate）
    mv_version: Optional[str] = Field(None, description="Suno 模型版本 mvVersion（如 chirp-v4/chirp-v5）")
    input_type: str = Field("20", description="输入类型 inputType（10=灵感模式, 20=自定义/歌词模式）")
    make_instrumental: bool = Field(True, description="是否纯音乐 makeInstrumental")
    tags: str = Field("", description="风格标签 tags")

    status: Literal["pending", "generated"] = Field(default="pending")
    prompt: Optional[str] = Field(None, description="生成提示词")
    model: Optional[str] = Field(None, description="使用的模型")
    file_path: str = Field("", description="文件路径，按命名规则")


class PendingLists(BaseModel):
    """所有待生成列表"""
    portraits: List[PortraitPendingItem] = Field(default_factory=list)
    backgrounds: List[BackgroundPendingItem] = Field(default_factory=list)
    cgs: List[CGPendingItem] = Field(default_factory=list)
    voices: List[VoicePendingItem] = Field(default_factory=list)
    bgms: List[BGMPendingItem] = Field(default_factory=list)

    # 语音面板：选择“使用原文/第二语言”来生成语音
    voice_text_mode: Literal["original", "second"] = Field(
        default="original",
        description="语音生成时对白来源：original=使用 text；second=优先使用 second_text（为空则回退 text）",
    )

    # 语音面板：批量翻译（LLM）相关输入/结果的持久化
    voice_translation_target_language: str = Field("", description="语音批量翻译：目标语言（用户输入）")
    voice_translation_instruction: str = Field("", description="语音批量翻译：指令文本（可编辑）")
    voice_translation_result: str = Field("", description="语音批量翻译：LLM 返回结果（可编辑/持久化）")


class AIProject(BaseModel):
    """AI辅助工程完整数据模型（.vnai文件格式）"""
    ai_project_info: AIProjectInfo = Field(default_factory=AIProjectInfo)
    story_config: StoryConfig = Field(default_factory=StoryConfig)
    character_config: List[CharacterConfig] = Field(default_factory=list)
    generation_history: GenerationHistory = Field(default_factory=GenerationHistory)
    pending_lists: PendingLists = Field(default_factory=PendingLists)
    
    def update_modified_time(self):
        """更新最后修改时间"""
        self.ai_project_info.last_modified_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ==================== 配置验证辅助 ====================

@validator("text_volume", pre=True, always=True)
def validate_text_volume(cls, v):
    """验证文本量是否在合理范围内"""
    if not isinstance(v, int):
        raise ValueError("文本量必须为整数")
    if v < 1000:
        raise ValueError("文本量不能少于1000字")
    if v > 500000:
        raise ValueError("文本量不能超过500000字")
    return v
