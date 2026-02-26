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
                    {
                        "background": "bg_room",
                        "bgm": "bgm_calm",
                        "bgm_desc": "舒缓的室内氛围钢琴配乐，柔和不抢戏",
                        "bgm_tags": "ambient, calm, piano, soft, slow, instrumental",
                    },
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

    bgm_calm = next((b for b in pending.bgms if str(b.file_path or "").endswith("bgm_calm.mp3")), None)
    assert bgm_calm is not None
    assert "piano" in (bgm_calm.tags or "")


def test_step5_sub_dialogue_var_ops_are_preserved_per_line():
    sg = StepGenerator(ConfigManager())

    story = {
        "style": "现代",
        "enable_condition_node": False,
    }
    chars = [
        {"char_id": "char_a", "char_name": "Alice"},
    ]

    chapter_details = [
        {
            "structured": {
                "chapter_title": "第1章",
                "summary": "测试子对白变量处理",
                "dialogues": [
                    {"background": "bg_room"},
                    {
                        "speaker": "Alice",
                        "text": "设置变量",
                        "var_ops": [
                            {
                                "dest": "flag",
                                "op": "=",
                                "left": 0,
                                "left_const": True,
                                "right": 1,
                                "right_const": True,
                            }
                        ],
                    },
                    {"speaker": "Alice", "text": "后续对白"},
                ],
            }
        }
    ]

    result = sg.build_pending_and_flow(story, chars, chapter_details)
    nodes = result["flow_nodes"]
    assert len(nodes) == 1
    assert nodes[0].node_type == "text"
    assert len(nodes[0].sub_dialogues) == 2

    first = nodes[0].sub_dialogues[0]
    second = nodes[0].sub_dialogues[1]

    assert isinstance(first.get("var_ops"), list)
    assert first["var_ops"][0]["dest"] == "flag"
    assert first["var_ops"][0]["op"] == "="
    assert isinstance(second.get("var_ops"), list)
    assert second.get("var_ops") in ([], None)


def test_step5_missing_target_chapter_falls_back_to_next_chapter_to_avoid_dangling_option_node():
    sg = StepGenerator(ConfigManager())

    story = {
        "style": "现代",
        "enable_condition_node": False,
    }
    chars = [
        {"char_id": "char_a", "char_name": "Alice"},
    ]

    chapter_details = [
        {
            "structured": {
                "chapter_id": "1",
                "chapter_title": "第1章",
                "summary": "测试缺失目标章节",
                "scenes": [
                    {"type": "text", "directives": {"background": "bg_room"}, "dialogues": [{"speaker": "Alice", "text": "1"}]}
                ],
                "exit": {
                    "type": "choice",
                    "choice": {
                        "prompt": "去不存在的章节？",
                        "options": [
                            {"text": "去不存在", "next_chapter_id": "MISSING_CHAPTER", "node": {"dialogues": []}},
                            {"text": "去下一章", "next_chapter_id": "2", "node": {"dialogues": []}},
                        ],
                    },
                },
            }
        },
        {
            "structured": {
                "chapter_id": "2",
                "chapter_title": "第2章",
                "summary": "下一章",
                "scenes": [
                    {"type": "text", "directives": {"background": "bg_room"}, "dialogues": [{"speaker": "Alice", "text": "2"}]}
                ],
                "exit": {"type": "end"},
            }
        },
    ]

    result = sg.build_pending_and_flow(story, chars, chapter_details)
    nodes = result["flow_nodes"]
    conns = result["connections"]

    start_2 = next(n for n in nodes if n.node_type == "text" and n.title == "第2章")
    opt_missing = next(n for n in nodes if n.node_type == "text" and n.title == "选项：去不存在")

    # 目标章节不存在时，应 fallback 到下一章（第2章）首节点，避免 opt_missing 无下游
    assert any(c.source == opt_missing.id and c.target == start_2.id for c in conns)

    # 额外保障：选项附属节点至少有一条出边（不悬空）
    assert any(c.source == opt_missing.id for c in conns)


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


