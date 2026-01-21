# -*- coding: utf-8 -*-
"""
测试AI辅助工程管理器
验证.vnai文件的创建、保存、加载功能
"""

import os
import sys
import tempfile
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.models import (
    CharacterConfig,
    StoryConfig,
    GenerationStep,
    PortraitPendingItem,
    BackgroundPendingItem
)


def test_create_and_save():
    """测试创建和保存AI工程"""
    print("=" * 60)
    print("测试1: 创建和保存AI工程")
    print("=" * 60)
    
    manager = AIProjectManager()
    
    # 创建临时文件路径
    temp_dir = tempfile.gettempdir()
    test_file = os.path.join(temp_dir, "test_project.vnai")
    
    # 删除旧文件（如果存在）
    if os.path.exists(test_file):
        os.remove(test_file)
    
    # 创建新工程
    project = manager.create_new_project(
        project_name="测试工程",
        save_path=test_file,
        story_title="夏日的风",
        description="这是一个测试AI工程"
    )
    
    print(f"✓ 工程创建成功")
    print(f"  - 工程名称: {project.ai_project_info.name}")
    print(f"  - 故事标题: {project.story_config.title}")
    print(f"  - 保存路径: {test_file}")
    
    # 验证文件是否创建
    assert os.path.exists(test_file), "工程文件未创建"
    print(f"✓ 文件已保存: {test_file}")
    
    return test_file


def test_load_project(file_path):
    """测试加载AI工程"""
    print("\n" + "=" * 60)
    print("测试2: 加载AI工程")
    print("=" * 60)
    
    manager = AIProjectManager()
    
    # 加载工程
    project = manager.load_project(file_path)
    
    assert project is not None, "加载失败"
    print(f"✓ 工程加载成功")
    print(f"  - 工程名称: {project.ai_project_info.name}")
    print(f"  - 创建时间: {project.ai_project_info.created_time}")
    print(f"  - 故事标题: {project.story_config.title}")
    
    return manager


def test_update_story_config(manager):
    """测试更新剧情配置"""
    print("\n" + "=" * 60)
    print("测试3: 更新剧情配置")
    print("=" * 60)
    
    new_story = StoryConfig(
        title="春日序曲",
        style="日系校园、治愈",
        plot_outline="少年与少女在春天的相遇...",
        text_volume=8000,
        enable_choice_node=True,
        enable_condition_node=True
    )
    
    success = manager.update_story_config(new_story)
    assert success, "更新失败"
    
    print(f"✓ 剧情配置更新成功")
    print(f"  - 新标题: {manager.current_project.story_config.title}")
    print(f"  - 文本量: {manager.current_project.story_config.text_volume}")
    
    # 保存更新
    manager.save_project()
    print(f"✓ 更新已保存")


def test_add_characters(manager):
    """测试添加角色"""
    print("\n" + "=" * 60)
    print("测试4: 添加角色")
    print("=" * 60)
    
    char1 = CharacterConfig(
        char_id="char_001",
        char_name="林风",
        role="男主角",
        is_player=True,
        persona_keywords="阳光、温柔、喜欢摄影",
        voice_tone="青年、温和、中等语速"
    )
    
    char2 = CharacterConfig(
        char_id="char_002",
        char_name="夏雨",
        role="女主角",
        persona_keywords="活泼、开朗、喜欢音乐",
        voice_tone="少女、甜美、语速偏快"
    )
    
    manager.add_character(char1)
    manager.add_character(char2)
    
    print(f"✓ 添加角色成功")
    print(f"  - 角色数量: {len(manager.current_project.character_config)}")
    for char in manager.current_project.character_config:
        print(f"  - {char.char_name} ({char.char_id}): {char.role}")
    
    manager.save_project()
    print(f"✓ 更新已保存")


def test_generation_history(manager):
    """测试生成历史记录"""
    print("\n" + "=" * 60)
    print("测试5: 生成历史记录")
    print("=" * 60)
    
    # 添加步骤1：角色人设
    personas_data = {
        "char_001": {
            "name": "林风",
            "persona": "阳光温柔的高中生，热爱摄影..."
        },
        "char_002": {
            "name": "夏雨",
            "persona": "活泼开朗的转校生，擅长音乐..."
        }
    }
    
    manager.update_generation_step("step1_personas", personas_data)
    print(f"✓ 步骤1（角色人设）已记录")
    
    # 添加Agent指令记录
    instruction = GenerationStep(
        step_name="generate_personas",
        instruction="根据角色配置生成详细人设",
        parameters={"char_count": 2},
        result=personas_data,
        status="success"
    )
    
    manager.add_agent_instruction(instruction)
    print(f"✓ Agent指令已记录")
    print(f"  - 指令数量: {len(manager.current_project.generation_history.agent_instructions)}")
    
    manager.save_project()
    print(f"✓ 更新已保存")


def test_pending_lists(manager):
    """测试待生成列表"""
    print("\n" + "=" * 60)
    print("测试6: 待生成列表")
    print("=" * 60)
    
    # 添加待生成立绘
    portrait1 = PortraitPendingItem(
        item_id="portrait_001",
        char_id="char_001",
        char_name="林风",
        description="男主角全身立绘",
        expressions=["happy", "sad", "shy"],
        poses=["stand"],
        status="pending"
    )
    
    portrait2 = PortraitPendingItem(
        item_id="portrait_002",
        char_id="char_002",
        char_name="夏雨",
        description="女主角全身立绘",
        expressions=["happy", "sad", "shy", "angry"],
        poses=["stand"],
        status="pending"
    )
    
    manager.current_project.pending_lists.portraits.append(portrait1)
    manager.current_project.pending_lists.portraits.append(portrait2)
    
    # 添加待生成背景
    background1 = BackgroundPendingItem(
        item_id="bg_001",
        bg_id="classroom",
        description="高中教室，靠窗位置",
        atmosphere="温馨、明亮",
        time_weather="午后晴天",
        status="pending",
        file_path="resources/images/classroom_afternoon.jpg"
    )
    
    manager.current_project.pending_lists.backgrounds.append(background1)
    
    print(f"✓ 待生成列表更新成功")
    print(f"  - 待生成立绘: {len(manager.current_project.pending_lists.portraits)}")
    print(f"  - 待生成背景: {len(manager.current_project.pending_lists.backgrounds)}")
    
    for p in manager.current_project.pending_lists.portraits:
        print(f"    • {p.char_name}: {len(p.expressions)}个表情")
    
    manager.save_project()
    print(f"✓ 更新已保存")


def test_project_summary(manager):
    """测试工程摘要"""
    print("\n" + "=" * 60)
    print("测试7: 工程摘要")
    print("=" * 60)
    
    summary = manager.get_project_summary()
    
    print(f"✓ 工程摘要:")
    for key, value in summary.items():
        print(f"  - {key}: {value}")


def main():
    """运行所有测试"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "AI辅助工程管理器测试" + " " * 18 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    try:
        # 测试1: 创建和保存
        test_file = test_create_and_save()
        
        # 测试2: 加载
        manager = test_load_project(test_file)
        
        # 测试3: 更新剧情配置
        test_update_story_config(manager)
        
        # 测试4: 添加角色
        test_add_characters(manager)
        
        # 测试5: 生成历史
        test_generation_history(manager)
        
        # 测试6: 待生成列表
        test_pending_lists(manager)
        
        # 测试7: 工程摘要
        test_project_summary(manager)
        
        print("\n" + "=" * 60)
        print("✓ 所有测试通过!")
        print("=" * 60)
        print(f"\n测试文件保存在: {test_file}")
        print("可以手动查看YAML文件内容验证结构\n")
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
