# -*- coding: utf-8 -*-
"""Designer dialog for function-script safety configuration."""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ScriptSafetyConfigDialog(QDialog):
    def __init__(
        self,
        *,
        allow_unsafe: bool = False,
        fs_root: str = "",
        project_dir: Path | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("脚本安全设置")
        self.setModal(True)

        self._project_dir = project_dir

        root = QVBoxLayout(self)

        tip = QLabel(
            "用于控制功能节点脚本的安全模式：\n"
            "- 默认安全模式：文件系统访问被限制在指定根目录下\n"
            "- 允许不安全脚本：放开多数限制（仅建议本地可信项目使用）"
        )
        tip.setWordWrap(True)
        root.addWidget(tip)

        form = QFormLayout()

        self.allow_unsafe_chk = QCheckBox("允许不安全功能脚本 (allow_unsafe_function_scripts)")
        self.allow_unsafe_chk.setChecked(bool(allow_unsafe))
        form.addRow(self.allow_unsafe_chk)

        self.fs_root_edit = QLineEdit()
        self.fs_root_edit.setText(str(fs_root or ""))
        row = QWidget()
        row_l = QHBoxLayout(row)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.setSpacing(6)
        row_l.addWidget(self.fs_root_edit)
        btn_pick = QPushButton("选择目录")
        btn_pick.clicked.connect(self._pick_dir)
        row_l.addWidget(btn_pick)
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(lambda: self.fs_root_edit.setText(""))
        row_l.addWidget(btn_clear)
        form.addRow("安全模式根目录 (function_script_fs_root)", row)

        root.addLayout(form)

        btns = QHBoxLayout()
        btns.addStretch(1)
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        root.addLayout(btns)

        self.allow_unsafe_chk.toggled.connect(self._sync_enabled)
        self._sync_enabled()

    def _sync_enabled(self):
        # Even when unsafe is allowed, keeping fs_root configurable is still useful;
        # we just don't force it.
        self.fs_root_edit.setEnabled(True)

    def _pick_dir(self):
        start_dir = ""
        try:
            cur = self.fs_root_edit.text().strip()
            if cur:
                start_dir = cur
            elif self._project_dir:
                start_dir = str(self._project_dir)
        except Exception:
            start_dir = ""

        path = QFileDialog.getExistingDirectory(self, "选择安全模式根目录", start_dir)
        if not path:
            return
        self.fs_root_edit.setText(path)

    def _on_ok(self):
        allow_unsafe = bool(self.allow_unsafe_chk.isChecked())
        fs_root = (self.fs_root_edit.text() or "").strip()

        if not allow_unsafe:
            # Safe mode: empty means project root in runtime, but we strongly
            # encourage explicit root to reduce surprises.
            if not fs_root:
                QMessageBox.information(
                    self,
                    "提示",
                    "未设置安全模式根目录时，运行时会默认使用工程目录。\n"
                    "如需更严格限制，请选择一个子目录。",
                )

        self._result = {
            "allow_unsafe_function_scripts": allow_unsafe,
            "function_script_fs_root": fs_root,
        }
        self.accept()

    def get_result(self) -> dict:
        return getattr(self, "_result", {
            "allow_unsafe_function_scripts": False,
            "function_script_fs_root": "",
        })


def _try_make_relative(path_str: str, project_dir: Path | None) -> str:
    if not path_str:
        return ""
    try:
        p = Path(path_str)
    except Exception:
        return path_str

    if project_dir is None:
        return path_str

    try:
        proj = project_dir.resolve()
        abs_p = p
        if not p.is_absolute():
            return path_str
        abs_p = p.resolve()
        rel = os.path.relpath(str(abs_p), str(proj))
        # Only store relative paths when inside project dir.
        if not rel.startswith("..") and not os.path.isabs(rel):
            return rel.replace("\\", "/")
    except Exception:
        return path_str

    return path_str
