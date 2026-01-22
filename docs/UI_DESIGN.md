# VNEngine UI 设计文档（Design System & 实现说明）

> 适用范围：VNEngine 设计器（PyQt6）与 AI 辅助窗口（PyQt6）。
>
> 本文档面向开发者/维护者，描述 VNEngine 的 UI 设计目标、主题系统、控件规范、关键界面布局与绘制规则，以及扩展 UI 时需要遵守的约束。
>
> 重要原则：**仅优化 UI，不改变任何功能/业务逻辑**。所有 UI 重构必须保持原信号槽语义与关键属性/字段契约不变。

---

## 1. 设计目标与非目标

### 1.1 设计目标

- 商业化观感：白色为主、橙色为品牌主色（`#FB8138`），整体干净、克制、统一。
- 高可读性：文本与控件对比充分，输入/聚焦态明显。
- 高一致性：同类控件在不同窗口/面板视觉一致（按钮高度、圆角、边框、间距）。
- 专业编辑器体验：流程图节点卡片化、阴影、悬浮/选中反馈明确。
- UI 变更不影响功能：不改变数据结构、流程逻辑、IO、信号槽行为。

### 1.2 非目标

- 不引入外部 UI 框架（保持 PyQt6 + QSS + 少量自绘）。
- 不把 UI 主题做成可切换皮肤系统（当前仅一套白橙主题）。
- 不对运行时（Pygame）界面进行系统性主题重构（本文档聚焦 PyQt6 设计器与 AI 辅助窗口）。

---

## 2. 主题系统总览

VNEngine 的主题由三部分组成：

1) **Qt Fusion 风格**：保证跨平台基础一致性
2) **QPalette**：统一窗口底色、文字色、Highlight 等
3) **QSS（Qt Style Sheet）**：细化控件边框、圆角、hover/focus、Tab/Menu 等
4) **自定义 QProxyStyle**：专门解决 SpinBox/ComboBox 箭头与按钮区绘制稳定性问题

核心入口：

- 主题应用函数：`src/designer/ui_theme.py` 中的 `apply_vnengine_theme(app)`
- 自定义 Style：`src/designer/ui_theme.py` 中的 `VNEngineStyle(QProxyStyle)`

### 2.1 颜色体系（Tokens）

- 主色（Primary）：`#FB8138`
- 主色 Hover：`#F97316`（更深一档）
- 主色 Pressed：`#EA580C`（再深一档）

中性色（建议语义）：

- 文本主色：`#111827`
- 文本次级：`#374151` / `#6B7280`
- 边框：`#E5E7EB`（常规）/ `#D1D5DB`（更强调）
- 背景：`#FFFFFF`（主背景）/ `#FFFCFA`（画布暖白背景）/ `#F9FAFB`（浅分区底色）

状态色（用于节点类型/提示）：

- Success：`#22C55E`
- Info：`#3B82F6`
- Accent Purple（用于条件节点类型条）：`#8B5CF6`

> 说明：状态色只用于“结构信息编码”（例如节点类型色条），避免大面积铺色。

### 2.2 圆角与高度

- 标准圆角：8px
- 卡片/面板圆角：10~12px
- 输入控件最小高度：30px（保证一致触达与观感）
- 工具栏按钮高度：建议 30px 左右（与输入控件一致）

### 2.3 阴影策略

- 卡片阴影应“轻”：低 alpha、小偏移
- 被选中（Selected）时，优先描边高亮（主色），阴影可减弱以提高边缘清晰度

---

## 3. 关键实现细节与约束

### 3.1 为什么要用自定义 QProxyStyle 绘制 SpinBox/ComboBox

在 Qt 中，全局 QSS 会启用样式表包装器（`QStyleSheetStyle`），对复杂控件（Complex Controls，如 SpinBox/ComboBox）的子控件绘制有较强接管行为。

实践结论：