def test_step5_chapter_level_choice_exit_builds_branch_chapters_and_converges():
    sg = StepGenerator(ConfigManager())

    story = {
        "style": "现代",
        "enable_condition_node": False,
    }
    chars = [
        {"char_id": "char_a", "char_name": "Alice"},
    ]

    chapter_details = [
        {
            "structured": {
                "chapter_id": "3",
                "chapter_title": "第3章-关键选择",
                "summary": "到达分歧点",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_room"},
                        "dialogues": [{"speaker": "Alice", "text": "要做选择了。"}],
                    }
                ],
                "exit": {
                    "type": "choice",
                    "choice": {
                        "prompt": "选择路线",
                        "options": [
                            {"text": "走A线", "next_chapter_id": "4A"},
                            {"text": "走B线", "next_chapter_id": "4B"},
                        ],
                    },
                },
            }
        },
        {
            "structured": {
                "chapter_id": "4A",
                "chapter_title": "第4A章",
                "summary": "A线发展",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_street"},
                        "dialogues": [{"speaker": "Alice", "text": "这是A线剧情。"}],
                    }
                ],
                "exit": {"type": "linear", "next_chapter_id": "6"},
            }
        },
        {
            "structured": {
                "chapter_id": "4B",
                "chapter_title": "第4B章",
                "summary": "B线发展",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_street"},
                        "dialogues": [{"speaker": "Alice", "text": "这是B线剧情。"}],
                    }
                ],
                "exit": {"type": "linear", "next_chapter_id": "6"},
            }
        },
        {
            "structured": {
                "chapter_id": "6",
                "chapter_title": "第6章-汇聚",
                "summary": "汇聚到共通线",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_room"},
                        "dialogues": [{"speaker": "Alice", "text": "汇聚后的剧情。"}],
                    }
                ],
                "exit": {"type": "end"},
            }
        },
    ]

    result = sg.build_pending_and_flow(story, chars, chapter_details)
    nodes = result["flow_nodes"]
    conns = result["connections"]

    # 应存在一个 choice 节点（exit 生成），且 options 为 2
    choice_nodes = [n for n in nodes if n.node_type == "choice"]
    assert len(choice_nodes) == 1
    assert len(choice_nodes[0].options) == 2
    assert choice_nodes[0].options[0] == "走A线"
    assert choice_nodes[0].options[1] == "走B线"

    # 不应出现旧的“分支占位”文本节点（说明没有走回退桩逻辑）
    assert all("分支占位" not in (n.content or "") for n in nodes)

    # choice 的两条出边应先进入“选项附属文本节点”，再跳转到 4A/4B 章节首节点，并保持顺序
    # 由于 node_id 是递增的，这里用 title 匹配章节首节点的 title（由 chap_title 生成）
    start_4a = next(n for n in nodes if n.node_type == "text" and n.title == "第4A章")
    start_4b = next(n for n in nodes if n.node_type == "text" and n.title == "第4B章")
    start_6 = next(n for n in nodes if n.node_type == "text" and n.title == "第6章-汇聚")

    opt_a = next(n for n in nodes if n.node_type == "text" and n.title == "选项：走A线")
    opt_b = next(n for n in nodes if n.node_type == "text" and n.title == "选项：走B线")

    out_from_choice = [c.target for c in conns if c.source == choice_nodes[0].id]
    assert out_from_choice == [opt_a.id, opt_b.id]

    assert any(c.source == opt_a.id and c.target == start_4a.id for c in conns)
    assert any(c.source == opt_b.id and c.target == start_4b.id for c in conns)

    # A/B 两章应都能连到第6章首节点（汇聚）
    in_to_6 = [c.source for c in conns if c.target == start_6.id]
    # 至少包含 4A/4B 两章的末尾节点；这里用“存在即可”避免依赖节点数
    assert any(s in in_to_6 for s in [start_4a.id])
    assert any(s in in_to_6 for s in [start_4b.id])


