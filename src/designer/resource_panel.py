# -*- coding: utf-8 -*-
"""Resource management dock widget with tabs for images and audios."""
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List

import pygame
from PyQt6.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QFileDialog,
    QMessageBox,
    QMenu,
    QInputDialog,
    QScrollArea,
)
from PyQt6.QtGui import QCursor, QGuiApplication, QIcon, QPixmap
from PyQt6.QtCore import Qt, QSize


class ResourceDock(QDockWidget):
    """资源管理面板（图片/音频）。"""

    def __init__(self, parent=None):
        super().__init__("资源管理", parent)
        self.setObjectName("ResourceDock")
        self.setAllowedAreas(self.allowedAreas())
        self._project_dir: Path | None = None

        self._tabs = QTabWidget()
        try:
            self._tabs.setDocumentMode(True)
        except Exception:
            pass
        self._image_list = QListWidget()
        self._audio_list = QListWidget()
        self._portrait_list = QListWidget()
        self._voice_list = QListWidget()
        self._video_list = QListWidget()

        for lw, size in [
            (self._image_list, QSize(72, 72)),
            (self._portrait_list, QSize(72, 72)),
            (self._audio_list, QSize(32, 32)),
            (self._voice_list, QSize(32, 32)),
            (self._video_list, QSize(64, 48)),
        ]:
            lw.setIconSize(size)

        for lw in [self._image_list, self._audio_list, self._portrait_list, self._voice_list, self._video_list]:
            lw.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self._image_list.customContextMenuRequested.connect(lambda pos: self._show_list_menu(self._image_list, pos, "images"))
        self._portrait_list.customContextMenuRequested.connect(lambda pos: self._show_list_menu(self._portrait_list, pos, "portraits"))
        self._audio_list.customContextMenuRequested.connect(lambda pos: self._show_list_menu(self._audio_list, pos, "audios"))
        self._voice_list.customContextMenuRequested.connect(lambda pos: self._show_list_menu(self._voice_list, pos, "voices"))
        self._video_list.customContextMenuRequested.connect(lambda pos: self._show_list_menu(self._video_list, pos, "videos"))

        self._tabs.addTab(self._make_tab(self._image_list, "images", is_media=False), "图片")
        self._tabs.addTab(self._make_tab(self._portrait_list, "portraits", is_media=False), "立绘")
        self._tabs.addTab(self._make_tab(self._audio_list, "audios", is_media=True), "音频")
        self._tabs.addTab(self._make_tab(self._voice_list, "voices", is_media=True), "语音")
        self._tabs.addTab(self._make_tab(self._video_list, "videos", is_media=True), "视频")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self._tabs)
        layout.setContentsMargins(4, 4, 4, 4)

        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.setWidget(scroll)

        # lazy init audio mixer for preview
        self._mixer_ready = False
        self._audio_channel = None
        self._path_role = Qt.ItemDataRole.UserRole

    def _make_tab(self, list_widget: QListWidget, res_key: str, is_media: bool) -> QWidget:
        tab = QWidget()
        vbox = QVBoxLayout(tab)

        import_btn = QPushButton("导入文件")
        import_btn.clicked.connect(lambda: self._import_files(list_widget, res_key, is_media))

        remove_btn = QPushButton("删除选中")
        remove_btn.clicked.connect(lambda: self._remove_selected(list_widget))

        vbox.addWidget(import_btn)
        vbox.addWidget(remove_btn)
        vbox.addWidget(list_widget)
        vbox.setContentsMargins(0, 0, 0, 0)
        return tab

    def _import_files(self, list_widget: QListWidget, res_key: str, is_media: bool):
        if res_key in ("images", "portraits"):
            filters = "图片文件 (*.png *.jpg *.jpeg *.bmp)"
        elif res_key == "videos":
            filters = "视频文件 (*.mp4 *.mov *.avi *.mkv)"
        else:
            filters = "音频文件 (*.mp3 *.ogg *.wav)"
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件", "", filters)
        if not files:
            return
        for file_path in files:
            try:
                stored_path = self._copy_into_project(file_path, res_key)
                self._add_item_if_absent(list_widget, stored_path)
            except Exception as exc:
                QMessageBox.critical(self, "导入失败", f"文件 {file_path} 导入失败: {exc}")

    def _add_item_if_absent(self, list_widget: QListWidget, file_path: str):
        # Avoid duplicates by comparing normalized paths
        norm = self._normalize_path(file_path)
        for idx in range(list_widget.count()):
            if list_widget.item(idx).data(self._path_role) == norm:
                return
        item = QListWidgetItem(Path(norm).name)
        item.setData(self._path_role, norm)
        if list_widget in (self._image_list, self._portrait_list):
            self._decorate_image_item(item)
        elif list_widget in (self._audio_list, self._voice_list):
            self._decorate_audio_item(item)
        elif list_widget is self._video_list:
            item.setToolTip(str(Path(norm)))
        list_widget.addItem(item)

    def _remove_selected(self, list_widget: QListWidget):
        for item in list_widget.selectedItems():
            list_widget.takeItem(list_widget.row(item))

    def clear_all(self):
        self._image_list.clear()
        self._audio_list.clear()
        self._portrait_list.clear()
        self._voice_list.clear()
        self._video_list.clear()

    def load_from_data(self, data: Dict):
        self.clear_all()
        if not isinstance(data, dict):
            return
        for key, lw in [
            ("images", self._image_list),
            ("audios", self._audio_list),
            ("portraits", self._portrait_list),
            ("voices", self._voice_list),
            ("videos", self._video_list),
        ]:
            for path in data.get(key, []) or []:
                self._add_item_if_absent(lw, path)

    def export_data(self) -> Dict[str, List[str]]:
        def collect(lw: QListWidget) -> List[str]:
            return [lw.item(i).data(self._path_role) for i in range(lw.count())]
        return {
            "images": collect(self._image_list),
            "audios": collect(self._audio_list),
            "portraits": collect(self._portrait_list),
            "voices": collect(self._voice_list),
            "videos": collect(self._video_list),
        }

    def set_project_dir(self, path: Path | None):
        self._project_dir = path

    def _copy_into_project(self, file_path: str, res_key: str) -> str:
        src = Path(file_path)
        if not src.exists():
            raise FileNotFoundError(f"{file_path} 不存在")

        base_dir = self._project_dir if self._project_dir else Path.cwd()
        target_dir = base_dir / "resources" / res_key
        os.makedirs(target_dir, exist_ok=True)

        target = target_dir / src.name
        counter = 1
        while target.exists():
            target = target_dir / f"{src.stem}_{counter}{src.suffix}"
            counter += 1

        shutil.copy2(src, target)

        try:
            rel_path = target.relative_to(base_dir)
            return str(rel_path)
        except ValueError:
            return str(target)

    def _normalize_path(self, path: str) -> str:
        # strip any old duration suffix like " (03:34)" then normalize
        cleaned = re.sub(r"\s*\(\d{2}:\d{2}\)$", "", path)
        p = Path(cleaned)
        if not p.is_absolute():
            return str(p)
        return str(p.resolve())

    def _show_list_menu(self, list_widget: QListWidget, pos, res_key: str):
        item = list_widget.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        open_action = menu.addAction("在资源管理器中打开")
        copy_action = menu.addAction("复制路径")
        rename_action = menu.addAction("重命名")
        delete_action = menu.addAction("删除并移除")
        play_action = None
        stop_action = None
        if list_widget is self._audio_list:
            play_action = menu.addAction("试听/播放")
            stop_action = menu.addAction("停止播放")

        action = menu.exec(QCursor.pos())
        path_str = item.data(self._path_role)
        abs_path = self._to_absolute(Path(path_str))

        if action == open_action:
            if abs_path.exists():
                os.startfile(abs_path)
            else:
                QMessageBox.warning(self, "提示", f"文件不存在：{abs_path}")
        elif action == copy_action:
            QGuiApplication.clipboard().setText(str(abs_path))
        elif action == rename_action:
            self._rename_item(item)
        elif action == delete_action:
            self._delete_item(item)
        elif play_action and action == play_action:
            self._preview_audio(item)
        elif stop_action and action == stop_action:
            self._stop_audio()

    def _to_absolute(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        base_dir = self._project_dir if self._project_dir else Path.cwd()
        candidate = (base_dir / path).resolve()
        if candidate.exists():
            return candidate
        # fallback: look under resources/ subdir
        res_root = (base_dir / "resources").resolve()
        alt = (res_root / path).resolve()
        if alt.exists():
            return alt
        # if path was just a file name, try resources/audios and resources/images
        if path.name:
            for sub in ["audios", "voices", "images", "portraits", "videos"]:
                candidate_sub = (res_root / sub / path.name).resolve()
                if candidate_sub.exists():
                    return candidate_sub
        return candidate

    def _decorate_image_item(self, item: QListWidgetItem):
        abs_path = self._to_absolute(Path(item.data(self._path_role)))
        if abs_path.exists():
            pix = QPixmap(str(abs_path)).scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            if not pix.isNull():
                item.setIcon(QIcon(pix))

    def _decorate_audio_item(self, item: QListWidgetItem):
        abs_path = self._to_absolute(Path(item.data(self._path_role)))
        duration = self._get_audio_duration(abs_path)
        base_name = Path(item.data(self._path_role)).name
        if duration:
            item.setText(f"{base_name} ({duration})")
        else:
            item.setText(base_name)
        item.setToolTip(str(abs_path))

    def _get_audio_duration(self, abs_path: Path) -> str | None:
        try:
            self._ensure_mixer()
            sound = pygame.mixer.Sound(str(abs_path))
            seconds = sound.get_length()
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes:02d}:{secs:02d}"
        except Exception:
            return None

    def _ensure_mixer(self):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self._mixer_ready = pygame.mixer.get_init() is not None
        except Exception:
            self._mixer_ready = False

    def _rename_item(self, item: QListWidgetItem):
        old_path = Path(item.data(self._path_role))
        abs_old = self._to_absolute(old_path)
        new_name, ok = QInputDialog.getText(self, "重命名", "新文件名（含扩展名）", text=abs_old.name)
        if not ok or not new_name:
            return
        new_abs = abs_old.with_name(new_name)
        try:
            abs_old.rename(new_abs)
            # update stored path (keep relative if original was relative)
            try:
                rel = new_abs.relative_to(self._project_dir if self._project_dir else new_abs.parent)
                new_store = str(rel)
            except ValueError:
                new_store = str(new_abs)
            item.setData(self._path_role, new_store)
            if item.listWidget() is self._image_list:
                item.setText(new_abs.name)
                self._decorate_image_item(item)
            else:
                item.setText(new_abs.name)
                self._decorate_audio_item(item)
        except Exception as exc:
            QMessageBox.critical(self, "重命名失败", f"无法重命名：{exc}")

    def _delete_item(self, item: QListWidgetItem):
        abs_path = self._to_absolute(Path(item.data(self._path_role)))
        reply = QMessageBox.question(self, "删除确认", f"是否删除文件：{abs_path}?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if abs_path.exists():
                abs_path.unlink()
        except Exception as exc:
            QMessageBox.warning(self, "删除失败", f"删除文件时出错：{exc}")
        lw = item.listWidget()
        lw.takeItem(lw.row(item))

    def _preview_audio(self, item: QListWidgetItem):
        abs_path = self._to_absolute(Path(item.data(self._path_role)))
        if not abs_path.exists():
            QMessageBox.warning(self, "预览失败", f"文件不存在：{abs_path}")
            return
        self._ensure_mixer()
        if not self._mixer_ready:
            QMessageBox.warning(self, "提示", "音频预览初始化失败")
            return
        try:
            sound = pygame.mixer.Sound(str(abs_path))
            if self._audio_channel and self._audio_channel.get_busy():
                self._audio_channel.stop()
            self._audio_channel = sound.play()
        except Exception as exc:
            QMessageBox.warning(self, "预览失败", f"播放音频失败：{exc}")

    def _stop_audio(self):
        if self._audio_channel and self._audio_channel.get_busy():
            self._audio_channel.stop()