- 仅靠 QSS 覆盖 `::up-button/::down-button/::drop-down`，在不同环境（打包/开发/资源路径）下箭头很容易消失或显示异常。
- 使用内置资源路径（`:/`）与 SVG 在当前环境不稳定。
- 最稳方案是：在 `VNEngineStyle.drawComplexControl()` 中**直接绘制**按钮区与箭头，并通过 `subControlRect()` 固定按钮区尺寸。

因此：

- **不要**在 QSS 中直接对 `QSpinBox/QDoubleSpinBox/QComboBox` 设置边框/圆角/子控件箭头。
- 让 `VNEngineStyle` 负责这类控件的外框/按钮区/箭头绘制。

### 3.2 QSS 使用规范

- 优先用“通用控件选择器”（如 `QLineEdit`、`QPushButton`）统一基础样式。
- 需要局部差异时，优先使用动态属性（如 `variant="primary"`、`pill="true"`、`card="true"`、`role="cardTitle"`）做选择器。
- 避免大范围对复杂控件子控件（`::subcontrol`）做样式覆盖。

---

## 4. 设计模式（Main Designer）UI 规范

主要窗口：`src/designer/main_designer.py`

### 4.1 菜单栏（MenuBar）

- 文件/打包/数据/UI 设计/AI 辅助为核心菜单组。
- 新增帮助栏（`帮助(&H)`）：用于“关于/联系/文档”等信息型入口。

**联系我们**：通过 `QMessageBox.about()` 弹窗展示联系方式。

> 建议：联系方式内容尽量提供“可复制”信息（如邮箱/群号/链接）。

### 4.2 工具栏（ToolBar）

- 主按钮“预览游戏”为 Primary。
- “保存工程”“AI辅助生成”紧挨预览按钮，复用既有槽函数，确保逻辑一致。

工具栏按钮原则：

- 文案明确（动作 + 对象）
- 图标使用 Qt 标准图标（可用时）
- 高度与输入框一致（约 30px）

### 4.3 Dock 面板

- 左侧：节点属性（PropertiesDock）
- 右侧：资源面板（ResourceDock）

原则：

- Dock 内容较长必须使用 `QScrollArea` 包裹。
- Dock 的标题与内容的间距统一。

---

## 5. 节点属性编辑（Properties Dock）UI 规范

文件：`src/designer/properties_panel.py`

### 5.1 四大面板分区

- 面板一：基础
- 面板二：节点内容
- 面板三：媒体配置
- 面板四：UI 设计文件

### 5.2 折叠/展开交互（箭头旋转）

当前使用 `_CollapsibleSection`：

- 左侧箭头：展开为 DownArrow，收起为 RightArrow
- 收起时仅保留标题行，高度更紧凑

折叠原则：

- 只影响“内容区可见性”，不改变任何控件值/绑定。
- 展开/收起不触发业务保存，仅改变布局展示。

### 5.3 文本节点：子节点列表高度

- 子节点列表（`QListWidget`）需要更大的可视高度，避免频繁滚动。
- 当前设定最小高度 `>= 320px`（约 3-4 倍体感提升）。

---

## 6. Graph 画布（流程图编辑器）UI 规范

文件：`src/designer/graph_canvas.py`

### 6.1 背景与网格

- 背景使用暖白 `#FFFCFA`
- 网格线使用更柔和的浅灰 `#EEF2F7`

原则：网格应“存在但不抢眼”。

### 6.2 节点（FlowTextNode）卡片化

节点视觉组成：

- 圆角卡片主体（白底）
- 轻阴影（未选中时）
- 选中态：主色描边
- Hover：边框微亮 + 阴影加深

### 6.3 标题区与类型色条

- 顶部标题区浅底（`#F9FAFB`）
- 类型色条：
  - text：橙 `#FB8138`
  - choice：蓝 `#3B82F6`
  - condition：紫 `#8B5CF6`

### 6.4 入度为 0 的起点标记

- 起点标记使用“内嵌圆角顶边细条”（`#22C55E`），避免硬直角绿条突兀。
- 仅影响绘制表现，不改变 `indegree` 计算逻辑。

### 6.5 连线（ConnectionPath）

