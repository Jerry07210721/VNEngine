# -*- coding: utf-8 -*-

from src.ai.core.config_manager import ConfigManager
from src.ai.core.step_generator import StepGenerator


def test_step5_text_node_aggregation_and_split_rules():
    sg = StepGenerator(ConfigManager())

    story = {
        "style": "现代",
        "enable_condition_node": False,
    }
    chars = [
        {"char_id": "char_a", "char_name": "Alice"},
        {"char_id": "char_b", "char_name": "Bob"},
    ]

    chapter_details = [
        {
            "structured": {
                "chapter_title": "第1章",
                "summary": "测试聚合",
                "dialogues": [
                    {"background": "bg_room", "bgm": "bgm_calm"},
                    {"speaker": "Alice", "text": "第一句"},
                    {"speaker": "Alice", "text": "第二句"},
                    {"background": "bg_street"},
                    {"speaker": "Bob", "text": "第三句"},
                    {"bgm": "stop"},
                    {"hide_textbox": True},
                    {"speaker": "Bob", "text": "第四句"},
                ],
            }
        }
    ]

    result = sg.build_pending_and_flow(story, chars, chapter_details)
    nodes = result["flow_nodes"]
    conns = result["connections"]
    pending = result["pending_lists"]

    # 期望：
    # - 前两句聚合到同一 text node (bg_room + bgm_calm)
    # - background 改变强制新 node
    # - stop_bgm / hide_textbox 变化强制新 node
    assert len(nodes) == 3
    assert all(n.node_type == "text" for n in nodes)

    assert len(nodes[0].sub_dialogues) == 2
    assert nodes[0].background.endswith("resources/images/bg_room.png")
    assert nodes[0].bgm.endswith("resources/audios/bgm_calm.mp3")

    assert len(nodes[1].sub_dialogues) == 1
    assert nodes[1].background.endswith("resources/images/bg_street.png")

    assert len(nodes[2].sub_dialogues) == 1
    assert nodes[2].stop_bgm is True
    assert nodes[2].bgm in ("", None)
    # hide_textbox 在运行时由 sub_dialogues 覆盖 node
    assert bool(nodes[2].sub_dialogues[0].get("hide_textbox")) is True

    # 顺序连接：3 个节点 => 2 条连接
    assert len(conns) == 2

    # voices 数量应等于有文本的对白数量（4句）
    assert len(pending.voices) == 4
    # backgrounds：bg_room/bg_street + 章节默认背景(若未用也会生成兜底) 可能存在 >=2
    assert len(pending.backgrounds) >= 2
    # bgm：bgm_calm + 章节默认bgm(兜底) 可能存在 >=1
    assert len(pending.bgms) >= 1


def test_step5_pov_first_person_skips_portrait_and_voice_and_cg_pending_has_node_id():
    sg = StepGenerator(ConfigManager())

    story = {
        "style": "现代",
        "enable_condition_node": False,
        "narrative_pov": "first",
        "first_person_name": "我",
        "first_person_has_portrait": False,
        "first_person_has_voice": False,
    }

    chars = [
        {"char_id": "char_player", "char_name": "我", "is_player": True, "voice_model_id": "playerModel"},
        {"char_id": "char_a", "char_name": "Alice", "voice_model_id": "aliceModel"},
    ]

    chapter_details = [
        {
            "structured": {
                "chapter_title": "第1章",
                "summary": "测试POV/CG",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_room", "bgm": "bgm_calm"},
                        "dialogues": [
                            {"speaker": "我", "text": "我在想……"},
                            {"speaker": "Alice", "text": "你好", "emotion": "happy"},
                        ],
                    },
                    {
                        "type": "text",
                        "directives": {"cg": "cg_01_01"},
                        "dialogues": [
                            {"speaker": "Alice", "text": "看这里"},
                        ],
                    },
                    {
                        "type": "text",
                        "directives": {"background": "bg_room"},
                        "dialogues": [
                            {"speaker": "我", "text": "（继续）"},
                        ],
                    },
                ],
            }
        }
    ]

    result = sg.build_pending_and_flow(story, chars, chapter_details)
    nodes = result["flow_nodes"]
    pending = result["pending_lists"]

    # 背景->CG->背景：应形成3个节点
    assert len(nodes) == 3
    assert nodes[0].background.endswith("resources/images/bg_room.png")
    assert nodes[1].background.endswith("resources/images/cg/cg_01_01.png")
    assert nodes[2].background.endswith("resources/images/bg_room.png")

    # 第一人称对白：不引用 portrait/voice
    assert nodes[0].sub_dialogues[0]["speaker"] == "我"
    assert nodes[0].sub_dialogues[0]["portrait"] in ("", None)
    assert nodes[0].sub_dialogues[0]["voice"] in ("", None)

    # 只为 Alice 生成语音，并带上 voice_model_id
    assert len(pending.voices) == 2
    assert all(v.speaker == "Alice" for v in pending.voices)
    assert all(v.voice_model_id == "aliceModel" for v in pending.voices)

    # 第一人称无立绘：不生成对应 portrait pending
    assert all(p.char_id != "char_player" for p in pending.portraits)

    # CG pending 应存在且 node_id 应指向使用 CG 的节点
    assert len(pending.cgs) == 1
    assert pending.cgs[0].file_path.endswith("resources/images/cg/cg_01_01.png")
    assert pending.cgs[0].node_id == str(nodes[1].id)


def test_step5_portrait_description_prefers_step1_persona_over_character_keywords():
    sg = StepGenerator(ConfigManager())

    story = {"style": "现代", "enable_condition_node": False}
    chars = [
        {"char_id": "char_a", "char_name": "Alice", "persona_keywords": "KEYWORDS_SHOULD_NOT_WIN"},
    ]
    personas_data = {
        "structured": {
            "personas": [
                {"char_id": "char_a", "persona": "STEP1_PERSONA_SHOULD_WIN"},
            ]
        }
    }

    chapter_details = [
        {
            "structured": {
                "chapter_title": "第1章",
                "summary": "测试人设来源",
                "dialogues": [
                    {"speaker": "Alice", "text": "你好"},
                ],
            }
        }
    ]

    result = sg.build_pending_and_flow(story, chars, chapter_details, personas_data=personas_data)
    pending = result["pending_lists"]
    assert len(pending.portraits) == 1
    assert pending.portraits[0].description == "STEP1_PERSONA_SHOULD_WIN"


def test_step5_background_pending_description_not_identical_across_backgrounds():
    sg = StepGenerator(ConfigManager())

    story = {"style": "现代", "enable_condition_node": False}
    chars = [
        {"char_id": "char_a", "char_name": "Alice"},
    ]

    chapter_details = [
        {
            "structured": {
                "chapter_title": "第1章",
                "summary": "测试背景描述",
                "scenes": [
                    {
                        "title": "室内",
                        "type": "text",
                        "directives": {"background": "bg_room"},
                        "dialogues": [
                            {"speaker": "Alice", "text": "这里好安静"},
                        ],
                    },
                    {
                        "title": "街道",
                        "type": "text",
                        "directives": {"background": "bg_street"},
                        "dialogues": [
                            {"speaker": "Alice", "text": "外面好热闹"},
                        ],
                    },
                ],
            }
        }
    ]

    result = sg.build_pending_and_flow(story, chars, chapter_details)
    pending = result["pending_lists"]
    desc_by_path = {b.file_path: b.description for b in pending.backgrounds}
    assert "resources/images/bg_room.png" in desc_by_path
    assert "resources/images/bg_street.png" in desc_by_path
    assert desc_by_path["resources/images/bg_room.png"] != desc_by_path["resources/images/bg_street.png"]