def test_step5_branch_can_end_without_merging_to_next_chapter():
    sg = StepGenerator(ConfigManager())

    story = {
        "style": "现代",
        "enable_condition_node": False,
    }
    chars = [
        {"char_id": "char_a", "char_name": "Alice"},
    ]

    chapter_details = [
        {
            "structured": {
                "chapter_id": "3",
                "chapter_title": "第3章-分歧",
                "summary": "出现分歧",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_room"},
                        "dialogues": [{"speaker": "Alice", "text": "要做选择了。"}],
                    }
                ],
                "exit": {
                    "type": "choice",
                    "choice": {
                        "prompt": "选择路线",
                        "options": [
                            {"text": "A线结局", "next_chapter_id": "4A"},
                            {"text": "B线继续", "next_chapter_id": "4B"},
                        ],
                    },
                },
            }
        },
        {
            "structured": {
                "chapter_id": "4A",
                "chapter_title": "第4A章-结局A",
                "summary": "A线直接结束",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_street"},
                        "dialogues": [{"speaker": "Alice", "text": "这是A线结局。"}],
                    }
                ],
                "exit": {"type": "end"},
            }
        },
        {
            "structured": {
                "chapter_id": "4B",
                "chapter_title": "第4B章",
                "summary": "B线继续",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_street"},
                        "dialogues": [{"speaker": "Alice", "text": "这是B线剧情。"}],
                    }
                ],
                "exit": {"type": "linear", "next_chapter_id": "6"},
            }
        },
        {
            "structured": {
                "chapter_id": "6",
                "chapter_title": "第6章-共通",
                "summary": "共通线继续",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_room"},
                        "dialogues": [{"speaker": "Alice", "text": "共通线剧情。"}],
                    }
                ],
                "exit": {"type": "end"},
            }
        },
    ]

    result = sg.build_pending_and_flow(story, chars, chapter_details)
    nodes = result["flow_nodes"]
    conns = result["connections"]

    start_4a = next(n for n in nodes if n.node_type == "text" and n.title == "第4A章-结局A")
    start_4b = next(n for n in nodes if n.node_type == "text" and n.title == "第4B章")
    start_6 = next(n for n in nodes if n.node_type == "text" and n.title == "第6章-共通")

    # B线应该能连到共通线
    in_to_6 = [c.source for c in conns if c.target == start_6.id]
    assert any(s in in_to_6 for s in [start_4b.id])

    # A线为 end：不应被默认线性规则连到后续章节（共通线）
    assert not any(c.source == start_4a.id and c.target == start_6.id for c in conns)


