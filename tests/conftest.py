from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root is importable when tests are run from arbitrary CWD.
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai.api.api_manager import APIManager
from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.config_manager import ConfigManager
from src.ai.core.master_agent import MasterAgent

from src.ai.agents.background_agent import BackgroundAgent
from src.ai.agents.bgm_agent import BGMAgent
from src.ai.agents.cg_agent import CGAgent
from src.ai.agents.plot_agent import PlotAgent
from src.ai.agents.portrait_agent import PortraitAgent
from src.ai.agents.voice_agent import VoiceAgent


@pytest.fixture
def file_path(tmp_path: Path) -> str:
    """Temporary .vnai file path with a minimal created project."""
    manager = AIProjectManager()
    test_file = tmp_path / "test_project.vnai"

    manager.create_new_project(
        project_name="测试工程",
        save_path=str(test_file),
        story_title="夏日的风",
        description="这是一个测试AI工程",
    )

    assert test_file.exists()
    return str(test_file)


@pytest.fixture
def manager(file_path: str) -> AIProjectManager:
    """AIProjectManager with current_project loaded from file_path."""
    mgr = AIProjectManager()
    project = mgr.load_project(file_path)
    assert project is not None
    return mgr


@pytest.fixture
def config_manager() -> ConfigManager:
    return ConfigManager()


@pytest.fixture
def api_manager(config_manager: ConfigManager) -> APIManager:
    return APIManager(config_manager)


@pytest.fixture
def master(config_manager: ConfigManager, api_manager: APIManager) -> MasterAgent:
    return MasterAgent(config_manager, api_manager)


@pytest.fixture
def agents(config_manager: ConfigManager, api_manager: APIManager) -> dict:
    return {
        "plot_agent": PlotAgent(config_manager, api_manager),
        "portrait_agent": PortraitAgent(config_manager, api_manager),
        "background_agent": BackgroundAgent(config_manager, api_manager),
        "cg_agent": CGAgent(config_manager, api_manager),
        "voice_agent": VoiceAgent(config_manager, api_manager),
        "bgm_agent": BGMAgent(config_manager, api_manager),
    }
