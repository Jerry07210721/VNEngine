import os
from pathlib import Path

import yaml


def test_protected_globals_do_not_rollback_on_load_or_new_game(tmp_path: Path):
    # Ensure pygame can init in CI/headless.
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    from src.game.game_runtime import VNGameRuntime

    project_dir = tmp_path / "proj"
    project_dir.mkdir(parents=True, exist_ok=True)
    project_path = project_dir / "demo.vngproj"

    data = {
        "game_config": {"window_width": 640, "window_height": 360},
        "global_variables": [
            {"name": "p", "initial": 0, "protected": True},
            {"name": "x", "initial": 0, "protected": False},
        ],
        "flow_nodes": {
            "nodes": [
                {
                    "id": 1,
                    "node_type": "text",
                    "title": "",
                    "content": "",
                    "speaker": "",
                    "sub_dialogues": [{"speaker": "A", "text": "第一句"}],
                }
            ],
            "connections": [],
        },
    }
    project_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    rt = VNGameRuntime(project_path=str(project_path))

    # Set vars and save.
    rt.variables["p"] = 5.0
    rt.variables["x"] = 1.0
    rt._update_persistent_from_runtime()
    rt._save_persistent_vars()
    rt.save_game(1)

    # Change vars in runtime: protected should stick across load.
    rt.variables["p"] = 9.0
    rt.variables["x"] = 2.0
    rt._update_persistent_from_runtime()
    rt._save_persistent_vars()

    rt.load_game(1)
    assert float(rt.variables.get("p")) == 9.0
    assert float(rt.variables.get("x")) == 1.0

    # Starting a new game with reset should keep protected but reset non-protected.
    rt.variables["p"] = 7.0
    rt.variables["x"] = 3.0
    rt._update_persistent_from_runtime()
    rt._save_persistent_vars()

    rt._start_new_game(reset_globals=True)
    assert float(rt.variables.get("p")) == 7.0
    assert float(rt.variables.get("x")) == 0.0

    rt.quit_game()
