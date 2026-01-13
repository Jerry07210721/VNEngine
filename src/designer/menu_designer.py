# -*- coding: utf-8 -*-
"""Main menu designer dialog for title/background/BGM."""
from pathlib import Path
import shutil
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QMessageBox,
    QFileDialog,
    QLabel,
    QCheckBox,
    QWidget,
)


class MainMenuDesigner(QDialog):
    def __init__(self, project_dir: Path | None, project_manager, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
        self.project_manager = project_manager
        self.setWindowTitle("主菜单设计")
        self.setMinimumWidth(480)

        data = (project_manager.project_data.get("game_config", {}) if project_manager else {}) or {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.title_edit = QLineEdit(data.get("menu_title", ""))
        form.addRow("标题文字", self.title_edit)

        self.bg_edit = QLineEdit(data.get("menu_background", ""))
        bg_row = self._make_file_row(self.bg_edit, self._pick_bg, True)
        form.addRow("背景图", bg_row)

        self.bgm_edit = QLineEdit(data.get("menu_bgm", ""))
        bgm_row = self._make_file_row(self.bgm_edit, self._pick_bgm, True)
        form.addRow("BGM", bgm_row)

        self.bgm_loop_chk = QCheckBox("BGM循环播放")
        self.bgm_loop_chk.setChecked(data.get("menu_bgm_loop", True))
        form.addRow("", self.bgm_loop_chk)

        layout.addLayout(form)

        hint = QLabel("说明：选择的背景/BGM 会复制到工程目录 (resources/images / resources/audios)。")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_cancel = QPushButton("取消")
        btn_save.clicked.connect(self._save)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def _make_file_row(self, edit: QLineEdit, handler, with_clear=False):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit)
        btn = QPushButton("选择")
        btn.clicked.connect(handler)
        layout.addWidget(btn)
        if with_clear:
            btn_clear = QPushButton("清除")
            btn_clear.clicked.connect(lambda: edit.setText(""))
            layout.addWidget(btn_clear)
        return row

    def _pick_bg(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择背景图", str(self.project_dir or ""), "图片 (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        stored = self._store_into_project(path, "resources/images")
        self.bg_edit.setText(stored)

    def _pick_bgm(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择BGM", str(self.project_dir or ""), "音频 (*.mp3 *.ogg *.wav)")
        if not path:
            return
        stored = self._store_into_project(path, "resources/audios")
        self.bgm_edit.setText(stored)

    def _store_into_project(self, src_path: str, subfolder: str) -> str:
        if not src_path:
            return ""
        if not self.project_dir:
            return src_path
        src = Path(src_path)
        target_dir = (self.project_dir / subfolder).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            if src.resolve().is_relative_to(self.project_dir.resolve()):
                return str(src.relative_to(self.project_dir))
        except Exception:
            pass
        target = target_dir / src.name
        try:
            shutil.copy2(src, target)
            return str(target.relative_to(self.project_dir))
        except Exception:
            return str(src)

    def _save(self):
        cfg = self.project_manager.project_data.setdefault("game_config", {}) if self.project_manager else {}
        cfg["menu_title"] = self.title_edit.text()
        cfg["menu_background"] = self.bg_edit.text()
        cfg["menu_bgm"] = self.bgm_edit.text()
        cfg["menu_bgm_loop"] = self.bgm_loop_chk.isChecked()
        QMessageBox.information(self, "已保存", "主菜单配置已写入工程，保存工程文件后生效。")
        self.accept()


__all__ = ["MainMenuDesigner"]
