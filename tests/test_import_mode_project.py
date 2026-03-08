# -*- coding: utf-8 -*-

from __future__ import annotations

from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.models import StoryConfig


def test_project_mode_default_generate(tmp_path):
    manager = AIProjectManager()
    path = tmp_path / "default_generate.vnai"

    project = manager.create_new_project(
        project_name="mode_default",
        save_path=str(path),
        story_title="t",
        description="d",
    )

    assert project.ai_project_info.project_mode == "generate"


def test_project_mode_import_forces_single_route(tmp_path):
    manager = AIProjectManager()
    path = tmp_path / "import_mode.vnai"

    project = manager.create_new_project(
        project_name="mode_import",
        save_path=str(path),
        story_title="t",
        description="d",
        project_mode="import",
    )

    assert project.ai_project_info.project_mode == "import"
    assert project.story_config.enable_single_route is True
    assert project.story_config.enable_multi_branch is False
    assert project.story_config.enable_choice_node is False
    assert project.story_config.enable_condition_node is False
    assert project.story_config.allow_loop_story is False


def test_import_chapter_sources_roundtrip(tmp_path):
    manager = AIProjectManager()
    path = tmp_path / "import_sources.vnai"

    project = manager.create_new_project(
        project_name="mode_import",
        save_path=str(path),
        story_title="t",
        description="d",
        project_mode="import",
    )

    project.generation_history.import_chapter_sources = {
        "1": {"source": "text", "text": "hello", "file_path": ""}
    }
    manager.save_project()

    manager2 = AIProjectManager()
    loaded = manager2.load_project(str(path))
    assert loaded.generation_history.import_chapter_sources["1"]["text"] == "hello"


def test_import_mode_update_story_config_forces_single_route(tmp_path):
    manager = AIProjectManager()
    path = tmp_path / "import_update_story.vnai"

    manager.create_new_project(
        project_name="mode_import",
        save_path=str(path),
        story_title="t",
        description="d",
        project_mode="import",
    )

    bad = StoryConfig(
        title="t",
        style="s",
        plot_outline="o",
        text_volume=5000,
        chapter_count=3,
        enable_single_route=False,
        enable_multi_branch=True,
        enable_choice_node=True,
        enable_condition_node=True,
        allow_loop_story=True,
    )
    manager.update_story_config(bad)

    sc = manager.current_project.story_config
    assert sc.enable_single_route is True
    assert sc.enable_multi_branch is False
    assert sc.enable_choice_node is False
    assert sc.enable_condition_node is False
    assert sc.allow_loop_story is False
