# -*- coding: utf-8 -*-
"""
语音专项Agent界面
支持单条生成与批量自动生成
"""

import time
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QComboBox,
    QCheckBox,
    QDoubleSpinBox,
    QGroupBox,
    QWidget,
    QMessageBox,
    QLineEdit,
    QFormLayout,
    QGridLayout,
    QFileDialog,
    QDialog,
    QScrollArea,
    QSplitter,
)
from PyQt6.QtCore import Qt, pyqtSignal

import json
import yaml

from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.config_manager import ConfigManager
from src.ai.core.models import PendingLists, VoicePendingItem, TaskAssignment
from src.ai.api.api_manager import APIManager
from src.ai.agents.voice_agent import VoiceAgent
from src.designer.async_elapsed_runner import AsyncElapsedRunner
from src.ai.utils.voice_emotion import emotion_to_ext, normalize_ext, EXT_KEYS
from src.designer.voice_model_dialog import VoiceModelPickerDialog, get_gptsovits_client


class AIVoicePanel(QWidget):
    """语音生成专项界面"""

    modified = pyqtSignal()
    batch_item_progress = pyqtSignal(object, int, int)

    def __init__(self, project_manager: AIProjectManager, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.project_manager = project_manager
        self.config_manager = config_manager
        self.api_manager = APIManager(self.config_manager)
        self.pending_items: List[VoicePendingItem] = []
        self.current_item: Optional[VoicePendingItem] = None
        self.voice_agent: Optional[VoiceAgent] = None
        self._is_busy = False
        self._auto_running = False
        self._runner = AsyncElapsedRunner(self)
        self.batch_item_progress.connect(self._on_batch_item_progress)
        self.init_ui()

    def _on_batch_item_progress(self, result: object, done: int, total: int):
        """UI线程：应用单条批量结果，并刷新进度显示。"""

        try:
            self._runner.update_base_text(f"状态：批量生成中 {int(done)}/{int(total)}")
        except Exception:
            # runner 可能已清理
            pass

        if isinstance(result, dict):
            item = self._get_item_by_id(str(result.get("item_id", "")))
            if item and result.get("ok"):
                outputs = self._normalize_paths(result.get("output_files", []) or [])
                if outputs:
                    item.file_path = outputs[0]
                item.prompt = result.get("spoken_text") or item.prompt
                item.status = "generated"
                # 若当前选中项就是它，同步详情
                if self.current_item and self.current_item.item_id == item.item_id:
                    self.status_label.setText(item.status)
                    self.file_label.setText("文件：" + (item.file_path or ""))

        # 及时写回并刷新列表文本（不等批量结束）
        self._persist_pending_lists()
        self._refresh_list_texts()

    def init_ui(self):
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        self.project_label = QLabel("未加载AI工程")
        try:
            self.project_label.setProperty("pill", "true")
        except Exception:
            pass
        header.addWidget(self.project_label)
        self.reload_btn = QPushButton("刷新待生成列表")
        self.reload_btn.clicked.connect(self.refresh)
        header.addWidget(self.reload_btn)
        header.addStretch(1)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self.list_widget = QListWidget()
        self.list_widget.itemSelectionChanged.connect(self.on_item_selected)
        splitter.addWidget(self.list_widget)

        right_container = QWidget()
        right = QVBoxLayout(right_container)

        info_group = QGroupBox("语音详情")
        form = QFormLayout()
        self.node_label = QLabel("-")
        form.addRow("节点ID", self.node_label)
        self.speaker_label = QLabel("-")
        form.addRow("角色", self.speaker_label)
        self.emotion_label = QLabel("-")
        form.addRow("情绪", self.emotion_label)
        self.status_label = QLabel("-")
        form.addRow("状态", self.status_label)
        self.model_combo = QComboBox()
        self.model_combo.addItem("GPT-SoVITS", "gptsovits")
        self.model_combo.setEnabled(False)
        form.addRow("模型", self.model_combo)

        # 语音生成文本来源（原文/第二语言）
        self.voice_text_mode_combo = QComboBox()
        self.voice_text_mode_combo.addItem("应用原对白", "original")
        self.voice_text_mode_combo.addItem("应用第二语言", "second")
        self.voice_text_mode_combo.setToolTip("选择语音合成默认使用的对白文本来源；若第二语言为空将自动回退原文")
        self.voice_text_mode_combo.currentIndexChanged.connect(self._sync_voice_text_mode_to_project)
        form.addRow("对白来源", self.voice_text_mode_combo)
        self.tts_style_combo = QComboBox()
        self.tts_style_combo.addItem("1 普遍模型", "1")
        self.tts_style_combo.addItem("2 专业模型", "2")
        self.tts_style_combo.addItem("3 多语言模型", "3")
        form.addRow("TTS版本(style)", self.tts_style_combo)
        self.tts_genre_combo = QComboBox()
        self.tts_genre_combo.addItem("0 参考原音频", 0)
        self.tts_genre_combo.addItem("1 语气参考", 1)
        form.addRow("TTS类别(genre)", self.tts_genre_combo)
        self.use_emotion_ext_check = QCheckBox("根据情绪发送 ext")
        self.use_emotion_ext_check.setChecked(True)
        form.addRow("情绪参数", self.use_emotion_ext_check)
        self.emotion_strength_spin = QDoubleSpinBox()
        self.emotion_strength_spin.setRange(0.0, 1.0)
        self.emotion_strength_spin.setSingleStep(0.1)
        self.emotion_strength_spin.setValue(1.0)
        form.addRow("情绪强度(0-1)", self.emotion_strength_spin)

        # 逐条覆盖参数（可选）
        self.item_audio_id_edit = QLineEdit()
        self.item_audio_id_edit.setPlaceholderText("可选：覆盖 audioId（优先于角色音色模型ID）")
        audio_row = QHBoxLayout()
        audio_row.addWidget(self.item_audio_id_edit)
        self.item_audio_id_query_btn = QPushButton("查询")
        self.item_audio_id_query_btn.clicked.connect(self._query_item_audio_id)
        audio_row.addWidget(self.item_audio_id_query_btn)
        form.addRow("条目 audioId", audio_row)

        self.item_tts_style_combo = QComboBox()
        self.item_tts_style_combo.addItem("跟随全局", None)
        self.item_tts_style_combo.addItem("1 普遍模型", "1")
        self.item_tts_style_combo.addItem("2 专业模型", "2")
        self.item_tts_style_combo.addItem("3 多语言模型", "3")
        form.addRow("条目 style", self.item_tts_style_combo)

        self.item_tts_genre_combo = QComboBox()
        self.item_tts_genre_combo.addItem("跟随全局", None)
        self.item_tts_genre_combo.addItem("0 参考原音频", 0)
        self.item_tts_genre_combo.addItem("1 语气参考", 1)
        form.addRow("条目 genre", self.item_tts_genre_combo)

        self.item_use_emotion_ext_combo = QComboBox()
        self.item_use_emotion_ext_combo.addItem("跟随全局", None)
        self.item_use_emotion_ext_combo.addItem("是", True)
        self.item_use_emotion_ext_combo.addItem("否", False)
        form.addRow("条目 use_ext", self.item_use_emotion_ext_combo)

        self._item_ext_spins = {}
        ext_widget = QWidget()
        ext_grid = QGridLayout(ext_widget)
        ext_grid.setContentsMargins(0, 0, 0, 0)
        ext_grid.setHorizontalSpacing(10)
        ext_grid.setVerticalSpacing(6)

        labels = {
            "happy": "开心(happy)",
            "angry": "愤怒(angry)",
            "sad": "悲伤(sad)",
            "afraid": "害怕(afraid)",
            "disgusted": "厌恶(disgusted)",
            "melancholic": "忧郁(melancholic)",
            "surprised": "惊讶(surprised)",
            "calm": "平静(calm)",
        }
        for idx, k in enumerate(EXT_KEYS):
            row = idx // 2
            col = (idx % 2) * 2
            ext_grid.addWidget(QLabel(labels.get(k, k)), row, col)
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1.0)
            spin.setDecimals(1)
            spin.setSingleStep(0.1)
            spin.setValue(0.0)
            self._item_ext_spins[k] = spin
            ext_grid.addWidget(spin, row, col + 1)

        ext_btn_row = QHBoxLayout()
        self.item_ext_reset_btn = QPushButton("重置为情绪默认")
        self.item_ext_reset_btn.clicked.connect(self._reset_item_ext_by_emotion)
        self.item_ext_clear_btn = QPushButton("清除覆盖")
        self.item_ext_clear_btn.clicked.connect(self._clear_item_ext_override)
        ext_btn_row.addWidget(self.item_ext_reset_btn)
        ext_btn_row.addWidget(self.item_ext_clear_btn)
        ext_btn_row.addStretch(1)

        ext_box = QVBoxLayout()
        ext_box.setContentsMargins(0, 0, 0, 0)
        ext_box.addWidget(ext_widget)
        ext_box.addLayout(ext_btn_row)
        ext_container = QWidget()
        ext_container.setLayout(ext_box)
        form.addRow("条目 ext(0-1)", ext_container)

        self.save_item_params_btn = QPushButton("保存条目参数")
        self.save_item_params_btn.clicked.connect(self._save_item_params)
        form.addRow("", self.save_item_params_btn)

        info_group.setLayout(form)
        right.addWidget(info_group)

        preview_group = QGroupBox("对白预览")
        preview_layout = QVBoxLayout()
        self.text_preview = QTextEdit()
        self.text_preview.setReadOnly(True)
        self.text_preview.setPlaceholderText("原对白预览")
        self.text_preview.setFixedHeight(80)
        preview_layout.addWidget(self.text_preview)

        self.second_text_preview = QTextEdit()
        self.second_text_preview.setReadOnly(True)
        self.second_text_preview.setPlaceholderText("第二语言预览（为空表示尚未翻译/未填写）")
        self.second_text_preview.setFixedHeight(80)
        preview_layout.addWidget(self.second_text_preview)
        preview_group.setLayout(preview_layout)
        right.addWidget(preview_group)

        prompt_group = QGroupBox("提示词/文本")
        prompt_layout = QVBoxLayout()
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("自动填充对白，可修改后生成")
        self.prompt_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        prompt_layout.addWidget(self.prompt_edit)
        btn_row = QHBoxLayout()
        self.fill_prompt_btn = QPushButton("填充默认文本")
        self.fill_prompt_btn.clicked.connect(self._fill_prompt)
        self.save_prompt_btn = QPushButton("保存指令")
        self.save_prompt_btn.clicked.connect(self._save_prompt_only)
        btn_row.addWidget(self.fill_prompt_btn)
        btn_row.addWidget(self.save_prompt_btn)
        btn_row.addStretch(1)
        prompt_layout.addLayout(btn_row)
        prompt_group.setLayout(prompt_layout)
        right.addWidget(prompt_group)

        # ==================== 批量翻译（第二语言） ====================
        translate_group = QGroupBox("批量翻译为第二语言（LLM）")
        translate_layout = QVBoxLayout()

        tl_form = QFormLayout()
        self.voice_translate_target_edit = QLineEdit()
        self.voice_translate_target_edit.setPlaceholderText("如：英语 / 日语 / 韩语 / 西班牙语...")
        tl_form.addRow("目标语言", self.voice_translate_target_edit)

        self.voice_translate_instruction_edit = QTextEdit()
        self.voice_translate_instruction_edit.setPlaceholderText("生成指令后可手动微调")
        self.voice_translate_instruction_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.voice_translate_instruction_edit.setFixedHeight(120)
        tl_form.addRow("指令", self.voice_translate_instruction_edit)

        self.voice_translate_result_edit = QTextEdit()
        self.voice_translate_result_edit.setPlaceholderText("LLM 返回结果会显示在这里；可手动修改后保存/应用")
        self.voice_translate_result_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.voice_translate_result_edit.setFixedHeight(140)
        tl_form.addRow("结果", self.voice_translate_result_edit)

        translate_layout.addLayout(tl_form)

        tl_btn_row = QHBoxLayout()
        self.voice_translate_build_btn = QPushButton("生成指令")
        self.voice_translate_build_btn.clicked.connect(self._build_voice_translate_instruction)
        self.voice_translate_call_btn = QPushButton("调用LLM翻译")
        self.voice_translate_call_btn.clicked.connect(self._call_llm_translate_voices)
        self.voice_translate_stop_btn = QPushButton("强制停止")
        self.voice_translate_stop_btn.clicked.connect(self._force_stop_task)
        self.voice_translate_save_btn = QPushButton("保存结果")
        self.voice_translate_save_btn.clicked.connect(self._save_voice_translate_fields)
        self.voice_translate_apply_btn = QPushButton("应用到第二语言")
        self.voice_translate_apply_btn.clicked.connect(self._apply_voice_translate_result)
        tl_btn_row.addWidget(self.voice_translate_build_btn)
        tl_btn_row.addWidget(self.voice_translate_call_btn)
        tl_btn_row.addWidget(self.voice_translate_stop_btn)
        tl_btn_row.addWidget(self.voice_translate_save_btn)
        tl_btn_row.addWidget(self.voice_translate_apply_btn)
        tl_btn_row.addStretch(1)
        translate_layout.addLayout(tl_btn_row)

        translate_group.setLayout(translate_layout)
        right.addWidget(translate_group)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_btn = QPushButton("选择保存路径")
        self.path_btn.clicked.connect(self._choose_path)
        path_row.addWidget(self.path_edit)
        path_row.addWidget(self.path_btn)
        right.addLayout(path_row)

        action_row = QHBoxLayout()
        self.generate_btn = QPushButton("生成当前语音")
        self.generate_btn.clicked.connect(self._generate_single)
        self.force_stop_btn = QPushButton("强制停止")
        self.force_stop_btn.clicked.connect(self._force_stop_task)
        self.mark_btn = QPushButton("标记完成")
        self.mark_btn.clicked.connect(self.mark_generated)
        self.reset_btn = QPushButton("重置待生成")
        self.reset_btn.clicked.connect(self.reset_status)
        action_row.addWidget(self.generate_btn)
        action_row.addWidget(self.force_stop_btn)
        action_row.addWidget(self.mark_btn)
        action_row.addWidget(self.reset_btn)
        action_row.addStretch(1)
        right.addLayout(action_row)

        auto_group = QGroupBox("自动生成模式")
        auto_layout = QHBoxLayout()
        self.start_auto_btn = QPushButton("开始批量生成")
        self.start_auto_btn.clicked.connect(self._start_auto)
        self.stop_auto_btn = QPushButton("停止")
        self.stop_auto_btn.clicked.connect(self._stop_auto)
        auto_layout.addWidget(self.start_auto_btn)
        auto_layout.addWidget(self.stop_auto_btn)
        auto_layout.addStretch(1)
        auto_group.setLayout(auto_layout)
        right.addWidget(auto_group)

        self.file_label = QLabel("文件：")
        self.file_label.setWordWrap(True)
        right.addWidget(self.file_label)
        self.progress_label = QLabel("状态：等待选择")
        right.addWidget(self.progress_label)
        right.addStretch(1)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setWidget(right_container)
        splitter.addWidget(right_scroll)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)

        # 语音TTS设置：变更时自动写回 story_config，便于 .vnai 持久化。
        self.tts_style_combo.currentIndexChanged.connect(self._sync_voice_tts_settings_to_project)
        self.tts_genre_combo.currentIndexChanged.connect(self._sync_voice_tts_settings_to_project)
        self.use_emotion_ext_check.stateChanged.connect(self._sync_voice_tts_settings_to_project)
        self.emotion_strength_spin.valueChanged.connect(self._sync_voice_tts_settings_to_project)

    def _force_stop_task(self):
        # 批量模式优先用“停止”逻辑（避免后台循环继续排队）
        try:
            if getattr(self, "_auto_running", False):
                self._stop_auto()
        except Exception:
            pass

        if self._runner.force_stop(stopped_text="状态：已强制停止"):
            return
        QMessageBox.information(self, "提示", "当前没有正在执行的任务。")

    # ==================== 列表与显示 ====================
    def refresh(self):
        project = self.project_manager.current_project
        if project is None:
            self.project_label.setText("未加载AI工程")
            self.pending_items = []
            self.list_widget.clear()
            self._clear_detail()
            return

        # 从工程 story_config 恢复语音TTS设置
        try:
            cfg = project.story_config
            self.tts_style_combo.blockSignals(True)
            self.tts_genre_combo.blockSignals(True)
            self.use_emotion_ext_check.blockSignals(True)
            self.emotion_strength_spin.blockSignals(True)

            style_val = str(getattr(cfg, "voice_tts_style", "2") or "2")
            style_idx = self.tts_style_combo.findData(style_val)
            if style_idx >= 0:
                self.tts_style_combo.setCurrentIndex(style_idx)

            genre_val = int(getattr(cfg, "voice_tts_genre", 1) if getattr(cfg, "voice_tts_genre", None) is not None else 1)
            genre_idx = self.tts_genre_combo.findData(genre_val)
            if genre_idx >= 0:
                self.tts_genre_combo.setCurrentIndex(genre_idx)

            self.use_emotion_ext_check.setChecked(bool(getattr(cfg, "voice_use_emotion_ext", True)))

            strength_val = float(getattr(cfg, "voice_emotion_strength", 1.0) or 1.0)
            if strength_val < 0.0:
                strength_val = 0.0
            if strength_val > 1.0:
                strength_val = 1.0
            self.emotion_strength_spin.setValue(strength_val)
        finally:
            self.tts_style_combo.blockSignals(False)
            self.tts_genre_combo.blockSignals(False)
            self.use_emotion_ext_check.blockSignals(False)
            self.emotion_strength_spin.blockSignals(False)

        self.project_label.setText(f"工程：{project.ai_project_info.name}")
        pending_lists: PendingLists = project.pending_lists or PendingLists()

        # 恢复语音文本来源与翻译面板输入/结果
        try:
            self.voice_text_mode_combo.blockSignals(True)
            mode = getattr(pending_lists, "voice_text_mode", "original") or "original"
            idx = self.voice_text_mode_combo.findData(mode)
            if idx >= 0:
                self.voice_text_mode_combo.setCurrentIndex(idx)
        finally:
            self.voice_text_mode_combo.blockSignals(False)

        try:
            self.voice_translate_target_edit.setText(getattr(pending_lists, "voice_translation_target_language", "") or "")
            self.voice_translate_instruction_edit.setPlainText(getattr(pending_lists, "voice_translation_instruction", "") or "")
            self.voice_translate_result_edit.setPlainText(getattr(pending_lists, "voice_translation_result", "") or "")
        except Exception:
            pass

        self.pending_items = list(pending_lists.voices or [])
        self._populate_list()
        if self.pending_items:
            self.list_widget.setCurrentRow(0)
        else:
            self._clear_detail()
            self.progress_label.setText("状态：无待生成语音")

    def _populate_list(self):
        self.list_widget.clear()
        for item in self.pending_items:
            eff_style, eff_genre = self._effective_tts_style_genre(item)
            style_part = f"style={eff_style}" if eff_style else "style=?"
            genre_part = f"genre={eff_genre}" if eff_genre is not None else "genre=?"
            text = f"{item.node_id} | {item.speaker} | {item.emotion} | {item.status} | {style_part} {genre_part}"
            lw = QListWidgetItem(text)
            lw.setData(Qt.ItemDataRole.UserRole, item.item_id)
            tip = f"原对白：{item.text}"
            if getattr(item, "second_text", None):
                tip += f"\n第二语言：{item.second_text}"
            lw.setToolTip(tip)
            self.list_widget.addItem(lw)

    def on_item_selected(self):
        current = self.list_widget.currentItem()
        if not current:
            self._clear_detail()
            return

        item_id = current.data(Qt.ItemDataRole.UserRole)
        item = self._get_item_by_id(item_id)
        self.current_item = item
        if item:
            self._show_item(item)

    def _get_item_by_id(self, item_id: str) -> Optional[VoicePendingItem]:
        for it in self.pending_items:
            if it.item_id == item_id:
                return it
        return None

    def _show_item(self, item: VoicePendingItem):
        self.node_label.setText(str(item.node_id))
        self.speaker_label.setText(f"{item.speaker} ({item.char_id})")
        self.emotion_label.setText(item.emotion)
        self.status_label.setText(item.status)
        self.text_preview.setPlainText(item.text)
        if hasattr(self, "second_text_preview"):
            self.second_text_preview.setPlainText(getattr(item, "second_text", "") or "")
        prompt_text = self._display_prompt_text(item)
        self.prompt_edit.setPlainText(prompt_text)
        self.path_edit.setText(self._resource_path(item.file_path or f"resources/voices/{item.char_id}/{item.voice_id}.mp3").as_posix())
        self.file_label.setText(f"文件：{item.file_path or '待生成'}")

        # 逐条覆盖参数显示
        self.item_audio_id_edit.setText(item.audio_id or "")
        style_idx = self.item_tts_style_combo.findData(item.tts_style)
        self.item_tts_style_combo.setCurrentIndex(style_idx if style_idx >= 0 else 0)
        genre_idx = self.item_tts_genre_combo.findData(item.tts_genre)
        self.item_tts_genre_combo.setCurrentIndex(genre_idx if genre_idx >= 0 else 0)
        use_idx = self.item_use_emotion_ext_combo.findData(item.use_emotion_ext)
        self.item_use_emotion_ext_combo.setCurrentIndex(use_idx if use_idx >= 0 else 0)
        if isinstance(item.tts_ext, dict) and item.tts_ext:
            self._set_item_ext_controls(item.tts_ext)
        else:
            # 未覆盖时展示“按情绪推导”的默认值（不落盘，需点保存）。
            self._set_item_ext_controls(emotion_to_ext(item.emotion))

        self.progress_label.setText("状态：就绪")

    def _clear_detail(self):
        self.current_item = None
        self.node_label.setText("-")
        self.speaker_label.setText("-")
        self.emotion_label.setText("-")
        self.status_label.setText("-")
        self.text_preview.clear()
        self.prompt_edit.clear()
        self.path_edit.clear()
        self.file_label.setText("文件：")
        self.progress_label.setText("状态：等待选择")

        self.item_audio_id_edit.clear()
        self.item_tts_style_combo.setCurrentIndex(0)
        self.item_tts_genre_combo.setCurrentIndex(0)
        self.item_use_emotion_ext_combo.setCurrentIndex(0)
        self._set_item_ext_controls(None)

    def _effective_tts_style_genre(self, item: VoicePendingItem):
        """返回条目实际生效的 style/genre（优先条目覆盖，其次全局 story_config）。"""
        project = self.project_manager.current_project
        cfg = project.story_config if project else None
        style = item.tts_style or (str(getattr(cfg, "voice_tts_style", "2") or "2") if cfg else "2")
        genre = item.tts_genre
        if genre is None:
            try:
                genre = int(getattr(cfg, "voice_tts_genre", 1) if cfg else 1)
            except Exception:
                genre = 1
        return style, genre

    def _set_item_ext_controls(self, ext: dict | None):
        if not self._item_ext_spins:
            return

        if ext is None:
            for k in EXT_KEYS:
                self._item_ext_spins[k].setValue(0.0)
            return

        normalized = normalize_ext(ext)
        for k in EXT_KEYS:
            try:
                self._item_ext_spins[k].setValue(round(float(normalized.get(k, 0.0)), 1))
            except Exception:
                self._item_ext_spins[k].setValue(0.0)

    def _item_ext_controls_to_sparse(self) -> dict | None:
        if not self._item_ext_spins:
            return None

        vals = {k: round(float(self._item_ext_spins[k].value()), 1) for k in EXT_KEYS}
        if all(abs(v) < 1e-9 for v in vals.values()):
            return None
        # 稀疏存储，减少 .vnai 冗余
        return {k: v for k, v in vals.items() if abs(v) >= 1e-9}

    def _reset_item_ext_by_emotion(self):
        if not self.current_item:
            return
        self._set_item_ext_controls(emotion_to_ext(self.current_item.emotion))

    def _clear_item_ext_override(self):
        self._set_item_ext_controls(None)

    def _query_item_audio_id(self):
        client = get_gptsovits_client(self.config_manager, self)
        if not client:
            return
        dlg = VoiceModelPickerDialog(client, self, allow_manage=False)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            audio_id = dlg.selected_audio_id() or ""
            self.item_audio_id_edit.setText(audio_id)

    def _save_item_params(self):
        if not self.current_item:
            return
        try:
            audio_id = self.item_audio_id_edit.text().strip() or None
            style = self.item_tts_style_combo.currentData()
            genre = self.item_tts_genre_combo.currentData()
            use_emotion_ext = self.item_use_emotion_ext_combo.currentData()
            ext = self._item_ext_controls_to_sparse()

            self.current_item.audio_id = audio_id
            self.current_item.tts_style = str(style) if style is not None else None
            self.current_item.tts_genre = int(genre) if genre is not None else None
            self.current_item.use_emotion_ext = bool(use_emotion_ext) if use_emotion_ext is not None else None
            self.current_item.tts_ext = ext

            self._persist_pending_lists()
            self._refresh_list_texts()
            self.progress_label.setText("状态：条目参数已保存")
        except Exception as exc:
            QMessageBox.warning(self, "提示", f"保存条目参数失败: {exc}")

    # ==================== 工具 ====================
    def _default_prompt(self, item: VoicePendingItem) -> str:
        # 这里的“提示词/文本”就是要合成的对白文本，不要把情绪标签拼进内容里。
        # 根据全局选择：优先 second_text（为空则回退 text）。
        mode = self._get_voice_text_mode()
        if mode == "second":
            txt2 = (getattr(item, "second_text", None) or "").strip()
            if txt2:
                return txt2
        return item.text or ""

    def _is_custom_prompt(self, item: VoicePendingItem) -> bool:
        """判定条目 prompt 是否是用户手动定制过的文本。

        规则：若 prompt 为空 => 非自定义；若 prompt 等于原文或等于 second_text => 视为“自动默认”，可随全局切换。
        只有当 prompt 与两者都不相等时，认为是自定义。
        """
        p = (item.prompt or "").strip()
        if not p:
            return False
        if p == (item.text or "").strip():
            return False
        if p == (getattr(item, "second_text", None) or "").strip():
            return False
        return True

    def _display_prompt_text(self, item: VoicePendingItem) -> str:
        if self._is_custom_prompt(item):
            return item.prompt or ""
        return self._default_prompt(item)

    def _spoken_text_for_generation(self, item: VoicePendingItem) -> str:
        """批量生成使用的 spoken_text：自定义 prompt 优先，否则随全局对白来源。"""
        if self._is_custom_prompt(item):
            return (item.prompt or "").strip()
        return self._default_prompt(item).strip()

    def _get_voice_text_mode(self) -> str:
        project = self.project_manager.current_project
        if not project or not project.pending_lists:
            return "original"
        mode = getattr(project.pending_lists, "voice_text_mode", "original") or "original"
        return "second" if str(mode).strip().lower() == "second" else "original"

    def _sync_voice_text_mode_to_project(self):
        project = self.project_manager.current_project
        if not project:
            return
        if project.pending_lists is None:
            project.pending_lists = PendingLists()
        mode = self.voice_text_mode_combo.currentData() or "original"
        project.pending_lists.voice_text_mode = "second" if str(mode).strip().lower() == "second" else "original"
        self.project_manager.update_pending_lists(project.pending_lists)
        self.modified.emit()
        # 切换后刷新当前详情的默认文本/预览
        if self.current_item:
            self._show_item(self.current_item)

    def _ensure_project(self) -> bool:
        if self.project_manager.current_project is None:
            QMessageBox.warning(self, "提示", "请先创建或打开AI工程。")
            return False
        return True

    def _ensure_agent(self) -> bool:
        if self.voice_agent:
            return True
        try:
            self.voice_agent = VoiceAgent(self.config_manager)
            return True
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"初始化语音Agent失败: {exc}")
            return False

    def _project_root(self) -> Path:
        project = self.project_manager.current_project
        if project is None:
            return Path.cwd() / "output" / "ai_project"

        if project.ai_project_info.vng_project_path:
            return Path(project.ai_project_info.vng_project_path).expanduser().resolve().parent

        if self.project_manager.current_file_path:
            return (
                Path(self.project_manager.current_file_path)
                .expanduser()
                .resolve()
                .parent
                / project.ai_project_info.name
            )

        return Path.cwd() / "output" / (project.ai_project_info.name or "ai_project")

    def _resource_path(self, rel_path: str) -> Path:
        p = Path(rel_path)
        return p.expanduser().resolve() if p.is_absolute() else (self._project_root() / p).expanduser().resolve()

    def _abs_path(self, path_str: str) -> Path:
        p = Path(path_str)
        return p if p.is_absolute() else (self._project_root() / p).resolve()

    def _normalize_paths(self, paths: List[str]) -> List[str]:
        root = self._project_root()
        normalized = []
        for p in paths:
            try:
                rel = self._abs_path(p).relative_to(root).as_posix()
                normalized.append(rel)
            except Exception:
                normalized.append(Path(p).as_posix())
        return normalized

    # ==================== 单条生成 ====================
    def _fill_prompt(self):
        if not self.current_item:
            return
        self.prompt_edit.setPlainText(self._default_prompt(self.current_item))

    def _choose_path(self):
        default_dir = self._project_root() / "resources" / "voices" / (self.current_item.char_id if self.current_item else "voice")
        default_dir.mkdir(parents=True, exist_ok=True)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存语音",
            str(default_dir / f"{(self.current_item.voice_id if self.current_item else 'voice')}.mp3"),
            "音频文件 (*.mp3)",
        )
        if file_path:
            self.path_edit.setText(file_path)

    def _save_prompt_only(self):
        if not self.current_item:
            return
        text = self.prompt_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "提示词为空，无法保存。")
            return
        self.current_item.prompt = text
        self._persist_pending_lists()
        self.progress_label.setText("状态：指令已保存")

    def _generate_single(self):
        if self._is_busy or not self._ensure_project() or not self.current_item or not self._ensure_agent():
            return
        self._sync_voice_tts_settings_to_project()
        spoken_text = self.prompt_edit.toPlainText().strip() or self._default_prompt(self.current_item)
        save_path = self.path_edit.text().strip()
        if not save_path:
            self._choose_path()
            save_path = self.path_edit.text().strip()
        if not save_path:
            QMessageBox.warning(self, "提示", "请先选择保存路径。")
            return

        # 条目覆盖优先于全局
        effective_style = self.current_item.tts_style or str(self.tts_style_combo.currentData() or "2")
        effective_genre = self.current_item.tts_genre
        if effective_genre is None:
            effective_genre = int(self.tts_genre_combo.currentData() if self.tts_genre_combo.currentData() is not None else 1)
        effective_use_ext = self.current_item.use_emotion_ext
        if effective_use_ext is None:
            effective_use_ext = bool(self.use_emotion_ext_check.isChecked())

        params = {
            "voice_id": self.current_item.voice_id,
            "node_id": self.current_item.node_id,
            "sub_id": self.current_item.sub_id,
            "speaker": self.current_item.speaker,
            "char_id": self.current_item.char_id,
            "text": spoken_text,
            "emotion": self.current_item.emotion,
            "voice_model_id": self.current_item.voice_model_id,
            "audio_id": self.current_item.audio_id,
            "tts_style": str(effective_style),
            "tts_genre": int(effective_genre),
            "tts_ext": self.current_item.tts_ext,
            "use_emotion_ext": bool(effective_use_ext),
            "emotion_strength": float(self.emotion_strength_spin.value()),
            "output_path": save_path,
            "project_root": str(self._project_root()),
        }
        task = TaskAssignment(
            task_id=f"voice-{int(time.time()*1000)}",
            agent_type="voice",
            task_type="generate_voice_item",
            task_content=f"生成语音 {self.current_item.voice_id}",
            parameters=params,
        )

        self._is_busy = True
        self.generate_btn.setEnabled(False)

        def _do_work():
            return self.voice_agent.execute(task)

        def _on_success(resp):
            if resp.status != "success":
                QMessageBox.critical(self, "生成失败", resp.error_message or "生成失败")
                self.progress_label.setText("状态：生成失败")
                return

            outputs = self._normalize_paths(resp.output_files or [])
            if outputs:
                self.current_item.file_path = outputs[0]
            self.current_item.prompt = spoken_text
            self.current_item.status = "generated"
            self.file_label.setText("文件：" + (self.current_item.file_path or ""))
            self._persist_pending_lists()
            self._refresh_list_texts()
            self.status_label.setText(self.current_item.status)
            self.progress_label.setText("状态：生成完成")

        def _on_finally():
            self._is_busy = False
            self.generate_btn.setEnabled(True)

        started = self._runner.run(
            label=self.progress_label,
            base_text="状态：生成中...",
            fn=_do_work,
            on_success=_on_success,
            on_finally=_on_finally,
        )
        if not started:
            self._is_busy = False
            self.generate_btn.setEnabled(True)
            QMessageBox.information(self, "提示", "已有任务在运行，请稍候。")

    # ==================== 批量生成 ====================
    def _start_auto(self):
        if self._is_busy or not self._ensure_project() or not self._ensure_agent():
            return
        self._sync_voice_tts_settings_to_project()
        pending = [it for it in self.pending_items if it.status == "pending"]
        if not pending:
            QMessageBox.information(self, "提示", "没有待生成的语音。")
            return

        total = len(pending)
        default_style = str(self.tts_style_combo.currentData() or "2")
        default_genre = int(self.tts_genre_combo.currentData() if self.tts_genre_combo.currentData() is not None else 1)
        default_use_emotion_ext = bool(self.use_emotion_ext_check.isChecked())
        emotion_strength = float(self.emotion_strength_spin.value())
        project_root = str(self._project_root())

        self._auto_running = True
        self._is_busy = True
        self.start_auto_btn.setEnabled(False)
        self.generate_btn.setEnabled(False)

        def _do_work():
            done = 0
            results = []
            for item in pending:
                if not self._auto_running:
                    break
                spoken_text = self._spoken_text_for_generation(item)

                # 条目覆盖优先
                style = item.tts_style or default_style
                genre = item.tts_genre if item.tts_genre is not None else default_genre
                use_ext = item.use_emotion_ext if item.use_emotion_ext is not None else default_use_emotion_ext

                params = {
                    "voice_id": item.voice_id,
                    "node_id": item.node_id,
                    "sub_id": item.sub_id,
                    "speaker": item.speaker,
                    "char_id": item.char_id,
                    "text": spoken_text,
                    "emotion": item.emotion,
                    "voice_model_id": item.voice_model_id,
                    "audio_id": item.audio_id,
                    "tts_style": style,
                    "tts_genre": genre,
                    "tts_ext": item.tts_ext,
                    "use_emotion_ext": use_ext,
                    "emotion_strength": emotion_strength,
                    "output_path": self._resource_path(
                        item.file_path or f"resources/voices/{item.char_id}/{item.voice_id}.mp3"
                    ).as_posix(),
                    "project_root": project_root,
                }
                task = TaskAssignment(
                    task_id=f"voice-batch-{int(time.time()*1000)}",
                    agent_type="voice",
                    task_type="generate_voice_item",
                    task_content=f"批量语音 {item.voice_id}",
                    parameters=params,
                )
                try:
                    resp = self.voice_agent.execute(task)
                    if resp.status == "success":
                        done += 1
                        r = {
                            "item_id": item.item_id,
                            "ok": True,
                            "spoken_text": spoken_text,
                            "output_files": list(resp.output_files or []),
                        }
                        results.append(r)
                        self.batch_item_progress.emit(r, done, total)
                    else:
                        r = {
                            "item_id": item.item_id,
                            "ok": False,
                            "spoken_text": spoken_text,
                            "error": resp.error_message or "生成失败",
                        }
                        results.append(r)
                        self.batch_item_progress.emit(r, done, total)
                except Exception as exc:  # noqa: BLE001
                    r = {
                        "item_id": item.item_id,
                        "ok": False,
                        "spoken_text": spoken_text,
                        "error": str(exc),
                    }
                    results.append(r)
                    self.batch_item_progress.emit(r, done, total)
            return {"done": done, "total": total, "results": results, "stopped": (not self._auto_running)}

        def _on_success(payload):
            done = int(payload.get("done", 0))
            total_local = int(payload.get("total", total))
            self.progress_label.setText(f"状态：批量完成 {done}/{total_local}")

        def _on_finally():
            self._auto_running = False
            self._is_busy = False
            self.start_auto_btn.setEnabled(True)
            self.generate_btn.setEnabled(True)

        started = self._runner.run(
            label=self.progress_label,
            base_text=f"状态：批量生成中 0/{total}",
            fn=_do_work,
            on_success=_on_success,
            on_finally=_on_finally,
        )
        if not started:
            self._auto_running = False
            self._is_busy = False
            self.start_auto_btn.setEnabled(True)
            self.generate_btn.setEnabled(True)
            QMessageBox.information(self, "提示", "已有任务在运行，请稍候。")

    def _sync_voice_tts_settings_to_project(self):
        """把语音TTS设置写回 story_config，便于 .vnai 持久化。"""
        project = self.project_manager.current_project
        if not project:
            return
        try:
            cfg = project.story_config
            cfg.voice_tts_style = str(self.tts_style_combo.currentData() or getattr(cfg, "voice_tts_style", "2") or "2")
            current_genre = self.tts_genre_combo.currentData()
            cfg.voice_tts_genre = int(current_genre if current_genre is not None else getattr(cfg, "voice_tts_genre", 1) or 1)
            cfg.voice_use_emotion_ext = bool(self.use_emotion_ext_check.isChecked())
            cfg.voice_emotion_strength = float(self.emotion_strength_spin.value())
            self.project_manager.update_story_config(cfg)
        except Exception:
            # UI 不应因写回失败而报错阻塞
            return

    def _stop_auto(self):
        self._auto_running = False
        if self._is_busy:
            self.progress_label.setText("状态：停止中，等待当前任务结束")

    def _select_item(self, item: VoicePendingItem):
        for i in range(self.list_widget.count()):
            lw = self.list_widget.item(i)
            if lw.data(Qt.ItemDataRole.UserRole) == item.item_id:
                self.list_widget.setCurrentRow(i)
                break

    # ==================== 标记与保存 ====================
    def mark_generated(self):
        if not self.current_item:
            return
        self.current_item.status = "generated"
        self._persist_pending_lists()
        self._refresh_list_texts()
        self.status_label.setText(self.current_item.status)
        self.progress_label.setText("状态：已标记完成")

    def reset_status(self):
        if not self.current_item:
            return
        self.current_item.status = "pending"
        self._persist_pending_lists()
        self._refresh_list_texts()
        self.status_label.setText(self.current_item.status)
        self.progress_label.setText("状态：已重置")

    def _persist_pending_lists(self):
        project = self.project_manager.current_project
        if project is None:
            return
        if project.pending_lists is None:
            project.pending_lists = PendingLists()

        project.pending_lists.voices = self.pending_items
        # 同步语音文本来源与翻译字段（避免只保存 voices 时丢失）
        try:
            mode = self.voice_text_mode_combo.currentData() if hasattr(self, "voice_text_mode_combo") else None
            project.pending_lists.voice_text_mode = "second" if str(mode).strip().lower() == "second" else "original"
            project.pending_lists.voice_translation_target_language = self.voice_translate_target_edit.text().strip()
            project.pending_lists.voice_translation_instruction = self.voice_translate_instruction_edit.toPlainText()
            project.pending_lists.voice_translation_result = self.voice_translate_result_edit.toPlainText()
        except Exception:
            pass

        self.project_manager.update_pending_lists(project.pending_lists)
        self.modified.emit()

    # ==================== 批量翻译（LLM） ====================

    def _build_voice_translate_instruction(self):
        if not self._ensure_project():
            return
        target = self.voice_translate_target_edit.text().strip()
        if not target:
            QMessageBox.warning(self, "提示", "请先填写目标语言。")
            return

        # 仅打包翻译所需最小字段，避免 token 爆炸。
        items = []
        for it in self.pending_items:
            items.append(
                {
                    "item_id": it.item_id,
                    "speaker": it.speaker,
                    "emotion": it.emotion,
                    "text": it.text,
                }
            )

        payload = json.dumps({"voices": items}, ensure_ascii=False, indent=2)

        instruction = f"""你是资深 Galgame 本地化翻译与对白润色专家。

任务：把下面 voices 列表中每条对白的 text 翻译为【{target}】，并把翻译写入 second_text 字段。

关键要求（必须遵守）：
1) 保持 Galgame 对白风格：自然口语、符合情绪（emotion），保留停顿/省略号/感叹号等语气，不一定需要逐字直译，可适当意译以符合目标语言习惯。
2) 不要翻译 speaker（角色名），不要改动 item_id。
3) 输出必须严格为 JSON（只输出 JSON，不要解释），结构如下：
   {{
     "voices": [
       {{"item_id": "voice_item_00001", "second_text": "..."}}
     ]
   }}
4) voices 数量必须与输入一致，且顺序保持一致。
5) 若原文包含称呼/人名/专有名词：优先使用目标语言常见译法；如不确定请音译但保持一致。

输入 voices：
{payload}
"""

        self.voice_translate_instruction_edit.setPlainText(instruction)
        self._save_voice_translate_fields(silent=True)

    def _get_llm_client(self):
        try:
            return self.api_manager.get_llm_client(prefer_claude=True)
        except Exception:
            return None

    def _extract_llm_text(self, response: dict) -> str:
        content = (response or {}).get("content", "")
        if isinstance(content, list):
            parts = []
            for blk in content:
                if isinstance(blk, dict) and isinstance(blk.get("text"), str):
                    parts.append(blk.get("text"))
            return "".join(parts)
        if isinstance(content, str):
            return content
        try:
            return json.dumps(content, ensure_ascii=False)
        except Exception:
            return str(content)

    def _call_llm_translate_voices(self):
        if self._is_busy or not self._ensure_project():
            return
        prompt = self.voice_translate_instruction_edit.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "提示", "请先生成/填写指令。")
            return

        client = self._get_llm_client()
        if not client:
            QMessageBox.warning(self, "提示", "未配置可用的 LLM（Claude/Kimi）。请先在 API 配置中设置。")
            return

        self._is_busy = True
        self.voice_translate_call_btn.setEnabled(False)

        def _do_work():
            resp = client.create_message(
                messages=[{"role": "user", "content": prompt}],
                system="你只输出严格 JSON。",
                temperature=0.2,
                max_tokens=32000,
            )
            return resp

        def _on_success(resp):
            text = self._extract_llm_text(resp if isinstance(resp, dict) else {})
            self.voice_translate_result_edit.setPlainText(text)
            self._save_voice_translate_fields(silent=True)
            self.progress_label.setText("状态：翻译结果已返回")

        def _on_finally():
            self._is_busy = False
            self.voice_translate_call_btn.setEnabled(True)

        started = self._runner.run(
            label=self.progress_label,
            base_text="状态：翻译中...",
            fn=_do_work,
            on_success=_on_success,
            on_finally=_on_finally,
        )
        if not started:
            self._is_busy = False
            self.voice_translate_call_btn.setEnabled(True)
            QMessageBox.information(self, "提示", "已有任务在运行，请稍候。")

    def _strip_code_fence(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        s = text.strip()
        if "```" not in s:
            return s
        # 尽量取第一个 fenced block 的内容
        try:
            _, after = s.split("```", 1)
            payload, _ = after.split("```", 1)
            # 去掉可能的语言标识行
            first, sep, rest = payload.lstrip().partition("\n")
            if first.strip().lower() in {"json", "yaml", "yml"}:
                return rest.strip()
            return payload.strip()
        except Exception:
            return s

    def _parse_translate_result(self, text: str):
        raw = self._strip_code_fence(text)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            try:
                return yaml.safe_load(raw)
            except Exception:
                return None

    def _apply_voice_translate_result(self):
        if not self._ensure_project():
            return
        parsed = self._parse_translate_result(self.voice_translate_result_edit.toPlainText())
        if parsed is None:
            QMessageBox.warning(self, "提示", "结果无法解析为 JSON/YAML。请确保输出是结构化 voices 列表。")
            return

        voices = None
        if isinstance(parsed, dict):
            if isinstance(parsed.get("voices"), list):
                voices = parsed.get("voices")
            elif isinstance(parsed.get("pending_lists"), dict) and isinstance((parsed.get("pending_lists") or {}).get("voices"), list):
                voices = (parsed.get("pending_lists") or {}).get("voices")
        elif isinstance(parsed, list):
            voices = parsed

        if not isinstance(voices, list):
            QMessageBox.warning(self, "提示", "未找到 voices 列表。期望形如 {\"voices\": [...]}。")
            return

        key_candidates = ["second_text", "text_second", "text2", "translated", "translation", "second_language"]
        mapping = {}
        for v in voices:
            if not isinstance(v, dict):
                continue
            item_id = str(v.get("item_id") or "").strip()
            if not item_id:
                continue
            val = None
            for k in key_candidates:
                if v.get(k) is not None:
                    val = v.get(k)
                    break
            if isinstance(val, str):
                mapping[item_id] = val

        if not mapping:
            QMessageBox.warning(self, "提示", "未从结果中提取到 second_text。请确认每条包含 item_id + second_text 字段。")
            return

        applied = 0
        for it in self.pending_items:
            if it.item_id in mapping:
                it.second_text = mapping[it.item_id]
                applied += 1

        self._persist_pending_lists()
        self._refresh_list_texts()
        if self.current_item:
            self._show_item(self.current_item)
        self.progress_label.setText(f"状态：已回填第二语言 {applied}/{len(self.pending_items)}")

    def _save_voice_translate_fields(self, silent: bool = False):
        if not self._ensure_project():
            return
        self._persist_pending_lists()
        if not silent:
            self.progress_label.setText("状态：翻译面板内容已保存")

    def _refresh_list_texts(self):
        for i in range(self.list_widget.count()):
            item_widget = self.list_widget.item(i)
            item_data = self._get_item_by_id(item_widget.data(Qt.ItemDataRole.UserRole))
            if not item_data:
                continue
            eff_style, eff_genre = self._effective_tts_style_genre(item_data)
            style_part = f"style={eff_style}" if eff_style else "style=?"
            genre_part = f"genre={eff_genre}" if eff_genre is not None else "genre=?"
            item_widget.setText(
                f"{item_data.node_id} | {item_data.speaker} | {item_data.emotion} | {item_data.status} | {style_part} {genre_part}"
            )
