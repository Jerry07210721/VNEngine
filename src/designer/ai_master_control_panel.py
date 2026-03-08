# -*- coding: utf-8 -*-
"""
主控Agent界面
负责分步生成（人设→大纲→章节→章节详稿），允许用户在每一步编辑指令与结果。
"""

import json
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QSpinBox,
    QGroupBox,
    QFrame,
    QSplitter,
    QWidget,
    QComboBox,
    QMessageBox,
    QFileDialog,
    QSizePolicy,
    QProgressDialog,
    QToolButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer, QElapsedTimer, QObject

from src.designer.async_elapsed_runner import AsyncElapsedRunner

from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.config_manager import ConfigManager
from src.ai.core.step_generator import StepGenerator
from src.ai.core.models import (
    GenerationStep,
    PendingLists,
    UserConfig,
    ProjectConfig,
    EnableAgentsConfig,
    MaterialConfig,
    FlowNodeData,
    ConnectionData,
    GlobalVariable,
)
from src.ai.integrator.integrator import Integrator


class AIMasterControlPanel(QWidget):
    """主控Agent界面"""

    modified = pyqtSignal()

    def __init__(self, project_manager: AIProjectManager, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.project_manager = project_manager
        self.config_manager = config_manager
        self.step_generator: StepGenerator | None = None
        self.step_generator_error: str | None = None
        self._active_worker: QThread | None = None
        self._elapsed_timer = QElapsedTimer()
        self._elapsed_updater = QTimer(self)
        self._elapsed_updater.setInterval(500)
        self._elapsed_updater.timeout.connect(self._update_elapsed_label)
        self._busy_label = None
        self._busy_prefix = ""

        # 文件IO（保存/加载）专用 runner：用于显示“计时弹窗”，避免大指令保存时 UI 假死。
        self._io_runner = AsyncElapsedRunner(self)

        # 指令保存性能优化：大工程写盘可能耗时数秒。
        # “保存指令”先更新内存字段并立即返回 UI，然后后台合并/去抖动落盘。
        self._deferred_save_timer = QTimer(self)
        self._deferred_save_timer.setSingleShot(True)
        self._deferred_save_timer.timeout.connect(self._flush_deferred_project_save)
        self._deferred_save_callbacks: list = []
        try:
            self.step_generator = StepGenerator(config_manager)
        except Exception as exc:  # 延迟提示，避免界面直接崩溃
            self.step_generator_error = str(exc)

        self.personas_data = None
        self.outline_data = None
        self.chapters_data = None
        self.chapter_details: list[dict] = []
        self.pending_lists: PendingLists | None = None
        self.flow_nodes: list[FlowNodeData] = []
        self.flow_connections: list[ConnectionData] = []
        self.global_variables: list[GlobalVariable] = []
        self.pending_summary: dict | None = None
        self.vngproj_path: str | None = None
        self.step_parameters = {
            "step1": None,
            "step2": None,
            "step3": None,
            "step4": None,
        }

        # UI 侧缓存：用于判断“是否已保存最新编辑的指令”
        self._saved_instruction_cache: dict[str, str] = {}
        self._saved_step4_instruction_cache: dict[int, str] = {}

        # Step4 批量生成（并行）
        self._step4_batch_executor: ThreadPoolExecutor | None = None
        self._step4_batch_running: bool = False
        self._step4_batch_stop_requested: bool = False
        self._step4_batch_task_meta: dict[int, dict] = {}
        self._step4_batch_row_by_idx: dict[int, int] = {}
        self._step4_batch_total: int = 0
        self._step4_batch_update_timer = QTimer(self)
        self._step4_batch_update_timer.setInterval(500)
        self._step4_batch_update_timer.timeout.connect(self._update_step4_batch_elapsed_cells)
        self._step4_batch_signals = self._Step4BatchSignals()
        self._step4_batch_signals.started.connect(self._on_step4_batch_task_started)
        self._step4_batch_signals.finished.connect(self._on_step4_batch_task_finished)
        self._step4_batch_signals.failed.connect(self._on_step4_batch_task_failed)

        self.init_ui()
        self.refresh()

    # ==================== max_tokens（每步持久化） ====================

    def _default_step_max_tokens(self) -> dict:
        try:
            return dict(getattr(StepGenerator, "DEFAULT_STEP_MAX_TOKENS", {}) or {})
        except Exception:
            return {"step1": 32000, "step2": 48000, "step3": 48000, "step4": 64000}

    def _hard_cap_max_tokens(self) -> int:
        try:
            return int(getattr(StepGenerator, "MAX_TOKENS_HARD_CAP", 64000) or 64000)
        except Exception:
            return 64000

    def _get_step_max_tokens(self, step_key: str) -> int:
        defaults = self._default_step_max_tokens()
        hard_cap = self._hard_cap_max_tokens()
        value = int(defaults.get(step_key, 32000))

        project = self.project_manager.current_project
        if project is not None:
            gh = getattr(project, "generation_history", None)
            stored = getattr(gh, "step_max_tokens", None) if gh else None
            if isinstance(stored, dict) and stored.get(step_key) is not None:
                try:
                    value = int(stored.get(step_key))
                except Exception:
                    pass

        if value <= 0:
            value = int(defaults.get(step_key, 32000))
        if value > hard_cap:
            value = hard_cap
        return value

    def _set_step_max_tokens(self, step_key: str, value: int) -> None:
        project = self.project_manager.current_project
        if project is None:
            return
        hard_cap = self._hard_cap_max_tokens()
        try:
            value = int(value)
        except Exception:
            return
        if value <= 0:
            return
        if value > hard_cap:
            value = hard_cap

        gh = project.generation_history
        if not isinstance(getattr(gh, "step_max_tokens", None), dict):
            gh.step_max_tokens = {}
        gh.step_max_tokens[step_key] = value
        project.update_modified_time()
        self.modified.emit()

    # ==================== 异步执行辅助 ====================

    def _update_elapsed_label(self):
        if not self._busy_label or not self._elapsed_timer.isValid():
            return
        secs = self._elapsed_timer.elapsed() / 1000.0
        self._busy_label.setText(f"{self._busy_prefix} (已耗时 {secs:.1f}s)")

    def _run_async(self, label, running_text: str, task_fn, on_success):
        """在后台线程执行耗时任务，并在label上显示耗时。"""
        if self._active_worker:
            QMessageBox.information(self, "提示", "已有任务进行中，请稍候")
            return

        class _TaskThread(QThread):
            result = pyqtSignal(object)
            error = pyqtSignal(str)

            def __init__(self, fn):
                super().__init__()
                self.fn = fn

            def run(self):  # pragma: no cover - UI thread usage
                try:
                    res = self.fn()
                    self.result.emit(res)
                except Exception as exc:  # noqa: BLE001
                    self.error.emit(str(exc))

        self._busy_label = label
        self._busy_prefix = running_text
        self._elapsed_timer.restart()
        self._elapsed_updater.start()
        label.setText(f"{running_text} (已耗时 0.0s)")

        worker = _TaskThread(task_fn)
        self._active_worker = worker

        def _finish(res):
            self._elapsed_updater.stop()
            self._active_worker = None
            self._busy_label = None
            on_success(res)

        def _fail(msg: str):
            self._elapsed_updater.stop()
            self._active_worker = None
            self._busy_label = None
            QMessageBox.critical(self, "错误", f"生成失败: {msg}")

        worker.result.connect(_finish)
        worker.error.connect(_fail)
        worker.start()

    def _force_stop_current_task(self) -> None:
        """强制终止当前正在执行的后台任务（尽力而为）。"""

        worker = self._active_worker
        if not worker or not worker.isRunning():
            QMessageBox.information(self, "提示", "当前没有正在执行的任务。")
            return

        confirm = QMessageBox.question(
            self,
            "确认强制停止",
            "将强制终止当前任务线程（可能导致当前请求/任务不完整）。\n确定要停止吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            try:
                worker.blockSignals(True)
            except Exception:
                pass
            try:
                worker.requestInterruption()
            except Exception:
                pass
            try:
                worker.terminate()
            except Exception:
                pass
            try:
                worker.wait(1200)
            except Exception:
                pass
        finally:
            self._elapsed_updater.stop()
            if self._busy_label is not None:
                try:
                    self._busy_label.setText("状态：已强制停止")
                except Exception:
                    pass
            try:
                worker.deleteLater()
            except Exception:
                pass
            self._active_worker = None
            self._busy_label = None

    # ==================== UI ====================

    class _Step4BatchSignals(QObject):
        started = pyqtSignal(int)
        finished = pyqtSignal(int, object, float)
        failed = pyqtSignal(int, str)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 顶部提示
        self.project_label = QLabel("当前未加载AI工程")
        try:
            self.project_label.setProperty("pill", "true")
        except Exception:
            pass
        layout.addWidget(self.project_label)

        # 步骤1：人设
        self.step1_group = self._build_step_box(
            title="步骤1：生成角色人设",
            step_key="step1",
            prepare_handler=self.prepare_personas,
            send_handler=self.send_personas,
            save_handler=self.save_personas_result,
            result_placeholder="角色人设将显示在这里，用户可直接编辑后再保存。",
        )
        layout.addWidget(self.step1_group)

        # 步骤2：故事大纲
        self.step2_group = self._build_step_box(
            title="步骤2：生成故事大纲",
            step_key="step2",
            prepare_handler=self.prepare_outline,
            send_handler=self.send_outline,
            save_handler=self.save_outline_result,
            result_placeholder="故事大纲将显示在这里，用户可直接编辑后再保存。",
        )
        layout.addWidget(self.step2_group)

        # 步骤3：章节列表
        self.step3_group = self._build_step_box(
            title="步骤3：生成章节列表",
            step_key="step3",
            prepare_handler=self.prepare_chapters,
            send_handler=self.send_chapters,
            save_handler=self.save_chapters_result,
            result_placeholder="章节列表（结构化JSON）将显示在这里。",
        )
        layout.addWidget(self.step3_group)

        # 步骤4：章节详细内容（逐章）
        self.step4_group = QFrame()
        self.step4_group.setProperty("card", "true")
        step4_layout = QVBoxLayout(self.step4_group)
        step4_layout.setContentsMargins(12, 12, 12, 12)
        step4_layout.setSpacing(10)

        step4_header = QHBoxLayout()
        step4_title = QLabel("步骤4：逐章生成详细内容")
        step4_title.setProperty("role", "cardTitle")
        step4_header.addWidget(step4_title)
        self.step4_status = QLabel("状态：等待指令")
        self.step4_status.setProperty("pill", "true")
        step4_header.addWidget(self.step4_status)

        self.step4_word_stats = QLabel("文本量：目标 - | 本次 -")
        self.step4_word_stats.setProperty("pill", "true")
        step4_header.addWidget(self.step4_word_stats)

        self.step4_compensate_btn = QPushButton("字数补偿")
        self.step4_compensate_btn.setEnabled(False)
        self.step4_compensate_btn.setToolTip("当章节文本量不足时，使用同一上下文继续补写")
        self.step4_compensate_btn.clicked.connect(self.compensate_chapter_word_count)
        step4_header.addWidget(self.step4_compensate_btn)

        step4_header.addStretch(1)
        step4_layout.addLayout(step4_header)

        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("选择章节："))
        self.chapter_selector = QComboBox()
        self.chapter_selector.addItem("尚未生成章节列表")
        selector_row.addWidget(self.chapter_selector)
        self.load_chapter_btn = QPushButton("加载章节列表")
        self.load_chapter_btn.clicked.connect(self.load_chapter_list)
        selector_row.addWidget(self.load_chapter_btn)
        self.chapter_selector.currentIndexChanged.connect(self.on_chapter_changed)

        self.step4_prepare_btn = QPushButton("准备指令")
        self.step4_send_btn = QPushButton("发送/生成")
        self.step4_stop_btn = QPushButton("强制停止")
        self.step4_save_instruction_btn = QPushButton("保存指令")
        self.step4_save_btn = QPushButton("保存结果")
        self.step4_prepare_btn.clicked.connect(self.prepare_chapter_detail)
        self.step4_send_btn.clicked.connect(self.send_chapter_detail)
        self.step4_stop_btn.clicked.connect(self._force_stop_current_task)
        self.step4_save_instruction_btn.clicked.connect(self.save_step4_instruction)
        self.step4_save_btn.clicked.connect(self.save_chapter_detail)

        self.step4_max_tokens_label = QLabel("maxTokens：")
        self.step4_max_tokens_spin = QSpinBox()
        self.step4_max_tokens_spin.setRange(1, self._hard_cap_max_tokens())
        self.step4_max_tokens_spin.setSingleStep(1000)
        self.step4_max_tokens_spin.setValue(self._get_step_max_tokens("step4"))
        self.step4_max_tokens_spin.setToolTip("步骤4 每次调用 LLM 的 max_tokens（最大 64000）")
        self.step4_max_tokens_spin.valueChanged.connect(lambda v: self._set_step_max_tokens("step4", v))

        # Put step controls on the right side (match step1-3 header layout)
        selector_row.addStretch(1)
        selector_row.addWidget(self.step4_prepare_btn)
        selector_row.addWidget(self.step4_save_instruction_btn)
        selector_row.addWidget(self.step4_send_btn)
        selector_row.addWidget(self.step4_stop_btn)
        selector_row.addWidget(self.step4_save_btn)
        selector_row.addSpacing(10)
        selector_row.addWidget(self.step4_max_tokens_label)
        selector_row.addWidget(self.step4_max_tokens_spin)
        step4_layout.addLayout(selector_row)

        # Step4 批量生成控制栏（可折叠）
        self._build_step4_batch_panel(step4_layout)

        step4_splitter = QSplitter(Qt.Orientation.Horizontal)
        step4_splitter.setChildrenCollapsible(False)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(QLabel("指令（可编辑）"))
        self.step4_instruction = QTextEdit()
        self.step4_instruction.setPlaceholderText("章节指令，生成后可手动编辑...")
        self.step4_instruction.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._set_textedit_min_lines(self.step4_instruction, 12)
        left_layout.addWidget(self.step4_instruction)
        step4_splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_layout.addWidget(QLabel("结果（可编辑）"))
        self.step4_result = QTextEdit()
        self.step4_result.setPlaceholderText("章节详细内容（可编辑）")
        self.step4_result.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._set_textedit_min_lines(self.step4_result, 12)
        right_layout.addWidget(self.step4_result)
        step4_splitter.addWidget(right)

        step4_splitter.setStretchFactor(0, 1)
        step4_splitter.setStretchFactor(1, 1)
        step4_layout.addWidget(step4_splitter)

        layout.addWidget(self.step4_group)

        # 步骤5：待生成列表 + 流程骨架
        self.step5_group = QFrame()
        self.step5_group.setProperty("card", "true")
        step5_layout = QVBoxLayout(self.step5_group)
        step5_layout.setContentsMargins(12, 12, 12, 12)
        step5_layout.setSpacing(10)

        step5_header = QHBoxLayout()
        step5_title = QLabel("步骤5：生成待生成列表与流程骨架")
        step5_title.setProperty("role", "cardTitle")
        step5_header.addWidget(step5_title)
        self.step5_status = QLabel("状态：等待生成")
        self.step5_status.setProperty("pill", "true")
        step5_header.addWidget(self.step5_status)
        step5_header.addStretch(1)
        step5_layout.addLayout(step5_header)

        btn_row5 = QHBoxLayout()
        self.step5_generate_btn = QPushButton("生成列表")
        self.step5_stop_btn = QPushButton("强制停止")
        self.step5_save_btn = QPushButton("保存到工程")
        self.step5_generate_btn.clicked.connect(self.generate_pending_lists)
        self.step5_stop_btn.clicked.connect(self._force_stop_current_task)
        self.step5_save_btn.clicked.connect(self.save_pending_lists)
        btn_row5.addWidget(self.step5_generate_btn)
        btn_row5.addWidget(self.step5_stop_btn)
        btn_row5.addWidget(self.step5_save_btn)
        btn_row5.addStretch(1)
        step5_layout.addLayout(btn_row5)
        self.step5_result = QTextEdit()
        self.step5_result.setPlaceholderText("待生成列表摘要将显示在这里，可手动调整后保存。")
        self.step5_result.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._set_textedit_min_lines(self.step5_result, 10)
        step5_layout.addWidget(self.step5_result)

        # Step5-2：素材 prompts（背景/CG/BGM）生成（不默认自动执行）
        step5_layout.addSpacing(6)
        prompts_header = QHBoxLayout()
        prompts_title = QLabel("Step5-Prompts：统一生成背景/CG/BGM prompts")
        prompts_title.setProperty("role", "cardTitle")
        prompts_header.addWidget(prompts_title)
        self.step5_prompts_status = QLabel("状态：等待指令")
        self.step5_prompts_status.setProperty("pill", "true")
        prompts_header.addWidget(self.step5_prompts_status)
        prompts_header.addStretch(1)
        step5_layout.addLayout(prompts_header)

        prompts_btn_row = QHBoxLayout()
        self.step5_prompts_prepare_btn = QPushButton("准备指令")
        self.step5_prompts_save_instruction_btn = QPushButton("保存指令")
        self.step5_prompts_send_btn = QPushButton("发送生成")
        self.step5_prompts_stop_btn = QPushButton("强制停止")
        self.step5_prompts_save_btn = QPushButton("保存结果")
        self.step5_prompts_prepare_btn.clicked.connect(self.prepare_material_prompts)
        self.step5_prompts_save_instruction_btn.clicked.connect(
            lambda: self.save_step_instruction("step5_prompts", self.step5_prompts_instruction, self.step5_prompts_status)
        )
        self.step5_prompts_send_btn.clicked.connect(self.send_material_prompts)
        self.step5_prompts_stop_btn.clicked.connect(self._force_stop_current_task)
        self.step5_prompts_save_btn.clicked.connect(self.save_material_prompts_result)
        prompts_btn_row.addWidget(self.step5_prompts_prepare_btn)
        prompts_btn_row.addWidget(self.step5_prompts_save_instruction_btn)
        prompts_btn_row.addWidget(self.step5_prompts_send_btn)
        prompts_btn_row.addWidget(self.step5_prompts_stop_btn)
        prompts_btn_row.addWidget(self.step5_prompts_save_btn)
        prompts_btn_row.addSpacing(10)
        self.step5_prompts_max_tokens_label = QLabel("Max Tokens")
        self.step5_prompts_max_tokens_spin = QSpinBox()
        self.step5_prompts_max_tokens_spin.setRange(512, 200000)
        self.step5_prompts_max_tokens_spin.setSingleStep(512)
        self.step5_prompts_max_tokens_spin.setValue(self._get_step_max_tokens("step5_prompts"))
        self.step5_prompts_max_tokens_spin.valueChanged.connect(lambda v: self._set_step_max_tokens("step5_prompts", v))
        prompts_btn_row.addWidget(self.step5_prompts_max_tokens_label)
        prompts_btn_row.addWidget(self.step5_prompts_max_tokens_spin)
        prompts_btn_row.addStretch(1)
        step5_layout.addLayout(prompts_btn_row)

        prompts_splitter = QSplitter(Qt.Orientation.Horizontal)
        prompts_splitter.setChildrenCollapsible(False)

        p_left = QWidget()
        p_left_layout = QVBoxLayout(p_left)
        p_left_layout.setContentsMargins(0, 0, 0, 0)
        p_left_layout.setSpacing(6)
        p_left_layout.addWidget(QLabel("指令（可编辑）"))
        self.step5_prompts_instruction = QTextEdit()
        self.step5_prompts_instruction.setPlaceholderText("素材 prompts 指令，生成后可手动编辑...")
        self.step5_prompts_instruction.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._set_textedit_min_lines(self.step5_prompts_instruction, 10)
        p_left_layout.addWidget(self.step5_prompts_instruction)
        prompts_splitter.addWidget(p_left)

        p_right = QWidget()
        p_right_layout = QVBoxLayout(p_right)
        p_right_layout.setContentsMargins(0, 0, 0, 0)
        p_right_layout.setSpacing(6)
        p_right_layout.addWidget(QLabel("结果（可编辑）"))
        self.step5_prompts_result = QTextEdit()
        self.step5_prompts_result.setPlaceholderText("LLM 输出的 prompts JSON 将显示在这里（可手动修改后保存结果）。")
        self.step5_prompts_result.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._set_textedit_min_lines(self.step5_prompts_result, 10)
        p_right_layout.addWidget(self.step5_prompts_result)
        prompts_splitter.addWidget(p_right)

        prompts_splitter.setStretchFactor(0, 1)
        prompts_splitter.setStretchFactor(1, 1)
        step5_layout.addWidget(prompts_splitter)
        layout.addWidget(self.step5_group)

        # 步骤6：生成工程文件（虚拟资源路径）
        self.step6_group = QFrame()
        self.step6_group.setProperty("card", "true")
        step6_layout = QVBoxLayout(self.step6_group)
        step6_layout.setContentsMargins(12, 12, 12, 12)
        step6_layout.setSpacing(10)

        step6_header = QHBoxLayout()
        step6_title = QLabel("步骤6：生成工程文件（先填路径，后补资源）")
        step6_title.setProperty("role", "cardTitle")
        step6_header.addWidget(step6_title)
        self.step6_status = QLabel("状态：等待生成")
        self.step6_status.setProperty("pill", "true")
        step6_header.addWidget(self.step6_status)
        step6_header.addStretch(1)
        step6_layout.addLayout(step6_header)

        btn_row6 = QHBoxLayout()
        self.step6_generate_btn = QPushButton("生成 .vngproj")
        self.step6_generate_btn.clicked.connect(self.generate_project_file)
        btn_row6.addWidget(self.step6_generate_btn)
        self.step6_stop_btn = QPushButton("强制停止")
        self.step6_stop_btn.clicked.connect(self._force_stop_current_task)
        btn_row6.addWidget(self.step6_stop_btn)
        btn_row6.addStretch(1)
        step6_layout.addLayout(btn_row6)
        self.step6_result = QTextEdit()
        self.step6_result.setPlaceholderText("生成的工程路径与摘要将显示在这里。")
        self.step6_result.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._set_textedit_min_lines(self.step6_result, 8)
        step6_layout.addWidget(self.step6_result)
        layout.addWidget(self.step6_group)

        layout.addStretch(1)

    def _build_step_box(self, title: str, step_key: str, prepare_handler, send_handler, save_handler, result_placeholder: str) -> QWidget:
        # UI-only: Card style container with header + two-column editors
        card = QFrame()
        card.setProperty("card", "true")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)

        title_label = QLabel(title)
        title_label.setProperty("role", "cardTitle")
        header.addWidget(title_label)

        status = QLabel("状态：等待指令")
        status.setProperty("pill", "true")
        header.addWidget(status)

        header.addStretch(1)

        prepare_btn = QPushButton("准备指令")
        send_btn = QPushButton("发送/生成")
        stop_btn = QPushButton("强制停止")
        save_instruction_btn = QPushButton("保存指令")
        prepare_btn.clicked.connect(prepare_handler)
        send_btn.clicked.connect(send_handler)
        stop_btn.clicked.connect(self._force_stop_current_task)
        header.addWidget(prepare_btn)
        header.addWidget(save_instruction_btn)
        header.addWidget(send_btn)
        header.addWidget(stop_btn)
        if save_handler:
            save_btn = QPushButton("保存结果")
            save_btn.clicked.connect(save_handler)
            header.addWidget(save_btn)

        max_tokens_label = QLabel("maxTokens：")
        max_tokens_spin = QSpinBox()
        max_tokens_spin.setRange(1, self._hard_cap_max_tokens())
        max_tokens_spin.setSingleStep(1000)
        max_tokens_spin.setValue(self._get_step_max_tokens(step_key))
        max_tokens_spin.setToolTip("本步骤 LLM 的 max_tokens（最大 64000）")
        max_tokens_spin.valueChanged.connect(lambda v: self._set_step_max_tokens(step_key, v))
        header.addSpacing(10)
        header.addWidget(max_tokens_label)
        header.addWidget(max_tokens_spin)

        outer.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(QLabel("指令（可编辑）"))
        instruction = QTextEdit()
        instruction.setPlaceholderText("生成的指令会显示在这里，发送前可自由修改...")
        instruction.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._set_textedit_min_lines(instruction, 12)
        left_layout.addWidget(instruction)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_layout.addWidget(QLabel("结果（可编辑）"))
        result = QTextEdit()
        result.setPlaceholderText(result_placeholder)
        result.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._set_textedit_min_lines(result, 12)
        right_layout.addWidget(result)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        outer.addWidget(splitter)

        # Keep attribute contracts used by existing logic
        card._instruction = instruction
        card._result = result
        card._status = status
        card._max_tokens_label = max_tokens_label
        card._max_tokens_spin = max_tokens_spin
        card._step_key = step_key
        card._save_instruction_btn = save_instruction_btn

        # bind save instruction
        save_instruction_btn.clicked.connect(lambda: self.save_step_instruction(step_key, instruction, status))
        return card

    @staticmethod
    def _set_textedit_min_lines(edit: QTextEdit, min_lines: int) -> None:
        """按行数设置 QTextEdit 最小高度，提升可读性。"""
        min_lines = max(1, int(min_lines))
        line_h = edit.fontMetrics().lineSpacing()
        # 经验值：额外 padding + 文档边距，避免恰好卡住最后一行
        min_h = int(line_h * min_lines + 24)
        edit.setMinimumHeight(min_h)
        edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    @staticmethod
    def _set_table_min_rows(table: QTableWidget, min_rows: int) -> None:
        """按行数设置 QTableWidget 最小高度，提升可读性。"""

        try:
            min_rows = max(1, int(min_rows))
        except Exception:
            min_rows = 8

        try:
            row_h = int(table.verticalHeader().defaultSectionSize() or 0)
        except Exception:
            row_h = 0
        if row_h <= 0:
            try:
                row_h = int(table.fontMetrics().lineSpacing() + 10)
            except Exception:
                row_h = 24

        try:
            header_h = int(table.horizontalHeader().height() or 0)
        except Exception:
            header_h = 28
        if header_h <= 0:
            header_h = 28

        # 经验值：额外边距 + 横向滚动条余量
        min_h = int(header_h + row_h * min_rows + 22)
        table.setMinimumHeight(min_h)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # ==================== 对话上下文拼装（去重追加最新 raw_response） ====================

    @staticmethod
    def _conv_contains_substring(conv: list[dict] | None, needle: str) -> bool:
        if not conv or not isinstance(needle, str) or not needle:
            return False
        try:
            for m in conv:
                if not isinstance(m, dict):
                    continue
                c = m.get("content")
                if isinstance(c, str) and needle in c:
                    return True
        except Exception:
            return False
        return False

    def _append_latest_raw_response_to_conv(self, conv: list[dict], raw: str | None, *, title: str) -> None:
        """向 conversation 追加“最新手动保存的 raw_response（以此为准）”，并做去重。

        设计目标：即使存在旧的 master_conversation_after_stepX 快照，也要确保下游发送时使用最新的上游结果。
        """

        if not isinstance(raw, str) or not raw.strip():
            return
        raw = raw.strip()
        if self._conv_contains_substring(conv, raw):
            return
        conv.append(
            {
                "role": "user",
                "content": f"补充：以下是用户手动修订并保存的{title}（以此为准）：\n" + raw,
            }
        )

    # ==================== 数据与状态 ====================

    def refresh(self):
        """刷新界面，加载现有工程数据与生成历史。"""
        project = self.project_manager.current_project
        if project is None:
            self.project_label.setText("当前未加载AI工程")
            self._clear_all()
            return

        self.project_label.setText(
            f"工程：{project.ai_project_info.name} | 角色：{len(project.character_config)} | 文本量：{project.story_config.text_volume}"
        )

        history = project.generation_history
        self.personas_data = self._normalize_step_payload(history.step1_personas)
        self.outline_data = self._normalize_step_payload(history.step2_outline)
        self.chapters_data = self._normalize_step_payload(history.step3_chapters)
        raw_details = history.step4_chapter_details or []
        if isinstance(raw_details, list):
            self.chapter_details = [self._normalize_step_payload(d) or d for d in raw_details]
        else:
            self.chapter_details = raw_details
        flow_step = getattr(history, "step5_flow_nodes", None)
        self.pending_lists = None
        if flow_step and isinstance(flow_step, dict) and flow_step.get("pending_lists"):
            try:
                self.pending_lists = PendingLists(**flow_step.get("pending_lists"))
            except Exception:
                self.pending_lists = None
        if flow_step:
            fn = flow_step.get("flow_nodes") or []
            cn = flow_step.get("connections") or []
            gv = flow_step.get("global_variables") or []
            try:
                self.flow_nodes = [FlowNodeData(**n) for n in fn]
                self.flow_connections = [ConnectionData(**c) for c in cn]
                self.global_variables = [GlobalVariable(**g) for g in gv]
            except Exception:
                self.flow_nodes = []
                self.flow_connections = []
                self.global_variables = []

        # 渲染已有数据
        if self.personas_data:
            self.step1_group._result.setPlainText(self._format_preview(self.personas_data))
            self.step1_group._status.setText("状态：已生成")
        else:
            self.step1_group._status.setText("状态：等待指令")

        if self.outline_data:
            self.step2_group._result.setPlainText(self._format_preview(self.outline_data))
            self.step2_group._status.setText("状态：已生成")
        else:
            self.step2_group._status.setText("状态：等待指令")

        if self.chapters_data:
            self.step3_group._result.setPlainText(self._format_preview(self.chapters_data))
            self.step3_group._status.setText("状态：已生成")
        else:
            self.step3_group._status.setText("状态：等待指令")

        self._refresh_chapter_selector()
        self._load_chapter_detail(self.chapter_selector.currentIndex())

        # 刷新每步 maxTokens（从工程持久化数据回填）
        self._refresh_step_max_tokens_ui()

        # 回填每步已保存指令
        self._load_saved_instructions_into_ui()

        # 渲染步骤5
        if self.pending_lists:
            summary = self._summarize_pending(self.pending_lists, getattr(history, "step5_flow_nodes", None))
            self.step5_result.setPlainText(summary)
            self.step5_status.setText("状态：已生成")
        else:
            self.step5_status.setText("状态：等待生成")

        # 渲染 Step5 prompts
        try:
            prompts_step = getattr(history, "step5_material_prompts", None)
        except Exception:
            prompts_step = None
        if prompts_step and isinstance(prompts_step, dict):
            self.step5_prompts_status.setText("状态：已生成")
            structured = prompts_step.get("structured")
            raw = prompts_step.get("raw_response")
            if isinstance(structured, dict):
                self.step5_prompts_result.setPlainText(json.dumps(structured, ensure_ascii=False, indent=2))
            elif isinstance(raw, str):
                self.step5_prompts_result.setPlainText(raw)
        else:
            self.step5_prompts_status.setText("状态：等待指令")

        # 渲染步骤6
        if self.project_manager.current_project.ai_project_info.vng_project_path:
            self.vngproj_path = self.project_manager.current_project.ai_project_info.vng_project_path
            self.step6_result.setPlainText(f"已关联工程: {self.vngproj_path}")
            self.step6_status.setText("状态：已关联，可重新生成")
        else:
            self.step6_status.setText("状态：等待生成")

    def _clear_all(self):
        for box in (self.step1_group, self.step2_group, self.step3_group):
            box._instruction.clear()
            box._result.clear()
            box._status.setText("状态：等待指令")
            if hasattr(box, "_max_tokens_spin"):
                try:
                    box._max_tokens_spin.setValue(self._get_step_max_tokens(getattr(box, "_step_key", "step1")))
                except Exception:
                    pass
        self.step4_instruction.clear()
        self.step4_result.clear()
        self.step4_status.setText("状态：等待指令")
        self.chapter_selector.clear()
        self.chapter_selector.addItem("尚未生成章节列表")
        if hasattr(self, "step4_max_tokens_spin"):
            try:
                self.step4_max_tokens_spin.setValue(self._get_step_max_tokens("step4"))
            except Exception:
                pass

        # 清空 UI 缓存（避免切工程残留）
        self._saved_instruction_cache = {}
        self._saved_step4_instruction_cache = {}

        # step4 batch
        try:
            self.stop_step4_batch_generation(silent=True)
        except Exception:
            pass
        try:
            if hasattr(self, "step4_batch_table") and self.step4_batch_table:
                self.step4_batch_table.clearContents()
                self.step4_batch_table.setRowCount(0)
            if hasattr(self, "step4_batch_status") and self.step4_batch_status:
                self.step4_batch_status.setText("批量：未开始")
        except Exception:
            pass

        # step5
        try:
            self.step5_result.clear()
            self.step5_status.setText("状态：等待生成")
        except Exception:
            pass

        # step5 prompts
        try:
            self.step5_prompts_instruction.clear()
            self.step5_prompts_result.clear()
            self.step5_prompts_status.setText("状态：等待指令")
            if hasattr(self, "step5_prompts_max_tokens_spin"):
                self.step5_prompts_max_tokens_spin.setValue(self._get_step_max_tokens("step5_prompts"))
        except Exception:
            pass

    # ==================== 指令保存/发送一致性 ====================

    def _persist_ai_project_to_disk(self) -> bool:
        """立即将当前 AI 工程持久化到 .vnai 文件。"""

        if not self.project_manager.current_project:
            return False
        # 沿用工程管理器已知路径
        try:
            return bool(self.project_manager.save_project())
        except Exception:
            return False

    def _show_busy_dialog(self, text: str) -> QProgressDialog:
        """显示不可取消的忙碌提示，用于大文件保存时避免“卡死”错觉。"""
        dlg = QProgressDialog(text, None, 0, 0, self)
        dlg.setWindowTitle("请稍候")
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setValue(0)
        dlg.show()
        return dlg

    def _persist_ai_project_to_disk_with_busy_dialog(self, base_text: str, *, on_done=None) -> None:
        """后台保存工程文件，并显示带耗时的弹窗。"""

        if not self.project_manager.current_project:
            if on_done is not None:
                on_done(False)
            return

        if self._io_runner.is_running():
            QMessageBox.information(self, "提示", "正在保存工程文件，请稍候...")
            return

        busy = self._show_busy_dialog(base_text)

        def _finally_close():
            try:
                busy.close()
                busy.deleteLater()
            except Exception:
                pass

        def _fn():
            return bool(self.project_manager.save_project())

        def _on_success(ok: bool):
            if on_done is not None:
                on_done(bool(ok))

        def _on_error(err_text: str):
            QMessageBox.critical(self, "错误", f"保存AI工程失败：{err_text}")
            if on_done is not None:
                on_done(False)

        self._io_runner.run_with_setter(
            set_text=busy.setLabelText,
            base_text=base_text,
            fn=_fn,
            on_success=_on_success,
            on_error=_on_error,
            on_finally=_finally_close,
            tick_ms=300,
        )

    def _schedule_deferred_project_save(self, *, on_done=None, debounce_ms: int = 250) -> None:
        """调度一次后台落盘（去抖动），避免 UI 因大文件保存产生明显等待。"""

        if on_done is not None:
            try:
                self._deferred_save_callbacks.append(on_done)
            except Exception:
                pass

        try:
            self._deferred_save_timer.start(int(debounce_ms))
        except Exception:
            self._flush_deferred_project_save()

    def _flush_deferred_project_save(self) -> None:
        if not self.project_manager.current_project:
            callbacks = list(self._deferred_save_callbacks or [])
            self._deferred_save_callbacks = []
            for cb in callbacks:
                try:
                    cb(False)
                except Exception:
                    pass
            return

        # 若正在进行其他 IO（加载/保存），稍后再尝试，合并多次触发
        if self._io_runner.is_running():
            try:
                self._deferred_save_timer.start(300)
            except Exception:
                pass
            return

        callbacks = list(self._deferred_save_callbacks or [])
        self._deferred_save_callbacks = []

        def _fn():
            return bool(self.project_manager.save_project())

        def _on_success(ok: bool):
            for cb in callbacks:
                try:
                    cb(bool(ok))
                except Exception:
                    pass

        def _on_error(err_text: str):
            QMessageBox.critical(self, "错误", f"保存AI工程失败：{err_text}")
            for cb in callbacks:
                try:
                    cb(False)
                except Exception:
                    pass

        # 后台保存，不显示忙碌弹窗（目标：像“保存结果”一样瞬时响应）
        self._io_runner.run_with_setter(
            set_text=lambda _t: None,
            base_text="后台保存中",
            fn=_fn,
            on_success=_on_success,
            on_error=_on_error,
            tick_ms=500,
        )

    def _saved_instruction_for_step(self, step_key: str) -> str:
        project = self.project_manager.current_project
        if not project:
            return ""
        history = project.generation_history
        if isinstance(getattr(history, "saved_step_instructions", None), dict):
            return (history.saved_step_instructions.get(step_key) or "").strip()
        return ""

    def _saved_instruction_for_step4(self, chapter_index: int) -> str:
        project = self.project_manager.current_project
        if not project:
            return ""
        history = project.generation_history
        mapping = getattr(history, "step4_saved_instructions", None)
        if isinstance(mapping, dict):
            return (mapping.get(str(int(chapter_index))) or "").strip()
        return ""

    def _set_saved_instruction_for_step(self, step_key: str, text: str) -> None:
        project = self.project_manager.current_project
        if not project:
            return
        history = project.generation_history
        if not isinstance(getattr(history, "saved_step_instructions", None), dict):
            history.saved_step_instructions = {}
        history.saved_step_instructions[step_key] = text
        project.update_modified_time()

    def _set_saved_instruction_for_step4(self, chapter_index: int, text: str) -> None:
        project = self.project_manager.current_project
        if not project:
            return
        history = project.generation_history
        if not isinstance(getattr(history, "step4_saved_instructions", None), dict):
            history.step4_saved_instructions = {}
        history.step4_saved_instructions[str(int(chapter_index))] = text
        project.update_modified_time()

    def save_step_instruction(self, step_key: str, editor: QTextEdit, status_label: QLabel | None = None) -> None:
        if not self._ensure_project():
            return
        text = (editor.toPlainText() or "").strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有可保存的指令内容。")
            return

        self._set_saved_instruction_for_step(step_key, text)
        self._saved_instruction_cache[step_key] = text

        if status_label is not None:
            status_label.setText("状态：指令已保存")

        self._record_instruction(f"manual_save_instruction_{step_key}", text, {}, None, "success")
        self.modified.emit()

    def save_step4_instruction(self) -> None:
        if not self._ensure_project():
            return
        chapters_struct = self._chapter_list()
        if not chapters_struct:
            QMessageBox.warning(self, "提示", "请先完成步骤3并选择章节后再保存指令。")
            return
        idx = self.chapter_selector.currentIndex()
        if idx < 0 or idx >= len(chapters_struct):
            QMessageBox.warning(self, "提示", "请选择有效的章节。")
            return
        text = (self.step4_instruction.toPlainText() or "").strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有可保存的指令内容。")
            return

        self._set_saved_instruction_for_step4(idx, text)
        self._saved_step4_instruction_cache[idx] = text

        self.step4_status.setText(f"状态：第{idx+1}章指令已保存")
        self._record_instruction(
            f"manual_save_instruction_step4_ch{idx}",
            text,
            {"chapter_index": idx},
            None,
            "success",
        )
        self.modified.emit()

    def _load_saved_instructions_into_ui(self) -> None:
        """从工程持久化字段回填 UI，并更新缓存。"""
        project = self.project_manager.current_project
        if not project:
            return

        # step1-3
        for group in (getattr(self, "step1_group", None), getattr(self, "step2_group", None), getattr(self, "step3_group", None)):
            if not group or not hasattr(group, "_step_key"):
                continue
            step_key = getattr(group, "_step_key", "")
            if not step_key:
                continue
            saved = self._saved_instruction_for_step(step_key)
            if saved:
                try:
                    group._instruction.blockSignals(True)
                    group._instruction.setPlainText(saved)
                finally:
                    group._instruction.blockSignals(False)
                self._saved_instruction_cache[step_key] = saved

        # step4（当前选择章节）
        chapters_struct = self._chapter_list()
        idx = self.chapter_selector.currentIndex()
        if chapters_struct and 0 <= idx < len(chapters_struct):
            saved4 = self._saved_instruction_for_step4(idx)
            if saved4:
                try:
                    self.step4_instruction.blockSignals(True)
                    self.step4_instruction.setPlainText(saved4)
                finally:
                    self.step4_instruction.blockSignals(False)
                self._saved_step4_instruction_cache[idx] = saved4

        # step5_prompts
        saved5p = self._saved_instruction_for_step("step5_prompts")
        if saved5p and hasattr(self, "step5_prompts_instruction"):
            try:
                self.step5_prompts_instruction.blockSignals(True)
                self.step5_prompts_instruction.setPlainText(saved5p)
            finally:
                self.step5_prompts_instruction.blockSignals(False)
            self._saved_instruction_cache["step5_prompts"] = saved5p

    def _ensure_send_uses_saved_instruction(self, step_key: str, editor: QTextEdit, *, chapter_index: int | None = None) -> str | None:
        """确保发送时使用“最新编辑且已保存”的指令。

        - 若编辑器内容与已保存版本一致：直接返回已保存文本
        - 若不一致：提示用户先保存（可选自动保存并继续）
        """
        if not self._ensure_project():
            return None

        current_text = (editor.toPlainText() or "").strip()
        if not current_text:
            QMessageBox.warning(self, "提示", "请先准备/编辑指令后再发送。")
            return None

        if chapter_index is None:
            saved_text = self._saved_instruction_for_step(step_key)
        else:
            saved_text = self._saved_instruction_for_step4(chapter_index)

        # 已保存且一致
        if saved_text and saved_text.strip() == current_text:
            return saved_text.strip()

        # 未保存或不一致：要求保存
        choice = QMessageBox.question(
            self,
            "指令未保存",
            "当前指令已修改但尚未保存。\n为了保证发送的是‘最新编辑且已保存’的指令，请先保存。\n\n是否现在保存并继续发送？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return None

        # 自动保存
        if chapter_index is None:
            self._set_saved_instruction_for_step(step_key, current_text)
            self._saved_instruction_cache[step_key] = current_text
        else:
            self._set_saved_instruction_for_step4(chapter_index, current_text)
            self._saved_step4_instruction_cache[chapter_index] = current_text
        self.modified.emit()
        return current_text

    def _ensure_send_uses_saved_instruction_async(
        self,
        step_key: str,
        editor: QTextEdit,
        *,
        chapter_index: int | None = None,
        status_label: QLabel | None = None,
        on_ready=None,
    ) -> None:
        """确保发送时使用“最新编辑且已保存”的指令（非阻塞版）。

        说明：当前“保存指令”逻辑与“保存结果”一致，只更新内存，不进行 .vnai 落盘。
        因此这里的“自动保存并继续发送”也只写入内存字段，然后立即回调 on_ready。
        """

        if on_ready is None:
            return
        if not self._ensure_project():
            return

        current_text = (editor.toPlainText() or "").strip()
        if not current_text:
            QMessageBox.warning(self, "提示", "请先准备/编辑指令后再发送。")
            return

        if chapter_index is None:
            saved_text = self._saved_instruction_for_step(step_key)
        else:
            saved_text = self._saved_instruction_for_step4(chapter_index)

        # 已保存且一致：直接继续
        if saved_text and saved_text.strip() == current_text:
            on_ready(saved_text.strip())
            return

        # 未保存或不一致：要求保存
        choice = QMessageBox.question(
            self,
            "指令未保存",
            "当前指令已修改但尚未保存。\n为了保证发送的是‘最新编辑且已保存’的指令，请先保存。\n\n是否现在保存并继续发送？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        # 先把“已保存指令”写入工程对象（保存文件会把它落盘）
        if chapter_index is None:
            self._set_saved_instruction_for_step(step_key, current_text)
            self._saved_instruction_cache[step_key] = current_text
        else:
            self._set_saved_instruction_for_step4(chapter_index, current_text)
            self._saved_step4_instruction_cache[chapter_index] = current_text

        if status_label is not None:
            try:
                status_label.setText("状态：指令已保存")
            except Exception:
                pass

        self.modified.emit()
        try:
            QTimer.singleShot(0, lambda: on_ready(current_text))
        except Exception:
            on_ready(current_text)

    def _refresh_step_max_tokens_ui(self) -> None:
        groups = [getattr(self, "step1_group", None), getattr(self, "step2_group", None), getattr(self, "step3_group", None)]
        for g in groups:
            if not g or not hasattr(g, "_max_tokens_spin"):
                continue
            step_key = getattr(g, "_step_key", "step1")
            spin = getattr(g, "_max_tokens_spin")
            try:
                spin.blockSignals(True)
                spin.setValue(self._get_step_max_tokens(step_key))
            finally:
                spin.blockSignals(False)

        if hasattr(self, "step4_max_tokens_spin"):
            try:
                self.step4_max_tokens_spin.blockSignals(True)
                self.step4_max_tokens_spin.setValue(self._get_step_max_tokens("step4"))
            finally:
                self.step4_max_tokens_spin.blockSignals(False)

        if hasattr(self, "step5_prompts_max_tokens_spin"):
            try:
                self.step5_prompts_max_tokens_spin.blockSignals(True)
                self.step5_prompts_max_tokens_spin.setValue(self._get_step_max_tokens("step5_prompts"))
            finally:
                self.step5_prompts_max_tokens_spin.blockSignals(False)

    def _refresh_chapter_selector(self):
        self.chapter_selector.blockSignals(True)
        self.chapter_selector.clear()
        chapters = self._chapter_list()
        if chapters:
            for idx, ch in enumerate(chapters):
                title = ch.get("chapter_title") or ch.get("title") or f"第{idx+1}章"
                self.chapter_selector.addItem(f"{idx+1}. {title}", idx)
        else:
            self.chapter_selector.addItem("尚未生成章节列表")
        self.chapter_selector.blockSignals(False)

        # 同步刷新批量任务清单
        try:
            self._refresh_step4_batch_task_table(preserve_checks=True)
        except Exception:
            pass

    def on_chapter_changed(self, idx: int):
        self._load_chapter_detail(idx)

        # 切换章节时：回填该章节已保存指令（若有）
        try:
            saved = self._saved_instruction_for_step4(idx)
            if saved:
                self.step4_instruction.setPlainText(saved)
                self._saved_step4_instruction_cache[idx] = saved
            else:
                # 未保存则清空，避免误发上一章指令
                self.step4_instruction.clear()
        except Exception:
            return

    def _ensure_project(self) -> bool:
        if self.project_manager.current_project is None:
            QMessageBox.warning(self, "提示", "请先创建或打开AI工程。")
            return False
        return True

    def _ensure_step_gen(self) -> bool:
        if self.step_generator:
            return True
        if self.step_generator_error:
            QMessageBox.critical(self, "错误", f"主控Agent初始化失败: {self.step_generator_error}")
            return False

    def _sync_project_configs(self):
        """将配置面板当前编辑内容静默同步回工程。

        目的：避免用户未点击“保存配置”导致 Step4/Step5 读取到旧的 story_config/character_config。
        """
        try:
            parent = self.parent()
            story_panel = getattr(parent, "story_panel", None) if parent else None
            if story_panel and hasattr(story_panel, "save_to_project"):
                story_panel.save_to_project(silent=True)
            char_panel = getattr(parent, "character_panel", None) if parent else None
            if char_panel and hasattr(char_panel, "save_current_character"):
                char_panel.save_current_character()
            if char_panel and hasattr(char_panel, "save_to_project"):
                char_panel.save_to_project(silent=True)
        except Exception:
            # 自动同步失败不应阻塞主流程
            return
        try:
            self.step_generator = StepGenerator(self.config_manager)
            return True
        except Exception as exc:
            self.step_generator_error = str(exc)
            QMessageBox.critical(self, "错误", f"主控Agent初始化失败: {exc}")
            return False

    def _story_dict(self) -> dict:
        return self.project_manager.current_project.story_config.model_dump() if self.project_manager.current_project else {}

    def _characters_dict(self) -> list[dict]:
        if not self.project_manager.current_project:
            return []
        return [c.model_dump() for c in self.project_manager.current_project.character_config]

    def _chapter_list(self) -> list[dict]:
        """提取章节列表，兼容 structured 为 dict 或 list 的情况。"""
        def _extract(obj):
            if isinstance(obj, list):
                return obj
            if isinstance(obj, dict):
                if isinstance(obj.get("chapters"), list):
                    return obj.get("chapters")
                if isinstance(obj.get("structured"), dict) and isinstance(obj["structured"].get("chapters"), list):
                    return obj["structured"].get("chapters")
                if isinstance(obj.get("structured"), list):
                    return obj.get("structured")
            return None

        if not isinstance(self.chapters_data, dict):
            return []

        # 1) 优先 structured
        chapters = _extract(self.chapters_data.get("structured")) or _extract(self.chapters_data)
        if isinstance(chapters, list):
            return chapters

        # 2) 尝试解析 raw_response（可能是带```json的字符串或嵌套JSON字符串）
        raw = self.chapters_data.get("raw_response")
        parsed = None
        if isinstance(raw, str):
            parsed = self._try_parse_json_block(raw) or self._safe_json_load(raw)
            if isinstance(parsed, dict) and isinstance(parsed.get("raw_response"), str):
                parsed_inner = self._try_parse_json_block(parsed.get("raw_response")) or self._safe_json_load(parsed.get("raw_response"))
                if parsed_inner:
                    parsed = parsed_inner
        chapters = _extract(parsed) if parsed else None
        return chapters if isinstance(chapters, list) else []

    def _safe_json_load(self, text: str):
        try:
            return json.loads(text)
        except Exception:
            return None

    def load_chapter_list(self):
        """从工程历史重新加载章节列表。"""
        history = None
        if self.project_manager.current_project:
            history = self.project_manager.current_project.generation_history.step3_chapters
        if history:
            self.chapters_data = history
            if self.project_manager.current_project.generation_history.step4_chapter_details:
                self.chapter_details = self.project_manager.current_project.generation_history.step4_chapter_details
            self._refresh_chapter_selector()
            self._load_chapter_detail(self.chapter_selector.currentIndex())
            QMessageBox.information(self, "成功", "已从工程加载章节列表")
        else:
            QMessageBox.warning(self, "提示", "工程中暂无已保存的章节列表，请先完成步骤3")

    def _record_instruction(self, step_name: str, instruction: str, parameters: dict, result: dict | None, status: str):
        if not self.project_manager.current_project:
            return
        record = GenerationStep(
            step_name=step_name,
            instruction=instruction,
            parameters=parameters or {},
            result=result,
            status=status,
        )
        self.project_manager.add_agent_instruction(record)

    def _format_preview(self, data: dict) -> str:
        if not data:
            return ""
        if isinstance(data, str):
            return data
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _normalize_step_payload(self, data: dict | str | None) -> dict | None:
        """解包可能被重复 JSON 序列化的步骤结果，保证 structured 可用。"""

        def _try_json(text: str | None):
            if not isinstance(text, str):
                return None
            try:
                return json.loads(text)
            except Exception:
                return None

        if data is None:
            return None

        # 字符串直接尝试解析
        if isinstance(data, str):
            parsed = _try_json(data)
            return parsed if isinstance(parsed, dict) else {"raw_response": data}

        if isinstance(data, dict):
            normalized = dict(data)

            raw_text = normalized.get("raw_response")
            parsed_raw = _try_json(raw_text) if isinstance(raw_text, str) else None
            if isinstance(parsed_raw, dict):
                # 保留原始 raw_response，避免再次保存时丢失原文
                normalized.update(parsed_raw)
                normalized["raw_response"] = raw_text

            structured = normalized.get("structured")
            parsed_struct = _try_json(structured) if isinstance(structured, str) else None
            if parsed_struct is not None:
                normalized["structured"] = parsed_struct

            return normalized

        return None

    def _try_parse_json_block(self, text: str):
        if not text:
            return None

        candidate = text.strip()

        def _strip_fence_payload(payload: str) -> str:
            payload = (payload or "").strip("\n\r \t")
            # 兼容 ```JSON / ```Json / ```json5 等：若第一行像语言标识，则去掉
            first_line, _, rest = payload.partition("\n")
            lang = first_line.strip().lower()
            if lang in {"json", "json5", "javascript", "js"}:
                return rest.strip("\n\r \t")
            return payload

        def _try_span(open_ch: str, close_ch: str):
            if open_ch not in candidate or close_ch not in candidate:
                return None
            start = candidate.find(open_ch)
            end = candidate.rfind(close_ch)
            if start < 0 or end <= start:
                return None
            snippet = candidate[start : end + 1].strip()
            try:
                return json.loads(snippet)
            except Exception:
                return None

        try:
            if "```json" in candidate.lower():
                # 使用 lower() 探测，但保持原文本切片：找到第一个 ```json（大小写不敏感）
                lower = candidate.lower()
                pos = lower.find("```json")
                payload = candidate[pos + len("```json") :]
                payload = payload.split("```", 1)[0]
                payload = _strip_fence_payload(payload)
                return json.loads(payload)
            if candidate.startswith("```"):
                payload = candidate.split("```", 1)[1].split("```", 1)[0]
                payload = _strip_fence_payload(payload)
                return json.loads(payload)
            return json.loads(candidate)
        except Exception:
            return _try_span("{", "}") or _try_span("[", "]")

    def _load_chapter_detail(self, idx: int):
        if idx < 0:
            self.step4_result.clear()
            self.step4_status.setText("状态：等待指令")
            try:
                self.step4_word_stats.setText("文本量：目标 - | 本次 -")
            except Exception:
                pass
            return
        if idx < len(self.chapter_details):
            detail = self.chapter_details[idx]
            if detail:
                self.step4_result.setPlainText(self._format_preview(detail))
                self.step4_status.setText(f"状态：第{idx+1}章已加载")
                self._update_step4_word_stats_from_detail(idx, detail)
                return
        self.step4_result.clear()
        self.step4_status.setText("状态：等待指令")
        try:
            self.step4_word_stats.setText("文本量：目标 - | 本次 -")
        except Exception:
            pass

    def _calc_cn_char_target_range(self, target_words: int) -> tuple[int, int]:
        """与 StepGenerator 口径一致：默认 ±5% 且最小容差 30。"""
        try:
            target_words = int(target_words or 0)
        except Exception:
            target_words = 0
        if target_words <= 0:
            return 0, 0
        tolerance = max(30, int(target_words * 0.05))
        return max(1, target_words - tolerance), target_words + tolerance

    def _update_step4_word_stats(self, *, target_min: int, target_max: int, actual: int | None) -> None:
        try:
            if target_min > 0 and target_max > 0:
                target_text = f"{target_min}~{target_max}"
            else:
                target_text = "-"
            actual_text = str(int(actual)) if actual is not None else "-"
            self.step4_word_stats.setText(f"文本量：目标 {target_text} | 本次 {actual_text}")

            # 字数补偿：仅在“本次 < 目标下限”时启用
            try:
                enable = actual is not None and int(actual) > 0 and int(target_min) > 0 and int(actual) < int(target_min)
            except Exception:
                enable = False
            try:
                if hasattr(self, "step4_compensate_btn") and self.step4_compensate_btn:
                    self.step4_compensate_btn.setEnabled(bool(enable))
            except Exception:
                pass
        except Exception:
            return

    def _update_step4_word_stats_from_params(self, idx: int, params: dict | None) -> None:
        params = params or {}
        min_cn = params.get("cn_char_min")
        max_cn = params.get("cn_char_max")
        try:
            min_cn = int(min_cn or 0)
            max_cn = int(max_cn or 0)
        except Exception:
            min_cn, max_cn = 0, 0
        if min_cn <= 0 or max_cn <= 0:
            # 兜底：从章节列表 estimated_words 计算
            chapters = self._chapter_list()
            if 0 <= idx < len(chapters):
                est = chapters[idx].get("estimated_words") or chapters[idx].get("target_words") or 0
                min_cn, max_cn = self._calc_cn_char_target_range(int(est or 0))
        self._update_step4_word_stats(target_min=min_cn, target_max=max_cn, actual=None)

    def _update_step4_word_stats_from_detail(self, idx: int, detail: dict | None) -> None:
        detail = detail or {}
        # 目标区间：优先从 parameters
        params = detail.get("parameters") if isinstance(detail, dict) else None
        if isinstance(params, dict):
            try:
                min_cn = int(params.get("cn_char_min") or 0)
                max_cn = int(params.get("cn_char_max") or 0)
            except Exception:
                min_cn, max_cn = 0, 0
        else:
            min_cn, max_cn = 0, 0

        if min_cn <= 0 or max_cn <= 0:
            chapters = self._chapter_list()
            if 0 <= idx < len(chapters):
                est = chapters[idx].get("estimated_words") or chapters[idx].get("target_words") or 0
                min_cn, max_cn = self._calc_cn_char_target_range(int(est or 0))

        # 实际：优先使用 detail.metrics.cn_char_count；否则尝试从 structured 计算
        actual = None
        try:
            metrics = detail.get("metrics") if isinstance(detail, dict) else None
            if isinstance(metrics, dict) and metrics.get("cn_char_count") is not None:
                actual = int(metrics.get("cn_char_count"))
        except Exception:
            actual = None
        if actual is None:
            try:
                structured = detail.get("structured") if isinstance(detail, dict) else None
                if self.step_generator and isinstance(structured, dict) and hasattr(self.step_generator, "_count_cn_chars_in_chapter_struct"):
                    actual = int(self.step_generator._count_cn_chars_in_chapter_struct(structured))
            except Exception:
                actual = None

        self._update_step4_word_stats(target_min=min_cn, target_max=max_cn, actual=actual)

    def compensate_chapter_word_count(self):
        """字数补偿：在当前章节的对话上下文中继续补写 append_scenes。"""

        if getattr(self, "_step4_batch_running", False):
            QMessageBox.information(self, "提示", "批量生成进行中，请等待完成或先停止批量任务。")
            return

        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        if not self._ensure_chapter_details():
            return

        chapters_struct = self._chapter_list()
        if not chapters_struct:
            QMessageBox.warning(self, "提示", "请先完成步骤3并确保章节列表为结构化JSON。")
            return
        idx = self.chapter_selector.currentIndex()
        if idx < 0 or idx >= len(chapters_struct):
            QMessageBox.warning(self, "提示", "请选择有效的章节。")
            return

        try:
            detail = self.chapter_details[idx] if idx < len(self.chapter_details) else None
        except Exception:
            detail = None
        if not isinstance(detail, dict) or not isinstance(detail.get("structured"), dict):
            QMessageBox.warning(self, "提示", "当前章节没有可补写的结构化结果，请先生成并保存。")
            return

        gh = self.project_manager.current_project.generation_history if self.project_manager.current_project else None
        conv = None
        try:
            if gh and isinstance(getattr(gh, "step4_conversations", None), dict):
                conv = gh.step4_conversations.get(str(idx))
        except Exception:
            conv = None
        if not isinstance(conv, list) or not conv:
            QMessageBox.warning(self, "提示", "未找到该章节的对话上下文，无法进行字数补偿。请先发送/生成该章节。")
            return

        # 注意：step_parameters 是 UI 运行态缓存，可能缺少 cn_char_min/max（例如：直接加载已保存指令后发送）。
        # 字数补偿必须以“原章节生成时的 parameters”为主，否则 StepGenerator 会因为 min_cn<=0 而直接返回不调用 LLM。
        params: dict = {}
        try:
            if isinstance(detail.get("parameters"), dict):
                params.update(detail.get("parameters") or {})
        except Exception:
            params = {}
        try:
            step4_cache = self.step_parameters.get("step4")
            if isinstance(step4_cache, dict):
                # 允许覆盖运行期的 max_tokens 等，但不要把关键字数目标冲掉
                for k, v in step4_cache.items():
                    if k in {"cn_char_min", "cn_char_max", "target_words", "target_words_boosted"}:
                        continue
                    params[k] = v
        except Exception:
            pass

        params["chapter_index"] = idx
        params["max_tokens"] = self._get_step_max_tokens("step4")

        # 若缺少 cn_char_min/max，则按章节 estimated_words 与 step4_word_boost_factor 兜底计算
        try:
            min_cn = int(params.get("cn_char_min") or 0)
            max_cn = int(params.get("cn_char_max") or 0)
        except Exception:
            min_cn, max_cn = 0, 0

        if min_cn <= 0 or max_cn <= 0:
            chapter_info = chapters_struct[idx] if 0 <= idx < len(chapters_struct) else {}
            try:
                target_words = int(
                    chapter_info.get("estimated_words")
                    or chapter_info.get("target_words")
                    or params.get("target_words")
                    or 0
                )
            except Exception:
                target_words = 0

            story_cfg = self._story_dict() or {}
            try:
                boost = float(story_cfg.get("step4_word_boost_factor", params.get("step4_word_boost_factor", 1.0)) or 1.0)
            except Exception:
                boost = 1.5
            if boost < 1.0:
                boost = 1.0
            if boost > 3.0:
                boost = 3.0

            boosted = 0
            if target_words > 0:
                boosted = max(1, int(round(target_words * boost)))
                tol = max(30, int(boosted * 0.05))
                min_cn = max(1, boosted - tol)
                max_cn = boosted + tol

            if min_cn > 0 and max_cn > 0:
                params["target_words"] = target_words
                params["step4_word_boost_factor"] = boost
                params["target_words_boosted"] = boosted
                params["cn_char_min"] = min_cn
                params["cn_char_max"] = max_cn
                params["enforce_cn_char_count"] = True

        # 用 structured 实时计算一次当前字数，便于判断是否真的发生了补写
        before_cn = None
        try:
            if self.step_generator and hasattr(self.step_generator, "_count_cn_chars_in_chapter_struct"):
                before_cn = int(self.step_generator._count_cn_chars_in_chapter_struct(detail.get("structured")))
        except Exception:
            before_cn = None

        def _task():
            return self.step_generator.continue_chapter_detail_word_compensation(detail, params, conversation=list(conv))

        def _on_success(updated):
            try:
                updated = self.step_generator._normalize_chapter_detail(updated)
            except Exception:
                pass

            # 若未触发任何续写（通常是 min_cn 缺失或已经达标），给出明确提示而不是假装补写成功
            try:
                after_cn = None
                if self.step_generator and isinstance(updated, dict) and isinstance(updated.get("structured"), dict):
                    after_cn = int(self.step_generator._count_cn_chars_in_chapter_struct(updated.get("structured")))
                if before_cn is not None and after_cn is not None and after_cn <= before_cn:
                    QMessageBox.information(self, "提示", "字数补偿未触发续写：当前文本量可能已达标，或缺少目标字数参数。")
            except Exception:
                pass

            while len(self.chapter_details) <= idx:
                self.chapter_details.append({})
            self.chapter_details[idx] = updated
            self.step4_result.setPlainText(self._format_preview(updated))
            self._update_step4_word_stats_from_detail(idx, updated)
            self.project_manager.update_generation_step("step4_chapter_details", self.chapter_details)

            # 保存更新后的章节会话
            try:
                new_conv = updated.get("conversation") if isinstance(updated, dict) else None
                if isinstance(new_conv, list):
                    step4_convs = dict(getattr(gh, "step4_conversations", {}) or {}) if gh else {}
                    step4_convs[str(idx)] = new_conv
                    self.project_manager.update_generation_history_field("step4_conversations", step4_convs)
            except Exception:
                pass

            self.step4_status.setText(f"状态：第{idx+1}章已补写")
            self.modified.emit()

        self._run_async(self.step4_status, f"状态：第{idx+1}章补写中", _task, _on_success)

    def _manual_result_payload(self, text: str, parameters: dict | None, extra: dict | None = None) -> dict:
        payload = {
            "raw_response": text,
            "structured": self._try_parse_json_block(text),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "parameters": parameters or {},
        }
        if extra:
            payload.update(extra)
        return payload

    # ==================== 步骤1：人设 ====================

    def prepare_personas(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        self._sync_project_configs()
        story_config = self._story_dict()
        characters = self._characters_dict()
        instruction, params = self.step_generator.prepare_personas_instruction(story_config, characters)
        params = dict(params or {})
        params["max_tokens"] = self._get_step_max_tokens("step1")
        self.step1_group._instruction.setPlainText(instruction)
        self.step1_group._status.setText("状态：指令已生成，请先保存指令再发送")
        self.step_parameters["step1"] = params
        self._record_instruction("generate_personas_prepare", instruction, params, None, "pending")
        self.modified.emit()

    def send_personas(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        params = dict(self.step_parameters.get("step1") or {})
        params["max_tokens"] = self._get_step_max_tokens("step1")

        def _start_send(instruction: str):
            def _task():
                # step1 作为 master_conversation 的起点：重新开一段对话上下文
                return self.step_generator.generate_personas(instruction, params, conversation=[])

            def _on_success(result):
                self.personas_data = result
                self.step1_group._result.setPlainText(self._format_preview(result))
                self.project_manager.update_generation_step("step1_personas", result)
                # 保存 step1 对话快照（用于 step2 重新生成的上下文起点）
                try:
                    conv = result.get("conversation") if isinstance(result, dict) else None
                    if isinstance(conv, list):
                        self.project_manager.update_generation_history_field("master_conversation", conv)
                        self.project_manager.update_generation_history_field("master_conversation_after_step1", conv)
                        # step1 发生变化时，后续步骤的快照/续写上下文都不再可靠，清空即可避免误用
                        self.project_manager.update_generation_history_field("master_conversation_after_step2", [])
                        self.project_manager.update_generation_history_field("master_conversation_after_step3", [])
                        self.project_manager.update_generation_history_field("step4_conversations", {})
                except Exception:
                    pass
                self._record_instruction("generate_personas", instruction, params, result, "success")
                self.step1_group._status.setText("状态：已生成")
                self.modified.emit()

            self._run_async(self.step1_group._status, "状态：生成中", _task, _on_success)

        self._ensure_send_uses_saved_instruction_async(
            "step1",
            self.step1_group._instruction,
            status_label=self.step1_group._status,
            on_ready=_start_send,
        )

    def save_personas_result(self):
        if not self._ensure_project():
            return
        text = self.step1_group._result.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有可保存的内容。")
            return
        params = self.step_parameters.get("step1")
        parsed = self._try_parse_json_block(text) or self._safe_json_load(text)
        if isinstance(parsed, dict):
            data = self._normalize_step_payload(parsed) or parsed
            data.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            if not isinstance(data.get("parameters"), dict):
                data["parameters"] = params or {}
            else:
                data["parameters"].update(params or {})
        else:
            data = self._manual_result_payload(text, params)
        self.personas_data = data
        self.project_manager.update_generation_step("step1_personas", data)

        # 用户手动修订了 step1 结果：下游步骤的对话快照/续写上下文可能不再可靠，清空避免误用。
        try:
            self.project_manager.update_generation_history_field("master_conversation_after_step2", [])
            self.project_manager.update_generation_history_field("master_conversation_after_step3", [])
            self.project_manager.update_generation_history_field("step4_conversations", {})
        except Exception:
            pass

        self.step1_group._status.setText("状态：已保存(手动)")
        self._record_instruction("manual_save_personas", "用户手动保存人设", {}, data, "success")
        self.modified.emit()

    # ==================== 步骤2：大纲 ====================

    def prepare_outline(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        self._sync_project_configs()
        if not self.personas_data and not self.project_manager.current_project.generation_history.step1_personas:
            QMessageBox.warning(self, "提示", "请先完成步骤1：角色人设。")
            return
        story_config = self._story_dict()
        personas = self.personas_data or self.project_manager.current_project.generation_history.step1_personas
        use_ctx = False
        try:
            gh = self.project_manager.current_project.generation_history if self.project_manager.current_project else None
            use_ctx = bool(
                gh
                and isinstance(getattr(gh, "master_conversation_after_step1", None), list)
                and gh.master_conversation_after_step1
            )
        except Exception:
            use_ctx = False
        instruction, params = self.step_generator.prepare_outline_instruction(
            story_config,
            personas or {},
            use_conversation_context=use_ctx,
        )
        params = dict(params or {})
        params["max_tokens"] = self._get_step_max_tokens("step2")
        self.step2_group._instruction.setPlainText(instruction)
        self.step2_group._status.setText("状态：指令已生成，请先保存指令再发送")
        self.step_parameters["step2"] = params
        self._record_instruction("generate_outline_prepare", instruction, params, None, "pending")
        self.modified.emit()

    def send_outline(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        params = dict(self.step_parameters.get("step2") or {})
        params["max_tokens"] = self._get_step_max_tokens("step2")

        def _start_send(instruction: str):
            def _task():
                conv = []
                try:
                    gh = self.project_manager.current_project.generation_history if self.project_manager.current_project else None
                    # step2 重新生成：只允许使用 step1 完成后的快照，不携带旧的 step2 对话
                    if (
                        gh
                        and isinstance(getattr(gh, "master_conversation_after_step1", None), list)
                        and gh.master_conversation_after_step1
                    ):
                        conv = list(gh.master_conversation_after_step1)
                    else:
                        # 兼容旧工程：若没有对话历史，则从 step1 结果回填上下文
                        step1 = gh.step1_personas if gh else None
                        raw1 = (step1 or {}).get("raw_response") if isinstance(step1, dict) else None
                        if isinstance(raw1, str) and raw1.strip():
                            conv = [{"role": "user", "content": "以下是已生成的角色人设，请记住并在后续生成中保持一致：\n" + raw1.strip()}]

                    # 关键修正：用户可能手动编辑并“保存结果”了 step1_personas。
                    # 为确保 step2 使用最新的人设（而不是旧的对话快照里的人设），这里追加一条补充消息。
                    step1_latest = gh.step1_personas if gh else None
                    raw_latest = (step1_latest or {}).get("raw_response") if isinstance(step1_latest, dict) else None
                    self._append_latest_raw_response_to_conv(conv, raw_latest, title="人设（用于生成大纲）")
                except Exception:
                    conv = []
                return self.step_generator.generate_outline(instruction, params, conversation=conv)

            def _on_success(result):
                self.outline_data = result
                self.step2_group._result.setPlainText(self._format_preview(result))
                self.project_manager.update_generation_step("step2_outline", result)
                # 保存 step2 对话快照（用于 step3 重新生成的上下文起点）
                try:
                    conv = result.get("conversation") if isinstance(result, dict) else None
                    if isinstance(conv, list):
                        self.project_manager.update_generation_history_field("master_conversation", conv)
                        self.project_manager.update_generation_history_field("master_conversation_after_step2", conv)
                        # step2 发生变化时，step3/step4 相关快照/续写上下文不再可靠
                        self.project_manager.update_generation_history_field("master_conversation_after_step3", [])
                        self.project_manager.update_generation_history_field("step4_conversations", {})
                except Exception:
                    pass
                self._record_instruction("generate_outline", instruction, params, result, "success")
                self.step2_group._status.setText("状态：已生成")
                self.modified.emit()

            self._run_async(self.step2_group._status, "状态：生成中", _task, _on_success)

        self._ensure_send_uses_saved_instruction_async(
            "step2",
            self.step2_group._instruction,
            status_label=self.step2_group._status,
            on_ready=_start_send,
        )

    def save_outline_result(self):
        if not self._ensure_project():
            return
        text = self.step2_group._result.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有可保存的内容。")
            return
        params = self.step_parameters.get("step2")
        parsed = self._try_parse_json_block(text) or self._safe_json_load(text)
        if isinstance(parsed, dict):
            data = self._normalize_step_payload(parsed) or parsed
            data.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            if not isinstance(data.get("parameters"), dict):
                data["parameters"] = params or {}
            else:
                data["parameters"].update(params or {})
        else:
            data = self._manual_result_payload(text, params)
        self.outline_data = data
        self.project_manager.update_generation_step("step2_outline", data)

        # 用户手动修订了 step2 结果：step3/step4 的对话快照可能不再可靠，清空避免误用。
        try:
            self.project_manager.update_generation_history_field("master_conversation_after_step2", [])
            self.project_manager.update_generation_history_field("master_conversation_after_step3", [])
            self.project_manager.update_generation_history_field("step4_conversations", {})
        except Exception:
            pass

        self.step2_group._status.setText("状态：已保存(手动)")
        self._record_instruction("manual_save_outline", "用户手动保存大纲", {}, data, "success")
        self.modified.emit()

    # ==================== 步骤3：章节列表 ====================

    def prepare_chapters(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        self._sync_project_configs()
        if not self.outline_data and not self.project_manager.current_project.generation_history.step2_outline:
            QMessageBox.warning(self, "提示", "请先完成步骤2：故事大纲。")
            return
        story_config = self._story_dict()
        characters = self._characters_dict()
        outline = self.outline_data or self.project_manager.current_project.generation_history.step2_outline
        use_ctx = False
        try:
            gh = self.project_manager.current_project.generation_history if self.project_manager.current_project else None
            use_ctx = bool(
                gh
                and isinstance(getattr(gh, "master_conversation_after_step2", None), list)
                and gh.master_conversation_after_step2
            )
        except Exception:
            use_ctx = False
        instruction, params = self.step_generator.prepare_chapters_instruction(
            story_config,
            outline or {},
            character_config=characters,
            use_conversation_context=use_ctx,
        )
        params = dict(params or {})
        params["max_tokens"] = self._get_step_max_tokens("step3")
        self.step3_group._instruction.setPlainText(instruction)
        self.step3_group._status.setText("状态：指令已生成，请先保存指令再发送")
        self.step_parameters["step3"] = params
        self._record_instruction("generate_chapters_prepare", instruction, params, None, "pending")
        self.modified.emit()

    def send_chapters(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        params = dict(self.step_parameters.get("step3") or {})
        params["max_tokens"] = self._get_step_max_tokens("step3")

        def _start_send(instruction: str):
            def _task():
                conv = []
                try:
                    gh = self.project_manager.current_project.generation_history if self.project_manager.current_project else None
                    # step3 重新生成：只允许使用 step2 完成后的快照，不携带旧的 step3 对话
                    if (
                        gh
                        and isinstance(getattr(gh, "master_conversation_after_step2", None), list)
                        and gh.master_conversation_after_step2
                    ):
                        conv = list(gh.master_conversation_after_step2)
                    else:
                        # 兼容旧工程：用 step1/step2 raw_response 回填上下文（保证步骤三能看到人设+大纲）
                        seed: list[dict] = []
                        step1 = getattr(gh, "step1_personas", None) if gh else None
                        raw1 = (step1 or {}).get("raw_response") if isinstance(step1, dict) else None
                        if isinstance(raw1, str) and raw1.strip():
                            seed.append({"role": "user", "content": "以下是已生成的角色人设，请记住并在后续章节规划中保持一致：\n" + raw1.strip()})
                        step2 = getattr(gh, "step2_outline", None) if gh else None
                        raw2 = (step2 or {}).get("raw_response") if isinstance(step2, dict) else None
                        if isinstance(raw2, str) and raw2.strip():
                            seed.append({"role": "user", "content": "以下是已生成的故事大纲，请记住并在后续章节规划中严格对齐：\n" + raw2.strip()})
                        conv = seed

                    # 关键修正：若用户手动修订并保存了 step1/step2 结果，确保 step3 发送时使用最新版本。
                    step1_latest = getattr(gh, "step1_personas", None) if gh else None
                    raw1_latest = (step1_latest or {}).get("raw_response") if isinstance(step1_latest, dict) else None
                    self._append_latest_raw_response_to_conv(conv, raw1_latest, title="人设（用于生成章节列表）")

                    step2_latest = getattr(gh, "step2_outline", None) if gh else None
                    raw2_latest = (step2_latest or {}).get("raw_response") if isinstance(step2_latest, dict) else None
                    self._append_latest_raw_response_to_conv(conv, raw2_latest, title="大纲（用于生成章节列表）")
                except Exception:
                    conv = []
                return self.step_generator.generate_chapters(instruction, params, conversation=conv)

            def _on_success(result):
                self.chapters_data = result
                self.step3_group._result.setPlainText(self._format_preview(result))
                self.project_manager.update_generation_step("step3_chapters", result)
                # 保存 step3 对话快照（用于 step4 重新生成的上下文起点）
                try:
                    conv = result.get("conversation") if isinstance(result, dict) else None
                    if isinstance(conv, list):
                        self.project_manager.update_generation_history_field("master_conversation", conv)
                        self.project_manager.update_generation_history_field("master_conversation_after_step3", conv)
                        # step3 发生变化时，step4 的续写上下文可能不再匹配，清空避免误用
                        self.project_manager.update_generation_history_field("step4_conversations", {})
                except Exception:
                    pass
                self._record_instruction("generate_chapters", instruction, params, result, "success")
                self.step3_group._status.setText("状态：已生成")
                self._refresh_chapter_selector()
                self.modified.emit()

            self._run_async(self.step3_group._status, "状态：生成中", _task, _on_success)

        self._ensure_send_uses_saved_instruction_async(
            "step3",
            self.step3_group._instruction,
            status_label=self.step3_group._status,
            on_ready=_start_send,
        )

    def save_chapters_result(self):
        if not self._ensure_project():
            return
        text = self.step3_group._result.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有可保存的内容。")
            return
        params = self.step_parameters.get("step3")
        parsed = self._try_parse_json_block(text) or self._safe_json_load(text)
        if isinstance(parsed, dict):
            data = self._normalize_step_payload(parsed) or parsed
            data.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            if not isinstance(data.get("parameters"), dict):
                data["parameters"] = params or {}
            else:
                data["parameters"].update(params or {})
        else:
            data = self._manual_result_payload(text, params)
        self.chapters_data = data
        self.project_manager.update_generation_step("step3_chapters", data)

        # 用户手动修订了 step3 结果：step4 的续写上下文可能不再匹配，清空避免误用。
        try:
            self.project_manager.update_generation_history_field("master_conversation_after_step3", [])
            self.project_manager.update_generation_history_field("step4_conversations", {})
        except Exception:
            pass

        self.step3_group._status.setText("状态：已保存(手动)")
        self._record_instruction("manual_save_chapters", "用户手动保存章节列表", {}, data, "success")
        self._refresh_chapter_selector()
        self.modified.emit()

    # ==================== 步骤4：章节详细内容 ====================

    def prepare_chapter_detail(self):
        if getattr(self, "_step4_batch_running", False):
            QMessageBox.information(self, "提示", "批量生成进行中，请等待完成或先停止批量任务。")
            return
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        self._sync_project_configs()
        chapters_struct = self._chapter_list()
        if not chapters_struct:
            QMessageBox.warning(self, "提示", "请先完成步骤3并确保章节列表为结构化JSON。")
            return
        idx = self.chapter_selector.currentIndex()
        if idx < 0 or idx >= len(chapters_struct):
            QMessageBox.warning(self, "提示", "请选择有效的章节。")
            return
        chapter_info = chapters_struct[idx]
        prev_context = None
        if idx > 0:
            prev = chapters_struct[idx - 1]
            prev_context = prev.get("summary") or prev.get("chapter_summary")
        chapters_plan = None
        try:
            if isinstance(self.chapters_data, dict):
                s = self.chapters_data.get("structured")
                if isinstance(s, dict) and isinstance(s.get("chapters"), list):
                    chapters_plan = s
                elif isinstance(s, list):
                    chapters_plan = {"chapters": s}
        except Exception:
            chapters_plan = None

        personas = self.personas_data or self.project_manager.current_project.generation_history.step1_personas

        use_ctx = False
        try:
            gh = self.project_manager.current_project.generation_history if self.project_manager.current_project else None
            use_ctx = bool(
                gh
                and isinstance(getattr(gh, "master_conversation_after_step3", None), list)
                and gh.master_conversation_after_step3
            )
        except Exception:
            use_ctx = False

        instruction, params = self.step_generator.prepare_chapter_detail_instruction(
            idx,
            chapter_info,
            prev_context,
            self._story_dict(),
            self._characters_dict(),
            personas,
            chapters_plan,
            use_conversation_context=use_ctx,
        )
        params = dict(params or {})
        params["max_tokens"] = self._get_step_max_tokens("step4")
        self.step4_instruction.setPlainText(instruction)
        self.step4_status.setText(f"状态：第{idx+1}章指令已生成，请先保存指令再发送")
        self._update_step4_word_stats_from_params(idx, params)
        self.step_parameters["step4"] = params
        self._record_instruction("generate_chapter_detail_prepare", instruction, params, None, "pending")
        self.modified.emit()

    def send_chapter_detail(self):
        if getattr(self, "_step4_batch_running", False):
            QMessageBox.information(self, "提示", "批量生成进行中，请等待完成或先停止批量任务。")
            return
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        self._sync_project_configs()
        chapters_struct = self._chapter_list()
        if not chapters_struct:
            QMessageBox.warning(self, "提示", "请先完成步骤3并确保章节列表为结构化JSON。")
            return
        idx = self.chapter_selector.currentIndex()
        if idx < 0 or idx >= len(chapters_struct):
            QMessageBox.warning(self, "提示", "请选择有效的章节。")
            return
        params = dict(self.step_parameters.get("step4") or {"chapter_index": idx})
        params["chapter_index"] = idx
        params["max_tokens"] = self._get_step_max_tokens("step4")

        def _start_send(instruction: str):
            def _task():
                conv = []
                try:
                    gh = self.project_manager.current_project.generation_history if self.project_manager.current_project else None
                    # step4 重新生成：默认不复用该章旧 step4 对话（避免“带着旧详稿继续写”的污染）
                    # 只有“字数补偿”按钮才会显式使用 step4_conversations[idx]
                    if (
                        gh
                        and isinstance(getattr(gh, "master_conversation_after_step3", None), list)
                        and gh.master_conversation_after_step3
                    ):
                        conv = list(gh.master_conversation_after_step3)
                    else:
                        # 兼容旧工程：用 step1-3 raw_response 回填上下文
                        seed: list[dict] = []
                        step1 = getattr(gh, "step1_personas", None) if gh else None
                        raw1 = (step1 or {}).get("raw_response") if isinstance(step1, dict) else None
                        if isinstance(raw1, str) and raw1.strip():
                            seed.append({"role": "user", "content": "以下是已生成的角色人设，请记住并在后续章节写作中保持一致：\n" + raw1.strip()})
                        step2 = getattr(gh, "step2_outline", None) if gh else None
                        raw2 = (step2 or {}).get("raw_response") if isinstance(step2, dict) else None
                        if isinstance(raw2, str) and raw2.strip():
                            seed.append({"role": "user", "content": "以下是已生成的故事大纲，请严格对齐：\n" + raw2.strip()})
                        step3 = getattr(gh, "step3_chapters", None) if gh else None
                        raw3 = (step3 or {}).get("raw_response") if isinstance(step3, dict) else None
                        if isinstance(raw3, str) and raw3.strip():
                            seed.append({"role": "user", "content": "以下是已生成的章节规划/分支计划，请严格遵守：\n" + raw3.strip()})
                        conv = seed

                    # 关键修正：若用户手动修订并保存了 step1~step3 结果，确保 step4 发送时使用最新版本。
                    step1_latest = getattr(gh, "step1_personas", None) if gh else None
                    raw1_latest = (step1_latest or {}).get("raw_response") if isinstance(step1_latest, dict) else None
                    self._append_latest_raw_response_to_conv(conv, raw1_latest, title="人设（用于生成章节详稿）")

                    step2_latest = getattr(gh, "step2_outline", None) if gh else None
                    raw2_latest = (step2_latest or {}).get("raw_response") if isinstance(step2_latest, dict) else None
                    self._append_latest_raw_response_to_conv(conv, raw2_latest, title="大纲（用于生成章节详稿）")

                    step3_latest = getattr(gh, "step3_chapters", None) if gh else None
                    raw3_latest = (step3_latest or {}).get("raw_response") if isinstance(step3_latest, dict) else None
                    self._append_latest_raw_response_to_conv(conv, raw3_latest, title="章节规划/分支计划（用于生成章节详稿）")
                except Exception:
                    conv = []
                return self.step_generator.generate_chapter_detail(instruction, params, conversation=conv)

            def _on_success(detail):
                # 兼容 LLM 输出带噪导致 structured=None：尽量做一次规范化
                try:
                    detail = self.step_generator._normalize_chapter_detail(detail)
                except Exception:
                    pass
                while len(self.chapter_details) <= idx:
                    self.chapter_details.append({})
                self.chapter_details[idx] = detail
                self.step4_result.setPlainText(self._format_preview(detail))
                self._update_step4_word_stats_from_detail(idx, detail)
                self.project_manager.update_generation_step("step4_chapter_details", self.chapter_details)
                # 保存 step4 对话历史（用于字数补偿续写/可复现）
                try:
                    conv = detail.get("conversation") if isinstance(detail, dict) else None
                    if isinstance(conv, list):
                        gh = self.project_manager.current_project.generation_history if self.project_manager.current_project else None
                        step4_convs = dict(getattr(gh, "step4_conversations", {}) or {}) if gh else {}
                        step4_convs[str(idx)] = conv
                        self.project_manager.update_generation_history_field("step4_conversations", step4_convs)
                except Exception:
                    pass
                self._record_instruction("generate_chapter_detail", instruction, params, detail, "success")
                self.step4_status.setText(f"状态：第{idx+1}章已生成")
                self.modified.emit()

            self._run_async(self.step4_status, f"状态：第{idx+1}章生成中", _task, _on_success)

        self._ensure_send_uses_saved_instruction_async(
            "step4",
            self.step4_instruction,
            chapter_index=idx,
            status_label=self.step4_status,
            on_ready=_start_send,
        )

    def save_chapter_detail(self):
        if not self._ensure_project():
            return
        chapters_struct = self._chapter_list()
        if not chapters_struct:
            QMessageBox.warning(self, "提示", "请先完成步骤3并选择章节。")
            return
        idx = self.chapter_selector.currentIndex()
        if idx < 0 or idx >= len(chapters_struct):
            QMessageBox.warning(self, "提示", "请选择有效的章节。")
            return
        text = self.step4_result.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有可保存的内容。")
            return
        params = self.step_parameters.get("step4") or {"chapter_index": idx}
        params["chapter_index"] = idx
        # 如果用户保存的是“已生成结果的JSON”，则尽量按原结构保存，避免覆盖/丢失 raw_response。
        parsed = self._try_parse_json_block(text) or self._safe_json_load(text)
        if isinstance(parsed, dict):
            detail = self._normalize_step_payload(parsed) or parsed
            detail.setdefault("chapter_index", idx)
            detail.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            # 确保 parameters 不丢
            if not isinstance(detail.get("parameters"), dict):
                detail["parameters"] = params
            else:
                detail["parameters"].update(params)
        else:
            detail = self._manual_result_payload(text, params, {"chapter_index": idx})
        while len(self.chapter_details) <= idx:
            self.chapter_details.append({})
        self.chapter_details[idx] = detail

        # 尝试补充/刷新 metrics.cn_char_count（用户手动编辑后也能看到对比）
        try:
            if self.step_generator and isinstance(detail, dict) and isinstance(detail.get("structured"), dict):
                cn_chars = int(self.step_generator._count_cn_chars_in_chapter_struct(detail.get("structured")))
                detail.setdefault("metrics", {})
                if isinstance(detail.get("metrics"), dict):
                    detail["metrics"]["cn_char_count"] = cn_chars
                self._update_step4_word_stats_from_detail(idx, detail)
        except Exception:
            pass

        self.project_manager.update_generation_step("step4_chapter_details", self.chapter_details)
        self.step4_status.setText(f"状态：第{idx+1}章已保存(手动)")
        self._record_instruction(
            "manual_save_chapter_detail",
            f"用户手动保存第{idx+1}章",
            {},
            detail,
            "success",
        )
        self.modified.emit()

    # ==================== Step4：批量生成（并行） ====================

    def _build_step4_batch_panel(self, parent_layout: QVBoxLayout) -> None:
        header_row = QHBoxLayout()

        self.step4_batch_toggle = QToolButton()
        self.step4_batch_toggle.setText("批量生成")
        self.step4_batch_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.step4_batch_toggle.setCheckable(True)
        self.step4_batch_toggle.setChecked(False)
        self.step4_batch_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.step4_batch_toggle.toggled.connect(self._toggle_step4_batch_panel)
        header_row.addWidget(self.step4_batch_toggle)

        self.step4_batch_status = QLabel("批量：未开始")
        self.step4_batch_status.setProperty("pill", "true")
        header_row.addWidget(self.step4_batch_status)

        header_row.addStretch(1)
        parent_layout.addLayout(header_row)

        self.step4_batch_panel = QFrame()
        self.step4_batch_panel.setProperty("card", "true")
        self.step4_batch_panel.setVisible(False)
        panel_layout = QVBoxLayout(self.step4_batch_panel)
        panel_layout.setContentsMargins(12, 10, 12, 10)
        panel_layout.setSpacing(8)

        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel("最大并行数："))
        self.step4_batch_parallel_spin = QSpinBox()
        self.step4_batch_parallel_spin.setRange(1, 32)
        self.step4_batch_parallel_spin.setValue(3)
        self.step4_batch_parallel_spin.setToolTip("批量生成时同时并行的章节数")
        ctrl_row.addWidget(self.step4_batch_parallel_spin)

        self.step4_batch_refresh_btn = QPushButton("刷新清单")
        self.step4_batch_refresh_btn.clicked.connect(lambda: self._refresh_step4_batch_task_table(preserve_checks=True))
        ctrl_row.addWidget(self.step4_batch_refresh_btn)

        self.step4_batch_start_btn = QPushButton("开始批量生成")
        self.step4_batch_start_btn.clicked.connect(self.start_step4_batch_generation)
        ctrl_row.addWidget(self.step4_batch_start_btn)

        self.step4_batch_stop_btn = QPushButton("停止批量")
        self.step4_batch_stop_btn.clicked.connect(self.stop_step4_batch_generation)
        ctrl_row.addWidget(self.step4_batch_stop_btn)

        ctrl_row.addStretch(1)
        panel_layout.addLayout(ctrl_row)

        self.step4_batch_table = QTableWidget(0, 3)
        self.step4_batch_table.setHorizontalHeaderLabels(["章节", "状态", "已耗时(s)"])
        self.step4_batch_table.verticalHeader().setVisible(False)
        try:
            self.step4_batch_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            self.step4_batch_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            self.step4_batch_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        except Exception:
            pass
        self.step4_batch_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.step4_batch_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.step4_batch_table.setWordWrap(False)
        # 列表高度调大一些：默认至少显示 12 行
        self._set_table_min_rows(self.step4_batch_table, 12)
        panel_layout.addWidget(self.step4_batch_table)

        parent_layout.addWidget(self.step4_batch_panel)

        # 初次构建时尝试填充
        self._refresh_step4_batch_task_table(preserve_checks=False)

    def _toggle_step4_batch_panel(self, expanded: bool) -> None:
        try:
            self.step4_batch_panel.setVisible(bool(expanded))
            self.step4_batch_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        except Exception:
            return

    def _refresh_step4_batch_task_table(self, *, preserve_checks: bool) -> None:
        chapters = self._chapter_list()
        if not isinstance(chapters, list) or not chapters:
            self._step4_batch_row_by_idx = {}
            try:
                self.step4_batch_table.setRowCount(0)
            except Exception:
                pass
            return

        prev_checks: dict[int, bool] = {}
        if preserve_checks and self._step4_batch_row_by_idx:
            try:
                for idx, row in (self._step4_batch_row_by_idx or {}).items():
                    it = self.step4_batch_table.item(int(row), 0)
                    if it is not None:
                        prev_checks[int(idx)] = it.checkState() == Qt.CheckState.Checked
            except Exception:
                prev_checks = {}

        self.step4_batch_table.setRowCount(len(chapters))
        self._step4_batch_row_by_idx = {}
        for idx, ch in enumerate(chapters):
            title = ch.get("chapter_title") or ch.get("title") or f"第{idx+1}章"

            first = QTableWidgetItem(f"{idx+1}. {title}")
            first.setData(Qt.ItemDataRole.UserRole, int(idx))
            first.setFlags(first.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            first.setCheckState(Qt.CheckState.Checked if prev_checks.get(int(idx), True) else Qt.CheckState.Unchecked)

            status = QTableWidgetItem("待生成")
            elapsed = QTableWidgetItem("-")

            self.step4_batch_table.setItem(idx, 0, first)
            self.step4_batch_table.setItem(idx, 1, status)
            self.step4_batch_table.setItem(idx, 2, elapsed)
            self._step4_batch_row_by_idx[int(idx)] = int(idx)

        try:
            self.step4_batch_table.resizeRowsToContents()
        except Exception:
            pass

    def _selected_step4_batch_indices(self) -> list[int]:
        selected: list[int] = []
        try:
            for row in range(self.step4_batch_table.rowCount()):
                it = self.step4_batch_table.item(row, 0)
                if it is None:
                    continue
                if it.checkState() != Qt.CheckState.Checked:
                    continue
                idx = it.data(Qt.ItemDataRole.UserRole)
                try:
                    selected.append(int(idx))
                except Exception:
                    continue
        except Exception:
            return []
        return sorted(set(selected))

    def start_step4_batch_generation(self) -> None:
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        if self._active_worker:
            QMessageBox.information(self, "提示", "当前有单章任务进行中，请先等待完成或停止。")
            return
        if self._step4_batch_running:
            QMessageBox.information(self, "提示", "批量生成已在运行中。")
            return

        self._sync_project_configs()

        chapters_struct = self._chapter_list()
        if not chapters_struct:
            QMessageBox.warning(self, "提示", "请先完成步骤3并确保章节列表为结构化JSON。")
            return

        selected = self._selected_step4_batch_indices()
        if not selected:
            QMessageBox.information(self, "提示", "请先在任务清单中勾选要生成的章节。")
            return

        max_workers = int(self.step4_batch_parallel_spin.value() or 1)
        if max_workers <= 0:
            max_workers = 1

        story_cfg = self._story_dict()
        characters = self._characters_dict()
        personas = self.personas_data or (self.project_manager.current_project.generation_history.step1_personas if self.project_manager.current_project else None)

        chapters_plan = None
        try:
            if isinstance(self.chapters_data, dict):
                s = self.chapters_data.get("structured")
                if isinstance(s, dict) and isinstance(s.get("chapters"), list):
                    chapters_plan = s
                elif isinstance(s, list):
                    chapters_plan = {"chapters": s}
        except Exception:
            chapters_plan = None

        # 基础对话上下文（与 send_chapter_detail 口径一致）
        conv_seed: list[dict] = []
        try:
            gh = self.project_manager.current_project.generation_history if self.project_manager.current_project else None
            if gh and isinstance(getattr(gh, "master_conversation_after_step3", None), list) and gh.master_conversation_after_step3:
                conv_seed = list(gh.master_conversation_after_step3)
            else:
                seed: list[dict] = []
                step1 = getattr(gh, "step1_personas", None) if gh else None
                raw1 = (step1 or {}).get("raw_response") if isinstance(step1, dict) else None
                if isinstance(raw1, str) and raw1.strip():
                    seed.append({"role": "user", "content": "以下是已生成的角色人设，请记住并在后续章节写作中保持一致：\n" + raw1.strip()})
                step2 = getattr(gh, "step2_outline", None) if gh else None
                raw2 = (step2 or {}).get("raw_response") if isinstance(step2, dict) else None
                if isinstance(raw2, str) and raw2.strip():
                    seed.append({"role": "user", "content": "以下是已生成的故事大纲，请严格对齐：\n" + raw2.strip()})
                step3 = getattr(gh, "step3_chapters", None) if gh else None
                raw3 = (step3 or {}).get("raw_response") if isinstance(step3, dict) else None
                if isinstance(raw3, str) and raw3.strip():
                    seed.append({"role": "user", "content": "以下是已生成的章节规划/分支计划，请严格遵守：\n" + raw3.strip()})
                conv_seed = seed

            step1_latest = getattr(gh, "step1_personas", None) if gh else None
            raw1_latest = (step1_latest or {}).get("raw_response") if isinstance(step1_latest, dict) else None
            self._append_latest_raw_response_to_conv(conv_seed, raw1_latest, title="人设（用于生成章节详稿）")
            step2_latest = getattr(gh, "step2_outline", None) if gh else None
            raw2_latest = (step2_latest or {}).get("raw_response") if isinstance(step2_latest, dict) else None
            self._append_latest_raw_response_to_conv(conv_seed, raw2_latest, title="大纲（用于生成章节详稿）")
            step3_latest = getattr(gh, "step3_chapters", None) if gh else None
            raw3_latest = (step3_latest or {}).get("raw_response") if isinstance(step3_latest, dict) else None
            self._append_latest_raw_response_to_conv(conv_seed, raw3_latest, title="章节规划/分支计划（用于生成章节详稿）")
        except Exception:
            conv_seed = []

        # 为每章准备 instruction/params（params 始终来自 prepare；instruction 优先使用已保存版本）
        prepared: dict[int, tuple[str, dict]] = {}
        for idx in selected:
            if idx < 0 or idx >= len(chapters_struct):
                continue
            chapter_info = chapters_struct[idx]
            prev_context = None
            if idx > 0:
                prev = chapters_struct[idx - 1]
                prev_context = prev.get("summary") or prev.get("chapter_summary")

            instruction_new, params = self.step_generator.prepare_chapter_detail_instruction(
                idx,
                chapter_info,
                prev_context,
                story_cfg,
                characters,
                personas,
                chapters_plan,
                use_conversation_context=bool(conv_seed),
            )
            params = dict(params or {})
            params["max_tokens"] = self._get_step_max_tokens("step4")

            saved = self._saved_instruction_for_step4(idx)
            if not saved:
                try:
                    self._set_saved_instruction_for_step4(idx, instruction_new)
                    self._saved_step4_instruction_cache[idx] = instruction_new
                except Exception:
                    pass
                instruction_use = instruction_new
            else:
                instruction_use = saved
            prepared[int(idx)] = (instruction_use, params)

        if not prepared:
            QMessageBox.information(self, "提示", "未找到可生成的章节任务。")
            return

        self._step4_batch_running = True
        self._step4_batch_stop_requested = False
        self._step4_batch_total = len(prepared)
        self._step4_batch_task_meta = {}
        self.step4_batch_status.setText(f"批量：运行中 0/{self._step4_batch_total}")

        # 标记选中行状态
        for idx in prepared.keys():
            row = self._step4_batch_row_by_idx.get(int(idx))
            if row is None:
                continue
            st = self.step4_batch_table.item(row, 1)
            el = self.step4_batch_table.item(row, 2)
            if st is not None:
                st.setText("排队")
                st.setToolTip("")
            if el is not None:
                el.setText("-")

        self._step4_batch_update_timer.start()
        self._step4_batch_executor = ThreadPoolExecutor(max_workers=max_workers)

        def _submit(chapter_index: int, instruction: str, params: dict):
            def _task():
                if self._step4_batch_stop_requested:
                    raise RuntimeError("batch_stop_requested")
                self._step4_batch_signals.started.emit(int(chapter_index))
                start = time.perf_counter()
                sg = StepGenerator(self.config_manager)
                res = sg.generate_chapter_detail(instruction, params, conversation=list(conv_seed))
                elapsed = float(time.perf_counter() - start)
                return res, elapsed

            def _done(fut):
                try:
                    res, elapsed = fut.result()
                    self._step4_batch_signals.finished.emit(int(chapter_index), res, float(elapsed))
                except Exception as exc:  # noqa: BLE001
                    self._step4_batch_signals.failed.emit(int(chapter_index), str(exc))

            future = self._step4_batch_executor.submit(_task)
            future.add_done_callback(_done)

        for idx, (instruction, params) in prepared.items():
            _submit(int(idx), instruction, dict(params))

    def stop_step4_batch_generation(self, *, silent: bool = False) -> None:
        if not self._step4_batch_running:
            if not silent:
                QMessageBox.information(self, "提示", "批量生成未在运行。")
            return

        if not silent:
            confirm = QMessageBox.question(
                self,
                "确认停止批量",
                "将停止继续排队新章节（已开始的章节可能仍会继续运行至结束）。\n确定要停止吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        self._step4_batch_stop_requested = True
        try:
            self.step4_batch_status.setText("批量：停止中")
        except Exception:
            pass
        try:
            if self._step4_batch_executor is not None:
                try:
                    self._step4_batch_executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    self._step4_batch_executor.shutdown(wait=False)
        except Exception:
            pass
        self._step4_batch_executor = None
        self._step4_batch_running = False
        try:
            self._step4_batch_update_timer.stop()
        except Exception:
            pass

    def _on_step4_batch_task_started(self, chapter_index: int) -> None:
        idx = int(chapter_index)
        self._step4_batch_task_meta[idx] = {
            "status": "running",
            "started_at": time.perf_counter(),
            "elapsed": 0.0,
        }
        row = self._step4_batch_row_by_idx.get(idx)
        if row is None:
            return
        st = self.step4_batch_table.item(row, 1)
        el = self.step4_batch_table.item(row, 2)
        if st is not None:
            st.setText("生成中")
            st.setToolTip("")
        if el is not None:
            el.setText("0.0")

    def _on_step4_batch_task_finished(self, chapter_index: int, detail_obj: object, elapsed: float) -> None:
        idx = int(chapter_index)
        try:
            if self.step_generator and isinstance(detail_obj, dict):
                detail_obj = self.step_generator._normalize_chapter_detail(detail_obj)
        except Exception:
            pass

        try:
            while len(self.chapter_details) <= idx:
                self.chapter_details.append({})
            if isinstance(detail_obj, dict):
                self.chapter_details[idx] = detail_obj
            self.project_manager.update_generation_step("step4_chapter_details", self.chapter_details)
        except Exception:
            pass

        try:
            if isinstance(detail_obj, dict):
                conv = detail_obj.get("conversation")
                if isinstance(conv, list):
                    gh = self.project_manager.current_project.generation_history if self.project_manager.current_project else None
                    step4_convs = dict(getattr(gh, "step4_conversations", {}) or {}) if gh else {}
                    step4_convs[str(idx)] = conv
                    self.project_manager.update_generation_history_field("step4_conversations", step4_convs)
        except Exception:
            pass

        meta = self._step4_batch_task_meta.get(idx) or {}
        meta["status"] = "success"
        meta["elapsed"] = float(elapsed or 0.0)
        self._step4_batch_task_meta[idx] = meta

        row = self._step4_batch_row_by_idx.get(idx)
        if row is not None:
            st = self.step4_batch_table.item(row, 1)
            el = self.step4_batch_table.item(row, 2)
            if st is not None:
                st.setText("完成")
            if el is not None:
                el.setText(f"{float(elapsed):.1f}")

        self._update_step4_batch_overall_status()
        self.modified.emit()

    def _on_step4_batch_task_failed(self, chapter_index: int, message: str) -> None:
        idx = int(chapter_index)
        meta = self._step4_batch_task_meta.get(idx) or {}
        meta["status"] = "failed"
        self._step4_batch_task_meta[idx] = meta

        row = self._step4_batch_row_by_idx.get(idx)
        if row is not None:
            st = self.step4_batch_table.item(row, 1)
            if st is not None:
                st.setText("失败")
                st.setToolTip(message or "")

        self._update_step4_batch_overall_status()

    def _update_step4_batch_overall_status(self) -> None:
        total = int(self._step4_batch_total or 0)
        done = sum(1 for v in (self._step4_batch_task_meta or {}).values() if v.get("status") in {"success", "failed"})
        running = sum(1 for v in (self._step4_batch_task_meta or {}).values() if v.get("status") == "running")
        if self._step4_batch_stop_requested and not self._step4_batch_running:
            self.step4_batch_status.setText(f"批量：已停止 {done}/{total}")
            return
        if total > 0 and done >= total and running == 0:
            self._step4_batch_running = False
            try:
                self._step4_batch_update_timer.stop()
            except Exception:
                pass
            try:
                if self._step4_batch_executor is not None:
                    self._step4_batch_executor.shutdown(wait=False, cancel_futures=False)
            except Exception:
                pass
            self._step4_batch_executor = None
            self.step4_batch_status.setText(f"批量：完成 {done}/{total}")
        else:
            self.step4_batch_status.setText(f"批量：运行中 {done}/{total}")

    def _update_step4_batch_elapsed_cells(self) -> None:
        if not self._step4_batch_task_meta:
            return
        now = time.perf_counter()
        for idx, meta in (self._step4_batch_task_meta or {}).items():
            if meta.get("status") != "running":
                continue
            start = meta.get("started_at")
            if not isinstance(start, (int, float)):
                continue
            elapsed = max(0.0, float(now - float(start)))
            meta["elapsed"] = elapsed
            row = self._step4_batch_row_by_idx.get(int(idx))
            if row is None:
                continue
            el = self.step4_batch_table.item(row, 2)
            if el is not None:
                el.setText(f"{elapsed:.1f}")

    # ==================== 步骤5：待生成列表 ====================

    def _ensure_chapter_details(self) -> bool:
        if self.chapter_details:
            return True
        if self.project_manager.current_project and self.project_manager.current_project.generation_history.step4_chapter_details:
            self.chapter_details = self.project_manager.current_project.generation_history.step4_chapter_details
            return True
        QMessageBox.warning(self, "提示", "请先完成步骤4并生成章节详细内容。")
        return False

    def _summarize_pending(self, pending_lists: PendingLists, extra: dict | None) -> str:
        summary = {
            "portraits": len(pending_lists.portraits),
            "backgrounds": len(pending_lists.backgrounds),
            "cgs": len(pending_lists.cgs),
            "voices": len(pending_lists.voices),
            "bgms": len(pending_lists.bgms),
        }
        flow_info = {}
        if extra and isinstance(extra, dict):
            flow_info = {
                "flow_nodes": len(extra.get("flow_nodes", [])),
                "connections": len(extra.get("connections", [])),
            }
        payload = {
            "pending_lists": summary,
            "flow": flow_info,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _clear_step5_related_project_data(
        self,
        *,
        clear_pending_lists: bool,
        clear_flow: bool,
        clear_prompts: bool,
    ) -> None:
        """清空 AI 工程文件中与 Step5 相关的旧数据，避免旧数据影响后续生成。

        - clear_pending_lists=True：同时清空工程的 pending_lists（立绘/背景/CG/语音/BGM 待生成清单）
        - clear_flow=True：清空 generation_history.step5_flow_nodes/step5_full_script
        - clear_prompts=True：清空 generation_history.step5_material_prompts，并清空 prompts 结果 UI
        """

        if not self._ensure_project():
            return

        if clear_flow:
            try:
                self.project_manager.update_generation_step("step5_full_script", None)
            except Exception:
                pass
            try:
                self.project_manager.update_generation_step("step5_flow_nodes", None)
            except Exception:
                pass

        if clear_prompts:
            try:
                self.project_manager.update_generation_step("step5_material_prompts", None)
            except Exception:
                pass

        if clear_pending_lists:
            try:
                self.project_manager.update_pending_lists(PendingLists())
            except Exception:
                pass

        if clear_pending_lists:
            # 同步清空 UI/内存缓存，避免 UI 继续展示旧数据
            try:
                self.pending_lists = None
                self.flow_nodes = []
                self.flow_connections = []
                self.global_variables = []
                self.pending_summary = None
            except Exception:
                pass

            try:
                self.step5_result.clear()
                self.step5_status.setText("状态：已清空旧数据")
            except Exception:
                pass

        if clear_prompts:
            try:
                # Step5 prompts 属于 Step5 的派生结果，清空旧结果但不强制清空指令（用户可能已保存指令）
                self.step5_prompts_result.clear()
                self.step5_prompts_status.setText("状态：等待指令")
            except Exception:
                pass

        self.modified.emit()
        # 后台去抖动落盘：确保 .vnai 中旧数据尽快被清除
        self._schedule_deferred_project_save()

    def generate_pending_lists(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        if not self._ensure_chapter_details():
            return

        # 生成前先清空旧 Step5 数据，防止旧数据在工程文件中残留/干扰
        self._clear_step5_related_project_data(clear_pending_lists=True, clear_flow=True, clear_prompts=True)

        story = self._story_dict()
        chars = self._characters_dict()
        personas = self.personas_data
        if not personas and self.project_manager.current_project:
            personas = self.project_manager.current_project.generation_history.step1_personas
        step3_chapters = None
        try:
            if getattr(self, "project_manager", None) and getattr(self.project_manager, "current_project", None):
                gh = getattr(self.project_manager.current_project, "generation_history", None)
                step3_chapters = getattr(gh, "step3_chapters", None) if gh else None
        except Exception:
            step3_chapters = None

        result = self.step_generator.build_pending_and_flow(
            story,
            chars,
            self.chapter_details,
            personas,
            chapters_plan=step3_chapters,
        )

        self.pending_lists = result.get("pending_lists")
        self.flow_nodes = result.get("flow_nodes") or []
        self.flow_connections = result.get("connections") or []
        self.global_variables = result.get("global_variables") or []
        self.pending_summary = result.get("summary") or {}

        display = self._summarize_pending(self.pending_lists, {"flow_nodes": self.flow_nodes, "connections": self.flow_connections})
        self.step5_result.setPlainText(display)
        self.step5_status.setText("状态：已生成，记得保存")
        self.modified.emit()

    def _apply_material_prompts_to_pending_lists(self, structured: dict) -> None:
        """将 prompts JSON 回填到内存中的 pending_lists（不自动保存到工程）。"""
        if not self.pending_lists or not isinstance(structured, dict):
            return

        bg_map = {
            x.get("item_id"): x.get("prompt")
            for x in (structured.get("backgrounds") or [])
            if isinstance(x, dict)
        }
        cg_map = {
            x.get("item_id"): x.get("prompt")
            for x in (structured.get("cgs") or [])
            if isinstance(x, dict)
        }
        bgm_map = {
            x.get("item_id"): x.get("prompt")
            for x in (structured.get("bgms") or [])
            if isinstance(x, dict)
        }

        for it in self.pending_lists.backgrounds or []:
            p = bg_map.get(it.item_id)
            if isinstance(p, str) and p.strip():
                it.prompt = p.strip()

        for it in self.pending_lists.cgs or []:
            p = cg_map.get(it.item_id)
            if isinstance(p, str) and p.strip():
                it.prompt = p.strip()

        for it in self.pending_lists.bgms or []:
            p = bgm_map.get(it.item_id)
            if isinstance(p, str) and p.strip():
                it.prompt = p.strip()

    def prepare_material_prompts(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        if not self.pending_lists:
            QMessageBox.warning(self, "提示", "请先生成步骤5的待生成列表，再生成 prompts。")
            return

        self._sync_project_configs()

        story = self._story_dict()
        personas = self.personas_data
        outline = None
        step3_chapters = None
        try:
            if self.project_manager.current_project:
                gh = self.project_manager.current_project.generation_history
                outline = getattr(gh, "step2_outline", None)
                step3_chapters = getattr(gh, "step3_chapters", None)
                if not personas:
                    personas = getattr(gh, "step1_personas", None)
        except Exception:
            outline = None
            step3_chapters = None

        instruction, params = self.step_generator.prepare_material_prompts_instruction(
            self.pending_lists,
            story_config=story,
            personas_data=personas,
            outline_data=outline,
            chapters_plan=step3_chapters,
        )
        params = dict(params or {})
        params["max_tokens"] = self._get_step_max_tokens("step5_prompts")
        params.setdefault("temperature", 0.4)
        self.step5_prompts_instruction.setPlainText(instruction)
        self.step5_prompts_status.setText("状态：指令已生成，请先保存指令再发送")
        self.step_parameters["step5_prompts"] = params
        self._record_instruction("generate_material_prompts_prepare", instruction, params, None, "pending")
        self.modified.emit()

    def send_material_prompts(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        if not self.pending_lists:
            QMessageBox.warning(self, "提示", "请先生成步骤5的待生成列表，再发送 prompts 生成。")
            return

        # 生成 prompts 前先清空旧 prompts 结果，避免旧数据残留导致误判
        self._clear_step5_related_project_data(clear_pending_lists=False, clear_flow=False, clear_prompts=True)

        params = dict(self.step_parameters.get("step5_prompts") or {})
        params["max_tokens"] = self._get_step_max_tokens("step5_prompts")
        temp = 0.4
        try:
            temp = float(params.get("temperature", 0.4))
        except Exception:
            temp = 0.4

        def _start_send(instruction: str):
            def _task():
                return self.step_generator.generate_material_prompts_from_instruction(
                    instruction,
                    params,
                    pending_lists=self.pending_lists,
                    temperature=temp,
                )

            def _on_success(result):
                # 回填 prompts 到 pending_lists（内存中，是否落盘由用户点击“保存到工程”决定）
                try:
                    pl = result.get("pending_lists") if isinstance(result, dict) else None
                    if isinstance(pl, PendingLists):
                        self.pending_lists = pl
                except Exception:
                    pass

                structured = result.get("structured") if isinstance(result, dict) else None
                raw = result.get("raw_response") if isinstance(result, dict) else None

                if isinstance(structured, dict):
                    self.step5_prompts_result.setPlainText(json.dumps(structured, ensure_ascii=False, indent=2))
                    self._apply_material_prompts_to_pending_lists(structured)
                elif isinstance(raw, str):
                    self.step5_prompts_result.setPlainText(raw)

                # 写入 generation_history.step5_material_prompts（新 step 字段）
                payload = {
                    "raw_response": raw if isinstance(raw, str) else (self.step5_prompts_result.toPlainText() or ""),
                    "structured": structured if isinstance(structured, dict) else self._try_parse_json_block(raw if isinstance(raw, str) else None),
                    "timestamp": result.get("timestamp") if isinstance(result, dict) else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "parameters": dict(params or {}),
                }
                self.project_manager.update_generation_step("step5_material_prompts", payload)

                self._record_instruction("generate_material_prompts", instruction, params, payload, "success")
                self.step5_prompts_status.setText("状态：已生成")
                self.modified.emit()

            self._run_async(self.step5_prompts_status, "状态：生成中", _task, _on_success)

        self._ensure_send_uses_saved_instruction_async(
            "step5_prompts",
            self.step5_prompts_instruction,
            status_label=self.step5_prompts_status,
            on_ready=_start_send,
        )

    def save_material_prompts_result(self):
        if not self._ensure_project():
            return
        text = (self.step5_prompts_result.toPlainText() or "").strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有可保存的内容。")
            return

        params = dict(self.step_parameters.get("step5_prompts") or {})
        params["max_tokens"] = self._get_step_max_tokens("step5_prompts")

        parsed = self._try_parse_json_block(text) or self._safe_json_load(text)
        if isinstance(parsed, dict):
            payload = {
                "raw_response": text,
                "structured": parsed,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "parameters": params or {},
            }
            # 手动编辑后保存：也回填到 pending_lists（仍不自动保存到工程）
            self._apply_material_prompts_to_pending_lists(parsed)
        else:
            payload = self._manual_result_payload(text, params)

        self.project_manager.update_generation_step("step5_material_prompts", payload)
        self.step5_prompts_status.setText("状态：已保存(手动)")
        self._record_instruction("manual_save_material_prompts", "用户手动保存素材prompts", {}, payload, "success")
        self.modified.emit()

    def save_pending_lists(self):
        if not self._ensure_project():
            return
        if not self.pending_lists:
            QMessageBox.warning(self, "提示", "请先生成待生成列表。")
            return
        # 允许用户在文本框里修改概要，不强制解析
        self.project_manager.update_pending_lists(self.pending_lists)
        # 记录流程骨架到 generation_history.step5_flow_nodes
        flow_payload = {
            "pending_lists": self.pending_lists.model_dump(),
            "flow_nodes": [n.model_dump() for n in self.flow_nodes],
            "connections": [c.model_dump() for c in self.flow_connections],
            "global_variables": [g.model_dump() for g in self.global_variables],
            "summary": self.pending_summary or {},
        }
        self.project_manager.update_generation_step("step5_flow_nodes", flow_payload)
        self.step5_status.setText("状态：已保存")
        self._record_instruction("save_pending_lists", "保存待生成列表", {}, flow_payload, "success")
        self.modified.emit()

    # ==================== 步骤6：生成工程文件 ====================

    def _build_user_config(self, vngproj_path: str) -> UserConfig:
        project_dir = Path(vngproj_path).parent
        project_name = Path(vngproj_path).stem
        ai_proj = self.project_manager.current_project
        story_cfg = ai_proj.story_config
        chars = ai_proj.character_config
        return UserConfig(
            project_info=ProjectConfig(
                project_path=str(project_dir),
                project_name=project_name,
                window_width=1280,
                window_height=720,
                engine_version="V2.7-AI",
            ),
            story_config=story_cfg,
            character_config=chars,
            enable_agents=EnableAgentsConfig(),
            material_config=MaterialConfig(),
        )

    def generate_project_file(self):
        if not self._ensure_project():
            return
        if not self.flow_nodes:
            QMessageBox.warning(self, "提示", "请先生成并保存待生成列表，确保流程骨架可用。")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "选择工程文件保存路径",
            "",
            "VNEngine 工程 (*.vngproj)",
        )
        if not file_path:
            return

        try:
            user_config = self._build_user_config(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"构建工程配置失败: {exc}")
            return

        integrator = Integrator(self.config_manager)
        try:
            project_file = integrator.integrate_from_data(
                user_config=user_config,
                flow_nodes=self.flow_nodes,
                connections=self.flow_connections,
                global_variables=self.global_variables,
                material_requirements=[],
                resources_dir=str(Path(file_path).parent / "resources"),
            )
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"生成工程失败: {exc}")
            return

        self.vngproj_path = project_file
        self.project_manager.set_vng_project_path(project_file)
        summary = {
            "project_file": project_file,
            "nodes": len(self.flow_nodes),
            "connections": len(self.flow_connections),
        }
        self.step6_result.setPlainText(json.dumps(summary, ensure_ascii=False, indent=2))
        self.step6_status.setText("状态：工程已生成（资源尚未补齐）")
        self._record_instruction("generate_vngproj", "生成工程文件", {"path": project_file}, summary, "success")
        self.modified.emit()

