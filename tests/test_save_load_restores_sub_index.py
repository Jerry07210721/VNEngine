import os
from pathlib import Path

import yaml


def test_save_load_restores_graph_sub_index(tmp_path: Path):
    # Ensure pygame can init in CI/headless.
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    # Import after env vars.
    from src.game.game_runtime import VNGameRuntime

    project_dir = tmp_path / "proj"
    project_dir.mkdir(parents=True, exist_ok=True)
    project_path = project_dir / "demo.vngproj"

    # Minimal graph project: one text node with two sub_dialogues.
    data = {
        "game_config": {"window_width": 640, "window_height": 360},
        "global_variables": [{"name": "x", "initial": 0}],
        "flow_nodes": {
            "nodes": [
                {
                    "id": 1,
                    "node_type": "text",
                    "title": "",
                    "content": "",
                    "speaker": "",
                    "sub_dialogues": [
                        {"speaker": "A", "text": "第一句"},
                        {"speaker": "A", "text": "第二句"},
                    ],
                }
            ],
            "connections": [],
        },
    }
    project_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    # Start runtime, move to sub_index=1, save.
    rt1 = VNGameRuntime(project_path=str(project_path))
    assert rt1.graph_mode is True
    assert rt1.current_node_id == 1
    rt1._sub_index = 1
    rt1.save_game(1)
    rt1.quit_game()

    # New runtime instance: load should restore node and sub_index.
    rt2 = VNGameRuntime(project_path=str(project_path))
    rt2.load_game(1)
    assert rt2.graph_mode is True
    assert rt2.current_node_id == 1
    assert rt2._sub_index == 1
    entry = rt2._current_entry()
    assert entry.get("content") == "第二句"
    rt2.quit_game()
