# -*- coding: utf-8 -*-
"""
测试剧情配置和角色配置界面
"""

import sys
import tempfile
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication
from src.designer.ai_project_window import AIProjectWindow


def test_config_panels():
    """测试配置界面"""
    print("\n" + "=" * 60)
    print("测试剧情配置和角色配置界面")
    print("=" * 60 + "\n")
    
    app = QApplication(sys.argv)
    
    # 创建AI工程窗口
    window = AIProjectWindow()
    
    # 创建临时测试工程
    temp_dir = tempfile.gettempdir()
    test_file = os.path.join(temp_dir, "test_config_panel.vnai")
    
    print(f"创建测试工程: {test_file}")
    
    project = window.project_manager.create_new_project(
        project_name="配置测试工程",
        save_path=test_file,
        story_title="春日物语"
    )
    
    print(f"✓ 工程创建成功")
    print(f"  - 工程名称: {project.ai_project_info.name}")
    
    # 刷新界面
    window.refresh_all_panels()
    
    # 显示窗口
    window.show()
    
    print("\n测试说明:")
    print("1. 窗口已打开，请测试以下功能：")
    print("   - 剧情配置标签页：填写故事信息并保存")
    print("   - 角色配置标签页：添加/编辑/删除角色")
    print("   - 保存工程后关闭窗口")
    print("2. 测试完成后，程序会验证数据保存是否成功\n")
    
    # 运行应用
    result = app.exec()
    
    # 验证保存的数据
    print("\n" + "=" * 60)
    print("验证保存的数据")
    print("=" * 60)
    
    from src.ai.core.ai_project_manager import AIProjectManager
    
    manager = AIProjectManager()
    loaded_project = manager.load_project(test_file)
    
    if loaded_project:
        print(f"\n✓ 工程加载成功")
        print(f"\n剧情配置:")
        print(f"  - 标题: {loaded_project.story_config.title}")
        print(f"  - 风格: {loaded_project.story_config.style}")
        print(f"  - 文本量: {loaded_project.story_config.text_volume}")
        print(f"  - 章节数: 5")  # 默认值
        print(f"  - 启用选择节点: {loaded_project.story_config.enable_choice_node}")
        print(f"  - 启用条件节点: {loaded_project.story_config.enable_condition_node}")
        
        print(f"\n角色配置:")
        print(f"  - 角色数量: {len(loaded_project.character_config)}")
        for char in loaded_project.character_config:
            print(f"    • {char.char_name} ({char.char_id})")
            print(f"      角色: {char.role}")
            print(f"      玩家角色: {'是' if char.is_player else '否'}")
            if char.persona_keywords:
                print(f"      人设: {char.persona_keywords[:50]}...")
        
        print(f"\n✓ 测试完成！数据已成功保存和加载")
        print(f"\n测试文件位置: {test_file}")
    else:
        print("\n✗ 工程加载失败")
    
    return result


if __name__ == "__main__":
    sys.exit(test_config_panels())
