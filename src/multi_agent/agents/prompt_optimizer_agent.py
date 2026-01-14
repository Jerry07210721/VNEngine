# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - Prompt优化Agent
基于Claude 3等高级模型优化各类生成任务的提示词
"""
from typing import Dict, Any
from src.multi_agent.core.agent_base import BaseAgent
from src.multi_agent.core.data_models import TaskResultSchema
from src.multi_agent.api_clients.llm_client import LLMClient
from src.multi_agent.utils.logger import LoggerFactory


class PromptOptimizerAgent(BaseAgent):
    """
    Prompt优化Agent
    接收原始需求描述，生成精准、结构化的Prompt
    """
    
    def __init__(
        self,
        agent_id: str = "prompt_optimizer_001",
        agent_name: str = "Prompt优化Agent",
        model_name: str = "gpt-4o",
        api_key: str = "",
        base_url: str = None
    ):
        """
        初始化Prompt优化Agent
        
        Args:
            agent_id: Agent唯一标识
            agent_name: Agent名称
            model_name: 使用的模型（推荐claude-3-opus或gpt-4o）
            api_key: API密钥
            base_url: 自定义API地址
        """
        super().__init__(agent_id, agent_name)
        
        # 设置日志工具
        self.logger = LoggerFactory.get_logger(agent_name)
        
        # 初始化LLM客户端
        self.llm_client = None
        if api_key:
            self.llm_client = LLMClient(
                model_name=model_name,
                api_key=api_key,
                base_url=base_url,
                timeout=60
            )
    
    def run(self, task_params: Dict[str, Any]) -> TaskResultSchema:
        """
        执行Prompt优化任务
        
        Args:
            task_params: 任务参数
                - task_type: 任务类型（portrait/background/cg/voice/bgm）
                - raw_description: 原始需求描述
                - target_model: 目标模型（sdxl/midjourney等）
                - additional_context: 额外上下文（可选）
                
        Returns:
            TaskResultSchema: 优化后的Prompt
        """
        self.logger.log_task_start("Prompt优化", task_params)
        
        # 校验参数
        required_fields = ["task_type", "raw_description", "target_model"]
        is_valid, error_msg = self.validate_params(task_params, required_fields)
        if not is_valid:
            return self.create_error_result(error_msg)
        
        task_type = task_params["task_type"]
        raw_description = task_params["raw_description"]
        target_model = task_params["target_model"]
        additional_context = task_params.get("additional_context", "")
        
        try:
            self.report_progress(0.3, "构建优化提示词")
            
            # 构建系统提示词
            system_prompt = self._build_system_prompt(task_type, target_model)
            
            # 构建用户提示词
            user_prompt = self._build_user_prompt(raw_description, additional_context)
            
            self.report_progress(0.5, "调用LLM优化Prompt")
            
            # 调用LLM优化
            if self.llm_client:
                optimized_prompt = self.llm_client.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=1000
                )
            else:
                # 如果未配置LLM，直接返回原始描述（降级处理）
                self.logger.warning("未配置LLM客户端，使用原始描述")
                optimized_prompt = raw_description
            
            self.report_progress(1.0, "Prompt优化完成")
            
            result_data = {
                "task_type": task_type,
                "optimized_prompt": optimized_prompt.strip(),
                "target_model": target_model
            }
            
            self.logger.log_task_end("Prompt优化", True, f"优化后Prompt：{optimized_prompt[:100]}...")
            return self.create_success_result(data=result_data, message="Prompt优化成功")
        
        except Exception as e:
            return self.create_error_result("Prompt优化失败", exception=e)
    
    def _build_system_prompt(self, task_type: str, target_model: str) -> str:
        """
        构建系统提示词
        
        Args:
            task_type: 任务类型
            target_model: 目标模型
            
        Returns:
            str: 系统提示词
        """
        base_prompt = f"""你是一位专业的AI Prompt工程师，擅长为{target_model}模型生成精准、高质量的提示词。
你的任务是根据用户的原始需求描述，优化生成适配{target_model}的Prompt。

核心要求：
1. 提示词必须精准、结构化、无歧义。
2. 提示词必须包含足够的细节，确保生成结果符合需求。
3. 提示词必须适配{target_model}的特性（如SDXL需要详细的视觉描述，MidJourney需要艺术风格标签）。
4. 提示词必须使用英文（针对图像生成模型）。
5. 禁止输出任何额外文字，只返回优化后的Prompt。"""

        # 根据任务类型添加专项要求
        if task_type == "portrait":
            base_prompt += "\n\n【立绘生成特殊要求】：\n- 必须包含角色外貌细节（发型、发色、眼睛、服装、表情、动作）\n- 必须添加透明背景要求（transparent background）\n- 必须添加质量标签（masterpiece, best quality, ultra-detailed）"
        elif task_type == "background":
            base_prompt += "\n\n【背景生成特殊要求】：\n- 必须包含场景详细描述（地点、时间、氛围、光线）\n- 必须强调无人物（no characters）\n- 必须添加质量标签（masterpiece, best quality, ultra-detailed）"
        elif task_type == "cg":
            base_prompt += "\n\n【CG生成特殊要求】：\n- 必须包含剧情描述与角色动作\n- 必须包含情感氛围标签\n- 必须添加高分辨率与电影级光照标签（8k, cinematic lighting）"
        
        return base_prompt
    
    def _build_user_prompt(self, raw_description: str, additional_context: str) -> str:
        """
        构建用户提示词
        
        Args:
            raw_description: 原始描述
            additional_context: 额外上下文
            
        Returns:
            str: 用户提示词
        """
        user_prompt = f"原始需求描述：\n{raw_description}"
        
        if additional_context:
            user_prompt += f"\n\n额外上下文：\n{additional_context}"
        
        user_prompt += "\n\n请基于以上信息，生成优化后的Prompt（只返回Prompt文本，不要任何额外说明）。"
        
        return user_prompt
    
    def close(self):
        """关闭资源"""
        if self.llm_client:
            self.llm_client.close()
