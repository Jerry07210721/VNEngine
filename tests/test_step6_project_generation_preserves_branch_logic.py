# -*- coding: utf-8 -*-

import tempfile
from pathlib import Path

import yaml

from src.ai.core.config_manager import ConfigManager
from src.ai.core.models import (
    CharacterConfig,
    ConnectionData,
    EnableAgentsConfig,
    FlowNodeData,
    GlobalVariable,
    MaterialConfig,
    ProjectConfig,
    StoryConfig,
    UserConfig,
)
from src.ai.integrator.integrator import Integrator


def test_step6_integrate_from_data_preserves_var_ops_and_condition_nodes():
    with tempfile.TemporaryDirectory() as td:
        project_dir = Path(td) / "proj"
        project_dir.mkdir(parents=True, exist_ok=True)

        user_config = UserConfig(
            project_info=ProjectConfig(
                project_path=str(project_dir),
                project_name="TestProject",
                window_width=1280,
                window_height=720,
                engine_version="V2.7-AI",
            ),
            story_config=StoryConfig(
                title="测试故事",
                style="现代",
                plot_outline="...",
                text_volume=5000,
            ),
            character_config=[
                CharacterConfig(char_id="char_a", char_name="Alice", persona_keywords=""),
            ],
            enable_agents=EnableAgentsConfig(),
            material_config=MaterialConfig(),
        )

        # graph: text -> choice -> option nodes (var_ops) -> common -> condition -> A/B
        nodes = [
            FlowNodeData(id=1, node_type="text", title="第3章", content="...", speaker="", portrait="", background="", voice="", bgm="", bgm_loop=True, stop_bgm=False, bg_fade_in=False, portrait_fade=False, portrait_fade_out=False, hide_textbox=False, ui_file="", video="", video_loop=False, options=[], sub_dialogues=[], var_ops=[], x=0, y=0),
            FlowNodeData(id=2, node_type="choice", title="选择", content="选择倾向", speaker="", portrait="", background="", voice="", bgm="", bgm_loop=True, stop_bgm=False, bg_fade_in=False, portrait_fade=False, portrait_fade_out=False, hide_textbox=False, ui_file="", video="", video_loop=False, options=["偏向A", "偏向B"], sub_dialogues=[], var_ops=[], x=220, y=0),
            FlowNodeData(id=3, node_type="text", title="选项：偏向A", content="", speaker="", portrait="", background="", voice="", bgm="", bgm_loop=True, stop_bgm=False, bg_fade_in=False, portrait_fade=False, portrait_fade_out=False, hide_textbox=True, ui_file="", video="", video_loop=False, options=[], sub_dialogues=[], var_ops=[{"dest": "route_flag", "left": 0, "left_const": True, "right": 1, "right_const": True, "op": "="}], x=440, y=0),
            FlowNodeData(id=4, node_type="text", title="选项：偏向B", content="", speaker="", portrait="", background="", voice="", bgm="", bgm_loop=True, stop_bgm=False, bg_fade_in=False, portrait_fade=False, portrait_fade_out=False, hide_textbox=True, ui_file="", video="", video_loop=False, options=[], sub_dialogues=[], var_ops=[{"dest": "route_flag", "left": 0, "left_const": True, "right": 0, "right_const": True, "op": "="}], x=440, y=120),
            FlowNodeData(id=5, node_type="text", title="第4章-共通", content="...", speaker="", portrait="", background="", voice="", bgm="", bgm_loop=True, stop_bgm=False, bg_fade_in=False, portrait_fade=False, portrait_fade_out=False, hide_textbox=False, ui_file="", video="", video_loop=False, options=[], sub_dialogues=[], var_ops=[], x=660, y=0),
            FlowNodeData(id=6, node_type="text", title="第5章-判断前", content="...", speaker="", portrait="", background="", voice="", bgm="", bgm_loop=True, stop_bgm=False, bg_fade_in=False, portrait_fade=False, portrait_fade_out=False, hide_textbox=False, ui_file="", video="", video_loop=False, options=[], sub_dialogues=[], var_ops=[], x=880, y=0),
            FlowNodeData(
                id=7,
                node_type="condition",
                title="条件判断",
                content="route_flag == 1",
                speaker="",
                portrait="",
                background="",
                voice="",
                bgm="",
                bgm_loop=True,
                stop_bgm=False,
                bg_fade_in=False,
                portrait_fade=False,
                portrait_fade_out=False,
                hide_textbox=False,
                ui_file="",
                video="",
                video_loop=False,
                options=[],
                condition_rules=[{"name": "RouteIsA", "logic": "and", "exprs": ["route_flag == 1"]}],
                sub_dialogues=[],
                var_ops=[],
                x=1100,
                y=0,
            ),
            FlowNodeData(id=8, node_type="text", title="第6A章", content="...", speaker="", portrait="", background="", voice="", bgm="", bgm_loop=True, stop_bgm=False, bg_fade_in=False, portrait_fade=False, portrait_fade_out=False, hide_textbox=False, ui_file="", video="", video_loop=False, options=[], sub_dialogues=[], var_ops=[], x=1320, y=0),
            FlowNodeData(id=9, node_type="text", title="第6B章", content="...", speaker="", portrait="", background="", voice="", bgm="", bgm_loop=True, stop_bgm=False, bg_fade_in=False, portrait_fade=False, portrait_fade_out=False, hide_textbox=False, ui_file="", video="", video_loop=False, options=[], sub_dialogues=[], var_ops=[], x=1320, y=120),
        ]

        connections = [
            ConnectionData(source=1, target=2),
            ConnectionData(source=2, target=3),
            ConnectionData(source=2, target=4),
            ConnectionData(source=3, target=5),
            ConnectionData(source=4, target=5),
            ConnectionData(source=5, target=6),
            ConnectionData(source=6, target=7),
            # condition true/false order is important
            ConnectionData(source=7, target=8),
            ConnectionData(source=7, target=9),
        ]

        integrator = Integrator(ConfigManager())
        project_file = integrator.integrate_from_data(
            user_config=user_config,
            flow_nodes=nodes,
            connections=connections,
            global_variables=[GlobalVariable(name="route_flag", initial=0.0, type="float")],
            material_requirements=[],
            resources_dir=str(project_dir / "resources"),
        )

        data = yaml.safe_load(Path(project_file).read_text(encoding="utf-8"))
        dumped_nodes = (data.get("flow_nodes") or {}).get("nodes") or []
        dumped_conns = (data.get("flow_nodes") or {}).get("connections") or []

        by_id = {int(n.get("id")): n for n in dumped_nodes}
        assert by_id[2].get("node_type") == "choice"
        assert by_id[2].get("var_ops") in ([], None)

        assert isinstance(by_id[3].get("var_ops"), list)
        assert by_id[3]["var_ops"][0]["dest"] == "route_flag"
        assert by_id[3]["var_ops"][0]["op"] == "="

        assert by_id[7].get("node_type") == "condition"
        rules = by_id[7].get("condition_rules")
        assert isinstance(rules, list) and len(rules) == 1
        assert rules[0].get("logic") == "and"
        assert rules[0].get("exprs") == ["route_flag == 1"]

        # connections should be preserved as-is (order matters: Rule1 then Else)
        assert dumped_conns[-2:] == [{"source": 7, "target": 8}, {"source": 7, "target": 9}]
