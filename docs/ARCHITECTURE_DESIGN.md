# VNEngine 架构与设计文档

本文件汇总当前代码实现（分支 feature/V1.0）与规划中的设计，便于后续迭代与协作。面向读者：开发者、测试、打包与发行相关人员。

## 1. 产品定位与运行模式
- 目标：提供一套支持「可视化剧情编辑 + 即时预览 + 可发布运行」的视觉小说（GalGame）引擎。
- 三大模式：
  - 设计模式（PyQt6）：编辑流程图、节点属性、资源、打包配置。
  - 预览模式（独立子进程）：从设计器调用，加载 `.vngproj` 数据并进入游戏运行时。
  - 游戏运行模式（Pygame）：负责剧情渲染、交互、存档/读档、设置与主菜单。

## 2. 代码与目录总览
- 入口与分发：
  - [main.py](main.py) 提供 `_dispatch`，支持默认设计器启动与 `--preview <project.vngproj>` 路由。
- 核心模块：
  - [src/core/common_utils.py](src/core/common_utils.py)：路径、目录创建、工程后缀校验。
  - [src/core/project_manager.py](src/core/project_manager.py)：工程数据结构、创建/保存/加载（YAML）。
- 设计器（PyQt6）：
  - [src/designer/main_designer.py](src/designer/main_designer.py)：主窗口、菜单/工具栏、资源面板、属性面板、打包与预览流程。
  - [src/designer/graph_canvas.py](src/designer/graph_canvas.py)：流程图画布、网格、缩放、节点/连线、上下文菜单。
  - [src/designer/properties_panel.py](src/designer/properties_panel.py)：节点属性编辑（文本/选择/条件、子对话、变量操作、媒体与 UI 关联）。
  - [src/designer/resource_panel.py](src/designer/resource_panel.py)：资源导入/重命名/删除/预览（图片、立绘、音频、语音、视频）。
  - [src/designer/global_vars_dialog.py](src/designer/global_vars_dialog.py)：全局变量维护。
  - 其他：UI 设计器、主菜单设计器、打包配置对话框等（文件已存在但未在本摘要展开）。
- 运行时（Pygame）：
  - [src/game/game_runtime.py](src/game/game_runtime.py)：主渲染/事件循环、主菜单、剧情驱动、BGM/语音/视频、存档、设置等。
  - [src/game/preview_runner.py](src/game/preview_runner.py)：独立模块入口，供 `--preview` 或 `python -m` 调用。
