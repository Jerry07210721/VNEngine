# -*- coding: utf-8 -*-
"""
主控Agent界面
负责分步生成（人设→大纲→章节→章节详稿），允许用户在每一步编辑指令与结果。
"""

import json
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QGroupBox,
    QWidget,
    QComboBox,
    QMessageBox,
    QFileDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer, QElapsedTimer

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

        self.init_ui()
        self.refresh()

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

    # ==================== UI ====================

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 顶部提示
        self.project_label = QLabel("当前未加载AI工程")
        self.project_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.project_label)

        # 步骤1：人设
        self.step1_group = self._build_step_box(
            title="步骤1：生成角色人设",
            prepare_handler=self.prepare_personas,
            send_handler=self.send_personas,
            save_handler=self.save_personas_result,
            result_placeholder="角色人设将显示在这里，用户可直接编辑后再保存。",
        )
        layout.addWidget(self.step1_group)

        # 步骤2：故事大纲
        self.step2_group = self._build_step_box(
            title="步骤2：生成故事大纲",
            prepare_handler=self.prepare_outline,
            send_handler=self.send_outline,
            save_handler=self.save_outline_result,
            result_placeholder="故事大纲将显示在这里，用户可直接编辑后再保存。",
        )
        layout.addWidget(self.step2_group)

        # 步骤3：章节列表
        self.step3_group = self._build_step_box(
            title="步骤3：生成章节列表",
            prepare_handler=self.prepare_chapters,
            send_handler=self.send_chapters,
            save_handler=self.save_chapters_result,
            result_placeholder="章节列表（结构化JSON）将显示在这里。",
        )
        layout.addWidget(self.step3_group)

        # 步骤4：章节详细内容（逐章）
        self.step4_group = QGroupBox("步骤4：逐章生成详细内容")
        step4_layout = QVBoxLayout()
        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("选择章节："))
        self.chapter_selector = QComboBox()
        self.chapter_selector.addItem("尚未生成章节列表")
        selector_row.addWidget(self.chapter_selector)
        self.load_chapter_btn = QPushButton("加载章节列表")
        self.load_chapter_btn.clicked.connect(self.load_chapter_list)
        selector_row.addWidget(self.load_chapter_btn)
        self.chapter_selector.currentIndexChanged.connect(self.on_chapter_changed)
        selector_row.addStretch(1)
        step4_layout.addLayout(selector_row)

        btn_row = QHBoxLayout()
        self.step4_prepare_btn = QPushButton("准备指令")
        self.step4_send_btn = QPushButton("发送/生成")
        self.step4_save_btn = QPushButton("保存结果")
        self.step4_prepare_btn.clicked.connect(self.prepare_chapter_detail)
        self.step4_send_btn.clicked.connect(self.send_chapter_detail)
        self.step4_save_btn.clicked.connect(self.save_chapter_detail)
        btn_row.addWidget(self.step4_prepare_btn)
        btn_row.addWidget(self.step4_send_btn)
        btn_row.addWidget(self.step4_save_btn)
        btn_row.addStretch(1)
        step4_layout.addLayout(btn_row)

        self.step4_instruction = QTextEdit()
        self.step4_instruction.setPlaceholderText("章节指令，生成后可手动编辑...")
        self.step4_instruction.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        step4_layout.addWidget(self.step4_instruction)

        self.step4_result = QTextEdit()
        self.step4_result.setPlaceholderText("章节详细内容（可编辑）")
        self.step4_result.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        step4_layout.addWidget(self.step4_result)

        self.step4_status = QLabel("状态：等待指令")
        step4_layout.addWidget(self.step4_status)

        self.step4_group.setLayout(step4_layout)
        layout.addWidget(self.step4_group)

        # 步骤5：待生成列表 + 流程骨架
        self.step5_group = QGroupBox("步骤5：生成待生成列表与流程骨架")
        step5_layout = QVBoxLayout()
        btn_row5 = QHBoxLayout()
        self.step5_generate_btn = QPushButton("生成列表")
        self.step5_save_btn = QPushButton("保存到工程")
        self.step5_generate_btn.clicked.connect(self.generate_pending_lists)
        self.step5_save_btn.clicked.connect(self.save_pending_lists)
        btn_row5.addWidget(self.step5_generate_btn)
        btn_row5.addWidget(self.step5_save_btn)
        btn_row5.addStretch(1)
        step5_layout.addLayout(btn_row5)
        self.step5_result = QTextEdit()
        self.step5_result.setPlaceholderText("待生成列表摘要将显示在这里，可手动调整后保存。")
        self.step5_result.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        step5_layout.addWidget(self.step5_result)
        self.step5_status = QLabel("状态：等待生成")
        step5_layout.addWidget(self.step5_status)
        self.step5_group.setLayout(step5_layout)
        layout.addWidget(self.step5_group)

        # 步骤6：生成工程文件（虚拟资源路径）
        self.step6_group = QGroupBox("步骤6：生成工程文件（先填路径，后补资源）")
        step6_layout = QVBoxLayout()
        btn_row6 = QHBoxLayout()
        self.step6_generate_btn = QPushButton("生成 .vngproj")
        self.step6_generate_btn.clicked.connect(self.generate_project_file)
        btn_row6.addWidget(self.step6_generate_btn)
        btn_row6.addStretch(1)
        step6_layout.addLayout(btn_row6)
        self.step6_result = QTextEdit()
        self.step6_result.setPlaceholderText("生成的工程路径与摘要将显示在这里。")
        self.step6_result.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        step6_layout.addWidget(self.step6_result)
        self.step6_status = QLabel("状态：等待生成")
        step6_layout.addWidget(self.step6_status)
        self.step6_group.setLayout(step6_layout)
        layout.addWidget(self.step6_group)

        layout.addStretch(1)

    def _build_step_box(self, title: str, prepare_handler, send_handler, save_handler, result_placeholder: str) -> QGroupBox:
        box = QGroupBox(title)
        vbox = QVBoxLayout()

        btn_row = QHBoxLayout()
        prepare_btn = QPushButton("准备指令")
        send_btn = QPushButton("发送/生成")
        prepare_btn.clicked.connect(prepare_handler)
        send_btn.clicked.connect(send_handler)
        btn_row.addWidget(prepare_btn)
        btn_row.addWidget(send_btn)
        if save_handler:
            save_btn = QPushButton("保存结果")
            save_btn.clicked.connect(save_handler)
            btn_row.addWidget(save_btn)
        btn_row.addStretch(1)
        vbox.addLayout(btn_row)

        instruction = QTextEdit()
        instruction.setPlaceholderText("生成的指令会显示在这里，发送前可自由修改...")
        instruction.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        vbox.addWidget(instruction)

        result = QTextEdit()
        result.setPlaceholderText(result_placeholder)
        result.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        vbox.addWidget(result)

        status = QLabel("状态：等待指令")
        vbox.addWidget(status)

        box.setLayout(vbox)

        box._instruction = instruction
        box._result = result
        box._status = status
        return box

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

        # 渲染步骤5
        if self.pending_lists:
            summary = self._summarize_pending(self.pending_lists, getattr(history, "step5_flow_nodes", None))
            self.step5_result.setPlainText(summary)
            self.step5_status.setText("状态：已生成")
        else:
            self.step5_status.setText("状态：等待生成")

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
        self.step4_instruction.clear()
        self.step4_result.clear()
        self.step4_status.setText("状态：等待指令")
        self.chapter_selector.clear()
        self.chapter_selector.addItem("尚未生成章节列表")

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

    def on_chapter_changed(self, idx: int):
        self._load_chapter_detail(idx)

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
        try:
            if "```json" in candidate:
                candidate = candidate.split("```json", 1)[1].split("```", 1)[0].strip()
            elif candidate.startswith("```"):
                candidate = candidate.split("```", 1)[1].split("```", 1)[0].strip()
            return json.loads(candidate)
        except Exception:
            return None

    def _load_chapter_detail(self, idx: int):
        if idx < 0:
            self.step4_result.clear()
            self.step4_status.setText("状态：等待指令")
            return
        if idx < len(self.chapter_details):
            detail = self.chapter_details[idx]
            if detail:
                self.step4_result.setPlainText(self._format_preview(detail))
                self.step4_status.setText(f"状态：第{idx+1}章已加载")
                return
        self.step4_result.clear()
        self.step4_status.setText("状态：等待指令")

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
        story_config = self._story_dict()
        characters = self._characters_dict()
        instruction, params = self.step_generator.prepare_personas_instruction(story_config, characters)
        self.step1_group._instruction.setPlainText(instruction)
        self.step1_group._status.setText("状态：指令已生成，待发送")
        self.step_parameters["step1"] = params
        self._record_instruction("generate_personas_prepare", instruction, params, None, "pending")
        self.modified.emit()

    def send_personas(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        params = self.step_parameters.get("step1") or {}
        instruction = self.step1_group._instruction.toPlainText().strip()
        if not instruction:
            QMessageBox.warning(self, "提示", "请先准备指令后再发送。")
            return
        def _task():
            return self.step_generator.generate_personas(instruction, params)

        def _on_success(result):
            self.personas_data = result
            self.step1_group._result.setPlainText(self._format_preview(result))
            self.project_manager.update_generation_step("step1_personas", result)
            self._record_instruction("generate_personas", instruction, params, result, "success")
            self.step1_group._status.setText("状态：已生成")
            self.modified.emit()

        self._run_async(self.step1_group._status, "状态：生成中", _task, _on_success)

    def save_personas_result(self):
        if not self._ensure_project():
            return
        text = self.step1_group._result.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有可保存的内容。")
            return
        data = self._manual_result_payload(text, self.step_parameters.get("step1"))
        self.personas_data = data
        self.project_manager.update_generation_step("step1_personas", data)
        self.step1_group._status.setText("状态：已保存(手动)")
        self._record_instruction("manual_save_personas", "用户手动保存人设", {}, data, "success")
        self.modified.emit()

    # ==================== 步骤2：大纲 ====================

    def prepare_outline(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        if not self.personas_data and not self.project_manager.current_project.generation_history.step1_personas:
            QMessageBox.warning(self, "提示", "请先完成步骤1：角色人设。")
            return
        story_config = self._story_dict()
        personas = self.personas_data or self.project_manager.current_project.generation_history.step1_personas
        instruction, params = self.step_generator.prepare_outline_instruction(story_config, personas or {})
        self.step2_group._instruction.setPlainText(instruction)
        self.step2_group._status.setText("状态：指令已生成，待发送")
        self.step_parameters["step2"] = params
        self._record_instruction("generate_outline_prepare", instruction, params, None, "pending")
        self.modified.emit()

    def send_outline(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        params = self.step_parameters.get("step2") or {}
        instruction = self.step2_group._instruction.toPlainText().strip()
        if not instruction:
            QMessageBox.warning(self, "提示", "请先准备指令后再发送。")
            return
        def _task():
            return self.step_generator.generate_outline(instruction, params)

        def _on_success(result):
            self.outline_data = result
            self.step2_group._result.setPlainText(self._format_preview(result))
            self.project_manager.update_generation_step("step2_outline", result)
            self._record_instruction("generate_outline", instruction, params, result, "success")
            self.step2_group._status.setText("状态：已生成")
            self.modified.emit()

        self._run_async(self.step2_group._status, "状态：生成中", _task, _on_success)

    def save_outline_result(self):
        if not self._ensure_project():
            return
        text = self.step2_group._result.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有可保存的内容。")
            return
        data = self._manual_result_payload(text, self.step_parameters.get("step2"))
        self.outline_data = data
        self.project_manager.update_generation_step("step2_outline", data)
        self.step2_group._status.setText("状态：已保存(手动)")
        self._record_instruction("manual_save_outline", "用户手动保存大纲", {}, data, "success")
        self.modified.emit()

    # ==================== 步骤3：章节列表 ====================

    def prepare_chapters(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        if not self.outline_data and not self.project_manager.current_project.generation_history.step2_outline:
            QMessageBox.warning(self, "提示", "请先完成步骤2：故事大纲。")
            return
        story_config = self._story_dict()
        outline = self.outline_data or self.project_manager.current_project.generation_history.step2_outline
        instruction, params = self.step_generator.prepare_chapters_instruction(story_config, outline or {})
        self.step3_group._instruction.setPlainText(instruction)
        self.step3_group._status.setText("状态：指令已生成，待发送")
        self.step_parameters["step3"] = params
        self._record_instruction("generate_chapters_prepare", instruction, params, None, "pending")
        self.modified.emit()

    def send_chapters(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        params = self.step_parameters.get("step3") or {}
        instruction = self.step3_group._instruction.toPlainText().strip()
        if not instruction:
            QMessageBox.warning(self, "提示", "请先准备指令后再发送。")
            return
        def _task():
            return self.step_generator.generate_chapters(instruction, params)

        def _on_success(result):
            self.chapters_data = result
            self.step3_group._result.setPlainText(self._format_preview(result))
            self.project_manager.update_generation_step("step3_chapters", result)
            self._record_instruction("generate_chapters", instruction, params, result, "success")
            self.step3_group._status.setText("状态：已生成")
            self._refresh_chapter_selector()
            self.modified.emit()

        self._run_async(self.step3_group._status, "状态：生成中", _task, _on_success)

    def save_chapters_result(self):
        if not self._ensure_project():
            return
        text = self.step3_group._result.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有可保存的内容。")
            return
        data = self._manual_result_payload(text, self.step_parameters.get("step3"))
        self.chapters_data = data
        self.project_manager.update_generation_step("step3_chapters", data)
        self.step3_group._status.setText("状态：已保存(手动)")
        self._record_instruction("manual_save_chapters", "用户手动保存章节列表", {}, data, "success")
        self._refresh_chapter_selector()
        self.modified.emit()

    # ==================== 步骤4：章节详细内容 ====================

    def prepare_chapter_detail(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
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
        instruction, params = self.step_generator.prepare_chapter_detail_instruction(idx, chapter_info, prev_context)
        self.step4_instruction.setPlainText(instruction)
        self.step4_status.setText(f"状态：第{idx+1}章指令已生成，待发送")
        self.step_parameters["step4"] = params
        self._record_instruction("generate_chapter_detail_prepare", instruction, params, None, "pending")
        self.modified.emit()

    def send_chapter_detail(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        chapters_struct = self._chapter_list()
        if not chapters_struct:
            QMessageBox.warning(self, "提示", "请先完成步骤3并确保章节列表为结构化JSON。")
            return
        idx = self.chapter_selector.currentIndex()
        if idx < 0 or idx >= len(chapters_struct):
            QMessageBox.warning(self, "提示", "请选择有效的章节。")
            return
        instruction = self.step4_instruction.toPlainText().strip()
        if not instruction:
            QMessageBox.warning(self, "提示", "请先准备指令后再发送。")
            return
        params = self.step_parameters.get("step4") or {"chapter_index": idx}
        params["chapter_index"] = idx
        def _task():
            return self.step_generator.generate_chapter_detail(instruction, params)

        def _on_success(detail):
            while len(self.chapter_details) <= idx:
                self.chapter_details.append({})
            self.chapter_details[idx] = detail
            self.step4_result.setPlainText(self._format_preview(detail))
            self.project_manager.update_generation_step("step4_chapter_details", self.chapter_details)
            self._record_instruction("generate_chapter_detail", instruction, params, detail, "success")
            self.step4_status.setText(f"状态：第{idx+1}章已生成")
            self.modified.emit()

        self._run_async(self.step4_status, f"状态：第{idx+1}章生成中", _task, _on_success)

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
        detail = self._manual_result_payload(text, params, {"chapter_index": idx})
        while len(self.chapter_details) <= idx:
            self.chapter_details.append({})
        self.chapter_details[idx] = detail
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

    def generate_pending_lists(self):
        if not self._ensure_project():
            return
        if not self._ensure_step_gen():
            return
        if not self._ensure_chapter_details():
            return

        story = self._story_dict()
        chars = self._characters_dict()
        result = self.step_generator.build_pending_and_flow(story, chars, self.chapter_details)

        self.pending_lists = result.get("pending_lists")
        self.flow_nodes = result.get("flow_nodes") or []
        self.flow_connections = result.get("connections") or []
        self.global_variables = result.get("global_variables") or []
        self.pending_summary = result.get("summary") or {}

        display = self._summarize_pending(self.pending_lists, {"flow_nodes": self.flow_nodes, "connections": self.flow_connections})
        self.step5_result.setPlainText(display)
        self.step5_status.setText("状态：已生成，记得保存")
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
                engine_version="V2.0-AI",
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

