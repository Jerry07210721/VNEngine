# -*- coding: utf-8 -*-
"""Designer UI main window using PyQt6."""
import sys
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QToolBar,
    QTextEdit,
    QVBoxLayout,
    QSpinBox,
    QWidget,
)
from pathlib import Path
from PyQt6.QtGui import QAction, QTextCursor, QIcon
from PyQt6.QtCore import Qt, QProcess
from src.core.project_manager import VNProjectManager
from src.game.game_runtime import VNGameRuntime
from src.designer.graph_canvas import GraphView
from src.designer.resource_panel import ResourceDock
from src.designer.properties_panel import PropertiesDock
from src.designer.ui_designer import UILayoutDesigner
from src.designer.menu_designer import MainMenuDesigner
from src.designer.global_vars_dialog import GlobalVarsDialog
from src.packager.packager_manager import PackagerManager
from src.packager.packager_dialog import PackagerDialog


class StartDialog(QDialog):
    """启动选择对话框：新建 / 加载 / 退出。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择操作")
        self.mode: str | None = None
        self.project_path: Path | None = None
        self.project_name: str | None = None
        layout = QVBoxLayout(self)
        tip = QLabel("请选择操作：")
        layout.addWidget(tip)
        btn_new = QPushButton("新建工程")
        btn_open = QPushButton("加载工程")
        btn_exit = QPushButton("退出")
        btn_new.clicked.connect(self._choose_new)
        btn_open.clicked.connect(self._choose_open)
        btn_exit.clicked.connect(self.reject)
        for btn in (btn_new, btn_open, btn_exit):
            layout.addWidget(btn)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

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
        self.current_project_path = None
        self.packager_manager = PackagerManager()
        self.packager_process: QProcess | None = None
        self.packager_output: list[str] = []
        self.packager_log_dialog: "PackagerLogDialog" | None = None
        self.preview_process: QProcess | None = None
        self.preview_output: list[str] = []
        self.project_dir: Path | None = None

        self.init_window()
        self.init_menu_bar()
        self.init_tool_bar()
        self.init_central_widget()
        self.init_resource_dock()
        self.init_properties_dock()
        self.init_status_bar()

    def init_window(self):
        self.setWindowTitle("VNEngine - 视觉小说引擎（设计模式）V0.1")
        self.setGeometry(100, 100, 1200, 800)
        icon_path = self._resolve_icon()
        if icon_path:
            app = QApplication.instance()
            if app:
                app.setWindowIcon(QIcon(str(icon_path)))
            self.setWindowIcon(QIcon(str(icon_path)))

    def _resolve_icon(self) -> Path | None:
        """Locate icon.ico in frozen or dev mode."""
        # 1) frozen temp dir (_MEIPASS)
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent))
        candidates = [base / "icon.ico", Path(__file__).resolve().parent.parent.parent / "icon.ico"]
        for p in candidates:
            if p.exists():
                return p
        return None

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
        self.menuBar().addMenu(ui_menu)

    def init_tool_bar(self):
        tool_bar = QToolBar("常用工具", self)
        self.addToolBar(tool_bar)

        preview_button = QPushButton("预览游戏")
        preview_button.clicked.connect(self.preview_game)
        tool_bar.addWidget(preview_button)

    def init_central_widget(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.graph_view = GraphView(self)
        layout.addWidget(self.graph_view)
        # 当场景选择变化时更新属性面板
        self.graph_view.scene.selectionChanged.connect(self.on_selection_changed)

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

    def _current_resolution(self) -> tuple[int, int]:
        cfg = self.project_manager.project_data.get("game_config", {}) if self.project_manager else {}
        try:
            w = int(cfg.get("window_width", 800))
            h = int(cfg.get("window_height", 600))
        except Exception:
            w, h = 800, 600
        return max(320, w), max(240, h)

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

        try:
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
        try:
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

    def _load_project_file(self, path: Path):
        try:
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

    def _start_preview_process(self):
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
            self.preview_process.setArguments(["--preview", self.current_project_path])
        else:
            program = sys.executable
            module_path = "src.game.preview_runner"
            self.preview_process.setProgram(program)
            self.preview_process.setArguments(["-m", module_path, self.current_project_path])
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
