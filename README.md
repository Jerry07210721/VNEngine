# VNEngine

A lightweight visual novel (GalGame) engine with a PyQt6-based visual designer and a Pygame runtime. The designer lets you build flow graphs, manage assets, edit node properties, design UI/layouts, and preview or package projects.

## Features
- Visual designer (PyQt6): flow graph with text/choice/condition nodes, drag/zoom, resource dock (images/portraits/audio/voice/video), node properties panel, UI layout and main menu designers, global variables.
- Runtime (Pygame): menu, start/continue, save/load, settings, text rendering, branching, BGM/voice, background/portrait transitions, video, fast-skip, history.
- Packaging: integrated PyInstaller runner with configurable options, supports external packaging interpreter (e.g., `venv_pack`).

## Project Layout
- `src/core/` project management utilities
- `src/designer/` PyQt6 designer UI and tools
- `src/game/` Pygame runtime and preview runner
- `src/packager/` PyInstaller command builder and UI
- `tests/` basic placeholders for CI hooks
- `main.py` designer entrypoint

## Requirements
- Windows 10/11
- Python 3.12 (recommended)
- Dependencies: see `requirements.txt` (PyQt6, pygame, pyyaml, Pillow, numpy, moviepy, PyInstaller, etc.)

## Setup (developer environment)
```bash
# from repo root
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```
Run designer:
```bash
python main.py
```

## Packaging Environment (recommended)
Use a dedicated venv for packaging to avoid depending on system PATH.
```bash
python -m venv venv_pack
venv_pack\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Packaging Workflow (from designer)
1. Open the designer (`python main.py`).
2. Create/open a project (`.vngproj`) and save it.
3. Open “打包配置” (Packaging Config): set **Python路径** to `venv_pack\Scripts\python.exe` (or browse). Other options: app name, icon, mode (onedir/onefile), console, include resources, etc.
4. Save the packaging config, then click “执行打包”. Output goes to `dist/` under the project folder.

Notes:
- `packager_config.yaml` is stored beside your project file; it remembers `python_path`.
- If you leave `python_path` empty, the tool auto-detects `venv_pack/venv1/pack_venv` next to the project.
- Default window icon uses `icon.ico` at repo root; ensure the file exists before packaging.

## Tests
Placeholder tests exist under `tests/`. Extend them as needed and run with pytest after installing dev dependencies.

## License
Add your preferred license here.
