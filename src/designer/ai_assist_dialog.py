# -*- coding: utf-8 -*-
"""AI 辅助配置对话框：工程/故事/角色/素材/Agent开关/API 密钥。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from src.ai.core.config_manager import ConfigManager
from src.ai.core.secret_store import get_secret_key_storage_display, get_secret_key_storage_path
from src.ai.api.gptsovits_client import GPTSoVITSClient


class AIAssistDialog(QDialog):
    """集中配置 AI 辅助参数，写入 ai_config.yaml。"""

    def __init__(self, config_manager: Optional[ConfigManager] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 辅助配置")
        # AI辅助界面默认窗口大小：1280x720
        self.resize(1280, 720)
        self.config_manager = config_manager or ConfigManager()

        self.tabs = QTabWidget(self)
        self._init_project_tab()
        self._init_story_tab()
        self._init_characters_tab()
        self._init_material_tab()
        self._init_agent_tab()
        self._init_api_tab()

        btn_row = QHBoxLayout()
        self.load_btn = QPushButton("从配置加载")
        self.save_btn = QPushButton("保存配置")
        self.close_btn = QPushButton("关闭")
        self.load_btn.clicked.connect(self.load_from_config)
        self.save_btn.clicked.connect(self.save_to_config)
        self.close_btn.clicked.connect(self.accept)
        btn_row.addStretch(1)
        for btn in (self.load_btn, self.save_btn, self.close_btn):
            btn_row.addWidget(btn)

        main = QVBoxLayout(self)
        main.addWidget(self.tabs)
        main.addLayout(btn_row)

        self.load_from_config()

    # --- 构建各 Tab ---
    def _init_project_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        self.project_name = QLineEdit()
        self.project_path = QLineEdit()
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self._pick_project_dir)
        path_row = QHBoxLayout()
        path_row.addWidget(self.project_path)
        path_row.addWidget(browse_btn)
        self.window_w = QSpinBox(); self.window_w.setRange(320, 4096)
        self.window_h = QSpinBox(); self.window_h.setRange(240, 4096)
        self.engine_ver = QLineEdit("V2.7-AI")
        form.addRow("工程名称", self.project_name)
        form.addRow("工程路径", path_row)
        form.addRow("窗口宽度", self.window_w)
        form.addRow("窗口高度", self.window_h)
        form.addRow("引擎版本", self.engine_ver)
        self.tabs.addTab(w, "工程配置")

    def _init_story_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        self.story_title = QLineEdit()
        self.story_style = QLineEdit()
        self.story_outline = QTextEdit()
        self.text_volume = QSpinBox(); self.text_volume.setRange(1000, 100000)
        self.story_pov = QComboBox(); self.story_pov.addItem("第三人称", "third"); self.story_pov.addItem("第一人称", "first")
        self.character_hint_weight = QDoubleSpinBox(); self.character_hint_weight.setRange(0.0, 1.0); self.character_hint_weight.setSingleStep(0.05); self.character_hint_weight.setValue(0.7)
        self.first_person_name = QLineEdit("我")
        self.first_person_portrait = QCheckBox("第一人称有立绘")
        self.first_person_voice = QCheckBox("第一人称有配音")
        self.first_person_cg = QCheckBox("第一人称出现在CG")
        self.first_person_cg.setChecked(True)
        self.first_person_cg_notes = QLineEdit()
        form.addRow("故事标题", self.story_title)
        form.addRow("故事风格", self.story_style)
        form.addRow("剧情梗概", self.story_outline)
        form.addRow("文本量", self.text_volume)
        form.addRow("叙述视角", self.story_pov)
        form.addRow("角色设定权重(0-1)", self.character_hint_weight)
        form.addRow("第一人称名字/代称", self.first_person_name)
        form.addRow(self.first_person_portrait)
        form.addRow(self.first_person_voice)
        form.addRow(self.first_person_cg)
        form.addRow("第一人称CG说明", self.first_person_cg_notes)
        self.tabs.addTab(w, "故事配置")

    def _init_characters_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        self.char_list = QListWidget()
        layout.addWidget(QLabel("角色列表（选择后可在右侧表单编辑，支持导入/导出）"))

        list_row = QHBoxLayout()
        list_row.addWidget(self.char_list, 1)

        form_wrap = QFormLayout()
        self.char_name = QLineEdit()
        self.char_role = QLineEdit("主角")
        self.char_first_person = QCheckBox("第一人称角色（第一人称视角时跳过立绘/语音）")
        self.char_persona = QLineEdit()
        self.char_voice = QLineEdit()
        voice_row = QHBoxLayout()
        voice_row.addWidget(self.char_voice)
        query_btn = QPushButton("查询模型ID")
        query_btn.clicked.connect(self._open_model_picker)
        create_btn = QPushButton("创建模型")
        create_btn.clicked.connect(self._create_model)
        delete_btn = QPushButton("删除模型")
        delete_btn.clicked.connect(self._delete_model)
        for btn in (query_btn, create_btn, delete_btn):
            voice_row.addWidget(btn)
        form_wrap.addRow("姓名", self.char_name)
        form_wrap.addRow("角色定位", self.char_role)
        form_wrap.addRow(self.char_first_person)
        form_wrap.addRow("人设关键词", self.char_persona)
        form_wrap.addRow("语音模型ID", voice_row)
        save_btn = QPushButton("更新当前")
        save_btn.clicked.connect(self._update_current_character)
        form_wrap.addRow(save_btn)

        form_widget = QWidget(); form_widget.setLayout(form_wrap)
        list_row.addWidget(form_widget, 1)
        layout.addLayout(list_row)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("添加角色")
        del_btn = QPushButton("删除角色")
        import_btn = QPushButton("导入JSON")
        export_btn = QPushButton("导出JSON")
        add_btn.clicked.connect(self._add_character)
        del_btn.clicked.connect(self._remove_character)
        import_btn.clicked.connect(self._import_characters)
        export_btn.clicked.connect(self._export_characters)
        for btn in (add_btn, del_btn, import_btn, export_btn):
            btn_row.addWidget(btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.char_list.currentRowChanged.connect(self._on_character_selected)
        self.tabs.addTab(w, "角色配置")

    def _init_material_tab(self):
        w = QWidget()
        grid = QGridLayout(w)
        self.portrait_fmt = self._fmt_combo()
        self.background_fmt = self._fmt_combo(default="jpg")
        self.cg_fmt = self._fmt_combo()
        self.voice_fmt = self._fmt_combo(default="mp3", choices=["mp3", "wav", "ogg"])
        self.bgm_fmt = self._fmt_combo(default="mp3", choices=["mp3", "wav", "ogg"])
        grid.addWidget(QLabel("立绘格式"), 0, 0); grid.addWidget(self.portrait_fmt, 0, 1)
        grid.addWidget(QLabel("背景格式"), 1, 0); grid.addWidget(self.background_fmt, 1, 1)
        grid.addWidget(QLabel("CG 格式"), 2, 0); grid.addWidget(self.cg_fmt, 2, 1)
        grid.addWidget(QLabel("语音格式"), 3, 0); grid.addWidget(self.voice_fmt, 3, 1)
        grid.addWidget(QLabel("BGM 格式"), 4, 0); grid.addWidget(self.bgm_fmt, 4, 1)
        grid.setColumnStretch(2, 1)
        self.tabs.addTab(w, "素材配置")

    def _init_agent_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("Agent 启用开关"))
        self.chk_plot = QCheckBox("剧情 Agent")
        self.chk_portrait = QCheckBox("立绘 Agent")
        self.chk_background = QCheckBox("背景 Agent")
        self.chk_cg = QCheckBox("CG Agent")
        self.chk_voice = QCheckBox("语音接口")
        self.chk_bgm = QCheckBox("BGM 接口")
        for chk in [self.chk_plot, self.chk_portrait, self.chk_background, self.chk_cg, self.chk_voice, self.chk_bgm]:
            chk.setChecked(True)
            layout.addWidget(chk)
        layout.addStretch(1)
        self.tabs.addTab(w, "Agent 开关")

    def _init_api_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)

        # Show where the encryption key is stored (for backup/migration).
        self.secret_key_path_edit = QLineEdit()
        self.secret_key_path_edit.setReadOnly(True)
        self.secret_key_path_edit.setText(get_secret_key_storage_display())
        copy_btn = QPushButton("复制")
        open_btn = QPushButton("打开文件夹")
        copy_btn.clicked.connect(self._copy_secret_key_path)
        open_btn.clicked.connect(self._open_secret_key_folder)
        key_row = QHBoxLayout()
        key_row.addWidget(self.secret_key_path_edit, 1)
        key_row.addWidget(copy_btn)
        key_row.addWidget(open_btn)
        form.addRow("加密密钥位置", key_row)

        # api_fields: api_name -> field_name -> widget (QLineEdit/QSpinBox...)
        self.api_fields: Dict[str, Dict[str, QWidget]] = {}
        api_defs = {
            "claude": {},
            "kimi": {},
            "midjourney": {"app_id": False},
            "flux": {"app_id": False},
            "gptsovits": {"sign": True},
            "suno": {"token": True, "user_id": False},
        }

        for api_name, extra in api_defs.items():
            field: Dict[str, QWidget] = {}
            key_edit = QLineEdit(); key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            model_edit = QLineEdit()
            fallback_edit = QLineEdit()
            base_url = QLineEdit()
            timeout_spin = QSpinBox(); timeout_spin.setRange(10, 86_400)
            field["api_key"] = key_edit
            field["primary_model"] = model_edit
            field["fallback_model"] = fallback_edit
            field["base_url"] = base_url
            field["timeout"] = timeout_spin

            toggle_btn = QPushButton("显示/隐藏")
            toggle_btn.setCheckable(True)
            toggle_btn.toggled.connect(lambda checked, edit=key_edit: edit.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))

            row = QWidget(); row_layout = QGridLayout(row); row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(QLabel("Key"), 0, 0); row_layout.addWidget(key_edit, 0, 1); row_layout.addWidget(toggle_btn, 0, 2)
            row_layout.addWidget(QLabel("主模型"), 1, 0); row_layout.addWidget(model_edit, 1, 1)
            row_layout.addWidget(QLabel("备选模型"), 2, 0); row_layout.addWidget(fallback_edit, 2, 1)
            row_layout.addWidget(QLabel("Base URL"), 3, 0); row_layout.addWidget(base_url, 3, 1)

            row_layout.addWidget(QLabel("超时(s)"), 4, 0)
            row_layout.addWidget(timeout_spin, 4, 1)

            row_idx = 5
            for extra_key, mask in extra.items():
                edit = QLineEdit()
                if mask:
                    edit.setEchoMode(QLineEdit.EchoMode.Password)
                field[extra_key] = edit
                row_layout.addWidget(QLabel(extra_key), row_idx, 0)
                row_layout.addWidget(edit, row_idx, 1)
                row_idx += 1

            form.addRow(f"{api_name} 配置", row)
            self.api_fields[api_name] = field
        self.validate_btn = QPushButton("验证配置")
        self.validate_btn.clicked.connect(self._validate_api_config)
        form.addRow(self.validate_btn)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.tabs.addTab(w, "API 配置")

    def _copy_secret_key_path(self):
        text = self.secret_key_path_edit.text().strip() if hasattr(self, "secret_key_path_edit") else ""
        if not text:
            return
        try:
            QApplication.clipboard().setText(text)
        except Exception:
            pass

    def _open_secret_key_folder(self):
        path = get_secret_key_storage_path()
        if path is None:
            QMessageBox.information(self, "提示", "当前使用环境变量 VNENGINE_SECRET_KEY 提供密钥，不存在密钥文件。")
            return
        try:
            folder = path.parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        except Exception:
            pass

    # --- 事件 ---
    def _fmt_combo(self, default: str = "png", choices: Optional[List[str]] = None) -> QComboBox:
        combo = QComboBox()
        for opt in (choices or ["png", "jpg", "jpeg"]):
            combo.addItem(opt)
        idx = combo.findText(default)
        combo.setCurrentIndex(max(0, idx))
        return combo

    def _pick_project_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择工程路径", str(Path.cwd()))
        if path:
            self.project_path.setText(path)

    def _add_character(self):
        item = QListWidgetItem("新角色 | 主角 | 性格关键词 | 语音模型ID | ")
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.char_list.addItem(item)
        self.char_list.editItem(item)
        self.char_list.setCurrentItem(item)
        self._apply_item_to_form(item)

    def _remove_character(self):
        row = self.char_list.currentRow()
        if row >= 0:
            self.char_list.takeItem(row)

    def _on_character_selected(self, row: int):
        item = self.char_list.item(row) if row >= 0 else None
        self._apply_item_to_form(item)

    def _apply_item_to_form(self, item: Optional[QListWidgetItem]):
        if not item:
            self.char_name.clear(); self.char_role.setText("主角"); self.char_persona.clear(); self.char_voice.clear(); self.char_first_person.setChecked(False)
            return
        name, role, persona, voice, is_fp = self._parse_item_text(item.text())
        self.char_name.setText(name)
        self.char_role.setText(role)
        self.char_persona.setText(persona)
        self.char_voice.setText(voice)
        self.char_first_person.setChecked(is_fp)

    def _update_current_character(self):
        item = self.char_list.currentItem()
        if not item:
            return
        name = self.char_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "姓名不能为空")
            return
        role = self.char_role.text().strip() or "主角"
        persona = self.char_persona.text().strip()
        voice = self.char_voice.text().strip()
        fp_flag = "第一人称" if self.char_first_person.isChecked() else ""
        item.setText(f"{name} | {role} | {persona} | {voice} | {fp_flag}")

    def _parse_item_text(self, text: str) -> tuple[str, str, str, str, bool]:
        parts = [p.strip() for p in (text or "").split("|")]
        while len(parts) < 5:
            parts.append("")
        return parts[0], parts[1], parts[2], parts[3], parts[4] == "第一人称"

    def _get_gptsovits_client(self) -> Optional[GPTSoVITSClient]:
        cfg = self.config_manager.load_config() or {}
        gpt_cfg = (cfg.get("api_keys") or {}).get("gptsovits", {})
        sign = gpt_cfg.get("sign", "")
        base_url = gpt_cfg.get("base_url", "https://openapi.lipvoice.cn")
        timeout = gpt_cfg.get("timeout", 300)

        if not sign:
            QMessageBox.warning(self, "缺少签名", "请先在 API 配置中填写 gptsovits 的 sign")
            return None

        try:
            return GPTSoVITSClient(sign=sign, base_url=base_url, timeout=int(timeout) if timeout is not None else 300)
        except Exception as exc:
            QMessageBox.critical(self, "初始化失败", f"无法创建 gptsovits 客户端：{exc}")
            return None

    def _open_model_picker(self):
        client = self._get_gptsovits_client()
        if not client:
            return

        try:
            data = client.list_reference_models(page=1, page_size=20)
        except Exception as exc:
            QMessageBox.critical(self, "获取失败", f"无法获取模型列表：{exc}")
            return

        models = data.get("list", []) if isinstance(data, dict) else []

        if not models:
            QMessageBox.information(self, "无数据", "未获取到模型列表")
            return

        picker = QDialog(self)
        picker.setWindowTitle("选择语音模型")
        vbox = QVBoxLayout(picker)
        list_widget = QListWidget()
        for m in models:
            audio_id = m.get("audioId", "")
            name = m.get("name", "")
            desc = m.get("describe", "")
            text = f"{name} | {audio_id} | {desc}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, audio_id)
            list_widget.addItem(item)
        vbox.addWidget(list_widget)
        btns = QHBoxLayout()
        ok_btn = QPushButton("确定")
        cancel_btn = QPushButton("取消")
        btns.addStretch(1)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        vbox.addLayout(btns)

        def apply_selection():
            item = list_widget.currentItem()
            if item:
                self.char_voice.setText(str(item.data(Qt.ItemDataRole.UserRole)))
            picker.accept()

        list_widget.itemDoubleClicked.connect(lambda _: apply_selection())
        ok_btn.clicked.connect(apply_selection)
        cancel_btn.clicked.connect(picker.reject)

        picker.exec()

    def _create_model(self):
        client = self._get_gptsovits_client()
        if not client:
            return

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
            data = client.upload_reference_model(file_path=file_path, name=name.strip(), describe=describe.strip())
        except Exception as exc:
            QMessageBox.critical(self, "创建失败", f"模型创建失败：{exc}")
            return

        audio_id = data.get("audioId") if isinstance(data, dict) else None
        if audio_id:
            self.char_voice.setText(str(audio_id))
            QMessageBox.information(self, "创建成功", f"模型已创建：{audio_id}")
        else:
            QMessageBox.warning(self, "创建结果", "模型创建成功但未返回 audioId")

    def _delete_model(self):
        client = self._get_gptsovits_client()
        if not client:
            return

        audio_id = self.char_voice.text().strip()
        if not audio_id:
            QMessageBox.warning(self, "缺少ID", "请先填入要删除的模型ID")
            return

        confirm = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除模型 {audio_id} 吗？删除后不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            client.delete_reference_model(audio_id)
        except Exception as exc:
            QMessageBox.critical(self, "删除失败", f"删除失败：{exc}")
            return

        self.char_voice.clear()
        QMessageBox.information(self, "已删除", "模型已删除")

    def _import_characters(self):
        path_str, _ = QFileDialog.getOpenFileName(self, "导入角色JSON", str(Path.cwd()), "JSON (*.json)")
        if not path_str:
            return
        try:
            with open(path_str, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("格式需为数组")
            self.char_list.clear()
            for ch in data:
                name = ch.get("char_name", "") or ch.get("name", "")
                role = ch.get("role", "主角")
                persona = ch.get("persona_keywords", "")
                voice = ch.get("voice_model_id", "")
                fp_flag = "第一人称" if ch.get("is_first_person", False) else ""
                item = QListWidgetItem(f"{name} | {role} | {persona} | {voice} | {fp_flag}")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                self.char_list.addItem(item)
            if self.char_list.count() > 0:
                self.char_list.setCurrentRow(0)
            QMessageBox.information(self, "导入成功", "角色已导入")
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", f"无法导入角色：{exc}")

    def _export_characters(self):
        path_str, _ = QFileDialog.getSaveFileName(self, "导出角色JSON", str(Path.cwd()), "JSON (*.json)")
        if not path_str:
            return
        data = self._collect_characters()
        try:
            with open(path_str, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "导出成功", "角色已导出")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", f"无法写入文件：{exc}")

    def load_from_config(self):
        cfg = self.config_manager.load_config() or {}
        proj = cfg.get("project_settings", {})
        agent_cfg = (cfg.get("agent_settings") or {}).get("enable_agents", {})
        material = cfg.get("material_settings", {})
        story_cfg = cfg.get("story_config", {})

        self.project_name.setText(proj.get("project_name", ""))
        self.project_path.setText(proj.get("resource_root", "output/projects"))
        self.window_w.setValue(int(proj.get("default_window_width", 1280)))
        self.window_h.setValue(int(proj.get("default_window_height", 720)))
        self.engine_ver.setText(proj.get("engine_version", "V2.7-AI"))

        self.story_title.setText(story_cfg.get("title", ""))
        self.story_style.setText(story_cfg.get("style", ""))
        self.story_outline.setPlainText(story_cfg.get("plot_outline", ""))
        self.text_volume.setValue(int(story_cfg.get("text_volume", 5000)))
        pov_val = story_cfg.get("narrative_pov", "third")
        idx = self.story_pov.findData(pov_val)
        self.story_pov.setCurrentIndex(idx if idx >= 0 else 0)
        self.character_hint_weight.setValue(float(story_cfg.get("character_hint_weight", 0.7)))
        self.first_person_name.setText(story_cfg.get("first_person_name", "我"))
        self.first_person_portrait.setChecked(bool(story_cfg.get("first_person_has_portrait", False)))
        self.first_person_voice.setChecked(bool(story_cfg.get("first_person_has_voice", False)))
        self.first_person_cg.setChecked(bool(story_cfg.get("first_person_cg_presence", True)))
        self.first_person_cg_notes.setText(story_cfg.get("first_person_cg_notes", ""))

        self._load_material(material)
        self._load_agents(agent_cfg)
        self._load_characters(cfg.get("character_config", []))
        self._load_api(cfg.get("api_keys", {}))

    def _load_material(self, material_cfg: Dict[str, Any]):
        self._set_combo(self.portrait_fmt, material_cfg.get("portrait", {}).get("format", "png"))
        self._set_combo(self.background_fmt, material_cfg.get("background", {}).get("format", "jpg"))
        self._set_combo(self.cg_fmt, material_cfg.get("cg", {}).get("format", "png"))
        self._set_combo(self.voice_fmt, material_cfg.get("voice", {}).get("format", "mp3"))
        self._set_combo(self.bgm_fmt, material_cfg.get("bgm", {}).get("format", "mp3"))

    def _load_agents(self, agent_cfg: Dict[str, Any]):
        self.chk_plot.setChecked(bool(agent_cfg.get("plot_agent", True)))
        self.chk_portrait.setChecked(bool(agent_cfg.get("portrait_agent", True)))
        self.chk_background.setChecked(bool(agent_cfg.get("background_agent", True)))
        self.chk_cg.setChecked(bool(agent_cfg.get("cg_agent", True)))
        self.chk_voice.setChecked(bool(agent_cfg.get("voice_api", True)))
        self.chk_bgm.setChecked(bool(agent_cfg.get("bgm_api", True)))

    def _load_characters(self, chars: List[Dict[str, Any]]):
        self.char_list.clear()
        for ch in chars:
            name = ch.get("char_name", ch.get("name", "角色"))
            role = ch.get("role", "主角")
            persona = ch.get("persona_keywords", ch.get("persona", ""))
            voice = ch.get("voice_model_id", "")
            fp_flag = "第一人称" if ch.get("is_first_person", False) else ""
            item = QListWidgetItem(f"{name} | {role} | {persona} | {voice} | {fp_flag}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.char_list.addItem(item)

    def _load_api(self, api_cfg: Dict[str, Any]):
        for name, fields in self.api_fields.items():
            data = api_cfg.get(name, {})
            # known text fields
            api_key = fields.get("api_key")
            if isinstance(api_key, QLineEdit):
                api_key.setText(data.get("api_key", ""))
            primary = fields.get("primary_model")
            if isinstance(primary, QLineEdit):
                primary.setText(data.get("primary_model", ""))
            fallback = fields.get("fallback_model")
            if isinstance(fallback, QLineEdit):
                fallback.setText(data.get("fallback_model", ""))
            base_url = fields.get("base_url")
            if isinstance(base_url, QLineEdit):
                base_url.setText(data.get("base_url", ""))

            timeout_w = fields.get("timeout")
            if isinstance(timeout_w, QSpinBox):
                try:
                    timeout_w.setValue(int(data.get("timeout", timeout_w.value() or 300)))
                except Exception:
                    timeout_w.setValue(timeout_w.value() or 300)

            for extra_key in [k for k in fields.keys() if k not in ["api_key", "primary_model", "fallback_model", "base_url", "timeout"]]:
                w = fields[extra_key]
                if isinstance(w, QLineEdit):
                    w.setText(str(data.get(extra_key, "") or ""))
                elif isinstance(w, QSpinBox):
                    try:
                        w.setValue(int(data.get(extra_key, w.value())))
                    except Exception:
                        pass

    def save_to_config(self):
        cfg = self.config_manager.config_data or {}
        cfg.setdefault("project_settings", {})
        cfg.setdefault("story_config", {})
        cfg.setdefault("agent_settings", {})
        cfg.setdefault("material_settings", {})
        cfg.setdefault("api_keys", {})

        cfg["project_settings"].update({
            "project_name": self.project_name.text().strip(),
            "resource_root": self.project_path.text().strip() or "output/projects",
            "default_window_width": int(self.window_w.value()),
            "default_window_height": int(self.window_h.value()),
            "engine_version": self.engine_ver.text().strip() or "V2.7-AI",
        })

        cfg["story_config"].update({
            "title": self.story_title.text().strip(),
            "style": self.story_style.text().strip(),
            "plot_outline": self.story_outline.toPlainText().strip(),
            "text_volume": int(self.text_volume.value()),
            "narrative_pov": self.story_pov.currentData(),
            "character_hint_weight": float(self.character_hint_weight.value()),
            "first_person_name": self.first_person_name.text().strip() or "我",
            "first_person_has_portrait": self.first_person_portrait.isChecked(),
            "first_person_has_voice": self.first_person_voice.isChecked(),
            "first_person_cg_presence": self.first_person_cg.isChecked(),
            "first_person_cg_notes": self.first_person_cg_notes.text().strip(),
        })

        cfg["agent_settings"]["enable_agents"] = {
            "plot_agent": self.chk_plot.isChecked(),
            "portrait_agent": self.chk_portrait.isChecked(),
            "background_agent": self.chk_background.isChecked(),
            "cg_agent": self.chk_cg.isChecked(),
            "voice_api": self.chk_voice.isChecked(),
            "bgm_api": self.chk_bgm.isChecked(),
        }

        cfg["material_settings"].update({
            "portrait": {"format": self.portrait_fmt.currentText()},
            "background": {"format": self.background_fmt.currentText()},
            "cg": {"format": self.cg_fmt.currentText()},
            "voice": {"format": self.voice_fmt.currentText()},
            "bgm": {"format": self.bgm_fmt.currentText()},
        })

        cfg["character_config"] = self._collect_characters()
        cfg["api_keys"] = self._collect_api(cfg.get("api_keys", {}))

        ok = self.config_manager.save_config(cfg)
        if ok:
            QMessageBox.information(self, "已保存", "配置已写入 ai_config.yaml")
        else:
            QMessageBox.critical(self, "保存失败", "写入配置失败，请检查路径")

    def _collect_characters(self) -> List[Dict[str, Any]]:
        chars: List[Dict[str, Any]] = []
        for idx in range(self.char_list.count()):
            text = self.char_list.item(idx).text()
            parts = [p.strip() for p in text.split("|")]
            while len(parts) < 5:
                parts.append("")
            name, role, persona, voice, fp_flag = parts[:5]
            if not name:
                continue
            chars.append({
                "char_id": name.lower().replace(" ", "_"),
                "char_name": name,
                "role": role,
                "persona_keywords": persona,
                "voice_model_id": voice,
                "is_first_person": fp_flag == "第一人称",
            })
        return chars

    def _collect_api(self, existing: Dict[str, Any]) -> Dict[str, Any]:
        data = existing.copy()
        for name, fields in self.api_fields.items():
            payload: Dict[str, Any] = {}
            api_key = fields.get("api_key")
            if isinstance(api_key, QLineEdit):
                payload["api_key"] = api_key.text().strip()
            primary = fields.get("primary_model")
            if isinstance(primary, QLineEdit):
                payload["primary_model"] = primary.text().strip()
            fallback = fields.get("fallback_model")
            if isinstance(fallback, QLineEdit):
                payload["fallback_model"] = fallback.text().strip()
            base_url = fields.get("base_url")
            if isinstance(base_url, QLineEdit):
                payload["base_url"] = base_url.text().strip()

            timeout_w = fields.get("timeout")
            if isinstance(timeout_w, QSpinBox):
                payload["timeout"] = int(timeout_w.value())

            for extra_key in [k for k in fields.keys() if k not in payload]:
                w = fields[extra_key]
                if isinstance(w, QLineEdit):
                    payload[extra_key] = w.text().strip()
                elif isinstance(w, QSpinBox):
                    payload[extra_key] = int(w.value())
            data[name] = payload
        return data

    def _validate_api_config(self):
        missing = []
        for name, fields in self.api_fields.items():
            key_w = fields.get("api_key")
            primary_w = fields.get("primary_model")
            key = key_w.text().strip() if isinstance(key_w, QLineEdit) else ""
            primary = primary_w.text().strip() if isinstance(primary_w, QLineEdit) else ""
            # 对剧情必须有claude或kimi，其余非空即认为配置完成
            if name in ["claude", "kimi"]:
                def _get_key(n: str) -> str:
                    w = (self.api_fields.get(n) or {}).get("api_key")
                    return w.text().strip() if isinstance(w, QLineEdit) else ""

                if not key and not any(_get_key(n) for n in ["claude", "kimi"]):
                    missing.append("需要配置 Claude 或 Kimi 的 Key")
            requires_primary = name not in ["gptsovits"]
            if key and requires_primary and not primary:
                missing.append(f"{name} 缺少主模型")
            if name in ["midjourney", "flux"] and key:
                w = fields.get("app_id", None)
                if not isinstance(w, QLineEdit) or not w.text().strip():
                    missing.append(f"{name} 需要 App ID")
            if name == "gptsovits" and key:
                w = fields.get("sign", None)
                if not isinstance(w, QLineEdit) or not w.text().strip():
                    missing.append("gptsovits 需要 sign")
            if name == "suno" and key:
                w = fields.get("token", None)
                if not isinstance(w, QLineEdit) or not w.text().strip():
                    missing.append("suno 需要 token (x-token)")
                w = fields.get("user_id", None)
                if not isinstance(w, QLineEdit) or not w.text().strip():
                    missing.append("suno 需要 user_id (x-userId)")
        if missing:
            QMessageBox.warning(self, "验证未通过", "\n".join(missing))
        else:
            QMessageBox.information(self, "验证通过", "配置看起来有效。请确保 Key 正确可用。")

    def _set_combo(self, combo: QComboBox, value: str):
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)


class APIConfigDialog(AIAssistDialog):
    """API 配置独立入口，复用 AIAssistDialog，默认切到 API 页。"""

    def __init__(self, config_manager: Optional[ConfigManager] = None, parent=None):
        super().__init__(config_manager=config_manager, parent=parent)
        self.setWindowTitle("API 配置")

        # 只保留“API 配置”页签，其余页签不展示（旧版入口的多页签对用户是干扰）。
        api_idx = -1
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i).strip() == "API 配置":
                api_idx = i
                break
        if api_idx >= 0:
            for i in reversed(range(self.tabs.count())):
                if i != api_idx:
                    self.tabs.removeTab(i)
            self.tabs.setCurrentIndex(0)
