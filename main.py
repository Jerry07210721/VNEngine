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
import os
import re
from src.designer.main_designer import run_designer
from src.game.preview_runner import main as preview_main


def _install_qt_message_filter():
    """Filter noisy Qt font warnings on Windows.

    Some system fonts can trigger repeated DirectWrite warnings like:
    `QWindowsFontEngineDirectWrite::recalcAdvances: GetDesignGlyphMetrics failed (操作成功完成。)`

    This is typically harmless but very noisy in console.
    """

    # Allow users to opt-out
    if os.environ.get("VNENGINE_QT_LOG_FILTER", "1").strip() in ("0", "false", "False"):
        return

    try:
        from PyQt6.QtCore import qInstallMessageHandler
    except Exception:
        return

    pattern = re.compile(r"QWindowsFontEngineDirectWrite::recalcAdvances: GetDesignGlyphMetrics failed")

    def handler(msg_type, context, message):
        try:
            if isinstance(message, str) and pattern.search(message):
                return
        except Exception:
            pass
        try:
            # Fallback: print the original message
            print(message)
        except Exception:
            pass

    try:
        qInstallMessageHandler(handler)
    except Exception:
        pass


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
    _install_qt_message_filter()
    run_designer()


if __name__ == "__main__":
    _dispatch(sys.argv)
