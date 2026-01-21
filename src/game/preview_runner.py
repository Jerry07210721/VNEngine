# -*- coding: utf-8 -*-
"""Standalone preview runner for VNEngine runtime.

Usage:
    python -m src.game.preview_runner <project_file.vngproj>
    python -m src.game.preview_runner <project_file.vngproj> --start-node 12
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from src.game.game_runtime import VNGameRuntime


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(prog="python -m src.game.preview_runner")
    parser.add_argument("project", help="工程文件路径（.vngproj）")
    parser.add_argument("--start-node", type=int, default=None, help="从指定流程节点 node_id 开始预览")
    args = parser.parse_args(argv)

    project_path = Path(args.project).resolve()
    if not project_path.exists():
        print(f"未找到工程文件: {project_path}")
        sys.exit(1)
    runtime = VNGameRuntime(project_path=project_path)
    if args.start_node is not None:
        runtime.set_preview_start_node(int(args.start_node))
    runtime.start_game()


if __name__ == "__main__":
    main(sys.argv[1:])
