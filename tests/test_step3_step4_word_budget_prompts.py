# -*- coding: utf-8 -*-

from src.ai.core.config_manager import ConfigManager
from src.ai.core.step_generator import StepGenerator


def test_step3_prompt_includes_word_budget_and_sum_rule():
    sg = StepGenerator(ConfigManager())

    story = {
        "style": "现代",
        "text_volume": 8000,
        "chapter_count": 5,
        "enable_choice_node": True,
        "enable_condition_node": False,
        "enable_multi_branch": True,
    }
    outline = {"raw_response": "大纲..."}

    instruction, params = sg.prepare_chapters_instruction(story, outline)

    assert "目标总文本量" in instruction
    assert "8000" in instruction
    assert "estimated_words" in instruction
    assert "总和" in instruction or "总" in instruction
    assert params.get("text_volume") == 8000


def test_step2_and_step3_prompt_includes_single_route_rules_when_enabled():
    sg = StepGenerator(ConfigManager())

    story = {
        "style": "现代",
        "text_volume": 8000,
        "chapter_count": 5,
        "enable_choice_node": False,
        "enable_condition_node": False,
        "enable_multi_branch": False,
        "enable_single_route": True,
        "title": "测试",
        "plot_outline": "...",
    }
    personas = {"raw_response": "人设..."}
    outline = {"raw_response": "大纲..."}

    ins2, params2 = sg.prepare_outline_instruction(story, personas)
    assert "单线叙事" in ins2
    assert params2.get("enable_single_route") is True

    ins3, params3 = sg.prepare_chapters_instruction(story, outline)
    assert "单线叙事" in ins3
    assert params3.get("enable_single_route") is True


def test_step2_prompt_requires_branch_control_plan_when_multi_branch_enabled():
    sg = StepGenerator(ConfigManager())

    story = {
        "style": "现代",
        "text_volume": 8000,
        "chapter_count": 5,
        "enable_multi_branch": True,
        "enable_choice_node": True,
        "enable_condition_node": True,
        "enable_single_route": False,
        "title": "测试",
        "plot_outline": "...",
    }
    personas = {"raw_response": "人设..."}

    ins2, params2 = sg.prepare_outline_instruction(story, personas)

    assert "分支控制计划" in ins2
    assert "var_ops" in ins2
    assert "condition" in ins2
    assert params2.get("enable_multi_branch") is True
    assert params2.get("enable_choice") is True
    assert params2.get("enable_condition") is True


def test_step4_prompt_includes_chapter_target_words():
    sg = StepGenerator(ConfigManager())

    story_cfg = {
        "style": "现代",
        "enable_choice_node": False,
        "enable_condition_node": False,
        "enable_multi_branch": True,
    }
    chapter_info = {
        "chapter_id": "4A",
        "title": "第4A章",
        "estimated_words": 1200,
    }

    instruction, params = sg.prepare_chapter_detail_instruction(
        0,
        chapter_info,
        previous_context=None,
        story_config=story_cfg,
        character_config=[],
    )

    assert "本章目标字数" in instruction
    assert "1200" in instruction
    assert params.get("target_words") == 1200


def test_step4_prompt_includes_step3_chapters_plan_when_provided():
    sg = StepGenerator(ConfigManager())

    story_cfg = {
        "style": "现代",
        "enable_multi_branch": True,
        "enable_choice_node": True,
        "enable_condition_node": True,
    }
    chapters_plan = {
        "chapters": [
            {"chapter_id": "1", "title": "第1章", "summary": "...", "estimated_words": 800, "route": "common"},
            {"chapter_id": "3", "title": "第3章-关键选择", "summary": "...", "estimated_words": 800, "route": "common"},
            {"chapter_id": "4A", "title": "第4A章", "summary": "...", "estimated_words": 600, "route": "A"},
        ],
        "branch_plan": [
            {
                "type": "choice",
                "at_chapter_id": "3",
                "prompt": "测试选择",
                "options": [
                    {"text": "A", "next_chapter_id": "4A"},
                    {"text": "B", "next_chapter_id": "4B"},
                ],
            }
        ],
    }
    chapter_info = {"chapter_id": "3", "title": "第3章-关键选择", "estimated_words": 800}

    instruction, params = sg.prepare_chapter_detail_instruction(
        2,
        chapter_info,
        previous_context=None,
        story_config=story_cfg,
        character_config=[],
        chapters_plan=chapters_plan,
    )

    assert "Step3 章节规划" in instruction
    assert "chapter_id=3" in instruction
    assert params.get("has_chapters_plan") is True
