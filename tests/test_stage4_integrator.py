# -*- coding: utf-8 -*-
"""
阶段4测试脚本 - Integrator资源整合器
测试AI生成内容到VNEngine工程的整合
"""

import sys
import os
from pathlib import Path
import json
import tempfile
import shutil

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ai.integrator.integrator import Integrator
from src.ai.core.config_manager import ConfigManager
from src.ai.core.models import UserConfig, ProjectConfig, StoryConfig, CharacterConfig
from src.ai.log.logger import get_logger


class TestStage4:
    """阶段4测试类"""
    
    def __init__(self):
        self.logger = get_logger("TestStage4")
        self.test_dir = Path("output/test_stage4")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建临时测试数据
        self._create_test_data()
    
    def _create_test_data(self):
        """创建测试用的剧情和资源数据"""
        
        # 创建测试剧情数据
        plot_data = {
            "title": "测试剧情",
            "chapters": [
                {
                    "chapter_id": 1,
                    "title": "第一章",
                    "scenes": [
                        {
                            "location": "教室",
                            "description": "阳光明媚的早晨",
                            "dialogues": [
                                {
                                    "speaker": "Alice",
                                    "content": "早上好！",
                                    "emotion": "happy",
                                    "action": "微笑着走进教室"
                                },
                                {
                                    "speaker": "Bob",
                                    "content": "早上好，Alice！",
                                    "emotion": "neutral",
                                    "action": "抬头看向Alice"
                                },
                                {
                                    "speaker": "Alice",
                                    "content": "今天天气真好啊。",
                                    "emotion": "happy",
                                    "action": "看向窗外"
                                }
                            ]
                        },
                        {
                            "location": "走廊",
                            "description": "放学后的走廊",
                            "dialogues": [
                                {
                                    "speaker": "Bob",
                                    "content": "Alice，等一下！",
                                    "emotion": "worried",
                                    "action": "快步追上Alice"
                                },
                                {
                                    "speaker": "Alice",
                                    "content": "什么事？",
                                    "emotion": "neutral",
                                    "action": "转过身"
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        # 保存剧情数据
        self.plot_file = self.test_dir / "test_plot.json"
        with open(self.plot_file, 'w', encoding='utf-8') as f:
            json.dump(plot_data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"测试剧情数据已创建: {self.plot_file}")
        
        # 创建测试资源目录（模拟AI生成的资源）
        self.portraits_dir = self.test_dir / "portraits"
        self.portraits_dir.mkdir(exist_ok=True)
        
        # 为每个角色创建目录和模拟文件
        for char_name in ["Alice", "Bob"]:
            char_dir = self.portraits_dir / char_name
            char_dir.mkdir(exist_ok=True)
            
            # 创建空的测试图片文件
            for emotion in ["neutral", "happy", "sad"]:
                test_file = char_dir / f"{char_name}_{emotion}.png"
                test_file.write_bytes(b"FAKE_PNG_DATA")
        
        # 创建背景测试文件
        self.backgrounds_dir = self.test_dir / "backgrounds"
        self.backgrounds_dir.mkdir(exist_ok=True)
        
        for bg_name in ["classroom", "corridor", "park"]:
            test_file = self.backgrounds_dir / f"{bg_name}.png"
            test_file.write_bytes(b"FAKE_PNG_DATA")
        
        # 创建语音测试文件
        self.voice_dir = self.test_dir / "voice"
        self.voice_dir.mkdir(exist_ok=True)
        
        for char_name in ["Alice", "Bob"]:
            char_voice_dir = self.voice_dir / char_name
            char_voice_dir.mkdir(exist_ok=True)
            
            for i in range(3):
                test_file = char_voice_dir / f"dialogue_{i}.mp3"
                test_file.write_bytes(b"FAKE_MP3_DATA")
        
        # 创建BGM测试文件
        self.bgm_dir = self.test_dir / "bgm"
        self.bgm_dir.mkdir(exist_ok=True)
        
        for bgm_name in ["main_theme", "romantic"]:
            test_file = self.bgm_dir / f"{bgm_name}.mp3"
            test_file.write_bytes(b"FAKE_MP3_DATA")
        
        self.logger.info("测试资源数据已创建")
    
    def _create_test_config(self) -> UserConfig:
        """创建测试用的用户配置"""
        
        project_config = ProjectConfig(
            project_path="output/test_stage4/projects/TestProject",
            project_name="TestProject",
            window_width=1280,
            window_height=720,
            engine_version="2.0"
        )
        
        story_config = StoryConfig(
            title="测试故事",
            style="romance",
            plot_outline="一个测试故事",
            text_volume=5000
        )
        
        characters = [
            CharacterConfig(
                char_id="alice",
                char_name="Alice",
                persona_keywords="开朗,活泼,善良"
            ),
            CharacterConfig(
                char_id="bob",
                char_name="Bob",
                persona_keywords="沉稳,友善,可靠"
            )
        ]
        
        from src.ai.core.models import EnableAgentsConfig, MaterialConfig
        
        enable_agents = EnableAgentsConfig(
            plot_agent=True,
            portrait_agent=True,
            background_agent=True,
            cg_agent=True,
            voice_api=True,
            bgm_api=True
        )
        
        material_config = MaterialConfig(
            portrait_format="png",
            background_format="jpg",
            cg_format="png",
            voice_format="mp3",
            bgm_format="mp3"
        )
        
        return UserConfig(
            project_info=project_config,
            story_config=story_config,
            character_config=characters,
            enable_agents=enable_agents,
            material_config=material_config
        )
    
    def test_01_integrator_init(self):
        """测试1: Integrator初始化"""
        
        self.logger.info("测试1: Integrator初始化")
        
        try:
            integrator = Integrator()
            
            assert integrator is not None, "Integrator创建失败"
            assert integrator.config_manager is not None, "ConfigManager未初始化"
            
            self.logger.info("✓ 通过")
            return True
        
        except Exception as e:
            self.logger.error(f"✗ 失败: {e}")
            return False
    
    def test_02_create_project(self):
        """测试2: 创建工程目录"""
        
        self.logger.info("测试2: 创建工程目录")
        
        try:
            integrator = Integrator()
            
            project_path = integrator.create_project(
                project_name="TestProject",
                output_dir=str(self.test_dir / "projects")
            )
            
            assert project_path.exists(), "工程目录未创建"
            assert integrator.resources_dir.exists(), "资源目录未创建"
            assert integrator.portraits_dir.exists(), "立绘目录未创建"
            assert integrator.backgrounds_dir.exists(), "背景目录未创建"
            
            self.logger.info(f"  工程路径: {project_path}")
            self.logger.info("✓ 通过")
            return True
        
        except Exception as e:
            self.logger.error(f"✗ 失败: {e}")
            return False
    
    def test_03_integrate_plot(self):
        """测试3: 整合剧情数据"""
        
        self.logger.info("测试3: 整合剧情数据")
        
        try:
            integrator = Integrator()
            integrator.create_project(
                project_name="TestProject",
                output_dir=str(self.test_dir / "projects")
            )
            
            node_count = integrator.integrate_plot(str(self.plot_file))
            
            assert node_count > 0, "未生成节点"
            assert len(integrator.flow_nodes) == node_count, "节点数量不匹配"
            assert len(integrator.connections) == node_count - 1, "连接数量不正确"
            
            self.logger.info(f"  生成节点数: {node_count}")
            self.logger.info(f"  连接数: {len(integrator.connections)}")
            self.logger.info("✓ 通过")
            return True
        
        except Exception as e:
            self.logger.error(f"✗ 失败: {e}")
            return False
    
    def test_04_integrate_portraits(self):
        """测试4: 整合立绘资源"""
        
        self.logger.info("测试4: 整合立绘资源")
        
        try:
            integrator = Integrator()
            integrator.create_project(
                project_name="TestProject",
                output_dir=str(self.test_dir / "projects")
            )
            
            integrator.integrate_plot(str(self.plot_file))
            
            char_mapping = {
                "Alice": "Alice",
                "Bob": "Bob"
            }
            
            integrator.integrate_portraits(str(self.portraits_dir), char_mapping)
            
            # 检查文件是否复制
            portrait_files = list(integrator.portraits_dir.glob("*.png"))
            
            assert len(portrait_files) > 0, "立绘文件未复制"
            
            # 检查节点是否更新了立绘路径
            nodes_with_portrait = [n for n in integrator.flow_nodes if n.portrait]
            
            self.logger.info(f"  复制立绘数: {len(portrait_files)}")
            self.logger.info(f"  设置立绘节点数: {len(nodes_with_portrait)}")
            self.logger.info("✓ 通过")
            return True
        
        except Exception as e:
            self.logger.error(f"✗ 失败: {e}")
            return False
    
    def test_05_integrate_backgrounds(self):
        """测试5: 整合背景资源"""
        
        self.logger.info("测试5: 整合背景资源")
        
        try:
            integrator = Integrator()
            integrator.create_project(
                project_name="TestProject",
                output_dir=str(self.test_dir / "projects")
            )
            
            integrator.integrate_plot(str(self.plot_file))
            integrator.integrate_backgrounds(str(self.backgrounds_dir))
            
            # 检查文件是否复制
            bg_files = list(integrator.backgrounds_dir.glob("*.png"))
            
            assert len(bg_files) > 0, "背景文件未复制"
            
            # 检查节点是否设置了背景
            nodes_with_bg = [n for n in integrator.flow_nodes if n.background]
            
            self.logger.info(f"  复制背景数: {len(bg_files)}")
            self.logger.info(f"  设置背景节点数: {len(nodes_with_bg)}")
            self.logger.info("✓ 通过")
            return True
        
        except Exception as e:
            self.logger.error(f"✗ 失败: {e}")
            return False
    
    def test_06_generate_project_file(self):
        """测试6: 生成工程文件"""
        
        self.logger.info("测试6: 生成工程文件")
        
        try:
            integrator = Integrator()
            
            project_path = integrator.create_project(
                project_name="TestProject",
                output_dir=str(self.test_dir / "projects")
            )
            
            integrator.integrate_plot(str(self.plot_file))
            
            user_config = self._create_test_config()
            project_file = integrator.generate_project_file(user_config)
            
            assert Path(project_file).exists(), "工程文件未生成"
            
            # 验证工程文件内容
            with open(project_file, 'r', encoding='utf-8') as f:
                project_data = json.load(f)
            
            assert "project_info" in project_data, "缺少project_info"
            assert "flow_data" in project_data, "缺少flow_data"
            assert "nodes" in project_data["flow_data"], "缺少nodes"
            assert "connections" in project_data["flow_data"], "缺少connections"
            
            self.logger.info(f"  工程文件: {project_file}")
            self.logger.info(f"  节点数: {len(project_data['flow_data']['nodes'])}")
            self.logger.info("✓ 通过")
            return True
        
        except Exception as e:
            self.logger.error(f"✗ 失败: {e}")
            return False
    
    def test_07_integrate_all(self):
        """测试7: 一键整合所有资源"""
        
        self.logger.info("测试7: 一键整合所有资源")
        
        try:
            integrator = Integrator()
            user_config = self._create_test_config()
            
            result = integrator.integrate_all(
                user_config=user_config,
                plot_file=str(self.plot_file),
                portraits_dir=str(self.portraits_dir),
                backgrounds_dir=str(self.backgrounds_dir),
                voice_dir=str(self.voice_dir),
                bgm_dir=str(self.bgm_dir)
            )
            
            assert result["success"], "整合失败"
            assert result["node_count"] > 0, "未生成节点"
            assert Path(result["project_file"]).exists(), "工程文件未生成"
            
            # 获取统计信息
            stats = integrator.get_statistics()
            
            self.logger.info(f"  工程路径: {result['project_path']}")
            self.logger.info(f"  节点数: {result['node_count']}")
            self.logger.info(f"  连接数: {result['connection_count']}")
            self.logger.info(f"  立绘数: {stats['portrait_count']}")
            self.logger.info(f"  背景数: {stats['background_count']}")
            self.logger.info(f"  语音数: {stats['voice_count']}")
            self.logger.info(f"  BGM数: {stats['bgm_count']}")
            self.logger.info("✓ 通过")
            return True
        
        except Exception as e:
            self.logger.error(f"✗ 失败: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        
        self.logger.info("=" * 80)
        self.logger.info("开始阶段4测试 - Integrator资源整合器")
        self.logger.info("=" * 80)
        
        tests = [
            self.test_01_integrator_init,
            self.test_02_create_project,
            self.test_03_integrate_plot,
            self.test_04_integrate_portraits,
            self.test_05_integrate_backgrounds,
            self.test_06_generate_project_file,
            self.test_07_integrate_all
        ]
        
        passed = 0
        failed = 0
        
        for test_func in tests:
            if test_func():
                passed += 1
            else:
                failed += 1
            self.logger.info("")
        
        self.logger.info("=" * 80)
        self.logger.info(f"总计: {passed + failed} 个测试")
        self.logger.info(f"通过: {passed}")
        self.logger.info(f"失败: {failed}")
        
        if failed == 0:
            self.logger.info("🎉 所有测试通过！阶段4开发完成！")
        else:
            self.logger.warning("⚠️  部分测试失败，需要修复")
        
        self.logger.info("=" * 80)


if __name__ == "__main__":
    tester = TestStage4()
    tester.run_all_tests()