- 默认线条：中性灰
- 选中线条：主色橙、加粗

---

## 7. AI 辅助窗口（AI Project Window）UI 规范

主窗口：`src/designer/ai_project_window.py`

### 7.1 Tab 结构

- 多 Tab 承载不同任务面板。
- 每个 Tab 内部如果内容长，使用 `QScrollArea`。

### 7.2 主控面板（Master Control Panel）卡片化

- Step1~Step6 使用卡片（Card）结构：header + 状态 pill + 操作区 + 双栏 splitter。
- 必须保持逻辑访问的属性不变（例如 `_instruction/_result/_status/_max_tokens_spin/_step_key` 等）。

---

## 8. 悬浮球与悬浮窗（Floating LLM Chat）UI 规范

文件：`src/designer/floating_llm_chat.py`

### 8.1 悬浮球（FloatingBall）

- 使用主色橙圆按钮（白字）
- Hover/Pressed 更深色
- 仅用于触发悬浮窗显示；拖拽阈值避免误触

### 8.2 悬浮窗（FloatingChatWidget）

- 白底卡片 + 轻边框，避免深色“电竞风”与全局主题冲突
- 输入框/输出框/按钮尽量不在局部 setStyleSheet 强行覆盖，交由全局主题统一
- “发送”按钮使用 `variant="primary"` 走主题主按钮样式

---

## 9. 新增 UI/改造 UI 的开发指南

### 9.1 新增窗口/对话框

- 入口处调用 `apply_vnengine_theme(app)`（通常在应用启动或独立窗口入口）。
- 对话框内容过长：外层 `QScrollArea.setWidgetResizable(True)`。
- 按钮区（确定/取消/保存）尽量固定在底部，不随滚动区滚动。

### 9.2 新增控件样式

优先顺序：

1) 复用全局 QSS 中已有规则
2) 添加动态属性并在 QSS 中写选择器
3) 最后才用局部 `setStyleSheet`，且应限定 `objectName`/局部范围，避免污染全局

### 9.3 关于 SpinBox/ComboBox 样式的硬约束

- 不要在 QSS 中对 SpinBox/ComboBox 直接设置边框/圆角/箭头子控件。
- 如果必须调整其外观：在 `VNEngineStyle` 中做绘制层变更。

---

## 10. 逐文件 UI 组件清单（维护索引）

本章用于“按文件定位 UI”，帮助后续继续商业化打磨时做到：**样式集中、属性可追溯、改动不破坏功能**。

- **关键控件**：窗口/面板的核心组件
- **动态属性**：用于主题选择器的 `setProperty()` 约定
- **QSS 选择器**：对应 `vnengine_qss()` 中的规则（或局部 objectName 规则）

> 说明：多数控件样式来自全局主题 `src/designer/ui_theme.py`。原则上避免在单个窗口里大量 `setStyleSheet()`（除非限定 objectName 并且范围很小）。

### 10.1 动态属性与 QSS 选择器对照表

以下规则定义于 `src/designer/ui_theme.py` 的 `vnengine_qss()`：

| 用途 | 动态属性（示例） | 选择器 | 说明 |
|---|---|---|---|
| 页面主标题 | `label.setProperty("role","title")` | `QLabel[role="title"]` | 更大字号、更粗字重 |
| 页面副标题 | `label.setProperty("role","subtitle")` | `QLabel[role="subtitle"]` | 灰色说明文字 |
| 胶囊标签 | `label.setProperty("pill","true")` | `QLabel[pill="true"]` | 圆角 999px、浅底、用于状态/信息 |
| 卡片容器 | `frame.setProperty("card","true")` | `QFrame[card="true"]` | 白底、浅边框、较大圆角 |
| 卡片标题 | `label.setProperty("role","cardTitle")` | `QLabel[role="cardTitle"]` | 14px/700 |
| 主按钮 | `btn.setProperty("variant","primary")` | `QPushButton[variant="primary"]` | 橙色背景、白字 |
| 危险按钮 | `btn.setProperty("variant","danger")` | `QPushButton[variant="danger"]` | 红色语义边框/文字 |

