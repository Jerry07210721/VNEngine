# -*- coding: utf-8 -*-
"""
打包功能测试脚本
验证PackagerManager的核心功能
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.packager.packager_manager import PackagerManager


def test_packager_manager():
    """测试PackagerManager基本功能"""
    print("=" * 60)
    print("VNEngine 打包管理器测试")
    print("=" * 60)
    
    manager = PackagerManager()
    
    # 1. 测试PyInstaller检测
    print("\n1. 检测PyInstaller...")
    available, info = manager.verify_pyinstaller()
    print(f"   结果: {'✓ 可用' if available else '✗ 不可用'}")
    print(f"   信息: {info}")
    
    # 2. 测试Python可执行文件路径
    print("\n2. Python可执行文件路径:")
    python_exe = manager.get_python_executable()
    print(f"   {python_exe}")
    
    # 3. 测试venv检测
    print("\n3. 检测虚拟环境...")
    venv_site = manager.get_venv_site_packages()
    if venv_site:
        print(f"   ✓ 在虚拟环境中")
        print(f"   site-packages: {venv_site}")
    else:
        print(f"   ℹ 不在虚拟环境中（或无法检测）")
    
    # 4. 测试默认配置
    print("\n4. 默认配置:")
    default_config = manager.default_config
    for key, value in default_config.items():
        print(f"   {key}: {value}")
    
    # 5. 测试配置保存/加载（使用临时路径）
    print("\n5. 测试配置保存/加载...")
    test_project_path = project_root / "test_project.vngproj"
    test_config = {
        "app_name": "TestGame",
        "version": "0.1.0",
        "one_file": True,
    }
    
    try:
        # 合并配置
        full_config = manager.default_config.copy()
        full_config.update(test_config)
        
        manager.save_config(str(test_project_path), full_config)
        print("   ✓ 配置保存成功")
        
        loaded_config = manager.load_config(str(test_project_path))
        print("   ✓ 配置加载成功")
        
        if loaded_config.get("app_name") == "TestGame":
            print("   ✓ 配置内容正确")
        else:
            print("   ✗ 配置内容不匹配")
        
        # 清理测试文件
        config_file = test_project_path.parent / "packager_config.yaml"
        if config_file.exists():
            config_file.unlink()
            print("   ✓ 测试文件已清理")
        
    except Exception as e:
        print(f"   ✗ 测试失败: {e}")
    
    # 6. 测试打包命令生成（不实际执行）
    print("\n6. 测试打包命令生成...")
    try:
        # 使用实际存在的工程文件（如果有）
        test_projects = list(project_root.glob("**/*.vngproj"))
        if test_projects:
            test_project = test_projects[0]
            print(f"   使用测试工程: {test_project.name}")
            
            cmd = manager.build_pyinstaller_command(str(test_project), manager.default_config)
            print(f"   ✓ 命令生成成功")
            print(f"   命令长度: {len(cmd)} 个参数")
            print(f"   前5个参数: {' '.join(cmd[:5])}")
        else:
            print("   ℹ 未找到工程文件，跳过此测试")
    except Exception as e:
        print(f"   ✗ 命令生成失败: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    test_packager_manager()
