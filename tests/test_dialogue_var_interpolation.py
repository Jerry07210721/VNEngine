import os
from pathlib import Path

import yaml


def _make_min_project(tmp_path: Path, content: str) -> Path:
    project_dir = tmp_path / "proj"
    project_dir.mkdir(parents=True, exist_ok=True)
    project_path = project_dir / "demo.vngproj"
    data = {
        "game_config": {"window_width": 640, "window_height": 360},
        "global_variables": [{"name": "x", "initial": 0.0}, {"name": "y", "initial": 0.0}],
        "flow_nodes": {
            "nodes": [
                {
                    "id": 1,
                    "node_type": "text",
                    "title": "",
                    "content": "",
                    "speaker": "",
                    "sub_dialogues": [{"speaker": "A", "text": content}],
                }
            ],
            "connections": [],
        },
    }
    project_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return project_path


def test_dialogue_interpolation_trims_float(tmp_path: Path):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from src.game.game_runtime import VNGameRuntime

    project_path = _make_min_project(tmp_path, "x={$x}, y={$y}, z={$z}")
    rt = VNGameRuntime(project_path=str(project_path))
    rt.variables["x"] = 1.0
    rt.variables["y"] = 2.1
    # z is unknown -> 0
    out = rt._interpolate_dialogue_template("x={$x}, y={$y}, z={$z}")
    assert out == "x=1, y=2.1, z=0"
    rt.quit_game()


def test_reveal_uses_interpolated_length(tmp_path: Path):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from src.game.game_runtime import VNGameRuntime

    project_path = _make_min_project(tmp_path, "val={$x}")
    rt = VNGameRuntime(project_path=str(project_path))
    rt.variables["x"] = 123.0
    rt._reset_typing_state()
    rt._reveal_current_text()
    # "val=123" length is 7
    assert rt.current_visible_len == len("val=123")
    rt.quit_game()