补充说明：

- 输入类：`QLineEdit`、`QPlainTextEdit`、`QTextEdit` 的边框/圆角/focus 由全局 QSS 统一。
- `QSpinBox/QDoubleSpinBox/QComboBox` 的按钮区/箭头由 `VNEngineStyle` 绘制（避免 QSS 接管导致箭头丢失）。

### 10.2 设计模式（Designer）相关文件

#### 10.2.1 `src/designer/main_designer.py`

- **窗口/类**：`StartDialog(QDialog)`、设计模式主窗口（同文件）
- **关键控件**：
  - 菜单栏：文件/打包/数据/UI 设计/AI 辅助/帮助
  - 工具栏：`预览游戏`（Primary）、`保存工程`、`AI辅助生成`
  - 中心区：`GraphView`（流程图画布）
  - 左 Dock：`PropertiesDock`（节点属性）
  - 右 Dock：`ResourceDock`（资源管理）
- **动态属性**：
  - `StartDialog` 中标题/副标题：`role=title`、`role=subtitle`
  - `StartDialog` 的主/危险按钮：`variant=primary`、`variant=danger`
  - 工具栏 `预览游戏`：`variant=primary`
- **QSS 关联点**：
  - 通用按钮/输入规则 + `variant/role` 规则
  - `QMenuBar/QMenu`（全局 QSS 内有对应样式）

#### 10.2.2 `src/designer/graph_canvas.py`

- **关键类**：`GraphScene`、`GraphView`、`FlowTextNode`、`ConnectionPath`
- **关键控件/绘制**：
  - `GraphScene.drawBackground()`：暖白背景 + 柔和网格
  - `FlowTextNode.paint()`：圆角卡片、标题区、类型色条、hover/selected、起点标记
  - `ConnectionPath.paint()`：默认灰、选中橙
- **动态属性**：无（主要是 QGraphicsItem 自绘，不走 QSS）
- **QSS 关联点**：几乎无；节点视觉由 `paint()` 控制

#### 10.2.3 `src/designer/properties_panel.py`

- **窗口/类**：`PropertiesDock(QDockWidget)`
- **关键控件**：
  - 4 个折叠分区（面板一~四）：使用 `_CollapsibleSection`（箭头 Right/Down）
  - 文本节点：子节点列表 `QListWidget`（最小高度 >= 320px）、子节点详情表单（`QLineEdit/QPlainTextEdit` 等）
  - 选择/条件节点：对应的堆叠页 `QStackedWidget`
- **动态属性**：无（采用标准控件 + 全局主题）
- **QSS 关联点**：输入框/按钮高度与边框统一来自全局 QSS

#### 10.2.4 `src/designer/resource_panel.py`

- **窗口/类**：`ResourceDock(QDockWidget)`
- **关键控件**：
  - 资源分类 Tab（图片/立绘/音频/语音/视频）
  - 列表（`QListWidget`）+ 预览区 + 操作按钮
- **动态属性**：无
- **QSS 关联点**：`QTabWidget/QTabBar` + 通用按钮/输入（全局 QSS）

#### 10.2.5 `src/designer/menu_designer.py`

- **窗口/类**：`MainMenuDesigner(QDialog)`、`MenuPreview(QWidget)`
- **关键控件**：表单 + 预览双栏布局；外层 `QScrollArea` 包裹长表单
- **动态属性**：无
- **QSS 关联点**：表单控件走全局主题

#### 10.2.6 `src/designer/ui_designer.py`

- **窗口/类**：UI 布局设计器（包含 `LayoutPreview(QWidget)`）
- **关键控件**：表单（位置/缩放/颜色等）+ 预览
- **动态属性**：无
- **QSS 关联点**：表单控件走全局主题

#### 10.2.7 `src/designer/global_vars_dialog.py`

- **窗口/类**：`GlobalVarsDialog(QDialog)`
- **关键控件**：变量列表/编辑控件（以标准控件为主）
- **动态属性**：通常无
- **QSS 关联点**：通用按钮/输入（全局 QSS）

