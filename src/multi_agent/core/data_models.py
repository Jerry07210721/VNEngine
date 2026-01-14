# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - 统一数据模型
定义所有Agent之间交互的标准化数据结构，确保类型安全与一致性
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime


class CharacterSchema(BaseModel):
    """
    角色人设数据模型
    用于在Agent之间传递角色基础信息
    """
    model_config = ConfigDict(extra='allow')
    
    char_id: str = Field(..., description="角色唯一标识，如char_001")
    name: str = Field(..., description="角色姓名")
    gender: Literal["男", "女", "其他"] = Field(..., description="角色性别")
    appearance: str = Field(..., description="外貌详细描述（供立绘生成使用）")
    personality: str = Field(..., description="性格详细描述（供剧情生成使用）")
    voice_style: str = Field(..., description="声线风格（供语音生成使用），如萝莉音、御姐音、少年音")
    default_pose: str = Field(default="站立", description="默认动作，如站立、坐姿、挥手")
    default_expression: str = Field(default="平静", description="默认表情，如平静、微笑、严肃")
    
    # 扩展字段
    age: Optional[int] = Field(default=None, description="年龄（可选）")
    occupation: Optional[str] = Field(default=None, description="职业（可选）")
    background_story: Optional[str] = Field(default=None, description="背景故事（可选）")


class VariableOperationSchema(BaseModel):
    """
    变量操作数据模型
    对应VNEngine节点的var_ops字段
    """
    model_config = ConfigDict(extra='allow')
    
    var_name: str = Field(..., description="变量名称")
    op: Literal["+", "-", "*", "/", "="] = Field(..., description="运算符")
    value: float = Field(..., description="操作数值")


class ConnectionSchema(BaseModel):
    """
    节点连接数据模型
    定义节点间的流转关系
    """
    model_config = ConfigDict(extra='allow')
    
    source: str = Field(..., description="源节点ID")
    target: str = Field(..., description="目标节点ID")
    option_index: Optional[int] = Field(default=None, description="选择节点的选项索引（0-based）")
    condition_result: Optional[bool] = Field(default=None, description="条件节点的分支结果（True/False）")


class ScriptNodeSchema(BaseModel):
    """
    剧本节点数据模型
    与VNEngine的FlowTextNode/FlowSelectNode/FlowConditionNode完全对齐
    """
    model_config = ConfigDict(extra='allow')
    
    # 通用字段
    node_id: str = Field(..., description="节点唯一标识，如node_001")
    node_type: Literal["text", "select", "condition"] = Field(..., description="节点类型")
    title: str = Field(..., description="节点标题（简短描述）")
    is_start: bool = Field(default=False, description="是否为起始节点")
    
    # 文本节点特有字段
    speaker: Optional[str] = Field(default=None, description="说话人（角色名称）")
    content: Optional[str] = Field(default=None, description="对白内容")
    
    # 选择节点特有字段
    options: Optional[List[str]] = Field(default=None, description="选项列表，2-4个选项")
    
    # 条件节点特有字段
    condition_var: Optional[str] = Field(default=None, description="条件变量名")
    condition_op: Optional[Literal["==", "!=", ">", "<", ">=", "<="]] = Field(default=None, description="条件运算符")
    condition_value: Optional[float] = Field(default=None, description="条件右值")
    condition_const: bool = Field(default=True, description="右值是否为常量")
    
    # 媒体资源字段
    background: Optional[str] = Field(default=None, description="背景图相对路径")
    portrait: Optional[str] = Field(default=None, description="立绘相对路径")
    voice: Optional[str] = Field(default=None, description="语音相对路径")
    bgm: Optional[str] = Field(default=None, description="BGM相对路径")
    video: Optional[str] = Field(default=None, description="视频相对路径")
    
    # 媒体控制字段
    bgm_loop: bool = Field(default=True, description="BGM是否循环")
    stop_bgm: bool = Field(default=False, description="是否停止BGM")
    bg_fade_in: float = Field(default=0.0, description="背景淡入时间（秒）")
    video_loop: bool = Field(default=False, description="视频是否循环")
    hide_textbox: bool = Field(default=False, description="是否隐藏文本框")
    portrait_fade: float = Field(default=0.0, description="立绘淡入时间（秒）")
    portrait_fade_out: float = Field(default=0.0, description="立绘淡出时间（秒）")
    
    # UI关联字段
    ui_file: Optional[str] = Field(default=None, description="自定义UI文件路径")
    
    # 变量操作字段
    var_ops: Optional[List[VariableOperationSchema]] = Field(default=None, description="变量操作列表")
    
    # 子对话列表（文本节点可包含多条对白）
    sub_dialogues: Optional[List[Dict[str, Any]]] = Field(default=None, description="子对话列表")
    
    # 场景与氛围标签（供视觉/音频Agent使用）
    scene_description: Optional[str] = Field(default=None, description="场景详细描述（供背景生成使用）")
    atmosphere: Optional[str] = Field(default=None, description="氛围标签，如温馨、伤感、紧张")
    
    # 节点位置（用于流程图显示）
    x: float = Field(default=0.0, description="节点X坐标")
    y: float = Field(default=0.0, description="节点Y坐标")


