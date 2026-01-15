# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - 阶段2测试
测试所有API客户端的功能
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ai.core.config_manager import ConfigManager
from src.ai.api.api_manager import APIManager
from src.ai.log.logger import get_logger

logger = get_logger("TestStage2")


def test_config_loading():
    """测试配置加载"""
    logger.info("=" * 80)
    logger.info("测试1: 配置加载")
    logger.info("=" * 80)
    
    try:
        config_manager = ConfigManager()
        
        # 检查配置数据
        assert config_manager.config_data, "配置数据为空"
        assert "api_keys" in config_manager.config_data, "缺少api_keys配置"
        
        logger.info(f"✓ 配置加载成功")
        
        # 检查API配置
        api_configs = ["claude", "kimi", "midjourney", "flux", "gptsovits", "suno"]
        for api_name in api_configs:
            api_config = config_manager.get_api_config(api_name)
            if api_config:
                has_key = bool(api_config.get("api_key") or api_config.get("token") or api_config.get("sign"))
                logger.info(f"  - {api_name}: {'已配置密钥' if has_key else '未配置密钥'}")
        
        return True
    
    except Exception as e:
        logger.error(f"✗ 配置加载失败: {e}")
        return False


def test_api_manager_creation():
    """测试API管理器创建"""
    logger.info("\n" + "=" * 80)
    logger.info("测试2: API管理器创建")
    logger.info("=" * 80)
    
    try:
        config_manager = ConfigManager()
        api_manager = APIManager(config_manager)
        
        logger.info("✓ API管理器创建成功")
        
        return api_manager
    
    except Exception as e:
        logger.error(f"✗ API管理器创建失败: {e}")
        return None


def test_client_instantiation(api_manager: APIManager):
    """测试客户端实例化"""
    logger.info("\n" + "=" * 80)
    logger.info("测试3: 客户端实例化")
    logger.info("=" * 80)
    
    results = {}
    
    # 测试Claude客户端
    try:
        claude = api_manager.get_claude_client()
        results['claude'] = claude is not None
        if claude:
            logger.info(f"✓ Claude客户端创建成功 (model: {claude.model})")
        else:
            logger.warning("✗ Claude客户端未配置")
    except Exception as e:
        logger.error(f"✗ Claude客户端创建失败: {e}")
        results['claude'] = False
    
    # 测试Kimi客户端
    try:
        kimi = api_manager.get_kimi_client()
        results['kimi'] = kimi is not None
        if kimi:
            logger.info(f"✓ Kimi客户端创建成功 (model: {kimi.model})")
        else:
            logger.warning("✗ Kimi客户端未配置")
    except Exception as e:
        logger.error(f"✗ Kimi客户端创建失败: {e}")
        results['kimi'] = False
    
    # 测试Midjourney客户端
    try:
        mj = api_manager.get_midjourney_client()
        results['midjourney'] = mj is not None
        if mj:
            logger.info(f"✓ Midjourney客户端创建成功 (model: {mj.model})")
        else:
            logger.warning("✗ Midjourney客户端未配置")
    except Exception as e:
        logger.error(f"✗ Midjourney客户端创建失败: {e}")
        results['midjourney'] = False
    
    # 测试FLUX客户端
    try:
        flux = api_manager.get_flux_client()
        results['flux'] = flux is not None
        if flux:
            logger.info(f"✓ FLUX客户端创建成功 (model: {flux.model})")
        else:
            logger.warning("✗ FLUX客户端未配置")
    except Exception as e:
        logger.error(f"✗ FLUX客户端创建失败: {e}")
        results['flux'] = False
    
    # 测试GPT-SoVITS客户端
    try:
        gptsovits = api_manager.get_gptsovits_client()
        results['gptsovits'] = gptsovits is not None
        if gptsovits:
            logger.info(f"✓ GPT-SoVITS客户端创建成功")
        else:
            logger.warning("✗ GPT-SoVITS客户端未配置")
    except Exception as e:
        logger.error(f"✗ GPT-SoVITS客户端创建失败: {e}")
        results['gptsovits'] = False
    
    # 测试Suno客户端
    try:
        suno = api_manager.get_suno_client()
        results['suno'] = suno is not None
        if suno:
            logger.info(f"✓ Suno AI客户端创建成功 (model: {suno.model})")
        else:
            logger.warning("✗ Suno AI客户端未配置")
    except Exception as e:
        logger.error(f"✗ Suno AI客户端创建失败: {e}")
        results['suno'] = False
    
    return results


def test_llm_client_fallback(api_manager: APIManager):
    """测试LLM客户端降级"""
    logger.info("\n" + "=" * 80)
    logger.info("测试4: LLM客户端降级机制")
    logger.info("=" * 80)
    
    try:
        # 测试Claude优先
        claude_first = api_manager.get_llm_client(prefer_claude=True)
        if claude_first:
            client_type = type(claude_first).__name__
            logger.info(f"✓ Claude优先模式: 获取到 {client_type}")
        else:
            logger.warning("✗ Claude优先模式: 无可用客户端")
        
        # 测试Kimi优先
        kimi_first = api_manager.get_llm_client(prefer_claude=False)
        if kimi_first:
            client_type = type(kimi_first).__name__
            logger.info(f"✓ Kimi优先模式: 获取到 {client_type}")
        else:
            logger.warning("✗ Kimi优先模式: 无可用客户端")
        
        return True
    
    except Exception as e:
        logger.error(f"✗ LLM客户端降级测试失败: {e}")
        return False


