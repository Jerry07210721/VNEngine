# -*- coding: utf-8 -*-
"""Dialog for editing global game variables."""
from __future__ import annotations

from typing import List, Dict
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QFormLayout,
    QLineEdit,
    QDoubleSpinBox,
    QCheckBox,
    QMessageBox,
)
from PyQt6.QtCore import Qt


class GlobalVarsDialog(QDialog):
    """Simple editor for global variables (float-only in current version)."""

    def __init__(self, project_manager, parent=None):
        super().__init__(parent)
        self.project_manager = project_manager
        self.setWindowTitle("全局变量设置")
        self.setMinimumWidth(420)
        self._vars: List[Dict] = []
        if project_manager:
            data = project_manager.project_data.get("global_variables") or []
            if isinstance(data, list):
                self._vars = [v for v in data if isinstance(v, dict)]

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _: self._edit_selected())

        btn_add = QPushButton("新增")
        btn_add.clicked.connect(self._add_var)
        btn_edit = QPushButton("编辑")
        btn_edit.clicked.connect(self._edit_selected)
        btn_del = QPushButton("删除")
        btn_del.clicked.connect(self._delete_selected)

        top = QHBoxLayout()
        top.addWidget(btn_add)
        top.addWidget(btn_edit)
        top.addWidget(btn_del)
        top.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self._accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        self._refresh_list()

    def _refresh_list(self):
        self._list.clear()
        for item in self._vars:
            name = item.get("name", "")
            init_val = item.get("initial", 0.0)
            protected = bool(item.get("protected", False))
            tag = " [保护]" if protected else ""
            display = f"{name or '<未命名>'} = {init_val} (float){tag}"
            lw_item = QListWidgetItem(display)
            lw_item.setData(Qt.ItemDataRole.UserRole, item)
            self._list.addItem(lw_item)

    def _add_var(self):
        edited = self._edit_var(None)
        if edited:
            self._vars.append(edited)
            self._refresh_list()

    def _edit_selected(self):
        current = self._list.currentItem()
        if not current:
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        edited = self._edit_var(data)
        if edited:
            idx = self._list.row(current)
            self._vars[idx] = edited
            self._refresh_list()
            self._list.setCurrentRow(idx)

    def _delete_selected(self):
        current = self._list.currentItem()
        if not current:
            return
        row = self._list.row(current)
        self._vars.pop(row)
        self._refresh_list()
        if self._list.count():
            self._list.setCurrentRow(min(row, self._list.count() - 1))

    def _edit_var(self, data: Dict | None) -> Dict | None:
        dlg = QDialog(self)
        dlg.setWindowTitle("编辑变量")
        form = QFormLayout(dlg)
        name_edit = QLineEdit(data.get("name", "") if data else "")
        value_spin = QDoubleSpinBox()
        value_spin.setRange(-1e12, 1e12)
        value_spin.setDecimals(6)
        value_spin.setValue(float(data.get("initial", 0.0)) if data else 0.0)
        protected_chk = QCheckBox("启用")
        protected_chk.setChecked(bool(data.get("protected", False)) if data else False)

        form.addRow("变量名", name_edit)
        form.addRow("初始值 (float)", value_spin)
        form.addRow("保护（读档/开始游戏不回溯）", protected_chk)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(dlg.accept)
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        form.addRow(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        name = name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "变量名不能为空")
            return None
        # name uniqueness check
        for existing in self._vars:
            if existing is data:
                continue
            if existing.get("name") == name:
                QMessageBox.warning(self, "提示", "变量名已存在")
                return None
        return {"name": name, "type": "float", "initial": value_spin.value(), "protected": bool(protected_chk.isChecked())}

    def _accept(self):
        if self.project_manager:
            self.project_manager.project_data["global_variables"] = self._vars
        self.accept()


__all__ = ["GlobalVarsDialog"]
