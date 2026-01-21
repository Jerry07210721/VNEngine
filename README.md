
# VNEngine 视觉小说引擎 / Visual Novel Engine

一个轻量级的视觉小说（GalGame）引擎，集成 PyQt6 可视化设计器、Pygame 运行时与 AI 辅助生成系统。
A lightweight visual novel (GalGame) engine with a PyQt6-based visual designer, Pygame runtime, and AI-assisted content generation system.

---

## 主要特性 / Features

- 可视化设计器（PyQt6）：流程图编辑（文本/选择/条件节点）、资源管理（图片/立绘/音频/语音/视频）、节点属性、UI/主菜单设计、全局变量。
- Visual designer (PyQt6): Flow graph editing (text/choice/condition nodes), resource management (images/portraits/audio/voice/video), node properties, UI/main menu designer, global variables.

- 运行时（Pygame）：菜单、开始/继续、存读档、设置、文本渲染、分支、BGM/语音、背景/立绘切换、视频、快进、历史。
- Runtime (Pygame): Menu, start/continue, save/load, settings, text rendering, branching, BGM/voice, background/portrait transitions, video, fast-skip, history.

- AI 辅助生成：支持 AI 辅助剧情、角色、分镜、语音、BGM、立绘、CG、背景等内容的分步生成与批量生成，支持可追溯、可编辑、可回放的生产链路。
- AI-assisted generation: Supports stepwise and batch AI generation of story, characters, scenes, voice, BGM, portraits, CG, backgrounds, with traceable, editable, and replayable workflow.

- 打包：集成 PyInstaller 打包流程，支持自定义 Python 路径、图标、模式（onedir/onefile）、资源收集等。
- Packaging: Integrated PyInstaller workflow, supports custom Python path, icon, mode (onedir/onefile), resource collection, etc.

---

## 目录结构 / Project Layout

- `src/core/`：工程管理与通用工具
- `src/core/`: Project management and utilities
- `src/designer/`：PyQt6 设计器 UI 与工具
- `src/designer/`: PyQt6 designer UI and tools
- `src/game/`：Pygame 运行时与预览
- `src/game/`: Pygame runtime and preview runner
- `src/packager/`：PyInstaller 打包命令与 UI
- `src/packager/`: PyInstaller command builder and UI
- `src/ai/`：AI 辅助生成核心、API、Agent、集成器、数据模型
- `src/ai/`: AI-assisted core, API, agents, integrator, data models
- `config/`：AI 配置（如 `ai_config.yaml`，密钥加密存储）
- `config/`: AI config (e.g., `ai_config.yaml`, encrypted secrets)
- `output/`：AI 生成与工程输出目录
- `output/`: AI generation and project output
- `tests/`：单元/集成测试
- `tests/`: Unit/integration tests
- `main.py`：设计器入口
- `main.py`: Designer entrypoint

---

## 环境要求 / Requirements

- Windows 10/11
- Python 3.12（推荐）
- 依赖见 `requirements.txt`（PyQt6, pygame, pyyaml, Pillow, numpy, moviepy, PyInstaller 等）
- Dependencies: see `requirements.txt` (PyQt6, pygame, pyyaml, Pillow, numpy, moviepy, PyInstaller, etc.)

---

## 安装与开发环境 / Setup (Developer Environment)

```bash
# 从仓库根目录 / From repo root
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

运行设计器 / Run designer:
```bash
python main.py
```

---

## AI 辅助生成入口 / AI-assisted Generation Entry

- 设计器菜单栏：AI 辅助 → AI辅助生成
- Designer menu: AI Assist → AI-assisted Generation
- 独立窗口，支持新建/加载/保存 `.vnai` AI 工程，分步生成剧情、角色、分镜、语音、BGM、立绘、CG、背景等。
- Standalone window, supports creating/loading/saving `.vnai` AI projects, stepwise generation of story, characters, scenes, voice, BGM, portraits, CG, backgrounds, etc.
- 各专项面板支持参数编辑、批量生成、进度追踪、失败重试。
- Each panel supports parameter editing, batch generation, progress tracking, and retry on failure.
- 配置文件 `config/ai_config.yaml`，敏感信息加密存储，首次需填写。
- Config file `config/ai_config.yaml`, secrets encrypted, fill in on first use.

---

## 打包环境与流程 / Packaging Environment & Workflow

建议为打包单独创建 venv，避免依赖系统 PATH。
It is recommended to use a dedicated venv for packaging to avoid system PATH issues.

```bash
python -m venv venv_pack
venv_pack\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

打包流程 / Packaging workflow:
1. 启动设计器（`python main.py`）。
	Launch designer (`python main.py`).
2. 创建/打开工程（`.vngproj`），保存。
	Create/open a project (`.vngproj`), save it.
3. 打开“打包配置”，设置 **Python路径** 为 `venv_pack\Scripts\python.exe`（或浏览选择）。可配置应用名、图标、模式、资源等。
	Open "Packaging Config", set **Python Path** to `venv_pack\Scripts\python.exe` (or browse). Configure app name, icon, mode, resources, etc.
4. 保存配置，点击“执行打包”，输出到工程目录下 `dist/`。
	Save config, click "Run Packaging", output goes to `dist/` under project folder.

注意 / Notes:
- `packager_config.yaml` 存储于工程旁，记忆 `python_path`。
- `packager_config.yaml` is stored beside your project file, remembers `python_path`.
- 若留空，自动检测 `venv_pack/venv1/pack_venv`。
- If left empty, auto-detects `venv_pack/venv1/pack_venv`.
- 默认窗口图标为仓库根目录 `icon.ico`，请确保存在。
- Default window icon is `icon.ico` at repo root, ensure it exists before packaging.

---

## 测试 / Tests

测试用例位于 `tests/`，可用 pytest 运行。
Test cases are under `tests/`, run with pytest after installing dev dependencies.

---

## 许可证 / License

请在此处添加你的许可证。
Add your preferred license here.
