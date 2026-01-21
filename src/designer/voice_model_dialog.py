# -*- coding: utf-8 -*-
"""语音模型选择/管理对话框

- 选择：用于填充 audioId（只读选择）
- 管理：支持分页查询、上传创建、删除

依赖 GPT-SoVITS 的 /api/third/reference/list 分页接口。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QInputDialog,
)

from src.ai.api.gptsovits_client import GPTSoVITSClient
from src.ai.core.config_manager import ConfigManager


def get_gptsovits_client(config_manager: ConfigManager, parent=None) -> GPTSoVITSClient | None:
    cfg = config_manager.load_config() or {}
    gpt_cfg = (cfg.get("api_keys") or {}).get("gptsovits", {})
    sign = gpt_cfg.get("sign", "")
    base_url = gpt_cfg.get("base_url", "https://openapi.lipvoice.cn")

    if not sign:
        QMessageBox.warning(parent, "缺少签名", "请先在 API 配置中填写 gptsovits 的 sign")
        return None

    try:
        return GPTSoVITSClient(sign=sign, base_url=base_url)
    except Exception as exc:
        QMessageBox.critical(parent, "初始化失败", f"无法创建 gptsovits 客户端：{exc}")
        return None


@dataclass
class VoiceModelRow:
    audio_id: str
    name: str = ""
    describe: str = ""

    @staticmethod
    def from_api(data: Dict[str, Any]) -> "VoiceModelRow":
        return VoiceModelRow(
            audio_id=str(data.get("audioId", "") or ""),
            name=str(data.get("name", "") or ""),
            describe=str(data.get("describe", "") or ""),
        )


class VoiceModelPickerDialog(QDialog):
    """分页选择语音模型 audioId。"""

    def __init__(
        self,
        client: GPTSoVITSClient,
        parent=None,
        *,
        allow_manage: bool = False,
        initial_page_size: int = 20,
    ):
        super().__init__(parent)
        self.client = client
        self.allow_manage = bool(allow_manage)
        self.page = 1
        self.page_size = int(initial_page_size) if initial_page_size else 20
        self.total: Optional[int] = None
        self.models: List[VoiceModelRow] = []

        self.setWindowTitle("语音模型配置" if self.allow_manage else "选择语音模型")
        self.resize(900, 520)

        self._init_ui()
        self._load_page(reset=True)

    def selected_audio_id(self) -> Optional[str]:
        item = self.list_widget.currentItem()
        if not item:
            return None
        return str(item.data(Qt.ItemDataRole.UserRole) or "") or None

    def _init_ui(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 10_000)
        self.page_spin.setValue(self.page)
        self.page_spin.valueChanged.connect(self._on_page_changed)

        self.page_size_combo = QComboBox()
        for v in (5, 10, 20):
            self.page_size_combo.addItem(str(v), v)
        idx = self.page_size_combo.findData(self.page_size)
        self.page_size_combo.setCurrentIndex(idx if idx >= 0 else self.page_size_combo.count() - 1)
        self.page_size_combo.currentIndexChanged.connect(self._on_page_size_changed)

        self.refresh_btn = QPushButton("查询")
        self.refresh_btn.clicked.connect(lambda: self._load_page(reset=False))

        self.prev_btn = QPushButton("上一页")
        self.next_btn = QPushButton("下一页")
        self.prev_btn.clicked.connect(self._prev_page)
        self.next_btn.clicked.connect(self._next_page)

        self.page_info = QLabel("-")

        top.addWidget(QLabel("页码"))
        top.addWidget(self.page_spin)
        top.addSpacing(10)
        top.addWidget(QLabel("每页"))
        top.addWidget(self.page_size_combo)
        top.addWidget(self.refresh_btn)
        top.addSpacing(10)
        top.addWidget(self.prev_btn)
        top.addWidget(self.next_btn)
        top.addStretch(1)
        top.addWidget(self.page_info)
        layout.addLayout(top)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _: self._accept_selection())
        layout.addWidget(self.list_widget, 1)

        if self.allow_manage:
            manage = QHBoxLayout()
            self.upload_btn = QPushButton("上传创建")
            self.delete_btn = QPushButton("删除选中")
            self.upload_btn.clicked.connect(self._upload_create)
            self.delete_btn.clicked.connect(self._delete_selected)
            manage.addWidget(self.upload_btn)
            manage.addWidget(self.delete_btn)
            manage.addStretch(1)
            layout.addLayout(manage)

        bottom = QHBoxLayout()
        self.ok_btn = QPushButton("确定")
        self.cancel_btn = QPushButton("取消")
        self.ok_btn.clicked.connect(self._accept_selection)
        self.cancel_btn.clicked.connect(self.reject)
        bottom.addStretch(1)
        bottom.addWidget(self.ok_btn)
        bottom.addWidget(self.cancel_btn)
        layout.addLayout(bottom)

    def _set_busy(self, busy: bool):
        for w in (self.page_spin, self.page_size_combo, self.refresh_btn, self.prev_btn, self.next_btn, self.ok_btn):
            w.setEnabled(not busy)
        if self.allow_manage:
            self.upload_btn.setEnabled(not busy)
            self.delete_btn.setEnabled(not busy)

    def _on_page_changed(self, v: int):
        self.page = int(v) if v and v > 0 else 1

    def _on_page_size_changed(self):
        self.page_size = int(self.page_size_combo.currentData() or 20)
        self.page = 1
        self.page_spin.setValue(self.page)

    def _prev_page(self):
        if self.page <= 1:
            return
        self.page -= 1
        self.page_spin.setValue(self.page)
        self._load_page(reset=False)

    def _next_page(self):
        self.page += 1
        self.page_spin.setValue(self.page)
        self._load_page(reset=False)

    def _load_page(self, *, reset: bool):
        if reset:
            self.page = 1
            self.page_spin.setValue(self.page)

        try:
            self._set_busy(True)
            data = self.client.list_reference_models(page=self.page, page_size=self.page_size)
        except Exception as exc:
            QMessageBox.critical(self, "获取失败", f"无法获取模型列表：{exc}")
            return
        finally:
            self._set_busy(False)

        raw_list = data.get("list", []) if isinstance(data, dict) else []
        self.total = data.get("total") if isinstance(data, dict) else None

        self.models = [VoiceModelRow.from_api(m) for m in raw_list if isinstance(m, dict)]
        self.list_widget.clear()
        for row in self.models:
            text = f"{row.name} | {row.audio_id} | {row.describe}".strip(" |")
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, row.audio_id)
            self.list_widget.addItem(item)

        # 页码按钮状态
        self.prev_btn.setEnabled(self.page > 1)
        if isinstance(self.total, int) and self.total >= 0:
            pages = max(1, (int(self.total) + self.page_size - 1) // self.page_size)
            self.page_info.setText(f"共 {self.total} 条 | {self.page}/{pages} 页")
            self.next_btn.setEnabled(self.page < pages)
        else:
            self.page_info.setText(f"第 {self.page} 页")
            self.next_btn.setEnabled(len(self.models) >= self.page_size)

        if self.models:
            self.list_widget.setCurrentRow(0)

    def _accept_selection(self):
        if self.selected_audio_id() is None:
            QMessageBox.information(self, "提示", "请先选择一条模型")
            return
        self.accept()

    def _upload_create(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择语音样本 (2-60秒, <50MB)",
            str(Path.cwd()),
            "Audio Files (*.mp3 *.wav *.m4a)"
        )
        if not file_path:
            return

        name, ok = QInputDialog.getText(self, "模型名称", "请输入模型名称：")
        if not ok or not name.strip():
            return
        describe, _ = QInputDialog.getText(self, "模型描述", "可选描述：")

        try:
            self._set_busy(True)
            self.client.upload_reference_model(file_path=file_path, name=name.strip(), describe=(describe or "").strip())
        except Exception as exc:
            QMessageBox.critical(self, "创建失败", f"模型创建失败：{exc}")
            return
        finally:
            self._set_busy(False)

        QMessageBox.information(self, "成功", "模型已创建，正在刷新列表")
        self._load_page(reset=True)

    def _delete_selected(self):
        audio_id = self.selected_audio_id()
        if not audio_id:
            QMessageBox.warning(self, "缺少ID", "请先选择要删除的模型")
            return

        confirm = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除模型 {audio_id} 吗？删除后不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            self._set_busy(True)
            self.client.delete_reference_model(audio_id)
        except Exception as exc:
            QMessageBox.critical(self, "删除失败", f"删除失败：{exc}")
            return
        finally:
            self._set_busy(False)

        QMessageBox.information(self, "已删除", "模型已删除，正在刷新列表")
        self._load_page(reset=False)
