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
    assert "300-500" in instruction or "300~500" in instruction
    assert "章节摘要" in instruction or "summary" in instruction
    assert params.get("text_volume") == 8000


def test_step3_prompt_requires_character_names_from_character_config_when_provided():
    sg = StepGenerator(ConfigManager())

    story = {
        "style": "现代",
        "text_volume": 5000,
        "chapter_count": 3,
        "enable_multi_branch": False,
    }
    outline = {"raw_response": "大纲..."}
    character_config = [
        {"char_id": "char_001", "char_name": "李雷", "role": "主角"},
        {"char_id": "char_002", "char_name": "韩梅梅", "role": "女主"},
    ]

    instruction, _ = sg.prepare_chapters_instruction(story, outline, character_config=character_config)

    assert "角色命名" in instruction
    assert "只能使用" in instruction
    assert "李雷" in instruction
    assert "韩梅梅" in instruction


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
    assert "1800" in instruction
    assert "1.5" in instruction or "×1.5" in instruction
    assert params.get("target_words") == 1200
    assert params.get("target_words_boosted") == 1800


def test_step4_prompt_includes_personas_raw_response_and_mp3_and_cn_char_rules_when_provided():
    sg = StepGenerator(ConfigManager())

    story_cfg = {
        "style": "现代",
        "enable_multi_branch": True,
        "enable_choice_node": False,
        "enable_condition_node": False,
    }
    personas = {"raw_response": "这里是步骤一的人设原始响应：主角性格外向，口头禅是‘没问题’。"}
    chapter_info = {"chapter_id": "1", "title": "第1章", "estimated_words": 300}

    instruction, params = sg.prepare_chapter_detail_instruction(
        0,
        chapter_info,
        previous_context=None,
        story_config=story_cfg,
        character_config=[{"char_id": "char_001", "char_name": "主角", "role": "主角"}],
        personas_data=personas,
        chapters_plan=None,
    )

    assert "原始响应" in instruction
    assert "步骤一的人设原始响应" in instruction
    assert ".mp3" in instruction
    assert "中文字符" in instruction
    assert "tts_ext" in instruction
    assert "必填" in instruction
    assert "emotion" in instruction
    assert "portrait" in instruction
    assert params.get("enforce_audio_mp3") is True
    assert params.get("enforce_cn_char_count") is True
    assert params.get("enforce_tts_ext_for_non_first_person") is True
    assert params.get("enforce_emotion_portrait_for_non_first_person") is True


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


def test_allow_loop_story_adds_loop_rules_to_prompts_when_multi_branch_enabled():
    sg = StepGenerator(ConfigManager())

    story = {
        "style": "现代",
        "text_volume": 8000,
        "chapter_count": 5,
        "enable_multi_branch": True,
        "enable_choice_node": True,
        "enable_condition_node": True,
        "allow_loop_story": True,
        "enable_single_route": False,
        "title": "测试",
        "plot_outline": "...",
    }
    personas = {"raw_response": "人设..."}
    outline = {"raw_response": "大纲..."}

    ins2, params2 = sg.prepare_outline_instruction(story, personas)
    assert "循环剧情" in ins2
    assert params2.get("allow_loop_story") is True

    ins3, params3 = sg.prepare_chapters_instruction(story, outline)
    assert "循环剧情" in ins3
    assert params3.get("allow_loop_story") is True

    chapter_info = {"chapter_id": "3", "title": "第3章", "estimated_words": 800}
    ins4, params4 = sg.prepare_chapter_detail_instruction(
        2,
        chapter_info,
        previous_context=None,
        story_config=story,
        character_config=[],
        chapters_plan=None,
    )
    assert "允许循环剧情" in ins4
    assert "循环剧情" in ins4
    assert params4.get("allow_loop_story") is True


def test_step3_generate_chapters_autofill_branch_plan_respects_route_order(monkeypatch):
    sg = StepGenerator(ConfigManager())

    # 模拟 LLM 只返回 chapters，branch_plan 不完整
    structured = {
        "word_budget": {"total_target": 8000, "by_route": {"common": 5000, "A": 1500, "B": 1500}},
        "chapters": [
            {"chapter_id": "1", "route": "common"},
            {"chapter_id": "2", "route": "common"},
            {"chapter_id": "3", "route": "common"},
            {"chapter_id": "4A", "route": "A"},
            {"chapter_id": "5A", "route": "A"},
            {"chapter_id": "4B", "route": "B"},
            {"chapter_id": "5B", "route": "B"},
            {"chapter_id": "6", "route": "common"},
        ],
        "branch_plan": [
            {"type": "linear", "at_chapter_id": "1", "next_chapter_id": "2"},
            # 故意缺失 2/3/4A/5A/4B/5B/6 的出口计划
        ],
    }

    def _fake_call_llm(*args, **kwargs):
        return ("RAW", structured)

    monkeypatch.setattr(sg, "_call_llm", _fake_call_llm)

    out = sg.generate_chapters("INS", {"allow_branch_plan": True})
    bp = out["structured"]["branch_plan"]
    by_at = {x.get("at_chapter_id"): x for x in bp}

    # common：应按 common 链接 1->2->3->6（而不是 3->4A）
    assert by_at["1"]["type"] == "linear" and by_at["1"]["next_chapter_id"] == "2"
    assert by_at["2"]["type"] == "linear" and by_at["2"]["next_chapter_id"] == "3"
    assert by_at["3"]["type"] == "linear" and by_at["3"]["next_chapter_id"] == "6"

    # route A：应 4A->5A，且 5A 默认 end（不猜测汇聚）
    assert by_at["4A"]["type"] == "linear" and by_at["4A"]["next_chapter_id"] == "5A"
    assert by_at["5A"]["type"] == "end"

    # route B：应 4B->5B，且 5B 默认 end
    assert by_at["4B"]["type"] == "linear" and by_at["4B"]["next_chapter_id"] == "5B"
    assert by_at["5B"]["type"] == "end"