#### 10.2.8 打包 UI

- **入口**：设计模式菜单“打包”触发
- **相关文件**：
  - `src/designer/main_designer.py`：`PackagerLogDialog` 与菜单入口
  - `src/packager/packager_dialog.py` 等：打包配置主对话框
- **QSS 关联点**：通用按钮/输入（全局主题）；复杂控件（SpinBox/ComboBox）按 `VNEngineStyle` 约束处理

### 10.3 AI 辅助相关文件

#### 10.3.1 `src/designer/ai_project_window.py`

- **窗口/类**：AI 辅助工程主窗口（独立顶层窗口）
- **关键控件**：多 Tab 承载不同任务面板；顶部项目信息标签；新建/保存等工具按钮
- **动态属性**：
  - 项目信息标签：`pill=true`
  - 主操作按钮：`variant=primary`
- **QSS 关联点**：pill、primary、Tab（全局 QSS）

#### 10.3.2 `src/designer/ai_master_control_panel.py`

- **面板/类**：主控 Agent 面板（Step1~Step6）
- **关键控件**：卡片（header + 状态 pill + 操作按钮 + 双栏 splitter）
- **动态属性**：`card=true`、`role=cardTitle`、`pill=true`（状态）、`variant=primary`（主操作）
- **QSS 关联点**：卡片/标题/pill/primary

#### 10.3.3 其他 AI 专项面板（语音/立绘/背景/CG/BGM）

- **相关文件**：
  - `src/designer/ai_voice_panel.py`
  - `src/designer/ai_portrait_panel.py`
  - `src/designer/ai_background_panel.py`
  - `src/designer/ai_cg_panel.py`
  - `src/designer/ai_bgm_panel.py`
- **共性控件**：左右 splitter、条目列表、参数表单、批量操作按钮
- **动态属性**：多数包含 `pill=true`（项目/状态信息）
- **QSS 关联点**：通用按钮/输入 + pill

#### 10.3.4 `src/designer/ai_assist_dialog.py`

- **窗口/类**：API 配置对话框等
- **关键控件**：`QScrollArea` 包裹长表单；Key 显示/隐藏切换
- **动态属性**：通常无
- **QSS 关联点**：通用按钮/输入

#### 10.3.5 `src/designer/floating_llm_chat.py`

- **控件**：`FloatingBall`（悬浮球）、`FloatingChatWidget`（悬浮窗）
- **关键样式入口**：
  - 悬浮球：objectName `VNEngineFloatingBall`（局部 QSS，橙色圆按钮）
  - 悬浮窗：objectName `VNEngineFloatingChat`（白底卡片），并尽量让全局主题接管输入框/按钮
  - 状态标签：objectName `VNEngineFloatingStatus`（橙色强调）
  - 发送按钮：`variant=primary`
- **QSS 选择器（局部）**：`#VNEngineFloatingBall`、`#VNEngineFloatingChat`、`#VNEngineFloatingChat QLabel#VNEngineFloatingStatus`

---

## 11. 测试与验收建议

- 视觉回归：
  - 设计模式打开工程、拖拽节点、连线、选择/条件节点切换
  - 属性面板四区折叠/展开、长表单滚动
  - 资源面板导入/预览
  - AI 窗口各面板打开、悬浮球与悬浮窗交互

- 自动化回归：运行 `pytest -q`，确保 UI-only 改动不破坏既有逻辑测试。

---

## 12. 变更记录（摘录）

- 统一白橙主题：Fusion + Palette + QSS
- 自定义 `VNEngineStyle`：保证 SpinBox/ComboBox 箭头稳定显示
- Graph 节点：圆角卡片、阴影、选中/hover、类型色条、起点标记优化
- 设计模式工具栏：预览旁新增保存工程/AI辅助生成
- 属性面板：四区箭头折叠、子节点列表高度提升
- 悬浮球/悬浮窗：配色与全局主题一致（白底 + 橙色强调）