def test_step5_branch_plan_fallback_creates_choice_and_route_links_when_step4_missing_exit():
    sg = StepGenerator(ConfigManager())

    story = {
        "style": "现代",
        "enable_condition_node": False,
        "enable_multi_branch": True,
    }
    chars = [
        {"char_id": "char_a", "char_name": "Alice"},
    ]

    # Step4 详稿：不提供 exit / choice scene
    chapter_details = [
        {
            "structured": {
                "chapter_id": "1",
                "chapter_title": "第1章",
                "summary": "共通",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_room"},
                        "dialogues": [{"speaker": "Alice", "text": "1"}],
                    }
                ],
            }
        },
        {
            "structured": {
                "chapter_id": "2",
                "chapter_title": "第2章",
                "summary": "共通",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_room"},
                        "dialogues": [{"speaker": "Alice", "text": "2"}],
                    }
                ],
            }
        },
        {
            "structured": {
                "chapter_id": "3",
                "chapter_title": "第3章-分歧点",
                "summary": "分歧",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_room"},
                        "dialogues": [{"speaker": "Alice", "text": "3"}],
                    }
                ],
            }
        },
        {
            "structured": {
                "chapter_id": "4A",
                "chapter_title": "第4A章",
                "summary": "A线",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_street"},
                        "dialogues": [{"speaker": "Alice", "text": "4A"}],
                    }
                ],
            }
        },
        {
            "structured": {
                "chapter_id": "4B",
                "chapter_title": "第4B章",
                "summary": "B线",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_street"},
                        "dialogues": [{"speaker": "Alice", "text": "4B"}],
                    }
                ],
            }
        },
        {
            "structured": {
                "chapter_id": "5A",
                "chapter_title": "第5A章",
                "summary": "A线延续",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_street"},
                        "dialogues": [{"speaker": "Alice", "text": "5A"}],
                    }
                ],
            }
        },
        {
            "structured": {
                "chapter_id": "5B",
                "chapter_title": "第5B章",
                "summary": "B线延续",
                "scenes": [
                    {
                        "type": "text",
                        "directives": {"background": "bg_street"},
                        "dialogues": [{"speaker": "Alice", "text": "5B"}],
                    }
                ],
            }
        },
    ]

    # Step3 章节规划：提供 branch_plan（真实场景里 Step5 需要它来兜底）
    chapters_plan = {
        "structured": {
            "chapters": [
                {"chapter_id": "1", "route": "common"},
                {"chapter_id": "2", "route": "common"},
                {"chapter_id": "3", "route": "common"},
                {"chapter_id": "4A", "route": "A"},
                {"chapter_id": "5A", "route": "A"},
                {"chapter_id": "4B", "route": "B"},
                {"chapter_id": "5B", "route": "B"},
            ],
            "branch_plan": [
                {
                    "type": "choice",
                    "at_chapter_id": "3",
                    "prompt": "选择路线",
                    "options": [
                        {"text": "走A线", "leads_to": ["4A", "5A"], "ends_to": "5A"},
                        {"text": "走B线", "leads_to": ["4B", "5B"], "ends_to": "5B"},
                    ],
                }
            ],
        }
    }

    result = sg.build_pending_and_flow(story, chars, chapter_details, chapters_plan=chapters_plan)
    nodes = result["flow_nodes"]
    conns = result["connections"]

    choice_nodes = [n for n in nodes if n.node_type == "choice"]
    assert len(choice_nodes) == 1
    assert choice_nodes[0].options == ["走A线", "走B线"]

    start_4a = next(n for n in nodes if n.node_type == "text" and n.title == "第4A章")
    start_5a = next(n for n in nodes if n.node_type == "text" and n.title == "第5A章")
    start_4b = next(n for n in nodes if n.node_type == "text" and n.title == "第4B章")
    start_5b = next(n for n in nodes if n.node_type == "text" and n.title == "第5B章")

    out_from_choice = [c.target for c in conns if c.source == choice_nodes[0].id]
    opt_a = next(n for n in nodes if n.node_type == "text" and n.title == "选项：走A线")
    opt_b = next(n for n in nodes if n.node_type == "text" and n.title == "选项：走B线")
    assert out_from_choice == [opt_a.id, opt_b.id]

    assert any(c.source == opt_a.id and c.target == start_4a.id for c in conns)
    assert any(c.source == opt_b.id and c.target == start_4b.id for c in conns)

    # 分支内部的 route 连线应按 leads_to 顺序生成
    assert any(c.source == start_4a.id and c.target == start_5a.id for c in conns)
    assert any(c.source == start_4b.id and c.target == start_5b.id for c in conns)

    # 不应把 A/B 分支按章节列表顺序串联
    assert not any(c.source == start_4a.id and c.target == start_4b.id for c in conns)


