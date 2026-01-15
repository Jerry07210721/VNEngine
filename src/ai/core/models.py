# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - 数据模型定义
使用 Pydantic 实现数据验证和序列化
"""

from typing import List, Dict, Optional, Any, Literal
from pydantic import BaseModel, Field, validator
from datetime import datetime


# ==================== 用户配置相关模型 ====================

class ProjectConfig(BaseModel):
    """工程基础配置"""
    project_path: str = Field(..., description="工程保存路径（绝对路径）")
    project_name: str = Field(..., description="工程名称")
    window_width: int = Field(1280, description="窗口宽度", ge=800, le=3840)
    window_height: int = Field(720, description="窗口高度", ge=600, le=2160)
    engine_version: str = Field("V2.0-AI", description="引擎版本")


class StoryConfig(BaseModel):
    """故事配置"""
    title: str = Field(..., description="故事标题")
    style: str = Field(..., description="故事风格（如：日系校园、纯爱、治愈）")
    plot_outline: str = Field(..., description="剧情梗概")
    text_volume: int = Field(..., description="文本量（字数）", ge=1000, le=100000)
    enable_choice_node: bool = Field(True, description="是否开启选择节点")
    enable_condition_node: bool = Field(True, description="是否开启条件节点")
    condition_type: str = Field("favorability", description="条件类型（如：好感度）")
    character_hint_weight: float = Field(0.7, ge=0.0, le=1.0, description="角色设定遵循用户配置的权重(0-1)")
    narrative_pov: Literal["first", "third"] = Field("third", description="叙述视角：第一人称/第三人称")
    first_person_name: str = Field("我", description="第一人称的名字/代称")
    first_person_has_portrait: bool = Field(False, description="第一人称是否有立绘")
    first_person_has_voice: bool = Field(False, description="第一人称是否有配音")
    first_person_cg_presence: bool = Field(True, description="第一人称是否会出现在CG中")
    first_person_cg_notes: str = Field("", description="第一人称在CG中的表现说明")


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

class FlowNodeData(BaseModel):
    """流程节点数据（对齐VNEngine格式）"""
    id: int = Field(..., description="节点ID")
    node_type: Literal["text", "choice", "condition"] = Field(..., description="节点类型")
    title: str = Field(..., description="节点标题")
    content: str = Field("", description="节点内容")
    speaker: str = Field("", description="发言者")
    portrait: str = Field("", description="立绘路径")
    background: str = Field("", description="背景路径")
    voice: str = Field("", description="语音路径")
    bgm: str = Field("", description="BGM路径")
    bgm_loop: bool = Field(True, description="BGM是否循环")
    stop_bgm: bool = Field(False, description="是否停止BGM")
    bg_fade_in: bool = Field(False, description="背景是否淡入")
    portrait_fade: bool = Field(False, description="立绘是否淡入")
    portrait_fade_out: bool = Field(False, description="立绘是否淡出")
    hide_textbox: bool = Field(False, description="是否隐藏文本框")
    ui_file: str = Field("", description="UI文件路径")
    video: str = Field("", description="视频路径")
    video_loop: bool = Field(False, description="视频是否循环")
    options: List[str] = Field(default_factory=list, description="选项列表（选择节点）")
    condition_var: str = Field("", description="条件变量名（条件节点）")
    condition_op: str = Field("==", description="条件运算符")
    condition_value: str = Field("", description="条件值")
    condition_const: bool = Field(False, description="条件值是否为常量")
    sub_dialogues: List[Dict[str, Any]] = Field(default_factory=list, description="子对话列表")
    var_ops: List[Dict[str, Any]] = Field(default_factory=list, description="变量运算列表")
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


# ==================== 配置验证辅助 ====================

@validator("text_volume", pre=True, always=True)
def validate_text_volume(cls, v):
    """验证文本量是否在合理范围内"""
    if not isinstance(v, int):
        raise ValueError("文本量必须为整数")
    if v < 1000:
        raise ValueError("文本量不能少于1000字")
    if v > 100000:
        raise ValueError("文本量不能超过100000字")
    return v
