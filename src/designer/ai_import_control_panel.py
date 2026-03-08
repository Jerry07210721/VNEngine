# -*- coding: utf-8 -*-
"""导入模式：完整故事导入（转视觉小说结构）。

步骤：
1) 章节配置：手动录入章节标题列表 -> 保存章节列表
2) 每章完整剧情：粘贴文本或关联 txt 文件 -> 保存
3) 结构化转换：对每章文本调用 LLM 生成符合 Step4 JSON 结构的报文
4) 生成待生成列表与素材 prompts（复用 StepGenerator 的 Step5 逻辑）
5) 生成 VNG 工程文件（复用 Integrator 逻辑）
"""

import json
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QElapsedTimer, QThread, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.core.config_manager import ConfigManager
from src.ai.core.models import (
    EnableAgentsConfig,
    FlowNodeData,
    ConnectionData,
    GlobalVariable,
    MaterialConfig,
    PendingLists,
    ProjectConfig,
    UserConfig,
)
from src.ai.core.step_generator import StepGenerator
from src.ai.integrator.integrator import Integrator


class AIImportControlPanel(QWidget):
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
        self._busy_label: QLabel | None = None
        self._busy_prefix = ""

        try:
            self.step_generator = StepGenerator(config_manager)
        except Exception as exc:  # noqa: BLE001
            self.step_generator_error = str(exc)

        # 内存缓存
        self.chapter_plan: dict | None = None
        self.chapter_details: list[dict] = []
        self.pending_lists: PendingLists | None = None
        self.flow_nodes: list[FlowNodeData] = []
        self.flow_connections: list[ConnectionData] = []
        self.global_variables: list[GlobalVariable] = []
        self.pending_summary: dict | None = None
        self.vngproj_path: str | None = None

        self._saved_step3_instruction_cache: dict[int, str] = {}
        self._saved_step4_prompts_instruction_cache: str = ""

        self.init_ui()
        self.refresh()

    # ==================== 基础检查 ====================

    def _ensure_project(self) -> bool:
        if not getattr(self.project_manager, "current_project", None):
            QMessageBox.warning(self, "提示", "请先新建或打开 AI 工程。")
            return False
        return True

    def _ensure_step_gen(self) -> bool:
        if self.step_generator is None:
            msg = self.step_generator_error or "StepGenerator 初始化失败"
            QMessageBox.critical(self, "错误", msg)
            return False
        return True

    def _project_mode(self) -> str:
        project = getattr(self.project_manager, "current_project", None)
        info = getattr(project, "ai_project_info", None) if project else None
        mode = getattr(info, "project_mode", "generate") if info else "generate"
        mode = str(mode or "generate").strip().lower()
        return mode if mode in {"generate", "import"} else "generate"

    # ==================== 异步执行辅助 ====================

    def _update_elapsed_label(self):
        if not self._busy_label or not self._elapsed_timer.isValid():
            return
        secs = self._elapsed_timer.elapsed() / 1000.0
        self._busy_label.setText(f"{self._busy_prefix} (已耗时 {secs:.1f}s)")

    def _run_async(self, label: QLabel, running_text: str, task_fn, on_success):
        if self._active_worker:
            QMessageBox.information(self, "提示", "已有任务进行中，请稍候")
            return

        class _TaskThread(QThread):
            result = pyqtSignal(object)
            error = pyqtSignal(str)

            def __init__(self, fn):
                super().__init__()
                self.fn = fn

            def run(self):  # pragma: no cover
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
            QMessageBox.critical(self, "错误", f"执行失败: {msg}")

        worker.result.connect(_finish)
        worker.error.connect(_fail)
        worker.start()

    # ==================== UI ====================

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.project_label = QLabel("当前未加载AI工程")
        try:
            self.project_label.setProperty("pill", "true")
        except Exception:
            pass
        layout.addWidget(self.project_label)

        self.step1_group = self._build_step1_box()
        self.step2_group = self._build_step2_box()
        self.step3_group = self._build_step3_box()
        self.step4_group = self._build_step4_box()
        self.step5_group = self._build_step5_box()

        layout.addWidget(self.step1_group)
        layout.addWidget(self.step2_group)
        layout.addWidget(self.step3_group)
        layout.addWidget(self.step4_group)
        layout.addWidget(self.step5_group)
        layout.addStretch()

    def _build_step1_box(self) -> QGroupBox:
        box = QGroupBox("步骤一：章节配置（导入模式）")
        v = QVBoxLayout(box)

        v.addWidget(QLabel("每行一个章节标题："))
        self.step1_titles = QTextEdit()
        self.step1_titles.setPlaceholderText("第1章：...\n第2章：...\n...")
        v.addWidget(self.step1_titles)

        h = QHBoxLayout()
        self.step1_count_label = QLabel("章节数：0")
        h.addWidget(self.step1_count_label)
        h.addStretch()
        self.step1_save_btn = QPushButton("解析并保存章节列表")
        self.step1_save_btn.clicked.connect(self.save_chapter_list)
        h.addWidget(self.step1_save_btn)
        v.addLayout(h)

        self.step1_preview = QTextEdit()
        self.step1_preview.setReadOnly(True)
        self.step1_preview.setPlaceholderText("这里显示保存后的章节列表结构（只读）")
        v.addWidget(self.step1_preview)

        self.step1_status = QLabel("状态：等待输入")
        v.addWidget(self.step1_status)
        return box

    def _build_step2_box(self) -> QGroupBox:
        box = QGroupBox("步骤二：每章完整剧情（粘贴或关联TXT）")
        v = QVBoxLayout(box)

        top = QHBoxLayout()
        top.addWidget(QLabel("选择章节："))
        self.step2_chapter_combo = QComboBox()
        self.step2_chapter_combo.currentIndexChanged.connect(self._load_step2_chapter_into_ui)
        top.addWidget(self.step2_chapter_combo)
        top.addStretch()
        v.addLayout(top)

        file_row = QHBoxLayout()
        self.step2_file_path = QLineEdit()
        self.step2_file_path.setPlaceholderText("可选：关联 txt 文件路径")
        file_row.addWidget(self.step2_file_path)
        pick_btn = QPushButton("选择TXT")
        pick_btn.clicked.connect(self.pick_step2_txt)
        file_row.addWidget(pick_btn)
        load_btn = QPushButton("加载文件到文本框")
        load_btn.clicked.connect(self.load_step2_txt_into_editor)
        file_row.addWidget(load_btn)
        v.addLayout(file_row)

        self.step2_use_file = QCheckBox("生成时优先使用关联文件")
        self.step2_use_file.setChecked(False)
        v.addWidget(self.step2_use_file)

        self.step2_text = QTextEdit()
        self.step2_text.setPlaceholderText("粘贴本章完整剧情（可包含对白/旁白/舞台说明）。")
        v.addWidget(self.step2_text)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.step2_save_btn = QPushButton("保存本章剧情")
        self.step2_save_btn.clicked.connect(self.save_step2_chapter_story)
        btn_row.addWidget(self.step2_save_btn)
        v.addLayout(btn_row)

        self.step2_status = QLabel("状态：等待章节列表")
        v.addWidget(self.step2_status)
        return box

    def _build_step3_box(self) -> QGroupBox:
        box = QGroupBox("步骤三：结构化转换（LLM 输出章节报文）")
        v = QVBoxLayout(box)

        sel = QHBoxLayout()
        sel.addWidget(QLabel("选择章节："))
        self.step3_chapter_combo = QComboBox()
        self.step3_chapter_combo.currentIndexChanged.connect(self._on_step3_chapter_changed)
        sel.addWidget(self.step3_chapter_combo)
        sel.addStretch()
        self.step3_prepare_btn = QPushButton("生成提示词")
        self.step3_prepare_btn.clicked.connect(self.prepare_step3_instruction)
        sel.addWidget(self.step3_prepare_btn)
        self.step3_save_instr_btn = QPushButton("保存指令")
        self.step3_save_instr_btn.clicked.connect(self.save_step3_instruction)
        sel.addWidget(self.step3_save_instr_btn)
        self.step3_send_btn = QPushButton("发送生成")
        self.step3_send_btn.clicked.connect(self.send_step3)
        sel.addWidget(self.step3_send_btn)
        self.step3_save_result_btn = QPushButton("保存结果")
        self.step3_save_result_btn.clicked.connect(self.save_step3_result)
        sel.addWidget(self.step3_save_result_btn)
        v.addLayout(sel)

        v.addWidget(QLabel("提示词："))
        self.step3_instruction = QTextEdit()
        v.addWidget(self.step3_instruction)

        v.addWidget(QLabel("LLM 返回（可手动编辑后再保存）："))
        self.step3_result = QTextEdit()
        v.addWidget(self.step3_result)

        self.step3_status = QLabel("状态：等待章节剧情")
        v.addWidget(self.step3_status)
        return box

    def _build_step4_box(self) -> QGroupBox:
        box = QGroupBox("步骤四：生成待生成列表与素材提示词（同生成模式步骤五）")
        v = QVBoxLayout(box)

        btns = QHBoxLayout()
        self.step4_gen_pending_btn = QPushButton("生成待生成列表")
        self.step4_gen_pending_btn.clicked.connect(self.generate_pending_lists)
        btns.addWidget(self.step4_gen_pending_btn)
        self.step4_save_pending_btn = QPushButton("保存待生成列表到工程")
        self.step4_save_pending_btn.clicked.connect(self.save_pending_lists)
        btns.addWidget(self.step4_save_pending_btn)
        btns.addStretch()
        v.addLayout(btns)

        self.step4_pending_view = QTextEdit()
        self.step4_pending_view.setReadOnly(True)
        self.step4_pending_view.setPlaceholderText("待生成列表摘要")
        v.addWidget(self.step4_pending_view)
        self.step4_pending_status = QLabel("状态：等待章节报文")
        v.addWidget(self.step4_pending_status)

        v.addWidget(QLabel("素材 prompts："))
        pbtn = QHBoxLayout()
        self.step4_prepare_prompts_btn = QPushButton("生成prompts指令")
        self.step4_prepare_prompts_btn.clicked.connect(self.prepare_material_prompts)
        pbtn.addWidget(self.step4_prepare_prompts_btn)
        self.step4_save_prompts_instr_btn = QPushButton("保存prompts指令")
        self.step4_save_prompts_instr_btn.clicked.connect(self.save_step4_prompts_instruction)
        pbtn.addWidget(self.step4_save_prompts_instr_btn)
        self.step4_send_prompts_btn = QPushButton("发送生成prompts")
        self.step4_send_prompts_btn.clicked.connect(self.send_material_prompts)
        pbtn.addWidget(self.step4_send_prompts_btn)
        self.step4_save_prompts_result_btn = QPushButton("保存prompts结果")
        self.step4_save_prompts_result_btn.clicked.connect(self.save_material_prompts_result)
        pbtn.addWidget(self.step4_save_prompts_result_btn)
        pbtn.addStretch()
        v.addLayout(pbtn)

        self.step4_prompts_instruction = QTextEdit()
        self.step4_prompts_instruction.setPlaceholderText("点击“生成prompts指令”生成")
        v.addWidget(self.step4_prompts_instruction)
        self.step4_prompts_result = QTextEdit()
        self.step4_prompts_result.setPlaceholderText("prompts 结果（JSON）")
        v.addWidget(self.step4_prompts_result)
        self.step4_prompts_status = QLabel("状态：等待待生成列表")
        v.addWidget(self.step4_prompts_status)

        return box

    def _build_step5_box(self) -> QGroupBox:
        box = QGroupBox("步骤五：生成项目工程文件（同生成模式步骤六）")
        v = QVBoxLayout(box)

        h = QHBoxLayout()
        self.step5_gen_btn = QPushButton("生成 VNG 工程文件")
        self.step5_gen_btn.clicked.connect(self.generate_project_file)
        h.addWidget(self.step5_gen_btn)
        h.addStretch()
        v.addLayout(h)

        self.step5_result = QTextEdit()
        self.step5_result.setReadOnly(True)
        self.step5_result.setPlaceholderText("生成结果摘要")
        v.addWidget(self.step5_result)

        self.step5_status = QLabel("状态：等待流程骨架")
        v.addWidget(self.step5_status)
        return box

    # ==================== 数据读写/刷新 ====================

    def refresh(self):
        project = getattr(self.project_manager, "current_project", None)
        if not project:
            self.project_label.setText("当前未加载AI工程")
            return

        if self._project_mode() != "import":
            # 宿主面板会切换掉当前 widget；这里不额外处理。
            return

        self.project_label.setText(
            f"工程：{project.ai_project_info.name} | 模式：导入模式 | 角色：{len(project.character_config)}"
        )

        gh = project.generation_history
        self.chapter_plan = None
        try:
            step3 = getattr(gh, "step3_chapters", None)
            if isinstance(step3, dict):
                structured = step3.get("structured")
                if isinstance(structured, dict):
                    self.chapter_plan = structured
        except Exception:
            self.chapter_plan = None

        # Step1 UI
        titles = []
        if isinstance(self.chapter_plan, dict) and isinstance(self.chapter_plan.get("chapters"), list):
            for c in self.chapter_plan.get("chapters"):
                if isinstance(c, dict):
                    t = str(c.get("title") or "").strip()
                    if t:
                        titles.append(t)
        if titles:
            self.step1_titles.blockSignals(True)
            self.step1_titles.setPlainText("\n".join(titles))
            self.step1_titles.blockSignals(False)
            self.step1_count_label.setText(f"章节数：{len(titles)}")
            self.step1_preview.setPlainText(json.dumps(self.chapter_plan, ensure_ascii=False, indent=2))
            self.step1_status.setText("状态：已加载")
        else:
            self.step1_count_label.setText("章节数：0")
            self.step1_preview.clear()
            self.step1_status.setText("状态：等待输入")

        # Step2/3 chapter combo
        self._reload_chapter_combos()

        # Step3 saved instructions cache
        try:
            saved_map = getattr(gh, "step4_saved_instructions", None)
            if isinstance(saved_map, dict):
                self._saved_step3_instruction_cache = {
                    int(k): str(v) for k, v in saved_map.items() if str(k).isdigit() and isinstance(v, str)
                }
        except Exception:
            self._saved_step3_instruction_cache = {}

        # Step4 prompts saved cache
        try:
            saved_steps = getattr(gh, "saved_step_instructions", None)
            if isinstance(saved_steps, dict):
                self._saved_step4_prompts_instruction_cache = str(saved_steps.get("step5_prompts", "") or "")
        except Exception:
            self._saved_step4_prompts_instruction_cache = ""

        # Step3/Step4 data
        try:
            self.chapter_details = list(getattr(gh, "step4_chapter_details", None) or [])
        except Exception:
            self.chapter_details = []

        # Step4：回填已保存的 pending_lists / flow_nodes / connections / global_variables
        self.pending_lists = getattr(project, "pending_lists", None)
        self.flow_nodes = []
        self.flow_connections = []
        self.global_variables = []
        self.pending_summary = None

        flow_payload = getattr(gh, "step5_flow_nodes", None)
        if isinstance(flow_payload, dict):
            try:
                fn = flow_payload.get("flow_nodes")
                if isinstance(fn, list):
                    self.flow_nodes = [FlowNodeData(**x) for x in fn if isinstance(x, dict)]
            except Exception:
                self.flow_nodes = []
            try:
                conns = flow_payload.get("connections")
                if isinstance(conns, list):
                    self.flow_connections = [ConnectionData(**x) for x in conns if isinstance(x, dict)]
            except Exception:
                self.flow_connections = []
            try:
                gvs = flow_payload.get("global_variables")
                if isinstance(gvs, list):
                    self.global_variables = [GlobalVariable(**x) for x in gvs if isinstance(x, dict)]
            except Exception:
                self.global_variables = []

            try:
                if self.pending_lists is None and isinstance(flow_payload.get("pending_lists"), dict):
                    self.pending_lists = PendingLists(**flow_payload.get("pending_lists"))
            except Exception:
                pass

            try:
                if isinstance(flow_payload.get("summary"), dict):
                    self.pending_summary = dict(flow_payload.get("summary") or {})
            except Exception:
                self.pending_summary = None

        # Step4：摘要回填到界面
        if self.flow_nodes or self.flow_connections or self.pending_lists:
            summary = {
                "portraits": len(getattr(self.pending_lists, "portraits", []) or []) if self.pending_lists else 0,
                "backgrounds": len(getattr(self.pending_lists, "backgrounds", []) or []) if self.pending_lists else 0,
                "cgs": len(getattr(self.pending_lists, "cgs", []) or []) if self.pending_lists else 0,
                "voices": len(getattr(self.pending_lists, "voices", []) or []) if self.pending_lists else 0,
                "bgms": len(getattr(self.pending_lists, "bgms", []) or []) if self.pending_lists else 0,
                "flow_nodes": len(self.flow_nodes),
                "connections": len(self.flow_connections),
                "global_variables": len(self.global_variables),
            }
            self.step4_pending_view.setPlainText(json.dumps(summary, ensure_ascii=False, indent=2))
            self.step4_pending_status.setText("状态：已加载（已保存）")
        else:
            self.step4_pending_view.clear()
            self.step4_pending_status.setText("状态：等待章节报文" if not self.chapter_details else "状态：可生成待生成列表")

        # Step4：prompts 指令与结果回填
        saved_prompts_instr = self._saved_step4_prompts_instruction_cache
        if saved_prompts_instr:
            self.step4_prompts_instruction.setPlainText(saved_prompts_instr)
        else:
            # 只有在没有保存内容时才清空，避免覆盖用户当前编辑但未保存的内容
            if not (self.step4_prompts_instruction.toPlainText() or "").strip():
                self.step4_prompts_instruction.clear()

        prompts_payload = getattr(gh, "step5_material_prompts", None)
        if isinstance(prompts_payload, dict):
            structured = prompts_payload.get("structured")
            raw = prompts_payload.get("raw_response")
            if isinstance(structured, dict):
                self.step4_prompts_result.setPlainText(json.dumps(structured, ensure_ascii=False, indent=2))
            elif isinstance(raw, str):
                self.step4_prompts_result.setPlainText(raw)
            self.step4_prompts_status.setText("状态：已加载（已保存）")
        else:
            self.step4_prompts_result.clear()
            self.step4_prompts_status.setText("状态：等待待生成列表")

        # Step5：回填已生成的 vngproj 路径
        try:
            self.vngproj_path = getattr(project.ai_project_info, "vng_project_path", None)
        except Exception:
            self.vngproj_path = None
        if self.vngproj_path:
            s = {
                "project_file": self.vngproj_path,
                "nodes": len(self.flow_nodes),
                "connections": len(self.flow_connections),
            }
            self.step5_result.setPlainText(json.dumps(s, ensure_ascii=False, indent=2))
            self.step5_status.setText("状态：已加载（工程已生成）")
        else:
            if not (self.step5_result.toPlainText() or "").strip():
                self.step5_result.clear()
            self.step5_status.setText("状态：等待流程骨架" if not self.flow_nodes else "状态：可生成 VNG 工程文件")

        self._load_step2_chapter_into_ui()
        self._on_step3_chapter_changed()

    def _reload_chapter_combos(self):
        chapters = []
        if isinstance(self.chapter_plan, dict) and isinstance(self.chapter_plan.get("chapters"), list):
            chapters = [c for c in self.chapter_plan.get("chapters") if isinstance(c, dict)]

        def _fill(combo: QComboBox):
            combo.blockSignals(True)
            combo.clear()
            for idx, c in enumerate(chapters):
                cid = str(c.get("chapter_id") or str(idx + 1))
                title = str(c.get("title") or f"第{idx + 1}章")
                combo.addItem(f"{cid} | {title}", (idx, cid, title))
            combo.blockSignals(False)

        _fill(self.step2_chapter_combo)
        _fill(self.step3_chapter_combo)

    def _current_chapter_info(self, combo: QComboBox) -> tuple[int, str, str] | None:
        data = combo.currentData()
        if not isinstance(data, tuple) or len(data) != 3:
            return None
        idx, cid, title = data
        try:
            return int(idx), str(cid), str(title)
        except Exception:
            return None

    # ==================== Step1：章节列表 ====================

    def save_chapter_list(self):
        if not self._ensure_project():
            return

        raw = (self.step1_titles.toPlainText() or "").strip()
        titles = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        if not titles:
            QMessageBox.warning(self, "提示", "请先输入章节标题（每行一个）。")
            return

        chapters = []
        for i, t in enumerate(titles):
            chapters.append(
                {
                    "chapter_id": str(i + 1),
                    "title": t,
                    "summary": "",
                    "estimated_words": 0,
                    "route": "common",
                }
            )

        structured = {"chapters": chapters, "branch_plan": []}
        payload = {
            "raw_response": raw,
            "structured": structured,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "parameters": {"mode": "import"},
        }

        self.project_manager.update_generation_step("step3_chapters", payload)

        # 同步章节数到 story_config
        try:
            proj = self.project_manager.current_project
            sc = proj.story_config
            sc.chapter_count = len(chapters)
            sc.enable_single_route = True
            sc.enable_multi_branch = False
            sc.enable_choice_node = False
            sc.enable_condition_node = False
            sc.allow_loop_story = False
            self.project_manager.update_story_config(sc)
        except Exception:
            pass

        self.chapter_plan = structured
        self.step1_count_label.setText(f"章节数：{len(chapters)}")
        self.step1_preview.setPlainText(json.dumps(structured, ensure_ascii=False, indent=2))
        self.step1_status.setText("状态：已保存")
        self._reload_chapter_combos()
        self.modified.emit()

    # ==================== Step2：完整剧情来源 ====================

    def pick_step2_txt(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择章节TXT", "", "文本文件 (*.txt)")
        if not file_path:
            return
        self.step2_file_path.setText(file_path)

    def load_step2_txt_into_editor(self):
        fp = (self.step2_file_path.text() or "").strip()
        if not fp:
            QMessageBox.warning(self, "提示", "请先选择 txt 文件路径。")
            return
        p = Path(fp)
        if not p.exists():
            QMessageBox.warning(self, "提示", f"文件不存在：{fp}")
            return
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            text = p.read_text(encoding="gbk", errors="ignore")
        self.step2_text.setPlainText(text)

    def save_step2_chapter_story(self):
        if not self._ensure_project():
            return
        cur = self._current_chapter_info(self.step2_chapter_combo)
        if not cur:
            QMessageBox.warning(self, "提示", "请先配置章节列表。")
            return
        _, cid, _ = cur

        fp = (self.step2_file_path.text() or "").strip()
        text = (self.step2_text.toPlainText() or "").strip()
        source = "file" if (self.step2_use_file.isChecked() and fp) else "text"

        if source == "file" and not fp:
            QMessageBox.warning(self, "提示", "已选择使用关联文件，但未填写路径。")
            return
        if source == "text" and not text:
            QMessageBox.warning(self, "提示", "请粘贴本章完整剧情文本。")
            return

        project = self.project_manager.current_project
        gh = project.generation_history
        if not isinstance(getattr(gh, "import_chapter_sources", None), dict):
            gh.import_chapter_sources = {}

        gh.import_chapter_sources[str(cid)] = {
            "source": source,
            "text": text,
            "file_path": fp,
        }
        project.update_modified_time()

        self.step2_status.setText(f"状态：已保存（chapter_id={cid}）")
        self.modified.emit()

    def _load_step2_chapter_into_ui(self):
        if not self._ensure_project():
            return
        cur = self._current_chapter_info(self.step2_chapter_combo)
        if not cur:
            self.step2_status.setText("状态：等待章节列表")
            return
        _, cid, _ = cur

        gh = self.project_manager.current_project.generation_history
        src = (getattr(gh, "import_chapter_sources", None) or {}).get(str(cid)) if gh else None
        if not isinstance(src, dict):
            src = {}

        self.step2_file_path.blockSignals(True)
        self.step2_use_file.blockSignals(True)
        self.step2_text.blockSignals(True)
        try:
            self.step2_file_path.setText(str(src.get("file_path") or ""))
            self.step2_use_file.setChecked(str(src.get("source") or "text") == "file")
            self.step2_text.setPlainText(str(src.get("text") or ""))
        finally:
            self.step2_file_path.blockSignals(False)
            self.step2_use_file.blockSignals(False)
            self.step2_text.blockSignals(False)

        self.step2_status.setText(f"状态：已加载（chapter_id={cid}）")

    def _get_chapter_story_text(self, chapter_id: str) -> str:
        project = self.project_manager.current_project
        gh = project.generation_history
        src = (getattr(gh, "import_chapter_sources", None) or {}).get(str(chapter_id))
        if not isinstance(src, dict):
            return ""

        source = str(src.get("source") or "text")
        text = str(src.get("text") or "")
        file_path = str(src.get("file_path") or "").strip()

        if source == "file" and file_path:
            p = Path(file_path)
            if p.exists():
                try:
                    return p.read_text(encoding="utf-8")
                except Exception:
                    return p.read_text(encoding="gbk", errors="ignore")
        return text

    # ==================== Step3：结构化转换 ====================

    def _on_step3_chapter_changed(self):
        if not self._ensure_project():
            return
        cur = self._current_chapter_info(self.step3_chapter_combo)
        if not cur:
            self.step3_status.setText("状态：等待章节列表")
            return

        idx, cid, _ = cur
        gh = self.project_manager.current_project.generation_history

        # 指令：优先显示已保存版本
        saved_map = getattr(gh, "step4_saved_instructions", None)
        saved = ""
        if isinstance(saved_map, dict):
            saved = str(saved_map.get(str(idx), "") or "")
        if saved:
            self.step3_instruction.setPlainText(saved)

        # 结果：若已有 step4_chapter_details，则显示对应 raw_response
        raw = ""
        try:
            details = list(getattr(gh, "step4_chapter_details", None) or [])
            if 0 <= idx < len(details):
                item = details[idx]
                if isinstance(item, dict):
                    raw = str(item.get("raw_response") or "")
        except Exception:
            raw = ""
        if raw:
            self.step3_result.setPlainText(raw)

        story_text = self._get_chapter_story_text(cid)
        self.step3_status.setText("状态：可生成提示词" if story_text.strip() else "状态：请先在步骤二保存本章剧情")

    def _get_step4_max_tokens(self) -> int:
        project = self.project_manager.current_project
        gh = project.generation_history
        stored = getattr(gh, "step_max_tokens", None)
        if isinstance(stored, dict) and stored.get("step4") is not None:
            try:
                v = int(stored.get("step4"))
                return max(1024, min(64000, v))
            except Exception:
                pass
        return 64000

    def prepare_step3_instruction(self):
        if not self._ensure_project() or not self._ensure_step_gen():
            return
        if not self.chapter_plan:
            QMessageBox.warning(self, "提示", "请先在步骤一保存章节列表。")
            return

        cur = self._current_chapter_info(self.step3_chapter_combo)
        if not cur:
            return
        idx, cid, title = cur

        chapter_text = self._get_chapter_story_text(cid)
        if not chapter_text.strip():
            QMessageBox.warning(self, "提示", "请先在步骤二保存本章完整剧情（或关联文件）。")
            return

        project = self.project_manager.current_project
        story = project.story_config.model_dump(mode="python")
        chars = [c.model_dump(mode="python") for c in (project.character_config or [])]

        chapter_info = {
            "chapter_id": cid,
            "title": title,
            "chapter_text": chapter_text,
        }

        instruction, params = self.step_generator.prepare_import_chapter_convert_instruction(
            chapter_index=idx,
            chapter_info=chapter_info,
            story_config=story,
            character_config=chars,
            chapters_plan=self.chapter_plan,
        )
        params = dict(params or {})
        params["max_tokens"] = self._get_step4_max_tokens()
        params.setdefault("temperature", 0.2)

        self.step3_instruction.setPlainText(instruction)
        self.step3_status.setText("状态：指令已生成，请先保存指令再发送")

        # 缓存参数到 generation_history.step4_saved_instructions/step4_chapter_details 时会用
        self._step3_params = params
        self.modified.emit()

    def save_step3_instruction(self):
        if not self._ensure_project():
            return
        cur = self._current_chapter_info(self.step3_chapter_combo)
        if not cur:
            return
        idx, _, _ = cur

        text = (self.step3_instruction.toPlainText() or "").strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有可保存的指令。")
            return

        project = self.project_manager.current_project
        gh = project.generation_history
        if not isinstance(getattr(gh, "step4_saved_instructions", None), dict):
            gh.step4_saved_instructions = {}
        gh.step4_saved_instructions[str(idx)] = text
        project.update_modified_time()

        self._saved_step3_instruction_cache[idx] = text
        self.step3_status.setText("状态：指令已保存(内存)")
        self.modified.emit()

    def _ensure_step3_send_instruction(self) -> str | None:
        cur = self._current_chapter_info(self.step3_chapter_combo)
        if not cur:
            return None
        idx, _, _ = cur

        current = (self.step3_instruction.toPlainText() or "").strip()
        if not current:
            QMessageBox.warning(self, "提示", "请先生成/填写提示词。")
            return None

        project = self.project_manager.current_project
        gh = project.generation_history
        saved_map = getattr(gh, "step4_saved_instructions", None)
        saved = str(saved_map.get(str(idx), "") or "") if isinstance(saved_map, dict) else ""

        if saved == current:
            return saved

        box = QMessageBox(self)
        box.setWindowTitle("提示")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("当前指令尚未保存。是否使用当前指令并更新已保存指令？")
        btn_use = box.addButton("使用并保存(内存)", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(btn_use)
        box.exec()
        if box.clickedButton() != btn_use:
            return None

        # 更新已保存指令（内存）
        if not isinstance(getattr(gh, "step4_saved_instructions", None), dict):
            gh.step4_saved_instructions = {}
        gh.step4_saved_instructions[str(idx)] = current
        project.update_modified_time()
        self._saved_step3_instruction_cache[idx] = current
        return current

    def send_step3(self):
        if not self._ensure_project() or not self._ensure_step_gen():
            return

        instruction = self._ensure_step3_send_instruction()
        if not instruction:
            return

        params = getattr(self, "_step3_params", None) or {}
        params = dict(params)
        params["max_tokens"] = self._get_step4_max_tokens()
        temp = 0.2
        try:
            temp = float(params.get("temperature", 0.2))
        except Exception:
            temp = 0.2

        def _task():
            return self.step_generator.generate_import_chapter_structured_from_instruction(
                instruction,
                params,
                temperature=temp,
            )

        def _on_success(result: dict):
            raw = result.get("raw_response") if isinstance(result, dict) else ""
            structured = result.get("structured") if isinstance(result, dict) else None
            self.step3_result.setPlainText(raw if isinstance(raw, str) else "")

            # 写入 generation_history.step4_chapter_details（按章节索引）
            cur = self._current_chapter_info(self.step3_chapter_combo)
            if not cur:
                return
            idx, cid, title = cur

            item = {
                "raw_response": raw if isinstance(raw, str) else "",
                "structured": structured if isinstance(structured, dict) else None,
                "timestamp": result.get("timestamp") if isinstance(result, dict) else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "parameters": dict(params or {}),
                "chapter_id": cid,
                "chapter_title": title,
            }

            project = self.project_manager.current_project
            gh = project.generation_history
            details = list(getattr(gh, "step4_chapter_details", None) or [])
            while len(details) <= idx:
                details.append({})
            details[idx] = item
            self.project_manager.update_generation_step("step4_chapter_details", details)

            self.chapter_details = details
            self.step3_status.setText("状态：已生成")
            self.modified.emit()

        self._run_async(self.step3_status, "状态：生成中", _task, _on_success)

    def save_step3_result(self):
        if not self._ensure_project():
            return
        cur = self._current_chapter_info(self.step3_chapter_combo)
        if not cur:
            return
        idx, cid, title = cur

        text = (self.step3_result.toPlainText() or "").strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有可保存的内容。")
            return

        payload = {
            "raw_response": text,
            "structured": None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "parameters": {"manual": True, "mode": "import"},
            "chapter_id": cid,
            "chapter_title": title,
        }

        project = self.project_manager.current_project
        gh = project.generation_history
        details = list(getattr(gh, "step4_chapter_details", None) or [])
        while len(details) <= idx:
            details.append({})
        details[idx] = payload
        self.project_manager.update_generation_step("step4_chapter_details", details)

        self.chapter_details = details
        self.step3_status.setText("状态：已保存(手动)")
        self.modified.emit()

    # ==================== Step4：pending + prompts ====================

    def _ensure_chapter_details(self) -> bool:
        if not self.chapter_details:
            try:
                proj = self.project_manager.current_project
                details = getattr(proj.generation_history, "step4_chapter_details", None)
                self.chapter_details = list(details or [])
            except Exception:
                self.chapter_details = []
        if not self.chapter_details:
            QMessageBox.warning(self, "提示", "请先在步骤三生成至少一章的结构化报文。")
            return False
        return True

    def generate_pending_lists(self):
        if not self._ensure_project() or not self._ensure_step_gen() or not self._ensure_chapter_details():
            return

        story = self.project_manager.current_project.story_config.model_dump(mode="python")
        chars = [c.model_dump(mode="python") for c in (self.project_manager.current_project.character_config or [])]
        step3_chapters = self.project_manager.current_project.generation_history.step3_chapters

        result = self.step_generator.build_pending_and_flow(
            story,
            chars,
            self.chapter_details,
            personas_data=None,
            chapters_plan=step3_chapters.get("structured") if isinstance(step3_chapters, dict) else None,
        )

        self.pending_lists = result.get("pending_lists")
        self.flow_nodes = result.get("flow_nodes") or []
        self.flow_connections = result.get("connections") or []
        self.global_variables = result.get("global_variables") or []
        self.pending_summary = result.get("summary") or {}

        # 简化摘要展示
        summary = {
            "portraits": len(getattr(self.pending_lists, "portraits", []) or []) if self.pending_lists else 0,
            "backgrounds": len(getattr(self.pending_lists, "backgrounds", []) or []) if self.pending_lists else 0,
            "cgs": len(getattr(self.pending_lists, "cgs", []) or []) if self.pending_lists else 0,
            "voices": len(getattr(self.pending_lists, "voices", []) or []) if self.pending_lists else 0,
            "bgms": len(getattr(self.pending_lists, "bgms", []) or []) if self.pending_lists else 0,
            "flow_nodes": len(self.flow_nodes),
            "connections": len(self.flow_connections),
        }
        self.step4_pending_view.setPlainText(json.dumps(summary, ensure_ascii=False, indent=2))
        self.step4_pending_status.setText("状态：已生成，记得保存")
        self.modified.emit()

    def save_pending_lists(self):
        if not self._ensure_project():
            return
        if not self.pending_lists:
            QMessageBox.warning(self, "提示", "请先生成待生成列表。")
            return

        self.project_manager.update_pending_lists(self.pending_lists)
        flow_payload = {
            "pending_lists": self.pending_lists.model_dump(),
            "flow_nodes": [n.model_dump() for n in self.flow_nodes],
            "connections": [c.model_dump() for c in self.flow_connections],
            "global_variables": [g.model_dump() for g in self.global_variables],
            "summary": self.pending_summary or {},
        }
        self.project_manager.update_generation_step("step5_flow_nodes", flow_payload)
        self.step4_pending_status.setText("状态：已保存")
        self.modified.emit()

    def prepare_material_prompts(self):
        if not self._ensure_project() or not self._ensure_step_gen():
            return
        if not self.pending_lists:
            QMessageBox.warning(self, "提示", "请先生成待生成列表。")
            return

        story = self.project_manager.current_project.story_config.model_dump(mode="python")
        step3_chapters = self.project_manager.current_project.generation_history.step3_chapters

        instruction, params = self.step_generator.prepare_material_prompts_instruction(
            self.pending_lists,
            story_config=story,
            personas_data=None,
            outline_data=None,
            chapters_plan=step3_chapters.get("structured") if isinstance(step3_chapters, dict) else None,
        )
        params = dict(params or {})
        params["max_tokens"] = 8000
        params.setdefault("temperature", 0.4)

        self.step4_prompts_instruction.setPlainText(instruction)
        self.step4_prompts_status.setText("状态：指令已生成，请先保存指令再发送")
        self._step4_prompts_params = params
        self.modified.emit()

    def save_step4_prompts_instruction(self):
        if not self._ensure_project():
            return
        text = (self.step4_prompts_instruction.toPlainText() or "").strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有可保存的指令。")
            return

        project = self.project_manager.current_project
        gh = project.generation_history
        if not isinstance(getattr(gh, "saved_step_instructions", None), dict):
            gh.saved_step_instructions = {}
        gh.saved_step_instructions["step5_prompts"] = text
        project.update_modified_time()
        self._saved_step4_prompts_instruction_cache = text

        self.step4_prompts_status.setText("状态：指令已保存(内存)")
        self.modified.emit()

    def _ensure_step4_prompts_send_instruction(self) -> str | None:
        current = (self.step4_prompts_instruction.toPlainText() or "").strip()
        if not current:
            QMessageBox.warning(self, "提示", "请先生成 prompts 指令。")
            return None

        project = self.project_manager.current_project
        gh = project.generation_history
        saved = ""
        if isinstance(getattr(gh, "saved_step_instructions", None), dict):
            saved = str(gh.saved_step_instructions.get("step5_prompts", "") or "")

        if saved == current:
            return saved

        box = QMessageBox(self)
        box.setWindowTitle("提示")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("当前 prompts 指令尚未保存。是否使用当前指令并更新已保存指令？")
        btn_use = box.addButton("使用并保存(内存)", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(btn_use)
        box.exec()
        if box.clickedButton() != btn_use:
            return None

        if not isinstance(getattr(gh, "saved_step_instructions", None), dict):
            gh.saved_step_instructions = {}
        gh.saved_step_instructions["step5_prompts"] = current
        project.update_modified_time()
        self._saved_step4_prompts_instruction_cache = current
        return current

    def send_material_prompts(self):
        if not self._ensure_project() or not self._ensure_step_gen():
            return
        if not self.pending_lists:
            QMessageBox.warning(self, "提示", "请先生成待生成列表。")
            return

        instruction = self._ensure_step4_prompts_send_instruction()
        if not instruction:
            return

        params = getattr(self, "_step4_prompts_params", None) or {}
        params = dict(params)
        temp = 0.4
        try:
            temp = float(params.get("temperature", 0.4))
        except Exception:
            temp = 0.4

        def _task():
            return self.step_generator.generate_material_prompts_from_instruction(
                instruction,
                params,
                pending_lists=self.pending_lists,
                temperature=temp,
            )

        def _on_success(result: dict):
            structured = result.get("structured") if isinstance(result, dict) else None
            raw = result.get("raw_response") if isinstance(result, dict) else ""
            if isinstance(structured, dict):
                self.step4_prompts_result.setPlainText(json.dumps(structured, ensure_ascii=False, indent=2))
            else:
                self.step4_prompts_result.setPlainText(raw if isinstance(raw, str) else "")

            payload = {
                "raw_response": raw if isinstance(raw, str) else (self.step4_prompts_result.toPlainText() or ""),
                "structured": structured if isinstance(structured, dict) else None,
                "timestamp": result.get("timestamp") if isinstance(result, dict) else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "parameters": dict(params or {}),
            }
            self.project_manager.update_generation_step("step5_material_prompts", payload)
            self.step4_prompts_status.setText("状态：已生成")
            self.modified.emit()

        self._run_async(self.step4_prompts_status, "状态：生成中", _task, _on_success)

    def save_material_prompts_result(self):
        if not self._ensure_project():
            return
        text = (self.step4_prompts_result.toPlainText() or "").strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有可保存的内容。")
            return
        payload = {
            "raw_response": text,
            "structured": None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "parameters": {"manual": True, "mode": "import"},
        }
        self.project_manager.update_generation_step("step5_material_prompts", payload)
        self.step4_prompts_status.setText("状态：已保存(手动)")
        self.modified.emit()

    # ==================== Step5：生成工程文件 ====================

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
        except Exception as exc:  # noqa: BLE001
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
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "错误", f"生成工程失败: {exc}")
            return

        self.vngproj_path = project_file
        self.project_manager.set_vng_project_path(project_file)
        summary = {
            "project_file": project_file,
            "nodes": len(self.flow_nodes),
            "connections": len(self.flow_connections),
        }
        self.step5_result.setPlainText(json.dumps(summary, ensure_ascii=False, indent=2))
        self.step5_status.setText("状态：工程已生成（资源尚未补齐）")
        self.modified.emit()