def test_step5_delayed_branch_via_var_ops_then_condition_from_branch_plan_fallback():
    sg = StepGenerator(ConfigManager())

    story = {
        "style": "现代",
        "enable_condition_node": False,
        "enable_multi_branch": True,
    }
    chars = [
        {"char_id": "char_a", "char_name": "Alice"},
    ]

    # Step4 详稿：不提供 exit / choice scene / condition scene
    chapter_details = [
        {
            "structured": {
                "chapter_id": "1",
                "chapter_title": "第1章",
                "summary": "共通",
                "scenes": [
                    {"type": "text", "directives": {"background": "bg_room"}, "dialogues": [{"speaker": "Alice", "text": "1"}]}
                ],
            }
        },
        {
            "structured": {
                "chapter_id": "2",
                "chapter_title": "第2章",
                "summary": "共通",
                "scenes": [
                    {"type": "text", "directives": {"background": "bg_room"}, "dialogues": [{"speaker": "Alice", "text": "2"}]}
                ],
            }
        },
        {
            "structured": {
                "chapter_id": "3",
                "chapter_title": "第3章-选择",
                "summary": "选择但不立刻分支",
                "scenes": [
                    {"type": "text", "directives": {"background": "bg_room"}, "dialogues": [{"speaker": "Alice", "text": "3"}]}
                ],
            }
        },
        {
            "structured": {
                "chapter_id": "4",
                "chapter_title": "第4章-共通",
                "summary": "继续共通线",
                "scenes": [
                    {"type": "text", "directives": {"background": "bg_room"}, "dialogues": [{"speaker": "Alice", "text": "4"}]}
                ],
            }
        },
        {
            "structured": {
                "chapter_id": "5",
                "chapter_title": "第5章-分流判断",
                "summary": "根据变量进入路线",
                "scenes": [
                    {"type": "text", "directives": {"background": "bg_room"}, "dialogues": [{"speaker": "Alice", "text": "5"}]}
                ],
            }
        },
        {
            "structured": {
                "chapter_id": "6A",
                "chapter_title": "第6A章",
                "summary": "A线",
                "scenes": [
                    {"type": "text", "directives": {"background": "bg_street"}, "dialogues": [{"speaker": "Alice", "text": "6A"}]}
                ],
            }
        },
        {
            "structured": {
                "chapter_id": "6B",
                "chapter_title": "第6B章",
                "summary": "B线",
                "scenes": [
                    {"type": "text", "directives": {"background": "bg_street"}, "dialogues": [{"speaker": "Alice", "text": "6B"}]}
                ],
            }
        },
    ]

    chapters_plan = {
        "structured": {
            "chapters": [
                {"chapter_id": "1", "route": "common"},
                {"chapter_id": "2", "route": "common"},
                {"chapter_id": "3", "route": "common"},
                {"chapter_id": "4", "route": "common"},
                {"chapter_id": "5", "route": "common"},
                {"chapter_id": "6A", "route": "A"},
                {"chapter_id": "6B", "route": "B"},
            ],
            "branch_plan": [
                {
                    "type": "choice",
                    "at_chapter_id": "3",
                    "prompt": "选择路线倾向（先继续共通线）",
                    "options": [
                        {
                            "text": "偏向A",
                            "next_chapter_id": "4",
                            "var_ops": [
                                {"dest": "route_flag", "op": "=", "right": 1, "right_const": True, "left": 0, "left_const": True}
                            ],
                        },
                        {
                            "text": "偏向B",
                            "next_chapter_id": "4",
                            "var_ops": [
                                {"dest": "route_flag", "op": "=", "right": 0, "right_const": True, "left": 0, "left_const": True}
                            ],
                        },
                    ],
                },
                {
                    "type": "condition",
                    "at_chapter_id": "5",
                    "prompt": "根据 route_flag 进入不同路线",
                    "condition": {
                        "rules": [
                            {
                                "name": "RouteIsA",
                                "logic": "and",
                                "exprs": ["route_flag == 1"],
                                "leads_to": ["6A"],
                            }
                        ],
                        "else_leads_to": ["6B"],
                    },
                },
            ],
        }
    }

    result = sg.build_pending_and_flow(story, chars, chapter_details, chapters_plan=chapters_plan)
    nodes = result["flow_nodes"]
    conns = result["connections"]

    choice_nodes = [n for n in nodes if n.node_type == "choice"]
    assert len(choice_nodes) == 1
    assert choice_nodes[0].options == ["偏向A", "偏向B"]

    start_4 = next(n for n in nodes if n.node_type == "text" and n.title == "第4章-共通")
    start_6a = next(n for n in nodes if n.node_type == "text" and n.title == "第6A章")
    start_6b = next(n for n in nodes if n.node_type == "text" and n.title == "第6B章")

    # choice 出边应先进入“选项处理节点”，并且每个节点携带 var_ops
    out_targets = [c.target for c in conns if c.source == choice_nodes[0].id]
    assert len(out_targets) == 2
    opt_nodes = [next(n for n in nodes if n.id == tid) for tid in out_targets]
    assert all(n.node_type == "text" for n in opt_nodes)
    assert all(isinstance(n.var_ops, list) and len(n.var_ops) >= 1 for n in opt_nodes)
    assert opt_nodes[0].var_ops[0]["dest"] == "route_flag"
    assert opt_nodes[1].var_ops[0]["dest"] == "route_flag"

    # 两个选项处理节点都应合并回共通第4章
    assert all(any(c.source == n.id and c.target == start_4.id for c in conns) for n in opt_nodes)

    # 第5章处应生成 condition 节点（新结构：condition_rules + 否则分支）
    def _rule_exprs(rule):
        if isinstance(rule, dict):
            return rule.get("exprs") or []
        return getattr(rule, "exprs", None) or []

    cond_nodes = [
        n
        for n in nodes
        if n.node_type == "condition"
        and isinstance(getattr(n, "condition_rules", None), list)
        and any(
            "route_flag" in str(expr)
            for rule in (n.condition_rules or [])
            for expr in _rule_exprs(rule)
        )
    ]
    assert len(cond_nodes) == 1
    cond_node = cond_nodes[0]
    assert any("route_flag" in str(expr) for expr in _rule_exprs(cond_node.condition_rules[0]))

    # 条件节点出边应为：Rule1 + Else，并各生成一个“分支处理节点”
    out_from_cond = [c.target for c in conns if c.source == cond_node.id]
    assert len(out_from_cond) == 2
    rule1_node = next(n for n in nodes if n.id == out_from_cond[0])
    else_node = next(n for n in nodes if n.id == out_from_cond[1])
    assert rule1_node.node_type == "text" and rule1_node.title.endswith("-Rule1")
    assert else_node.node_type == "text" and else_node.title.endswith("-Else")

    # 分支处理节点再跨章节连到目标章节起始节点
    assert any(c.source == rule1_node.id and c.target == start_6a.id for c in conns)
    assert any(c.source == else_node.id and c.target == start_6b.id for c in conns)


