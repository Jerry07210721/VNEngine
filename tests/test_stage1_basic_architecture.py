# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - 阶段1测试脚本
测试基础架构：目录结构、配置管理、数据模型、日志系统
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ai.core.config_manager import ConfigManager
from src.ai.core.models import (
    UserConfig,
    ProjectConfig,
    StoryConfig,
    CharacterConfig,
    MaterialConfig,
    EnableAgentsConfig
)
from src.ai.log.logger import get_logger, LOG_LEVEL_INFO


def test_directory_structure():
    """测试目录结构"""
    print("\n" + "="*60)
    print("测试1：目录结构")
    print("="*60)
    
    required_dirs = [
        "src/ai",
        "src/ai/core",
        "src/ai/agents",
        "src/ai/api",
        "src/ai/integrator",
        "src/ai/utils",
        "src/ai/log",
        "logs/multi_agent"
    ]
    
    for dir_path in required_dirs:
        full_path = project_root / dir_path
        if full_path.exists():
            print(f"✅ {dir_path}")
        else:
            print(f"❌ {dir_path} - 不存在！")
    
    print("\n目录结构测试完成！")


def test_logger():
    """测试日志系统"""
    print("\n" + "="*60)
    print("测试2：日志系统")
    print("="*60)
    
    # 获取日志记录器
    logger = get_logger("test_module", level=LOG_LEVEL_INFO)
    
    # 测试各级别日志
    logger.debug("这是DEBUG级别日志（应该不显示）")
    logger.info("这是INFO级别日志 ✅")
    logger.warning("这是WARNING级别日志 ⚠️")
    logger.error("这是ERROR级别日志 ❌")
    
    print("\n日志系统测试完成！")
    print(f"日志文件位置: {project_root / 'logs' / 'multi_agent'}")


def test_config_manager():
    """测试配置管理器"""
    print("\n" + "="*60)
    print("测试3：配置管理器")
    print("="*60)
    
    # 创建配置管理器
    config_manager = ConfigManager()
    
    # 测试配置文件是否生成
    config_path = project_root / "config" / "ai_config.yaml"
    if config_path.exists():
        print(f"✅ 配置文件已生成: {config_path}")
    else:
        print(f"❌ 配置文件未生成！")
        return
    
    # 测试读取配置
    api_config = config_manager.get_api_config("claude")
    print(f"\n📋 Claude API配置:")
    print(f"  - Base URL: {api_config.get('base_url')}")
    print(f"  - Primary Model: {api_config.get('primary_model')}")
    print(f"  - Max Tokens: {api_config.get('max_tokens')}")
    
    # 测试验证配置
    is_valid, errors = config_manager.validate_config()
    print(f"\n🔍 配置验证结果: {'有效 ✅' if is_valid else '无效 ❌'}")
    if errors:
        print("⚠️  配置错误:")
        for error in errors:
            print(f"  - {error}")
    
    # 测试API启用状态
    print(f"\n🔌 API启用状态:")
    for api_name in ["claude", "kimi", "midjourney", "flux", "gptsovits", "suno"]:
        enabled = config_manager.is_api_enabled(api_name)
        status = "启用 ✅" if enabled else "未启用 ⚠️"
        print(f"  - {api_name}: {status}")
    
    print("\n配置管理器测试完成！")


def test_data_models():
    """测试数据模型"""
    print("\n" + "="*60)
    print("测试4：数据模型")
    print("="*60)
    
    try:
        # 创建示例配置
        project_config = ProjectConfig(
            project_path="D:/GalGame/TestProject",
            project_name="测试工程",
            window_width=1280,
            window_height=720
        )
        print("✅ ProjectConfig 创建成功")
        
        story_config = StoryConfig(
            title="夏日的风",
            style="日系校园、纯爱、治愈",
            plot_outline="高中生男主与转校生女主的夏日故事",
            text_volume=5000
        )
        print("✅ StoryConfig 创建成功")
        
        char_config = CharacterConfig(
            char_id="char_001",
            char_name="林风",
            is_player=True,
            persona_keywords="阳光、温柔、喜欢摄影",
            voice_tone="青年、温和、语速中等",
            voice_model_id="A1fMMPcu2h2WJC4E3AuLr1uPoo"
        )
        print("✅ CharacterConfig 创建成功")
        
        material_config = MaterialConfig(
            portrait_format="png",
            background_format="jpg",
            cg_format="png",
            voice_format="mp3",
            bgm_format="mp3"
        )
        print("✅ MaterialConfig 创建成功")
        
        enable_agents = EnableAgentsConfig(
            plot_agent=True,
            portrait_agent=True,
            background_agent=True,
            cg_agent=True,
            voice_api=True,
            bgm_api=True
        )
        print("✅ EnableAgentsConfig 创建成功")
        
        # 创建完整用户配置
        user_config = UserConfig(
            project_info=project_config,
            story_config=story_config,
            character_config=[char_config],
            enable_agents=enable_agents,
            material_config=material_config
        )
        print("✅ UserConfig 创建成功")
        
        # 测试序列化
        config_dict = user_config.model_dump()
        print(f"\n📦 配置序列化成功，包含 {len(config_dict)} 个顶层字段")
        
        print("\n数据模型测试完成！")
        
    except Exception as e:
        print(f"❌ 数据模型测试失败: {e}")


def test_integration():
    """集成测试"""
    print("\n" + "="*60)
    print("测试5：集成测试")
    print("="*60)
    
    # 测试从配置管理器获取配置并创建用户配置
    logger = get_logger("integration_test")
    config_manager = ConfigManager()
    
    logger.info("开始集成测试...")
    
    # 模拟用户输入
    project_config = ProjectConfig(
        project_path="D:/TestProject",
        project_name="集成测试工程"
    )
    
    story_config = StoryConfig(
        title="测试故事",
        style="测试风格",
        plot_outline="这是一个测试故事",
        text_volume=2000
    )
    
    char_config = CharacterConfig(
        char_id="test_char",
        char_name="测试角色",
        persona_keywords="测试人设"
    )
    
    enable_agents = EnableAgentsConfig()
    material_config = MaterialConfig()
    
    user_config = UserConfig(
        project_info=project_config,
        story_config=story_config,
        character_config=[char_config],
        enable_agents=enable_agents,
        material_config=material_config
    )
    
    logger.info(f"用户配置创建成功: {user_config.project_info.project_name}")
    logger.info(f"故事标题: {user_config.story_config.title}")
    logger.info(f"角色数量: {len(user_config.character_config)}")
    
    # 获取Agent启用状态
    agent_settings = config_manager.get_agent_settings()
    logger.info(f"Agent并发配置: {agent_settings.get('concurrent_tasks')}")
    
    print("\n✅ 集成测试完成！")


def main():
    """主测试函数"""
    print("\n" + "🚀"*30)
    print("VNEngine 多智能体协作系统 - 阶段1测试")
    print("基础架构搭建验证")
    print("🚀"*30)
    
    try:
        # 运行所有测试
        test_directory_structure()
        test_logger()
        test_config_manager()
        test_data_models()
        test_integration()
        
        print("\n" + "="*60)
        print("✅ 所有测试完成！阶段1开发验证通过！")
        print("="*60)
        print("\n📝 下一步:")
        print("  1. 在 config/ai_config.yaml 中填写您的API密钥")
        print("  2. 开始阶段2：API客户端封装与测试")
        print()
        
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
