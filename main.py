# -*- coding: utf-8 -*-
"""VNEngine entrypoint for designer mode."""
from src.designer.main_designer import run_designer
"""
VNEngine 视觉小说引擎入口文件
支持两种启动模式：
1) 默认启动设计器
2) 预览模式：--preview <project.vngproj>
"""
import sys
from src.designer.main_designer import run_designer
from src.game.preview_runner import main as preview_main


def _dispatch(argv):
    # 预览模式：在打包后的环境中由设计器子进程启动
    if len(argv) >= 2 and argv[1] == "--preview":
        if len(argv) < 3:
            print("用法: --preview <工程文件.vngproj> [--start-node <node_id>]")
            sys.exit(1)
        # 透传预览参数给 preview_runner（支持 --start-node 等）
        preview_main(argv[2:])
        return

    print("VNEngine 视觉小说引擎启动中...")
    run_designer()


if __name__ == "__main__":
    _dispatch(sys.argv)
