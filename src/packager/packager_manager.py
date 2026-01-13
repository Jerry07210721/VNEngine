# -*- coding: utf-8 -*-
"""
打包管理器 - 负责PyInstaller打包配置和执行
支持venv虚拟环境下的打包
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import importlib.metadata
import yaml


class PackagerManager:
    """视觉小说引擎打包管理器"""

    def __init__(self):
        self.default_config = {
            "app_name": "MyVNGame",
            "version": "1.0.0",
            "author": "",
            "description": "",
            "icon_path": "",
            "python_path": "",  # 可选：用于指定外部Python（在打包后的引擎内再打包时使用）
            "one_file": False,  # False = 文件夹模式, True = 单文件模式
            "console": False,  # 是否显示控制台窗口
            "clean_before_build": True,
            "include_resources": True,
            "compression": True,
            "extra_data": [],  # 额外的数据文件 [(src, dst), ...]
            "hidden_imports": [],  # 隐藏导入
        }

    def load_config(self, project_path: str) -> Dict:
        """从工程目录加载打包配置，并尽量自动填充 Python 路径。

        注意：工程目录与引擎安装目录可能不同，优先在引擎所在目录寻找便携 Python，
        其次才尝试工程同级目录的 venv_pack/venv1/pack_venv。
        """
        project_dir = Path(project_path).parent
        config_file = project_dir / "packager_config.yaml"
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f) or {}
                # 合并默认配置
                config = self.default_config.copy()
                config.update(loaded)
                if not config.get("python_path"):
                    auto_py = self._suggest_pack_python(project_dir)
                    if auto_py:
                        config["python_path"] = str(auto_py)
                return config
            except Exception as e:
                print(f"加载打包配置失败: {e}")
                return self.default_config.copy()
        # 配置文件不存在时，也尝试自动填充 python_path
        config = self.default_config.copy()
        auto_py = self._suggest_pack_python(Path(project_path).parent)
        if auto_py:
            config["python_path"] = str(auto_py)
        return config

    def save_config(self, project_path: str, config: Dict) -> None:
        """保存打包配置到工程目录"""
        config_file = Path(project_path).parent / "packager_config.yaml"
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True, indent=4)
        except Exception as e:
            raise Exception(f"保存打包配置失败: {e}")

    def verify_pyinstaller(self, python_path: str | None = None) -> Tuple[bool, str]:
        """验证PyInstaller是否可用。

        在非冻结环境下尝试直接导入；在冻结环境（打包后的引擎）下，
        使用提供或自动探测的外部 Python 调用 ``python -m PyInstaller --version``。
        """
        candidate = Path(python_path) if python_path else None

        if getattr(sys, "frozen", False):
            # 冻结环境：用外部Python检测
            python_exe = candidate or self._find_external_python(prefer_windowless=True)
            if not python_exe:
                return False, "未找到可用的Python解释器，请在配置中指定 python_path 或设置环境变量 VNE_PYTHON"
            cmd = [str(python_exe), "-m", "PyInstaller", "--version"]
            try:
                result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=15)
                return True, result.strip()
            except Exception as exc:
                return False, f"PyInstaller 检测失败：{exc}"

        # 非冻结环境：直接尝试导入
        try:
            import PyInstaller

            version = PyInstaller.__version__
            return True, f"PyInstaller {version} 已安装"
        except ImportError:
            return False, "PyInstaller未安装"

    def get_python_executable(self, override: str | None = None, prefer_windowless: bool = False) -> str:
        """返回用于打包的Python可执行文件。

        - override 优先；可指向 python.exe 或 pythonw.exe。
        - 冻结环境下避免使用自身 exe，改为查找外部 Python（配置 python_path、环境变量 VNE_PYTHON、PATH）。
        - prefer_windowless=True 时会优先选择同目录的 pythonw.exe，减少黑窗闪现。
        """
        if override:
            return self._prefer_pythonw(Path(override)) if prefer_windowless else override

        if getattr(sys, "frozen", False):
            ext = self._find_external_python(prefer_windowless=prefer_windowless)
            if ext:
                return str(ext)
            raise RuntimeError("冻结环境中未找到可用的Python，请在配置中填写 python_path 或设置环境变量 VNE_PYTHON")

        return sys.executable

    def _prefer_pythonw(self, exe: Path) -> str:
        if exe.name.lower() == "python.exe":
            candidate = exe.parent / "pythonw.exe"
            if candidate.exists():
                return str(candidate)
        return str(exe)

    def _find_external_python(self, prefer_windowless: bool = False) -> Path | None:
        """在冻结环境下寻找可用的外部 Python 可执行文件。"""
        # 1) 环境变量显式指定
        env_path = os.environ.get("VNE_PYTHON")
        if env_path and Path(env_path).exists():
            return Path(self._prefer_pythonw(Path(env_path)) if prefer_windowless else Path(env_path))

        # 2) PATH 中的 python / python3
        for name in ["python", "python3", "pythonw"]:
            found = shutil.which(name)
            if found:
                exe = Path(found)
                if prefer_windowless:
                    return Path(self._prefer_pythonw(exe))
                return exe
        return None

    def get_engine_root_path(self) -> Path:
        """获取引擎根目录（包含 src/），用于PyInstaller路径收集"""
        # 当前文件位于 <root>/src/packager/packager_manager.py
        return Path(__file__).resolve().parent.parent.parent

    def _suggest_pack_python(self, project_dir: Path) -> Optional[Path]:
        """自动寻找打包专用Python。

        优先级：
        1) 引擎安装目录同级（冻结后）：engine_dir/pythonw.exe 或 engine_dir/python/pythonw.exe
           以及 engine_dir/venv_pack/Scripts/pythonw.exe。
        2) 工程目录同级：venv_pack/venv1/pack_venv 下的 pythonw/python。
        """
        engine_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent if getattr(sys, "frozen", False) else __file__)).resolve()
        engine_root = engine_dir.parent if engine_dir.is_file() else engine_dir

        # 先查引擎目录下的便携解释器
        for candidate in [
            engine_root / "pythonw.exe",
            engine_root / "python" / "pythonw.exe",
            engine_root / "python" / "python.exe",
            engine_root / "venv_pack" / "Scripts" / "pythonw.exe",
            engine_root / "venv_pack" / "Scripts" / "python.exe",
        ]:
            if candidate.exists():
                return candidate

        # 再查工程目录旁的常见命名
        for name in ["venv_pack", "venv1", "pack_venv"]:
            base = project_dir / name
            win = base / "Scripts" / "pythonw.exe"
            win_fallback = base / "Scripts" / "python.exe"
            nix = base / "bin" / "python"
            for c in [win, win_fallback, nix]:
                if c.exists():
                    return c
        return None

    def get_venv_site_packages(self) -> Optional[Path]:
        """
        获取venv虚拟环境的site-packages路径
        如果不在venv中则返回None
        """
        python_exe = Path(sys.executable)
        
        # 检查是否在venv中
        # venv结构: venv/Scripts/python.exe (Windows) 或 venv/bin/python (Unix)
        if python_exe.parent.name in ("Scripts", "bin"):
            venv_root = python_exe.parent.parent
            
            # Windows: venv/Lib/site-packages
            site_pkg_win = venv_root / "Lib" / "site-packages"
            if site_pkg_win.exists():
                return site_pkg_win
            
            # Unix: venv/lib/pythonX.Y/site-packages
            lib_dir = venv_root / "lib"
            if lib_dir.exists():
                for item in lib_dir.iterdir():
                    if item.is_dir() and item.name.startswith("python"):
                        site_pkg = item / "site-packages"
                        if site_pkg.exists():
                            return site_pkg
        
        return None

    def build_pyinstaller_command(self, project_path: str, config: Dict) -> List[str]:
        """
        构建PyInstaller命令
        
        Args:
            project_path: 工程文件(.vngproj)的完整路径
            config: 打包配置字典
            
        Returns:
            命令列表，可直接传递给subprocess
        """
        project_file = Path(project_path)
        project_dir = project_file.parent
        
        # 使用当前Python环境的PyInstaller
        python_exe = self.get_python_executable(config.get("python_path") or None, prefer_windowless=True)
        engine_root = self.get_engine_root_path()
        
        # 构建命令: python -m PyInstaller [options]
        cmd = [python_exe, "-m", "PyInstaller"]
        
        # 创建打包入口脚本
        entry_script = self._create_game_entry_script(project_dir, project_file)
        cmd.append(str(entry_script))
        
        # 应用名称
        app_name = config.get("app_name", "MyVNGame")
        cmd.extend(["--name", app_name])
        
        # 单文件或文件夹模式
        if config.get("one_file", False):
            cmd.append("--onefile")
        else:
            cmd.append("--onedir")
        
        # 控制台窗口
        if not config.get("console", False):
            cmd.append("--windowed")
        else:
            cmd.append("--console")
        
        # 图标
        icon_path = config.get("icon_path", "")
        if icon_path and Path(icon_path).exists():
            cmd.extend(["--icon", str(icon_path)])
        
        # 输出目录
        dist_dir = project_dir / "dist"
        build_dir = project_dir / "build"
        cmd.extend(["--distpath", str(dist_dir)])
        cmd.extend(["--workpath", str(build_dir)])
        
        # spec文件路径
        spec_dir = project_dir
        cmd.extend(["--specpath", str(spec_dir)])
        
        # 添加资源文件
        if config.get("include_resources", True):
            self._add_resource_datas(cmd, project_dir)
        
        # 添加工程文件
        cmd.extend(["--add-data", f"{project_file};."])
        
        # 添加额外的数据文件
        for src, dst in config.get("extra_data", []):
            if Path(src).exists():
                cmd.extend(["--add-data", f"{src};{dst}"])
        
        # 隐藏导入
        hidden_imports = config.get("hidden_imports", [])
        # 添加默认必需的隐藏导入
        default_hidden = [
            "pygame",
            "yaml",
            "PyQt6",
            "PyQt6.QtCore",
            "PyQt6.QtGui",
            "PyQt6.QtWidgets",
            "PIL",
            "PIL.Image",
            "pkg_resources",
            "numpy",
            "imageio",
            "imageio_ffmpeg",
            "moviepy",
            "moviepy.editor",
        ]
        # 仅当环境中存在 jaraco 模块时才加入隐藏导入
        if self._has_distribution("jaraco.collections") or self._has_distribution("jaraco"):
            default_hidden.append("jaraco")

        for module in default_hidden + hidden_imports:
            cmd.extend(["--hidden-import", module])
        
        # 收集子模块 / 资源
        cmd.extend(["--collect-submodules", "pygame"])
        cmd.extend(["--collect-submodules", "PyQt6"])
        cmd.extend(["--collect-submodules", "pkg_resources"])
        cmd.extend(["--collect-all", "numpy"])
        cmd.extend(["--collect-all", "imageio"])
        cmd.extend(["--collect-all", "imageio_ffmpeg"])
        cmd.extend(["--collect-all", "moviepy"])
        # 排除未使用的 Qt QML/3D/SQL 模块，避免缺失 DLL 警告（当前引擎仅用 Widgets）
        for mod in [
            "PyQt6.QtQml",
            "PyQt6.QtQuick",
            "PyQt6.QtQuick3D",
            "PyQt6.QtQuickControls2",
            "PyQt6.QtQuickWidgets",
            "PyQt6.QtSql",
        ]:
            cmd.extend(["--exclude-module", mod])
        # 仅在存在 jaraco 时才收集其子模块，避免缺失包导致错误
        if self._has_distribution("jaraco.collections") or self._has_distribution("jaraco"):
            cmd.extend(["--collect-submodules", "jaraco"])
        
        # 不强制 copy-metadata，避免目标 Python 未安装对应包导致失败
        
        # 如果在venv中，添加venv的site-packages路径
        venv_site = self.get_venv_site_packages()
        if venv_site:
            cmd.extend(["--paths", str(venv_site)])
            # 避免同时引入全局numpy重复，限定优先使用venv包

        # 添加引擎根路径，确保 src.* 模块被正确收集（sys.path 需指向包含 src 的父目录）
        if engine_root.exists():
            cmd.extend(["--paths", str(engine_root)])
            # 保险起见收集 src 下所有子模块
            cmd.extend(["--collect-submodules", "src"])
        
        # UPX压缩 (如果启用且可用)
        if not config.get("compression", True):
            cmd.append("--noupx")
        
        # 清理
        if config.get("clean_before_build", True):
            cmd.append("--clean")
        
        # 不要确认覆盖
        cmd.append("--noconfirm")
        
        return cmd

    def _create_game_entry_script(self, project_dir: Path, project_file: Path) -> Path:
        """
        创建游戏启动入口脚本
        这个脚本会在打包后的EXE中作为主入口
        """
        entry_script = project_dir / "_game_launcher.py"
        
        # 获取工程文件名（相对于project_dir）
        try:
            rel_project = project_file.relative_to(project_dir)
        except ValueError:
            rel_project = project_file.name
        
        script_content = f'''# -*- coding: utf-8 -*-
"""
游戏启动入口脚本 - 由VNEngine打包工具自动生成
此脚本用于打包后的可执行文件
"""
import sys
import os
from pathlib import Path

def get_resource_path(relative_path):
    """获取资源文件的绝对路径（兼容PyInstaller打包后的环境）"""
    try:
        # PyInstaller创建临时文件夹，路径存储在_MEIPASS中
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        # 开发环境
        base_path = Path(__file__).parent
    
    return base_path / relative_path

if __name__ == "__main__":
    # 设置工作目录为可执行文件所在目录
    if getattr(sys, 'frozen', False):
        # 打包后的环境
        app_dir = Path(sys.executable).parent
    else:
        # 开发环境
        app_dir = Path(__file__).parent
    
    os.chdir(app_dir)
    
    # 导入游戏运行时
    from src.game.game_runtime import VNGameRuntime
    
    # 获取工程文件路径
    project_file = get_resource_path("{rel_project}")
    
    if not project_file.exists():
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("错误", f"找不到工程文件: {{project_file}}")
        sys.exit(1)
    
    # 启动游戏
    try:
        game = VNGameRuntime(
            game_title="VN Game",
            window_size=(800, 600),
            project_path=str(project_file)
        )
        game.start_game()
    except Exception as e:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("启动失败", f"游戏启动失败:\\n{{str(e)}}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
'''
        
        with open(entry_script, "w", encoding="utf-8") as f:
            f.write(script_content)
        
        return entry_script

    def _add_resource_datas(self, cmd: List[str], project_dir: Path) -> None:
        """添加资源文件到打包命令"""
        # 添加resources目录
        resources_dir = project_dir / "resources"
        if resources_dir.exists():
            cmd.extend(["--add-data", f"{resources_dir};resources"])
        
        # 添加ui目录
        ui_dir = project_dir / "ui"
        if ui_dir.exists():
            cmd.extend(["--add-data", f"{ui_dir};ui"])
        
        # 添加saves目录（如果存在）
        saves_dir = project_dir / "saves"
        if saves_dir.exists():
            cmd.extend(["--add-data", f"{saves_dir};saves"])

    def clean_build_artifacts(self, project_path: str) -> None:
        """清理之前的构建文件"""
        project_dir = Path(project_path).parent
        
        # 删除build目录
        build_dir = project_dir / "build"
        if build_dir.exists():
            shutil.rmtree(build_dir, ignore_errors=True)
        
        # 删除dist目录（可选，保留可能有用）
        # dist_dir = project_dir / "dist"
        # if dist_dir.exists():
        #     shutil.rmtree(dist_dir, ignore_errors=True)
        
        # 删除spec文件
        for spec_file in project_dir.glob("*.spec"):
            try:
                spec_file.unlink()
            except:
                pass
        
        # 删除临时启动脚本
        entry_script = project_dir / "_game_launcher.py"
        if entry_script.exists():
            try:
                entry_script.unlink()
            except:
                pass

    def _has_distribution(self, name: str) -> bool:
        """检查给定分发包是否已安装，避免 copy-metadata 缺包报错"""
        try:
            importlib.metadata.distribution(name)
            return True
        except importlib.metadata.PackageNotFoundError:
            return False

    def get_output_path(self, project_path: str, config: Dict) -> Optional[Path]:
        """
        获取打包输出路径
        
        Returns:
            打包后可执行文件的路径，如果不存在则返回None
        """
        project_dir = Path(project_path).parent
        app_name = config.get("app_name", "MyVNGame")
        
        if config.get("one_file", False):
            # 单文件模式
            exe_path = project_dir / "dist" / f"{app_name}.exe"
        else:
            # 文件夹模式
            exe_path = project_dir / "dist" / app_name / f"{app_name}.exe"
        
        return exe_path if exe_path.exists() else None

    def verify_build_result(self, project_path: str, config: Dict) -> Tuple[bool, str]:
        """
        验证打包结果
        
        Returns:
            (是否成功, 消息)
        """
        output_path = self.get_output_path(project_path, config)
        
        if output_path is None:
            return False, "未找到打包输出文件"
        
        if not output_path.exists():
            return False, f"输出文件不存在: {output_path}"
        
        # 检查文件大小
        file_size = output_path.stat().st_size
        if file_size < 1024:  # 小于1KB明显有问题
            return False, f"输出文件太小 ({file_size} bytes)，可能打包失败"
        
        return True, f"打包成功！\n输出位置: {output_path}\n文件大小: {file_size / 1024 / 1024:.2f} MB"