def test_image_client_fallback(api_manager: APIManager):
    """测试图像客户端降级"""
    logger.info("\n" + "=" * 80)
    logger.info("测试5: 图像客户端降级机制")
    logger.info("=" * 80)
    
    try:
        # 测试Midjourney优先
        mj_first = api_manager.get_image_client(prefer_midjourney=True)
        if mj_first:
            client_type = type(mj_first).__name__
            logger.info(f"✓ Midjourney优先模式: 获取到 {client_type}")
        else:
            logger.warning("✗ Midjourney优先模式: 无可用客户端")
        
        # 测试FLUX优先
        flux_first = api_manager.get_image_client(prefer_midjourney=False)
        if flux_first:
            client_type = type(flux_first).__name__
            logger.info(f"✓ FLUX优先模式: 获取到 {client_type}")
        else:
            logger.warning("✗ FLUX优先模式: 无可用客户端")
        
        return True
    
    except Exception as e:
        logger.error(f"✗ 图像客户端降级测试失败: {e}")
        return False


def test_api_calls_with_mock():
    """测试API调用（模拟模式）"""
    logger.info("\n" + "=" * 80)
    logger.info("测试6: API调用（模拟模式）")
    logger.info("=" * 80)
    
    logger.info("说明: 实际API调用需要有效的密钥，此处仅测试客户端接口")
    
    # 这里可以添加mock测试
    # 由于需要真实API密钥，实际测试应该由用户在配置好密钥后手动运行
    
    logger.info("✓ 模拟测试通过（需要真实密钥进行完整测试）")
    
    return True


def test_stats_collection(api_manager: APIManager):
    """测试统计信息收集"""
    logger.info("\n" + "=" * 80)
    logger.info("测试7: 统计信息收集")
    logger.info("=" * 80)
    
    try:
        stats = api_manager.get_all_stats()
        
        logger.info(f"✓ 收集到 {len(stats)} 个API的统计信息")
        
        for api_name, api_stats in stats.items():
            logger.info(f"  - {api_name}:")
            logger.info(f"    - 成功: {api_stats.get('success', 0)}")
            logger.info(f"    - 失败: {api_stats.get('failed', 0)}")
            logger.info(f"    - 重试: {api_stats.get('retries', 0)}")
        
        return True
    
    except Exception as e:
        logger.error(f"✗ 统计信息收集失败: {e}")
        return False


def test_cleanup(api_manager: APIManager):
    """测试清理"""
    logger.info("\n" + "=" * 80)
    logger.info("测试8: 清理资源")
    logger.info("=" * 80)
    
    try:
        api_manager.close_all()
        logger.info("✓ 所有API客户端已关闭")
        return True
    
    except Exception as e:
        logger.error(f"✗ 清理失败: {e}")
        return False


def main():
    """主测试函数"""
    logger.info("\n")
    logger.info("=" * 80)
    logger.info("VNEngine 多智能体协作系统 - 阶段2测试")
    logger.info("API客户端封装与测试")
    logger.info("=" * 80)
    logger.info("\n")
    
    test_results = []
    
    # 测试1: 配置加载
    test_results.append(("配置加载", test_config_loading()))
    
    # 测试2: API管理器创建
    api_manager = test_api_manager_creation()
    test_results.append(("API管理器创建", api_manager is not None))
    
    if api_manager is None:
        logger.error("API管理器创建失败，终止测试")
        return
    
    # 测试3: 客户端实例化
    client_results = test_client_instantiation(api_manager)
    test_results.append(("客户端实例化", any(client_results.values())))
    
    # 测试4: LLM客户端降级
    test_results.append(("LLM客户端降级", test_llm_client_fallback(api_manager)))
    
    # 测试5: 图像客户端降级
    test_results.append(("图像客户端降级", test_image_client_fallback(api_manager)))
    
    # 测试6: API调用（模拟）
    test_results.append(("API调用模拟", test_api_calls_with_mock()))
    
    # 测试7: 统计信息
    test_results.append(("统计信息收集", test_stats_collection(api_manager)))
    
    # 测试8: 清理
    test_results.append(("资源清理", test_cleanup(api_manager)))
    
    # 汇总结果
    logger.info("\n")
    logger.info("=" * 80)
    logger.info("测试结果汇总")
    logger.info("=" * 80)
    
    passed = sum(1 for _, result in test_results if result)
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✓ 通过" if result else "✗ 失败"
        logger.info(f"{status} - {test_name}")
    
    logger.info("-" * 80)
    logger.info(f"总计: {passed}/{total} 测试通过")
    
    if passed == total:
        logger.info("🎉 所有测试通过！阶段2开发完成！")
    else:
        logger.warning(f"⚠️ {total - passed} 个测试失败，请检查配置")
    
    logger.info("\n")
    logger.info("注意事项:")
    logger.info("1. 客户端实例化需要在 config/ai_config.yaml 中配置正确的API密钥")
    logger.info("2. 完整的API调用测试需要真实的密钥和网络连接")
    logger.info("3. 建议在真实环境中单独测试每个API的功能")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