def test_step5_scene_choice_generates_option_nodes_with_branch_dialogues_and_merges_back():
    sg = StepGenerator(ConfigManager())

    story = {
        "style": "现代",
        "enable_condition_node": False,
    }
    chars = [
        {"char_id": "char_a", "char_name": "Alice"},
    ]

    chapter_details = [
        {
            "structured": {
                "chapter_id": "1",
                "chapter_title": "第1章",
                "summary": "场景内选择分支",
                "scenes": [
                    {"type": "text", "directives": {"background": "bg_room"}, "dialogues": [{"speaker": "Alice", "text": "选择前"}]},
                    {
                        "type": "choice",
                        "title": "路口选择",
                        "prompt": "你要往哪边走？",
                        "options": [
                            {"text": "去左边", "node": {"dialogues": [{"speaker": "Alice", "text": "走左边。", "emotion": "calm"}]}, "var_ops": []},
                            {"text": "去右边", "node": {"dialogues": [{"speaker": "Alice", "text": "走右边。", "emotion": "calm"}]}, "var_ops": []},
                        ],
                    },
                    {"type": "text", "directives": {"background": "bg_room"}, "dialogues": [{"speaker": "Alice", "text": "选择后汇合"}]},
                ],
                "exit": {"type": "end"},
            }
        }
    ]

    result = sg.build_pending_and_flow(story, chars, chapter_details)
    nodes = result["flow_nodes"]
    conns = result["connections"]

    choice_node = next(n for n in nodes if n.node_type == "choice" and n.title == "路口选择")
    opt_left = next(n for n in nodes if n.node_type == "text" and n.title == "选项：去左边")
    opt_right = next(n for n in nodes if n.node_type == "text" and n.title == "选项：去右边")
    after_node = next(n for n in nodes if n.node_type == "text" and any((sub.get("text") or "") == "选择后汇合" for sub in (n.sub_dialogues or [])))

    # choice 必须先连到两个选项节点（顺序保持）
    out_from_choice = [c.target for c in conns if c.source == choice_node.id]
    assert out_from_choice == [opt_left.id, opt_right.id]

    # 两个选项节点都应承载分支对白，并汇合回后续节点
    assert any((sub.get("text") or "") == "走左边。" for sub in (opt_left.sub_dialogues or []))
    assert any((sub.get("text") or "") == "走右边。" for sub in (opt_right.sub_dialogues or []))
    assert any(c.source == opt_left.id and c.target == after_node.id for c in conns)
    assert any(c.source == opt_right.id and c.target == after_node.id for c in conns)


