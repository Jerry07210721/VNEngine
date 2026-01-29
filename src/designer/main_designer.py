# -*- coding: utf-8 -*-
"""Designer UI main window using PyQt6."""
import sys
from PyQt6.QtWidgets import (
    QApplication,
    QCommandLinkButton,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QStatusBar,
    QToolBar,
    QTextEdit,
    QVBoxLayout,
    QSpinBox,
    QProgressDialog,
    QWidget,
)
from pathlib import Path
from PyQt6.QtGui import QAction, QTextCursor, QIcon, QDesktopServices
from PyQt6.QtCore import Qt, QProcess, QThread, pyqtSignal, QUrl
from src.core.project_manager import VNProjectManager
from src.game.game_runtime import VNGameRuntime
from src.designer.graph_canvas import GraphView
from src.designer.resource_panel import ResourceDock
from src.designer.properties_panel import PropertiesDock
from src.designer.ui_designer import UILayoutDesigner
from src.designer.function_menu_designer import FunctionMenuDesigner
from src.designer.menu_designer import MainMenuDesigner
from src.designer.global_vars_dialog import GlobalVarsDialog
from src.designer.ai_assist_dialog import AIAssistDialog, APIConfigDialog
from src.designer.ai_progress_dialog import AIProgressDialog
from src.ai.core.config_manager import ConfigManager
from src.ai.core.master_agent import MasterAgent
from src.ai.core.models import (
    UserConfig,
    ProjectConfig,
    StoryConfig,
    CharacterConfig,
    EnableAgentsConfig,
    MaterialConfig,
)
from src.ai.agents import PlotAgent, PortraitAgent, BackgroundAgent, CGAgent, VoiceAgent, BGMAgent, IntegratorAgent
from src.designer.ai_worker import AITaskWorker
from src.designer.ai_project_window import AIProjectWindow
from src.packager.packager_manager import PackagerManager
from src.packager.packager_dialog import PackagerDialog


def _resolve_app_icon_path() -> Path | None:
    """Locate icon.ico in frozen or dev mode."""
    # 1) frozen temp dir (_MEIPASS)
    project_root = Path(__file__).resolve().parents[2]
    base = Path(getattr(sys, "_MEIPASS", project_root))
    candidates = [base / "icon.ico", project_root / "icon.ico"]
    for p in candidates:
        if p.exists():
            return p
    return None


class StartDialog(QDialog):
    """启动选择对话框：新建 / 加载 / 退出。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VNEngine")
        self.setObjectName("StartDialog")
        self.setMinimumWidth(520)

        icon_path = _resolve_app_icon_path()
        if icon_path:
            app = QApplication.instance()
            if app:
                app.setWindowIcon(QIcon(str(icon_path)))
            self.setWindowIcon(QIcon(str(icon_path)))
        self.mode: str | None = None
        self.project_path: Path | None = None
        self.project_name: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel("欢迎使用 VNEngine")
        title.setProperty("role", "title")
        subtitle = QLabel("请选择开始方式：新建工程、加载工程，或退出")
        subtitle.setProperty("role", "subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        icon_new = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        icon_open = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        icon_exit = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton)

        btn_new = QCommandLinkButton("新建工程", "创建一个新的 VNEngine 工程（.vngproj）")
        btn_new.setIcon(icon_new)
        btn_new.setProperty("variant", "primary")
        btn_new.clicked.connect(self._choose_new)

        btn_open = QCommandLinkButton("加载工程", "打开已有工程并继续编辑")
        btn_open.setIcon(icon_open)
        btn_open.clicked.connect(self._choose_open)

        btn_exit = QCommandLinkButton("退出", "关闭 VNEngine")
        btn_exit.setIcon(icon_exit)
        btn_exit.setProperty("variant", "danger")
        btn_exit.clicked.connect(self.reject)

        layout.addSpacing(6)
        layout.addWidget(btn_new)
        layout.addWidget(btn_open)
        layout.addWidget(btn_exit)
        layout.addStretch(1)

        # keyboard friendly defaults
        btn_new.setDefault(True)
        btn_new.setAutoDefault(True)

    def _choose_new(self):
        self.mode = "new"
        self.accept()

    def _choose_open(self):
        self.mode = "open"
        self.accept()


class ProjectResolutionDialog(QDialog):
    """弹窗：创建工程时选择窗口长宽像素。"""

    def __init__(self, default_size: tuple[int, int] = (800, 600), parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择游戏分辨率")
        self._width = QSpinBox()
        self._height = QSpinBox()
        for sp in (self._width, self._height):
            sp.setRange(320, 4096)
        self._width.setValue(int(default_size[0]))
        self._height.setValue(int(default_size[1]))

        form = QFormLayout(self)
        form.addRow("宽度 (px)", self._width)
        form.addRow("高度 (px)", self._height)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("确定")
        cancel_btn = QPushButton("取消")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch(1)
        form.addRow(btn_row)

    def get_resolution(self) -> tuple[int, int]:
        return int(self._width.value()), int(self._height.value())


class PackagerLogDialog(QDialog):
    """实时显示打包日志的对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("打包日志")
        self.setMinimumSize(700, 420)
        layout = QVBoxLayout(self)
        self.status_label = QLabel("准备中...")
        layout.addWidget(self.status_label)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.text_edit.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 11px;")
        layout.addWidget(self.text_edit)

    def append_text(self, text: str):
        if not text:
            return
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.text_edit.setTextCursor(cursor)
        self.text_edit.insertPlainText(text)
        self.text_edit.moveCursor(QTextCursor.MoveOperation.End)

    def set_status(self, text: str):
        self.status_label.setText(text)


