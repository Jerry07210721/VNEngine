# -*- coding: utf-8 -*-
"""
非GUI测试：验证配置数据读写
"""

import sys
import tempfile
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.models import StoryConfig, CharacterConfig


def test_story_config_save_load():
    """测试剧情配置保存和加载"""
    print("\n" + "=" * 60)
    print("测试1: 剧情配置保存和加载")
    print("=" * 60)
    
    manager = AIProjectManager()
    
    # 创建工程
    temp_dir = tempfile.gettempdir()
    test_file = os.path.join(temp_dir, "test_story_config.vnai")
    
    if os.path.exists(test_file):
        os.remove(test_file)
    
    project = manager.create_new_project(
        project_name="剧情测试",
        save_path=test_file
    )
    
    print("✓ 工程创建成功")
    
    # 创建剧情配置
    story_config = StoryConfig(
        title="夏日回忆",
        style="日系校园、治愈、青春",
        plot_outline="少年与少女在暑假的相遇，一段美好的回忆...",
        text_volume=8000,
        enable_choice_node=True,
        enable_condition_node=True,
        condition_type="favorability",
        character_hint_weight=0.8
    )
    
    # 保存到工程
    manager.update_story_config(story_config)
    manager.save_project()
    
    print("✓ 剧情配置已保存")
    
    # 重新加载
    manager2 = AIProjectManager()
    loaded_project = manager2.load_project(test_file)
    
    assert loaded_project is not None
    assert loaded_project.story_config.title == "夏日回忆"
    assert loaded_project.story_config.style == "日系校园、治愈、青春"
    assert loaded_project.story_config.text_volume == 8000
    assert loaded_project.story_config.character_hint_weight == 0.8
    
    print("✓ 剧情配置加载验证通过")
    print(f"  - 标题: {loaded_project.story_config.title}")
    print(f"  - 风格: {loaded_project.story_config.style}")
    print(f"  - 文本量: {loaded_project.story_config.text_volume}")
    print(f"  - 权重: {loaded_project.story_config.character_hint_weight}")


def test_character_config_save_load():
    """测试角色配置保存和加载"""
    print("\n" + "=" * 60)
    print("测试2: 角色配置保存和加载")
    print("=" * 60)
    
    manager = AIProjectManager()
    
    # 创建工程
    temp_dir = tempfile.gettempdir()
    test_file = os.path.join(temp_dir, "test_char_config.vnai")
    
    if os.path.exists(test_file):
        os.remove(test_file)
    
    project = manager.create_new_project(
        project_name="角色测试",
        save_path=test_file
    )
    
    print("✓ 工程创建成功")
    
    # 创建角色配置
    char1 = CharacterConfig(
        char_id="char_001",
        char_name="林风",
        role="男主角",
        is_player=True,
        persona_keywords="阳光、温柔、喜欢摄影、成绩中等",
        voice_tone="青年、温和、中等语速",
        voice_model_id="voice_001"
    )
    
    char2 = CharacterConfig(
        char_id="char_002",
        char_name="夏雨",
        role="女主角",
        is_player=False,
        persona_keywords="活泼、开朗、喜欢音乐、擅长钢琴",
        voice_tone="少女、甜美、语速偏快",
        reference_image="D:/ref/xiayu.png"
    )
    
    # 添加角色
    manager.add_character(char1)
    manager.add_character(char2)
    manager.save_project()
    
    print("✓ 角色配置已保存")
    
    # 重新加载
    manager2 = AIProjectManager()
    loaded_project = manager2.load_project(test_file)
    
    assert loaded_project is not None
    assert len(loaded_project.character_config) == 2
    
    loaded_char1 = loaded_project.character_config[0]
    loaded_char2 = loaded_project.character_config[1]
    
    assert loaded_char1.char_id == "char_001"
    assert loaded_char1.char_name == "林风"
    assert loaded_char1.is_player == True
    assert loaded_char1.voice_model_id == "voice_001"
    
    assert loaded_char2.char_id == "char_002"
    assert loaded_char2.char_name == "夏雨"
    assert loaded_char2.reference_image == "D:/ref/xiayu.png"
    
    print("✓ 角色配置加载验证通过")
    print(f"  - 角色数量: {len(loaded_project.character_config)}")
    for char in loaded_project.character_config:
        print(f"    • {char.char_name} ({char.char_id})")
        print(f"      角色: {char.role}")
        print(f"      玩家角色: {'是' if char.is_player else '否'}")


def test_mixed_config():
    """测试混合配置"""
    print("\n" + "=" * 60)
    print("测试3: 混合配置（剧情+角色）")
    print("=" * 60)
    
    manager = AIProjectManager()
    
    temp_dir = tempfile.gettempdir()
    test_file = os.path.join(temp_dir, "test_mixed_config.vnai")
    
    if os.path.exists(test_file):
        os.remove(test_file)
    
    # 创建工程
    project = manager.create_new_project(
        project_name="完整测试",
        save_path=test_file
    )
    
    # 配置剧情
    story_config = StoryConfig(
        title="春日物语",
        style="日系校园、纯爱",
        plot_outline="春天的校园，少年少女的初恋故事",
        text_volume=10000,
        enable_choice_node=True,
        enable_condition_node=True
    )
    manager.update_story_config(story_config)
    
    # 添加多个角色
    for i in range(3):
        char = CharacterConfig(
            char_id=f"char_{str(i+1).zfill(3)}",
            char_name=f"角色{i+1}",
            role="主角" if i == 0 else "配角",
            is_player=(i == 0),
            persona_keywords=f"角色{i+1}的人设关键词"
        )
        manager.add_character(char)
    
    manager.save_project()
    
    print("✓ 混合配置已保存")
    
    # 验证
    manager2 = AIProjectManager()
    loaded = manager2.load_project(test_file)
    
    assert loaded.story_config.title == "春日物语"
    assert len(loaded.character_config) == 3
    assert loaded.character_config[0].is_player == True
    
    print("✓ 混合配置验证通过")
    print(f"  - 故事: {loaded.story_config.title}")
    print(f"  - 角色: {len(loaded.character_config)}个")


def main():
    """运行所有测试"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "配置界面数据读写测试" + " " * 18 + "║")
    print("╚" + "=" * 58 + "╝")
    
    try:
        test_story_config_save_load()
        test_character_config_save_load()
        test_mixed_config()
        
        print("\n" + "=" * 60)
        print("✓ 所有测试通过!")
        print("=" * 60)
        print()
        
    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