- 打包：
  - [package.txt](package.txt)：PyInstaller 命令示例（onedir、收集资源和子模块）。
  - [src/packager/*](src/packager)（未展开）：构建配置、命令生成、清理与进程管理。
- 测试：
  - [tests](tests) 目录存在基础测试占位（未深入）。

## 3. 工程数据模型（YAML：.vngproj）
`project_manager.py` 中的默认结构：
- `project_info`: name/version/engine_version/create_time/last_modify_time。
- `game_config`: 窗口尺寸、标题、分支策略，以及主菜单配置（背景、视频、BGM、标题位置/颜色/图片、覆盖透明度等）。
- `resources`: images/audios/portraits/voices/videos（列表存储相对或绝对路径）。
- `global_variables`: 全局变量数组（当前 UI 支持 float 类型，含 name/initial）。
- `flow_nodes`: `{"nodes": [...], "connections": [...]}`，由画布导出，驱动预览/运行时剧情逻辑。

### 节点模型（GraphView / PropertiesDock）
- 支持节点类型：文本、选择、条件。
- 主要字段（根据 `FlowTextNode` 属性与属性面板）：
  - 通用：`node_id`, `title`, `node_type`, `background`, `portrait`, `voice`, `bgm`, `bgm_loop`, `stop_bgm`, `bg_fade_in`, `video`, `video_loop`, `ui_file`, `hide_textbox`, `portrait_fade`, `portrait_fade_out`, `is_start`。
  - 文本节点：`speaker`, `content`, `sub_dialogues`（1-50 条，含 speaker/text/voice/portrait/hide_textbox/portrait_fade/portrait_fade_out），`var_ops`（变量运算列表）。
  - 选择节点：`options`（字符串列表），可附带展示文本/立绘/语音等；连线出口需与选项数量一致。
  - 条件节点：`condition_var`, `condition_value`, `condition_op`, `condition_const`（右值是否常量），并有真/假两条出口。
- 连接：`connections` 存储 `source -> target`，用于构建有向图；画布提供分析函数检测循环、无起点、不可达、出度与选项不匹配等情况。

### 资源模型（ResourceDock）
- 导入：复制文件到工程 `resources/<type>/`，避免重名，路径以相对工程目录存储。
- 管理：重命名、删除（可选物理删除）、路径复制、资源管理器打开。
- 预览：
  - 图片/立绘显示缩略图。
  - 音频/语音：lazy init mixer，支持试听与停止；自动显示时长。
  - 视频：路径管理，占位无内嵌播放（播放在运行时）。

## 4. 主要运行流程
### 4.1 设计器启动
1) 入口 `main.py` 默认调用 `run_designer()`。
2) `StartDialog` 询问新建/加载/退出。
3) 主窗口初始化：菜单（文件/打包/数据/UI）、工具栏（预览按钮）、中心画布（GraphView）、左属性面板、右资源面板、状态栏。

### 4.2 工程生命周期
- 新建：
  - 通过文件对话框选择 `.vngproj` 保存位置，创建工程目录与子目录（resources/images|audios|portraits|voices|videos, ui, saves）。
  - 初始化 `project_data` 并立即保存空工程。
- 打开：读取 YAML，应用工程目录，加载流程图与资源列表，重置属性绑定。
- 保存：
  - 从画布导出 `flow_nodes`，资源面板导出 `resources`，写回 YAML。
  - 状态栏提示并弹窗确认。

### 4.3 画布与节点编辑
- 交互：网格背景、滚轮缩放、中键平移、节点拖拽、双击标题编辑。
- 上下文菜单：添加文本节点、删除/复制选中、清空画布；连线通过端口点击拖拽创建，连线呈贝塞尔曲线。
- 属性面板：分区编辑（基础、内容、媒体、UI、子对话、变量处理、选项/条件特定字段），同步写入当前节点对象。

### 4.4 资源管理
- 多标签：图片、立绘、音频、语音、视频。
- 导入复制到工程资源目录；防重名；可预览/试听；支持重命名/删除/复制路径。
- 导出数据随工程保存，运行时按相对路径解析。

### 4.5 预览链路
1) 设计器点击「预览游戏」。
2) 先运行流程分析（循环、无起点、不可达、选择/条件出度不匹配），给出警告可继续。
3) 保存当前工程，启动独立子进程：
   - 开发环境：`python -m src.game.preview_runner <project>`。
   - 打包环境：`<exe> --preview <project>`。
4) 子进程加载 YAML，构建节点图并进入 Pygame 运行时。

### 4.6 运行时（Pygame）
- 窗口/缩放：逻辑渲染面 `render_surface`，可切换全屏，适配 4:3 逻辑尺寸到窗口尺寸。
- 菜单：背景图/视频、BGM、标题/选项位置与颜色；菜单项：开始、继续、读取、设置、退出。
- 剧情驱动：
  - 图模式：根据 `flow_nodes` 构建 `nodes_map` 与邻接表，支持分支策略（first/random/longest 预留）。
  - 文本展示：逐字显示，三角提示；支持子对话列表；背景/立绘淡入/淡出；语音/BGM 播放与停止。
  - 选择/条件：渲染选项，按连线跳转；变量运算与条件判断支持。
- 媒体：背景/立绘缓存预热，语音缓存，BGM 淡入/循环，视频播放（moviepy + imageio + numpy）。
- 交互：点击/回车推进，ESC 菜单，快进开关，历史记录叠加层，保存/读取/设置叠加层。
- 存档与设置：
  - 存档目录 `saves/`（相对工程），槽位默认 5；存档存储当前节点、变量、时间戳等（JSON）。
  - 设置文件 `settings.yaml`：文本速度、音量、全屏等；启动时加载并应用。

## 5. 打包与发布
- 手工命令示例：见 [package.txt](package.txt)，基于 PyInstaller onedir，收集 PyQt6/pygame/numpy/imageio/moviepy 等子模块与资源。
- 设计器内置打包流程：
  - 菜单「打包」→ 配置对话框（保存到工程旁配置文件）→ 生成命令并以子进程运行。
  - 进度/日志：`PackagerLogDialog` 实时展示 stdout/stderr；支持清理旧 build/dist。
  - PyInstaller 可通过外部 Python 解释器路径配置；优先无控制台解释器。

## 6. 扩展与迭代建议（结合既有代码与计划）
1) 流程图：补完节点类型间的出入度规则校验；支持节点模板与批量编辑；开放变量类型（int/bool/string）。
2) 资源：增加格式校验、重复检测、占用提示；支持视频缩略与简易播放；资源引用计数/清理。
3) 运行时：
   - 完善存档（多槽、缩略图、当前节点标注）；
   - 提供快进/已读跳过、自动播放；
   - 更丰富的 UI 布局与主题切换；
   - 分支策略与变量系统健壮性（类型系统、默认值、调试 HUD）。
4) 预览与热重载：设计器修改后增量推送到预览进程，减少重启成本；错误日志回传到设计器。
5) 打包：增加单文件模式、图标/版本配置、资源压缩与体积优化；跨平台打包（macOS/Android 预研）。
6) 测试：补充针对 GraphView 导入导出、resource 操作、runtime 流程跳转与存档的自动化测试；在 CI 添加 smoke test（启动设计器、无头运行时加载示例工程）。

## 7. 环境与依赖
- Python 3.12；核心依赖：PyQt6、pygame、pyyaml、Pillow、moviepy、imageio、numpy、pyinstaller（打包阶段）。
- Windows 为主要目标环境；路径处理以 `pathlib` / `os.path` 兼容，资源相对路径优先。

## 8. 典型使用路径（开发者）
1) `python main.py` 启动设计器 → 新建工程（自动创建资源与存档目录）。
2) 在画布添加节点、编辑属性；在资源面板导入图片/音频/立绘/视频；必要时设置全局变量。
3) 保存工程；点击「预览游戏」触发子进程运行时，验证流程/素材/分支。
4) 打包：配置 PyInstaller 选项，执行打包，产物位于工程 `dist/`。

---
本文档随代码更新，若有结构调整或新增功能，请同步修订相关章节与数据模型描述。