class ResourceMetaSchema(BaseModel):
    """
    资源元数据模型
    记录生成的各类资源的路径与绑定关系
    """
    model_config = ConfigDict(extra='allow')
    
    res_id: str = Field(..., description="资源唯一标识")
    res_type: Literal["portrait", "background", "cg", "voice", "bgm", "video"] = Field(..., description="资源类型")
    path: str = Field(..., description="相对工程目录的路径")
    name: str = Field(..., description="资源名称")
    
    # 绑定关系
    related_node_id: Optional[str] = Field(default=None, description="绑定的剧本节点ID")
    related_char_id: Optional[str] = Field(default=None, description="绑定的角色ID")
    
    # 立绘差分特有字段
    pose: Optional[str] = Field(default=None, description="动作类型（站立、坐姿、挥手等）")
    expression: Optional[str] = Field(default=None, description="表情类型（开心、生气、哭等）")
    
    # 生成信息
    prompt: Optional[str] = Field(default=None, description="生成时使用的Prompt（可选，用于追溯）")
    model_name: Optional[str] = Field(default=None, description="使用的模型名称（可选）")
    generated_at: datetime = Field(default_factory=datetime.now, description="生成时间")


class GenerationConfigSchema(BaseModel):
    """
    AI生成配置数据模型
    对应UI配置面板的所有用户输入
    """
    model_config = ConfigDict(extra='allow')
    
    # 基础信息
    game_name: str = Field(..., description="游戏名称")
    game_version: str = Field(default="1.0.0", description="游戏版本")
    save_path: str = Field(..., description="工程保存路径")
    window_size: tuple[int, int] = Field(default=(1280, 720), description="窗口尺寸")
    
    # 剧情配置
    game_theme: str = Field(..., description="游戏主题，如校园恋爱、奇幻冒险")
    char_count: int = Field(default=2, ge=1, le=5, description="角色数量")
    script_length: int = Field(default=5000, ge=2000, le=10000, description="剧情字数")
    branch_count: int = Field(default=2, ge=1, le=4, description="分支数量")
    script_style: List[str] = Field(default=["温馨", "浪漫"], description="剧情风格标签")
    extra_requirements: Optional[str] = Field(default=None, description="额外剧情要求")
    
    # 视觉配置
    portrait_style: str = Field(default="萌系", description="立绘风格")
    portrait_resolution: tuple[int, int] = Field(default=(896, 1408), description="立绘分辨率")
    character_poses: List[str] = Field(default=["站立", "坐姿", "挥手"], description="角色动作列表")
    character_expressions: List[str] = Field(default=["开心", "生气", "哭"], description="角色表情列表")
    cg_count: int = Field(default=2, ge=1, le=5, description="CG数量")
    cg_resolution: tuple[int, int] = Field(default=(2048, 2048), description="CG分辨率")
    background_style: Optional[str] = Field(default=None, description="背景风格（默认与立绘风格一致）")
    
    # 音频配置
    voice_language: Literal["中文", "日语", "中日双语"] = Field(default="中文", description="语音语言")
    voice_speed: float = Field(default=1.0, ge=0.8, le=1.2, description="语速")
    emotion_strength: float = Field(default=0.8, ge=0.5, le=1.0, description="情感强度")
    bgm_style: str = Field(default="温馨", description="BGM风格")
    bgm_duration: int = Field(default=120, ge=60, le=180, description="BGM时长（秒）")
    
    # API配置
    api_configs: Dict[str, Dict[str, str]] = Field(default_factory=dict, description="各模型的API配置")
    api_timeout: int = Field(default=30, ge=10, le=60, description="API超时时间（秒）")
    api_retry_count: int = Field(default=3, ge=1, le=5, description="API重试次数")


class TaskResultSchema(BaseModel):
    """
    Agent任务执行结果数据模型
    统一封装所有Agent的返回结果
    """
    model_config = ConfigDict(extra='allow')
    
    agent_id: str = Field(..., description="Agent唯一标识")
    agent_name: str = Field(..., description="Agent名称")
    success: bool = Field(..., description="任务是否成功")
    message: str = Field(default="", description="结果消息")
    
    # 结果数据（根据Agent类型不同，内容不同）
    data: Optional[Dict[str, Any]] = Field(default=None, description="结果数据")
    
    # 执行信息
    start_time: datetime = Field(default_factory=datetime.now, description="开始时间")
    end_time: Optional[datetime] = Field(default=None, description="结束时间")
    error_msg: Optional[str] = Field(default=None, description="错误信息（失败时）")


class ProjectIntegrationSchema(BaseModel):
    """
    工程整合数据模型
    包含完整的工程数据，供ProjectIntegrator使用
    """
    model_config = ConfigDict(extra='allow')
    
    # 基础信息
    project_name: str = Field(..., description="工程名称")
    project_path: str = Field(..., description="工程保存路径")
    
    # 人设数据
    characters: List[CharacterSchema] = Field(default_factory=list, description="角色列表")
    
    # 剧本数据
    script_nodes: List[ScriptNodeSchema] = Field(default_factory=list, description="剧本节点列表")
    connections: List[ConnectionSchema] = Field(default_factory=list, description="节点连接列表")
    
    # 资源数据
    resources: List[ResourceMetaSchema] = Field(default_factory=list, description="资源元数据列表")
    
    # 全局变量
    global_variables: List[Dict[str, Any]] = Field(default_factory=list, description="全局变量列表")
    
    # 游戏配置
    game_config: Dict[str, Any] = Field(default_factory=dict, description="游戏配置")