def test_step5_scene_condition_generates_true_false_nodes_with_dialogues_and_merges_back():
    sg = StepGenerator(ConfigManager())

    story = {
        "style": "现代",
        "enable_condition_node": True,
    }
    chars = [
        {"char_id": "char_a", "char_name": "Alice"},
    ]

    chapter_details = [
        {
            "structured": {
                "chapter_id": "1",
                "chapter_title": "第1章",
                "summary": "场景内条件分支",
                "scenes": [
                    {"type": "text", "directives": {"background": "bg_room"}, "dialogues": [{"speaker": "Alice", "text": "判断前"}]},
                    {
                        "type": "condition",
                        "title": "是否有钥匙",
                        "prompt": "检查钥匙",
                        "condition": {
                            "rules": [
                                {
                                    "name": "HasKey",
                                    "logic": "and",
                                    "exprs": ["has_key == 1"],
                                    "node": {"dialogues": [{"speaker": "Alice", "text": "有钥匙。", "emotion": "calm"}]},
                                }
                            ],
                            "else_node": {"dialogues": [{"speaker": "Alice", "text": "没钥匙。", "emotion": "calm"}]},
                        },
                    },
                    {"type": "text", "directives": {"background": "bg_room"}, "dialogues": [{"speaker": "Alice", "text": "判断后汇合"}]},
                ],
                "exit": {"type": "end"},
            }
        }
    ]

    result = sg.build_pending_and_flow(story, chars, chapter_details)
    nodes = result["flow_nodes"]
    conns = result["connections"]

    cond_node = next(n for n in nodes if n.node_type == "condition" and n.title == "是否有钥匙")
    rule1_node = next(n for n in nodes if n.node_type == "text" and n.title.endswith("-Rule1"))
    else_node = next(n for n in nodes if n.node_type == "text" and n.title.endswith("-Else"))
    after_node = next(n for n in nodes if n.node_type == "text" and any((sub.get("text") or "") == "判断后汇合" for sub in (n.sub_dialogues or [])))

    out_from_cond = [c.target for c in conns if c.source == cond_node.id]
    assert out_from_cond == [rule1_node.id, else_node.id]

    assert any((sub.get("text") or "") == "有钥匙。" for sub in (rule1_node.sub_dialogues or []))
    assert any((sub.get("text") or "") == "没钥匙。" for sub in (else_node.sub_dialogues or []))
    assert any(c.source == rule1_node.id and c.target == after_node.id for c in conns)
    assert any(c.source == else_node.id and c.target == after_node.id for c in conns)