class VNDesignerMainWindow(QMainWindow):
    """视觉小说引擎设计界面主窗口"""

    def __init__(self):
        super().__init__()
        self.project_manager = VNProjectManager()
        self.config_manager = ConfigManager()
        self.master_agent: MasterAgent | None = None
        self.ai_worker: "AITaskWorker" | None = None
        self.ai_progress_dialog: AIProgressDialog | None = None
        self.current_project_path = None
        self.packager_manager = PackagerManager()
        self.packager_process: QProcess | None = None
        self.packager_output: list[str] = []
        self.packager_log_dialog: "PackagerLogDialog" | None = None
        self.preview_process: QProcess | None = None
        self.preview_output: list[str] = []
        self.project_dir: Path | None = None
        
        # AI辅助工程窗口
        self.ai_project_window: AIProjectWindow | None = None

        self.init_window()
        self.init_menu_bar()
        self.init_tool_bar()
        self.init_central_widget()
        self.init_resource_dock()
        self.init_properties_dock()
        self.init_status_bar()

    def init_window(self):
        self.setWindowTitle("VNEngine - 视觉小说引擎（设计模式）V2.5")
        self.setObjectName("VNDesignerMainWindow")
        # 设计模式默认窗口大小：1280x720
        self.setGeometry(100, 100, 1280, 720)
        icon_path = self._resolve_icon()
        if icon_path:
            app = QApplication.instance()
            if app:
                app.setWindowIcon(QIcon(str(icon_path)))
            self.setWindowIcon(QIcon(str(icon_path)))

    def _show_busy_dialog(self, text: str) -> QProgressDialog:
        """显示一个不可取消的忙碌提示，用于大文件打开/保存时避免“卡死”错觉。"""
        dlg = QProgressDialog(text, None, 0, 0, self)
        dlg.setWindowTitle("请稍候")
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setValue(0)
        dlg.show()
        QApplication.processEvents()
        return dlg

    def _find_neighbor_ai_project(self) -> Path | None:
        """在设计模式工程文件同级目录寻找 AI 工程（*.vnai）。

        优先：与 .vngproj 同名的 .vnai；其次：同级目录下最新修改的 .vnai。
        """
        if not self.current_project_path:
            return None
        try:
            base = Path(self.current_project_path)
        except Exception:
            return None
        if not base.exists():
            return None
        folder = base.parent
        preferred = folder / f"{base.stem}.vnai"
        if preferred.exists():
            return preferred
        candidates = list(folder.glob("*.vnai"))
        if not candidates:
            return None
        try:
            return max(candidates, key=lambda p: p.stat().st_mtime)
        except Exception:
            return sorted(candidates)[0]

    def _resolve_icon(self) -> Path | None:
        return _resolve_app_icon_path()

    def init_menu_bar(self):
        file_menu = QMenu("文件(&F)", self)

        new_project_action = QAction("新建工程(&N)", self)
        new_project_action.triggered.connect(self.new_project)
        file_menu.addAction(new_project_action)

        open_project_action = QAction("打开工程(&O)", self)
        open_project_action.triggered.connect(self.open_project)
        file_menu.addAction(open_project_action)

        save_project_action = QAction("保存工程(&S)", self)
        save_project_action.triggered.connect(self.save_project)
        file_menu.addAction(save_project_action)

        edit_resolution_action = QAction("修改分辨率", self)
        edit_resolution_action.triggered.connect(self.edit_resolution)
        file_menu.addAction(edit_resolution_action)

        exit_action = QAction("退出(&E)", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        self.menuBar().addMenu(file_menu)

        pack_menu = QMenu("打包(&P)", self)
        pack_config_action = QAction("打包配置...", self)
        pack_config_action.triggered.connect(self.open_packager_config)
        pack_menu.addAction(pack_config_action)
        pack_run_action = QAction("执行打包", self)
        pack_run_action.triggered.connect(self.run_packager)
        pack_menu.addAction(pack_run_action)
        self.menuBar().addMenu(pack_menu)

        data_menu = QMenu("数据(&D)", self)
        global_var_action = QAction("全局变量设置", self)
        global_var_action.triggered.connect(self.open_global_vars)
        data_menu.addAction(global_var_action)
        self.menuBar().addMenu(data_menu)

        ui_menu = QMenu("UI设计(&U)", self)
        ui_edit_action = QAction("打开UI设计器", self)
        ui_edit_action.triggered.connect(self.open_ui_designer)
        ui_menu.addAction(ui_edit_action)
        menu_design_action = QAction("主菜单设计", self)
        menu_design_action.triggered.connect(self.open_menu_designer)
        ui_menu.addAction(menu_design_action)

        func_menu_action = QAction("功能菜单设计", self)
        func_menu_action.triggered.connect(self.open_function_menu_designer)
        ui_menu.addAction(func_menu_action)
        self.menuBar().addMenu(ui_menu)

        ai_menu = QMenu("AI 辅助(&A)", self)
        
        # 新的AI辅助工程入口
        ai_project_action = QAction("AI辅助生成", self)
        ai_project_action.triggered.connect(self.open_ai_project_window)
        ai_menu.addAction(ai_project_action)

        ai_menu.addSeparator()
        ai_help = QAction("使用帮助", self)
        ai_help.triggered.connect(self.open_ai_help)
        ai_menu.addAction(ai_help)
        self.menuBar().addMenu(ai_menu)

        help_menu = QMenu("帮助(&H)", self)
        contact_action = QAction("联系我们", self)
        contact_action.triggered.connect(self.open_contact_us)
        help_menu.addAction(contact_action)
        self.menuBar().addMenu(help_menu)

    def init_tool_bar(self):
        tool_bar = QToolBar("常用工具", self)
        self.addToolBar(tool_bar)

        preview_button = QPushButton("预览游戏")
        try:
            preview_button.setProperty("variant", "primary")
            preview_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        except Exception:
            pass
        preview_button.clicked.connect(self.preview_game)
        tool_bar.addWidget(preview_button)

        save_btn = QPushButton("保存工程")
        try:
            save_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        except Exception:
            pass
        save_btn.clicked.connect(self.save_project)
        tool_bar.addWidget(save_btn)

        ai_btn = QPushButton("AI辅助生成")
        try:
            ai_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        except Exception:
            pass
        ai_btn.clicked.connect(self.open_ai_project_window)
        tool_bar.addWidget(ai_btn)

    def init_central_widget(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.graph_view = GraphView(self)
        layout.addWidget(self.graph_view)
        # 当场景选择变化时更新属性面板
        self.graph_view.scene.selectionChanged.connect(self.on_selection_changed)

        # 预览：从指定节点开始（右键节点）
        self.graph_view.previewFromNodeRequested.connect(self.preview_game_from_node)

    def init_resource_dock(self):
        self.resource_dock = ResourceDock(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.resource_dock)

    def init_status_bar(self):
        status_bar = QStatusBar()
        status_bar.showMessage("就绪 - 未打开任何工程")
        self.setStatusBar(status_bar)

    def init_properties_dock(self):
        self.properties_dock = PropertiesDock(self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.properties_dock)
        self.properties_dock.set_graph_view(self.graph_view)

    def open_ai_assist(self):
        dlg = AIAssistDialog(config_manager=self.config_manager, parent=self)
        dlg.exec()
    
    def open_ai_project_window(self):
        """打开AI辅助工程窗口（新架构）"""
        if self.ai_project_window is None:
            # 必须是独立顶层窗口（无 parent），否则会变成“从属窗口”：
            # - 始终压在父窗口上层
            # - Windows 任务栏不显示独立窗口
            self.ai_project_window = AIProjectWindow(None)

        # 若设计模式已打开工程，则尝试加载同级目录下的 AI 工程文件（*.vnai）
        ai_path = self._find_neighbor_ai_project()
        if ai_path is not None:
            try:
                self.ai_project_window.load_project_file(str(ai_path))
            except Exception:
                # 自动加载失败时不影响窗口打开，保持原逻辑
                pass
        
        self.ai_project_window.show()
        self.ai_project_window.raise_()
        self.ai_project_window.activateWindow()

    def open_api_config(self):
        dlg = APIConfigDialog(config_manager=self.config_manager, parent=self)
        dlg.exec()

    def open_ai_help(self):
        help_path = Path(__file__).resolve().parents[2] / "docs" / "AI_ASSIST_HELP.md"
        if help_path.exists():
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(help_path)))
            if opened:
                return

        QMessageBox.information(
            self,
            "AI 辅助使用帮助",
            f"未能自动打开帮助文档。请手动查看：{help_path}",
        )

    def open_contact_us(self):
        # UI-only: contact/help information dialog
        QMessageBox.about(
            self,
            "联系我们",
            "VNEngine\n\n"
            "如需联系/反馈建议，可通过以下方式：\n"
            "1) GitHub: https://github.com/Jerry07210721/VNEngine\n"
            "2) E-mail: 1732769392@qq.com\n\n",
        )

    def start_ai_generation(self):
        """读取 ai_config 并启动 MasterAgent，进度联动到 AIProgressDialog。"""

        try:
            cfg = self.config_manager.load_config() or {}
            user_config = self._build_user_config_from_ai_cfg(cfg)
        except Exception as exc:
            QMessageBox.critical(self, "配置错误", f"无法解析 ai_config.yaml：{exc}")
            return

        self.master_agent = MasterAgent(config_manager=self.config_manager)
        self._register_agents_for_master(user_config)

        progress = self.master_agent.start_task(user_config)

        # 展示进度对话框
        self.ai_progress_dialog = AIProgressDialog(self)
        self.ai_progress_dialog.update_progress(progress)
        self.ai_progress_dialog.canceled.connect(self._cancel_ai_tasks)
        self.ai_progress_dialog.show()

        # 后台线程执行任务并实时回调
        self.ai_worker = AITaskWorker(self.master_agent)
        self.ai_worker.progress_signal.connect(self.ai_progress_dialog.update_progress)
        self.ai_worker.log_signal.connect(self.ai_progress_dialog.append_log)
        self.ai_worker.finished_signal.connect(self._on_ai_finished)
        self.ai_worker.start()

    def _current_resolution(self) -> tuple[int, int]:
        cfg = self.project_manager.project_data.get("game_config", {}) if self.project_manager else {}
        try:
            w = int(cfg.get("window_width", 800))
            h = int(cfg.get("window_height", 600))
        except Exception:
            w, h = 800, 600
        return max(320, w), max(240, h)

    def _build_user_config_from_ai_cfg(self, cfg: dict) -> UserConfig:
        proj_cfg = cfg.get("project_settings", {})
        story_cfg = cfg.get("story_config", {})
        material_cfg = cfg.get("material_settings", {})
        agent_cfg = (cfg.get("agent_settings") or {}).get("enable_agents", {})
        chars = cfg.get("character_config", []) or []

        project_name = proj_cfg.get("project_name") or story_cfg.get("title") or "AIProject"
        resource_root = proj_cfg.get("resource_root", "output/projects")
        project_path = str(Path(resource_root) / project_name)

        project_info = ProjectConfig(
            project_path=project_path,
            project_name=project_name,
            window_width=int(proj_cfg.get("default_window_width", 1280)),
            window_height=int(proj_cfg.get("default_window_height", 720)),
            engine_version=proj_cfg.get("engine_version", "V2.0-AI"),
        )

        story = StoryConfig(
            title=story_cfg.get("title", project_name),
            style=story_cfg.get("style", ""),
            plot_outline=story_cfg.get("plot_outline", ""),
            text_volume=int(story_cfg.get("text_volume", 5000)),
            chapter_count=int(story_cfg.get("chapter_count", 5)),
            enable_choice_node=bool(story_cfg.get("enable_choice_node", False)),
            enable_condition_node=bool(story_cfg.get("enable_condition_node", False)),
            enable_multi_branch=bool(story_cfg.get("enable_multi_branch", False)),
            enable_single_route=bool(story_cfg.get("enable_single_route", False)),
            condition_type="favorability",
            character_hint_weight=float(story_cfg.get("character_hint_weight", 0.7)),
            narrative_pov=story_cfg.get("narrative_pov", "third"),
            first_person_name=story_cfg.get("first_person_name", "我"),
            first_person_has_portrait=bool(story_cfg.get("first_person_has_portrait", False)),
            first_person_has_voice=bool(story_cfg.get("first_person_has_voice", False)),
            first_person_cg_presence=bool(story_cfg.get("first_person_cg_presence", True)),
            first_person_cg_notes=story_cfg.get("first_person_cg_notes", ""),
        )

        characters: list[CharacterConfig] = []
        for ch in chars:
            if not (ch.get("char_name") or ch.get("name")):
                continue
            characters.append(
                CharacterConfig(
                    char_id=ch.get("char_id") or ch.get("char_name", "").lower().replace(" ", "_"),
                    char_name=ch.get("char_name") or ch.get("name", "角色"),
                    is_player=ch.get("is_player", False),
                    is_first_person=ch.get("is_first_person", False),
                    persona_keywords=ch.get("persona_keywords", ""),
                    reference_image=ch.get("reference_image"),
                    voice_tone=ch.get("voice_tone"),
                    voice_model_id=ch.get("voice_model_id"),
                )
            )

        enable_agents = EnableAgentsConfig(
            plot_agent=bool(agent_cfg.get("plot_agent", True)),
            portrait_agent=bool(agent_cfg.get("portrait_agent", True)),
            background_agent=bool(agent_cfg.get("background_agent", True)),
            cg_agent=bool(agent_cfg.get("cg_agent", True)),
            voice_api=bool(agent_cfg.get("voice_api", True)),
            bgm_api=bool(agent_cfg.get("bgm_api", True)),
        )

        material = MaterialConfig(
            portrait_format=material_cfg.get("portrait", {}).get("format", "png"),
            background_format=material_cfg.get("background", {}).get("format", "jpg"),
            cg_format=material_cfg.get("cg", {}).get("format", "png"),
            voice_format=material_cfg.get("voice", {}).get("format", "mp3"),
            bgm_format=material_cfg.get("bgm", {}).get("format", "mp3"),
        )

        return UserConfig(
            project_info=project_info,
            story_config=story,
            character_config=characters,
            enable_agents=enable_agents,
            material_config=material,
        )

    def _register_agents_for_master(self, user_config: UserConfig):
        if not self.master_agent:
            return
        try:
            if user_config.enable_agents.plot_agent:
                self.master_agent.register_agent("plot_agent", PlotAgent(self.config_manager, self.master_agent.api_manager))
            if user_config.enable_agents.portrait_agent:
                self.master_agent.register_agent("portrait_agent", PortraitAgent(self.config_manager, self.master_agent.api_manager))
            if user_config.enable_agents.background_agent:
                self.master_agent.register_agent("background_agent", BackgroundAgent(self.config_manager, self.master_agent.api_manager))
            if user_config.enable_agents.cg_agent:
                self.master_agent.register_agent("cg_agent", CGAgent(self.config_manager, self.master_agent.api_manager))
            if user_config.enable_agents.voice_api:
                self.master_agent.register_agent("voice_agent", VoiceAgent(self.config_manager, self.master_agent.api_manager))
            if user_config.enable_agents.bgm_api:
                self.master_agent.register_agent("bgm_agent", BGMAgent(self.config_manager, self.master_agent.api_manager))
            # 整合 Agent 始终注册，作为收尾步骤
            self.master_agent.register_agent("integrator_agent", IntegratorAgent(self.config_manager))
        except Exception as exc:
            QMessageBox.warning(self, "Agent 注册", f"部分 Agent 注册失败：{exc}")

    def _cancel_ai_tasks(self):
        if self.ai_worker:
            self.ai_worker.request_cancel()
            self.ai_progress_dialog.append_log("已请求取消，等待当前任务结束...")

    def _on_ai_finished(self):
        if self.ai_progress_dialog:
            self.ai_progress_dialog.append_log("AI 任务已结束。")
            self.ai_progress_dialog.update_progress(self.master_agent.get_progress() if self.master_agent else None)
        self.statusBar().showMessage("AI 生成完成")

    def new_project(self):
        """交互式新建工程：询问名称和目录，创建隔离文件夹。"""
        name, _ = QFileDialog.getSaveFileName(self, "输入工程名并选择保存位置", "", "VNEngine工程文件 (*.vngproj)")
        if not name:
            return
        file_path = Path(name)
        if file_path.suffix != ".vngproj":
            file_path = file_path.with_suffix(".vngproj")
        project_dir = file_path.parent
        project_name = file_path.stem
        # 选择项目分辨率（创建后不可修改）
        default_res = self._current_resolution()
        res_dialog = ProjectResolutionDialog(default_res, self)
        if res_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        width, height = res_dialog.get_resolution()

        self._create_project_structure(project_dir, project_name)
        self._create_or_overwrite_project(project_dir, project_name, file_path, width, height)

    def open_project(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开工程", "", "VNEngine工程文件 (*.vngproj)"
        )
        if not file_path:
            return
        self._load_project_file(Path(file_path))

    def edit_resolution(self):
        if not self.project_manager or not self.project_manager.project_data:
            QMessageBox.information(self, "提示", "请先新建或打开工程后再修改分辨率。")
            return
        current_w, current_h = self._current_resolution()
        dlg = ProjectResolutionDialog((current_w, current_h), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_w, new_h = dlg.get_resolution()
        cfg = self.project_manager.project_data.setdefault("game_config", {})
        cfg["window_width"] = int(new_w)
        cfg["window_height"] = int(new_h)
        self.statusBar().showMessage(f"分辨率已更新：{new_w}x{new_h}（请保存工程后生效）")

    def save_project(self):
        if not self.current_project_path:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "保存工程", "", "VNEngine工程文件 (*.vngproj)"
            )
            if not file_path:
                return
            self.current_project_path = file_path
            self._apply_project_dir(Path(file_path).parent)

        busy = None
        try:
            busy = self._show_busy_dialog("正在保存工程文件，请稍候...")
            # 同步画布数据到工程数据
            self.project_manager.project_data["flow_nodes"] = self.graph_view.export_scene()
            self.project_manager.project_data["resources"] = self.resource_dock.export_data()
            self.project_manager.save_project(self.current_project_path)
            project_name = self.project_manager.project_data["project_info"]["name"]
            self.statusBar().showMessage(
                f"工程已保存：{project_name} - {self.current_project_path}"
            )
            QMessageBox.information(self, "提示", f"工程「{project_name}」保存成功。")
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"保存工程失败：{str(exc)}")
        finally:
            if busy is not None:
                try:
                    busy.close()
                    busy.deleteLater()
                except Exception:
                    pass

    def _load_flow_nodes_from_data(self, data: dict):
        flow_data = data.get("flow_nodes") if isinstance(data, dict) else None
        if isinstance(flow_data, dict):
            self.graph_view.load_scene(flow_data)
        else:
            self.graph_view.clear_scene()
        self.properties_dock.bind_node(None)

    def _load_resources_from_data(self, data: dict):
        res_data = data.get("resources") if isinstance(data, dict) else None
        self.resource_dock.load_from_data(res_data)

    def _apply_project_dir(self, project_dir: Path | None):
        self.project_dir = project_dir
        self.resource_dock.set_project_dir(project_dir)
        self.properties_dock.set_project_dir(project_dir)

    def open_ui_designer(self):
        if not self.project_dir:
            QMessageBox.warning(self, "提示", "请先新建或加载工程后再设计UI。")
            return
        dlg = UILayoutDesigner(self.project_dir, self._current_resolution(), self)
        dlg.exec()

    def open_menu_designer(self):
        if not self.project_dir:
            QMessageBox.warning(self, "提示", "请先新建或加载工程后再设计主菜单。")
            return
        dlg = MainMenuDesigner(self.project_dir, self.project_manager, self._current_resolution(), self)
        dlg.exec()

    def open_function_menu_designer(self):
        if not self.project_dir:
            QMessageBox.warning(self, "提示", "请先新建或加载工程后再设计功能菜单。")
            return
        dlg = FunctionMenuDesigner(Path(self.project_dir), self.project_manager, self._current_resolution(), self)
        dlg.exec()

    def open_global_vars(self):
        dlg = GlobalVarsDialog(self.project_manager, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("全局变量已更新")

    def _create_project_structure(self, project_dir: Path, project_name: str):
        project_dir.mkdir(parents=True, exist_ok=True)
        res_root = project_dir / "resources"
        for sub in ["images", "audios", "portraits", "voices", "videos"]:
            (res_root / sub).mkdir(parents=True, exist_ok=True)
        (project_dir / "ui").mkdir(parents=True, exist_ok=True)
        (project_dir / "saves").mkdir(parents=True, exist_ok=True)

    def _create_or_overwrite_project(self, project_dir: Path, project_name: str, project_file: Path, width: int, height: int):
        busy = None
        try:
            busy = self._show_busy_dialog("正在创建/保存工程文件，请稍候...")
            self.project_manager.new_project(project_name, width, height)
            self.current_project_path = str(project_file)
            self._apply_project_dir(project_dir)
            self.graph_view.clear_scene()
            self.resource_dock.clear_all()
            self.properties_dock.bind_node(None)
            self.project_manager.save_project(self.current_project_path)
            self.statusBar().showMessage(f"已新建工程：{project_name} ({width}x{height}) - {project_file}")
            QMessageBox.information(self, "提示", f"工程「{project_name}」已创建。\n分辨率：{width}x{height}")
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"新建工程失败：{str(exc)}")
        finally:
            if busy is not None:
                try:
                    busy.close()
                    busy.deleteLater()
                except Exception:
                    pass

    def _load_project_file(self, path: Path):
        busy = None
        try:
            busy = self._show_busy_dialog("正在打开工程文件，请稍候...")
            data = self.project_manager.open_project(str(path))
            self.current_project_path = str(path)
            self._apply_project_dir(path.parent)
            self._load_flow_nodes_from_data(data)
            self._load_resources_from_data(data)
            self.properties_dock.bind_node(None)
            project_name = self.project_manager.project_data["project_info"].get("name", path.stem)
            w, h = self._current_resolution()
            self.statusBar().showMessage(f"已打开工程：{project_name} ({w}x{h}) - {path}")
            QMessageBox.information(self, "提示", f"工程「{project_name}」打开成功。")
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"打开工程失败：{str(exc)}")
        finally:
            if busy is not None:
                try:
                    busy.close()
                    busy.deleteLater()
                except Exception:
                    pass

    def preview_game(self):
        try:
            # 确保当前工程路径存在，且保存最新数据后再预览
            if not self.current_project_path:
                QMessageBox.warning(self, "提示", "请先保存工程，再进行预览。")
                return
            analysis = self.graph_view.analyze_flow()
            warn_msgs = []
            if analysis.get("has_cycle"):
                warn_msgs.append("检测到循环：预览时可能无法正常结束。")
            if not analysis.get("start_nodes"):
                warn_msgs.append("没有起始节点：请添加至少一个无入度节点。")
            if analysis.get("unreachable"):
                warn_msgs.append(f"有 {len(analysis.get('unreachable'))} 个节点不可达：预览时将被跳过。")
            mismatches = analysis.get("choice_mismatch", [])
            if mismatches:
                detail_lines = [f"选择节点 {nid}：选项数 {opt} ≠ 出边数 {out}" for nid, opt, out in mismatches]
                warn_msgs.append("\n".join(detail_lines))
            cond_mismatches = analysis.get("condition_mismatch", [])
            if cond_mismatches:
                detail_lines = [f"条件节点 {nid}：出边数 {out}，应为2 (真/假)" for nid, out in cond_mismatches]
                warn_msgs.append("\n".join(detail_lines))
            if warn_msgs:
                detail = "\n".join(warn_msgs)
                choice = QMessageBox.warning(self, "流程警告", f"{detail}\n仍要启动预览吗？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if choice != QMessageBox.StandardButton.Yes:
                    return
            # 先保存一次，保证数据与画布同步
            self.project_manager.project_data["flow_nodes"] = self.graph_view.export_scene()
            self.project_manager.project_data["resources"] = self.resource_dock.export_data()
            self.project_manager.save_project(self.current_project_path)
            self._start_preview_process()
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"启动游戏预览失败：{str(exc)}")

    def preview_game_from_node(self, node_id: int):
        """从指定流程节点启动预览（由流程图右键菜单触发）。"""
        try:
            if not self.current_project_path:
                QMessageBox.warning(self, "提示", "请先保存工程，再进行预览。")
                return
            # 先保存一次，保证数据与画布同步
            self.project_manager.project_data["flow_nodes"] = self.graph_view.export_scene()
            self.project_manager.project_data["resources"] = self.resource_dock.export_data()
            self.project_manager.save_project(self.current_project_path)
            self._start_preview_process(start_node_id=int(node_id))
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"启动游戏预览失败：{str(exc)}")

    def open_packager_config(self):
        """打开打包配置对话框"""
        if not self.current_project_path:
            QMessageBox.warning(self, "提示", "请先保存工程，再进行打包配置。")
            return
        
        project_dir = Path(self.current_project_path).parent
        
        cfg_probe = self.packager_manager.load_config(self.current_project_path)
        # 先验证PyInstaller（若配置里指定了 python_path 会优先使用）
        available, info = self.packager_manager.verify_pyinstaller(cfg_probe.get("python_path"))
        if not available:
            msg = f"PyInstaller不可用：{info}\n\n请在命令行中执行以下命令安装：\npip install pyinstaller\n\n仍要继续配置吗？"
            reply = QMessageBox.warning(
                self,
                "PyInstaller未安装",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        cfg = self.packager_manager.load_config(self.current_project_path)
        dialog = PackagerDialog(project_dir, cfg, self.packager_manager, self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_cfg = dialog.get_config()
            try:
                self.packager_manager.save_config(self.current_project_path, new_cfg)
                self.statusBar().showMessage("打包配置已保存")
                QMessageBox.information(self, "提示", "打包配置已保存。\n点击「执行打包」按钮开始打包。")
            except Exception as exc:
                QMessageBox.critical(self, "错误", f"保存打包配置失败：{str(exc)}")

    def run_packager(self):
        """执行打包"""
        if self.packager_process and self.packager_process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, "提示", "打包正在进行中，请稍候完成。")
            return
        
        if not self.current_project_path:
            QMessageBox.warning(self, "提示", "请先保存工程，再进行打包。")
            return
        
        cfg = self.packager_manager.load_config(self.current_project_path)

        # 验证PyInstaller（考虑配置中的外部Python路径，优先无控制台的解释器）
        available, info = self.packager_manager.verify_pyinstaller(cfg.get("python_path"))
        if not available:
            QMessageBox.critical(
                self,
                "无法打包",
                f"PyInstaller不可用：{info}\n\n请在命令行中执行：\npip install pyinstaller"
            )
            return
        
        project_dir = Path(self.current_project_path).parent
        
        # 清理旧文件
        if cfg.get("clean_before_build", True):
            try:
                self.packager_manager.clean_build_artifacts(self.current_project_path)
                self.statusBar().showMessage("已清理旧的构建文件...")
            except Exception as exc:
                QMessageBox.warning(self, "警告", f"清理构建文件失败：{str(exc)}\n仍将继续打包。")
        
        # 构建命令
        try:
            cmd = self.packager_manager.build_pyinstaller_command(self.current_project_path, cfg)
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"生成打包命令失败：{str(exc)}")
            return
        
        if not cmd:
            QMessageBox.warning(self, "提示", "打包命令生成失败，请检查配置。")
            return
        
        # 显示确认对话框
        cmd_str = " ".join(cmd)
        # 为避免弹窗过大，仅展示命令前 200 字符，尾部省略
        short_cmd = (cmd_str[:200] + " ...") if len(cmd_str) > 200 else cmd_str
        msg = (
            "即将执行打包命令：\n\n"
            f"{short_cmd}\n\n"
            f"工作目录：{project_dir}\n\n"
            "打包可能需要几分钟时间，确定继续吗？"
        )
        reply = QMessageBox.question(
            self,
            "确认打包",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # 启动打包进程
        self.packager_output = []
        self.packager_process = QProcess(self)
        self.packager_process.setProgram(cmd[0])
        self.packager_process.setArguments(cmd[1:])
        self.packager_process.setWorkingDirectory(str(project_dir))
        self.packager_process.readyReadStandardOutput.connect(self._on_packager_stdout)
        self.packager_process.readyReadStandardError.connect(self._on_packager_stderr)
        self.packager_process.finished.connect(self._on_packager_finished)
        
        try:
            # 打开/重置日志窗口
            if self.packager_log_dialog is None:
                self.packager_log_dialog = PackagerLogDialog(self)
            self.packager_log_dialog.set_status("正在打包...")
            self.packager_log_dialog.text_edit.clear()
            self.packager_log_dialog.append_text(f"工作目录: {project_dir}\n命令: {' '.join(cmd)}\n\n")
            self.packager_log_dialog.show()
            self.packager_log_dialog.raise_()
            self.packager_log_dialog.activateWindow()

            self.packager_process.start()
            self.statusBar().showMessage("正在打包，请稍候...")
            QMessageBox.information(self, "提示", "已开始打包，请稍候。完成后会弹出提示。\n\n可以在状态栏查看进度。")
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"启动打包进程失败：{str(exc)}")

    def _on_packager_stdout(self):
        if not self.packager_process:
            return
        text = bytes(self.packager_process.readAllStandardOutput()).decode(errors="ignore")
        if text:
            self.packager_output.append(text)
            if self.packager_log_dialog:
                self.packager_log_dialog.append_text(text)

    def _on_packager_stderr(self):
        if not self.packager_process:
            return
        text = bytes(self.packager_process.readAllStandardError()).decode(errors="ignore")
        if text:
            self.packager_output.append(text)
            if self.packager_log_dialog:
                self.packager_log_dialog.append_text(text)

    def _on_packager_finished(self, exit_code, exit_status):
        status = "成功" if exit_code == 0 else "失败"
        log_text = "".join(self.packager_output[-20:])
        self.statusBar().showMessage(f"打包{status}")
        if self.packager_log_dialog:
            self.packager_log_dialog.set_status(f"打包{status} (退出码 {exit_code})")
        if exit_code == 0:
            QMessageBox.information(self, "打包完成", f"打包成功！\n输出目录：{Path(self.current_project_path).parent / 'dist'}")
        else:
            QMessageBox.critical(self, "打包失败", f"打包失败，退出码 {exit_code}\n最近输出：\n{log_text}")
        self.packager_process = None

    def _start_preview_process(self, start_node_id: int | None = None):
        # 若已有预览进程，先终止
        if self.preview_process and self.preview_process.state() != QProcess.ProcessState.NotRunning:
            self.preview_process.kill()
            self.preview_process.waitForFinished(2000)
        self.preview_output = []
        self.preview_process = QProcess(self)
        repo_root = Path(__file__).resolve().parent.parent.parent
        self.preview_process.setWorkingDirectory(str(repo_root))
        if getattr(sys, "frozen", False):
            # 已打包环境：复用自身 exe，使用 --preview 路由到预览
            program = sys.executable
            self.preview_process.setProgram(program)
            args = ["--preview", self.current_project_path]
            if start_node_id is not None:
                args += ["--start-node", str(int(start_node_id))]
            self.preview_process.setArguments(args)
        else:
            program = sys.executable
            module_path = "src.game.preview_runner"
            self.preview_process.setProgram(program)
            args = ["-m", module_path, self.current_project_path]
            if start_node_id is not None:
                args += ["--start-node", str(int(start_node_id))]
            self.preview_process.setArguments(args)
        self.preview_process.readyReadStandardOutput.connect(self._on_preview_stdout)
        self.preview_process.readyReadStandardError.connect(self._on_preview_stderr)
        self.preview_process.finished.connect(self._on_preview_finished)
        self.preview_process.start()
        self.statusBar().showMessage("预览已启动（独立进程）")

    def _on_preview_stdout(self):
        if not self.preview_process:
            return
        text = bytes(self.preview_process.readAllStandardOutput()).decode(errors="ignore")
        if text:
            self.preview_output.append(text)

    def _on_preview_stderr(self):
        if not self.preview_process:
            return
        text = bytes(self.preview_process.readAllStandardError()).decode(errors="ignore")
        if text:
            self.preview_output.append(text)

    def _on_preview_finished(self, exit_code, exit_status):
        if exit_code != 0:
            log_text = "".join(self.preview_output[-20:])
            QMessageBox.warning(self, "预览退出", f"预览进程退出码 {exit_code}\n最近输出：\n{log_text}")
        self.statusBar().showMessage("预览进程已结束")
        self.preview_process = None

    def on_selection_changed(self):
        selected = [item for item in self.graph_view.scene.selectedItems()]
        if not selected:
            self.properties_dock.bind_node(None)
            return
        node = next((i for i in selected if hasattr(i, "set_title")), None)
        self.properties_dock.bind_node(node)

    def closeEvent(self, event):  # noqa: N802
        # 关闭前终止预览进程，避免孤儿进程
        if self.preview_process and self.preview_process.state() != QProcess.ProcessState.NotRunning:
            self.preview_process.kill()
            self.preview_process.waitForFinished(1000)
        super().closeEvent(event)


def run_designer():
    app = QApplication(sys.argv)
    # Apply VNEngine commercial theme (UI only)
    try:
        from src.designer.ui_theme import apply_vnengine_theme

        apply_vnengine_theme(app)
    except Exception:
        # Theme failure must not block app startup
        pass
    icon_path = _resolve_app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(str(icon_path)))
    start = StartDialog()
    if start.exec() != QDialog.DialogCode.Accepted or not start.mode:
        sys.exit(0)

    window = VNDesignerMainWindow()
    if start.mode == "open":
        window.open_project()
    elif start.mode == "new":
        window.new_project()
    window.show()
    sys.exit(app.exec())
