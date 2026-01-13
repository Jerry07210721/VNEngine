# -*- coding: utf-8 -*-
"""Standalone preview runner for VNEngine runtime.

Usage: python -m src.game.preview_runner <project_file.vngproj>
"""
from __future__ import annotations

import sys
from pathlib import Path
from src.game.game_runtime import VNGameRuntime


def main():
    if len(sys.argv) < 2:
        print("用法: python -m src.game.preview_runner <工程文件.vngproj>")
        sys.exit(1)
    project_path = Path(sys.argv[1]).resolve()
    if not project_path.exists():
        print(f"未找到工程文件: {project_path}")
        sys.exit(1)
    runtime = VNGameRuntime(project_path=project_path)
    runtime.start_game()


if __name__ == "__main__":
    main()
