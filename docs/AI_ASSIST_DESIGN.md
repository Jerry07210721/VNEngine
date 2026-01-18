# VNEngine AI 辅助生成系统 - 项目设计文档（V2.1）

> 本文档面向开发者/维护者，描述 VNEngine 的 **AI 辅助生成（.vnai）** 功能在 V2.1 版本的整体设计：从 UI 入口、配置与安全、数据模型、主控分步生成、各专项面板、到整合为 VNEngine 工程（.vngproj）与运行预览的全链路。
>
> 配套“用户操作说明”请参考：`docs/AI_ASSIST_HELP.md`。

---

## 0. 版本信息

- 文档版本：V2.1
- 适用分支：`feature/V2.1`
- 主要入口：
  - 设计器菜单：AI 辅助 → AI辅助生成（从设计模式进入 AI 工程窗口）
  - AI 工程窗口工具菜单：API 配置、语音模型配置

---

## 1. 背景与目标

### 1.1 背景
VNEngine 的 AI 辅助生成用于将“故事设定 → 剧情脚本 → 流程图骨架 → 待生成素材列表 → 资源生成与整合”串成一个可追溯、可编辑、可回放的生产链路。

系统强调：
- **可编辑**：LLM/接口的输入指令与输出结果都可以被用户修改再保存。
- **可追溯**：每一步都有参数、时间戳、原始响应保留。
- **可分工**：主控流程负责分步生成与结构化，专项面板负责各类素材生成。
- **可落盘**：产出写入 VNEngine 工程目录结构，并对齐运行时读取方式。

### 1.2 目标（V2.1）
- 通过 `.vnai` 管理 AI 工程生命周期（新建/加载/保存/导出）。
- 在“主控 Agent”里完成分步生成并允许人工修订。
- 在专项面板中对待生成条目进行参数编辑与批量执行。
- 最终通过 Integrator 生成 `.vngproj` 并准备资源目录结构。
- 对 API Key/Token/Sign 等敏感信息 **加密落盘**，且密钥与工程分离。

### 1.3 非目标
- 不追求一次性全自动生成可直接发布的“完美作品”。
- 不在 V2.1 中实现跨平台（macOS/Linux）打包策略。
- 不将密钥托管到远端；默认使用本机密钥文件/环境变量。

---

## 2. 术语与概念

- **AI 工程（.vnai）**：AI 辅助制作过程的工程文件，包含配置、生成历史、待生成列表、部分流程图骨架等。
- **VNEngine 工程（.vngproj）**：设计器/运行时使用的主工程文件，包含流程图、资源引用、UI/变量等。
- **主控分步生成（StepGenerator）**：将“人设→大纲→章节→章节详稿→待生成列表/流程骨架→工程文件”拆成可编辑步骤。
- **多 Agent 主控（MasterAgent）**：面向并发/调度的任务规划与进度追踪框架，支持对多个子 Agent 进行协调。
- **Integrator（资源整合器）**：把 AI 侧的结构化结果和生成的资源组织为 VNEngine 工程格式与目录结构。

---

## 3. 入口与 UI 架构

### 3.1 AI 工程主窗口（独立窗口）
AI 辅助生成窗口由 `src/designer/ai_project_window.py` 提供，结构为多 Tab：
- 剧情配置
- 角色配置
- 主控Agent（分步生成 + 可编辑）
- 立绘生成
- CG生成
- 背景生成
- 语音生成
- BGM生成

每个 Tab 为一个 Panel（QWidget），窗口使用 `QScrollArea` 包裹，避免长内容撑开窗口。

### 3.2 主控 Agent 面板
主控面板 `src/designer/ai_master_control_panel.py` 的设计要点：
- 每一步有 3 个动作：准备指令 → 发送/生成 → 保存结果。
- 指令和结果都用 `QTextEdit` 展示，并允许用户手动编辑。
- 耗时任务在后台线程运行，避免 UI 卡顿；状态行显示耗时。

> 备注：V2.1 已提升指令/结果文本框的默认高度，改善可读性。

### 3.3 专项面板
专项面板负责把 `PendingLists` 中的待生成条目可视化、可编辑，并执行具体接口调用：
- `AIVoicePanel`：支持单条/批量生成，逐条覆盖 TTS 参数（style/genre/ext 等）。
- `AIBGMPanel`：支持待生成条目参数编辑与持久化（如 Suno inputType/makeInstrumental/tags/prompt）。
- `AIPortraitPanel` / `AIBackgroundPanel` / `AICGPanel`：负责图像相关提示词、模型与任务状态管理。

### 3.4 配置对话框（API 配置）
`src/designer/ai_assist_dialog.py` 提供 API 配置 UI（并显示密钥文件路径/来源），写入 `config/ai_config.yaml`。

---

## 4. 配置与安全设计

### 4.1 配置文件：config/ai_config.yaml
- 位置：工程根目录 `config/ai_config.yaml`
- 内容：各 API 的 base_url、模型参数、超时/轮询参数、以及敏感字段（api_key/token/sign 等）。

### 4.2 敏感信息加密落盘
- 方案：对敏感字段进行字符串加密后写入 YAML，明文仅存在于内存。
- 标识：落盘值以 `ENC::` 前缀标记。
- 关键模块：`src/ai/core/secret_store.py`
  - 默认密钥文件：用户数据目录下 `secret.key`（不在仓库内）
  - 环境变量覆盖：
    - `VNENGINE_SECRET_KEY`：直接提供 Fernet key（不落盘）
    - `VNENGINE_SECRET_KEY_FILE`：指定 key 文件路径

### 4.3 与版本控制的关系
建议：
- **不要提交**开发机的 `config/ai_config.yaml`（即使加密，也属于个人环境配置）。
- 推荐在发布包内携带“默认配置模板”，由用户首次打开后填写 Key。

---

## 5. 数据模型与文件格式

### 5.1 .vnai（AI 工程文件）
- 管理器：`src/ai/core/ai_project_manager.py`
- 序列化：YAML（UTF-8）
- 顶层结构（Pydantic）：`src/ai/core/models.py` 中的 `AIProject` / `AIProjectInfo` / `StoryConfig` / `CharacterConfig` / `GenerationHistory` / `PendingLists` 等。

核心字段（概念层）：
- `ai_project_info`：工程基础信息、关联的 `.vngproj` 路径、创建/修改时间。
- `story_config`：故事标题、风格、梗概、章节数、文本量、第一人称策略、语音合成默认参数等。
- `character_config`：角色列表（id/name/人设关键词/参考图/语音模型 id…）。
- `generation_history`：主控步骤结果与 Agent 调用记录。
- `pending_lists`：各类素材待生成列表（portrait/background/cg/voice/bgm…）。

### 5.2 PendingLists 与条目
- `PendingLists` 统一承载各面板的“待生成条目列表”。
- 每类条目（如 `VoicePendingItem`、`BGMPendingItem`）包含：
  - 可定位的 `item_id`
  - 生成状态（pending/generated/failed 等）
  - prompt/参数覆写/输出路径等

设计原则：
- **可编辑**：条目参数应能在 UI 中单独修改并写回 `.vnai`。
- **可回放**：生成输出路径与关键调用参数要能复现。

### 5.3 VNEngine 工程结构（输出目录）
Integrator 默认输出：`output/projects/<project_name>/`（或用户指定绝对路径）。
目录结构需对齐 VNEngine 运行时/设计器：
- `resources/portraits/`
- `resources/images/`（背景）
- `resources/images/cg/`
- `resources/voices/`
- `resources/audios/`（BGM）
- `resources/videos/`

---

## 6. 核心链路：主控分步生成（StepGenerator）

### 6.1 位置与职责
- 模块：`src/ai/core/step_generator.py`
- 职责：提供“分步生成”的准备/执行能力，并尽可能产出结构化结果。

通用能力：
- 统一 LLM 调用封装（抽取文本、尝试从 JSON/代码块解析结构化内容）。
- 每一步返回：
  - `raw_response`（原文）
  - `structured`（解析出的 JSON/结构）
  - `timestamp`
  - `parameters`

### 6.2 步骤定义（V2.1 实际 UI 对齐）
主控 UI 侧提供的步骤（以 `AIMasterControlPanel` 为准）：
1) 角色人设（personas）
2) 故事大纲（outline）
3) 章节列表（chapters，结构化 JSON）
4) 章节详稿（按章节逐条生成/编辑）
5) 待生成列表 + 流程骨架（pending_lists / flow_nodes / connections / global_variables）
6) 生成 VNEngine 工程文件（.vngproj），先写虚拟资源路径，后续由专项面板补齐资源

### 6.3 输出要求
- 尽可能生成 `flow_nodes/connections` 以便 Integrator 直接导入。
- 若无法提供完整流程骨架，仍应至少产出章节/场景/对白结构，供后续转换。

---

## 7. 多 Agent 协同框架（MasterAgent）

### 7.1 位置与职责
- 模块：`src/ai/core/master_agent.py`
- 职责：按用户配置生成任务清单、调度执行、进度跟踪、质量校验与结果聚合。

关键组成：
- `TaskScheduler`：并发控制与任务状态
- `ProgressMonitor`：进度统计
- `QualityValidator`：结果质量检查（可扩展）
- `ResultAggregator`：汇总结果并生成最终产物（可扩展）

### 7.2 任务规划策略（示例）
MasterAgent 根据 `UserConfig` 中的 enable 开关规划任务：
- plot → portrait → background → cg → voice → bgm → integrator

并包含第一人称规则：
- 第一人称角色可跳过立绘/语音生成（除非启用“第一人称有立绘/配音”）。

> 注：V2.1 主控 UI 以 StepGenerator 为主；MasterAgent 提供更偏“全自动/并发”的演进方向。

---

## 8. API 与 Agent 设计

### 8.1 API Manager 与客户端
- API 管理：`src/ai/api/api_manager.py`
- 基类：`src/ai/api/base_client.py`
- 客户端实现：Claude/Kimi/Flux/Midjourney/GPT-SoVITS/Suno 等。

统一目标：
- 隔离“面板/Agent 业务逻辑”和“第三方 API 细节”。
- 兼容超时、轮询、多模型 fallback、错误重试。

### 8.2 各 Agent 的职责边界
- `plot_agent.py`：负责文本生成（人设/大纲/章节/脚本/节点骨架）。
- `portrait_agent.py`：生成立绘素材（可能含差分/表情）。
- `background_agent.py`：生成背景图。
- `cg_agent.py`：生成 CG。
- `voice_agent.py`：语音合成（对接 GPT-SoVITS）。
- `bgm_agent.py`：BGM 生成（对接 Suno 等）。
- `integrator_agent.py`：整合输出（可作为 MasterAgent 的最终步骤）。

---

## 9. Integrator：将 AI 结果落盘为 VNEngine 工程

### 9.1 位置与职责
- 模块：`src/ai/integrator/integrator.py`
- 职责：
  - 创建工程目录结构
  - 写入 `.vngproj`
  - 将生成的资源复制/归档到规范目录
  - 把 plot 输出转换为 `FlowNodeData/ConnectionData/GlobalVariable`

### 9.2 两种剧情导入方式
Integrator 的剧情整合支持：
1) **直接载入流程骨架**：plot 输出包含 `flow_nodes` / `connections`，则直接解析并写入。
2) **传统转换**：只有 chapters/scenes/dialogues 时，按规则转换为顺序文本节点并串联。

---

## 10. 并发、线程与进度呈现

- UI 层耗时任务通过后台线程执行（避免卡 UI），并用信号回传结果。
- 批量生成（如语音）需要：
  - 进度实时刷新
  - 失败可继续/可中止
  - 条目状态与输出路径同步回写 `.vnai`

---

## 11. 错误处理与可恢复性

推荐策略：
- API 调用：明确区分“可重试错误”（超时、429）与“不可重试错误”（鉴权失败、参数错误）。
- 解析失败：保留 raw_response，structured 为空也可继续人工编辑。
- 文件落盘：写入失败需要给出可定位的路径与原因（权限/占用/路径非法）。

---

## 12. 打包与发布（面向 2.1）

### 12.1 PyInstaller 打包建议
- 建议使用 `VNEngineDesigner.spec` 打包（可复现）。
- 发布包应包含：
  - 源代码（PyInstaller 收集后的模块）
  - icon.ico
  - 必要的默认配置模板（建议是“无个人密钥”的模板）

### 12.2 配置与密钥的发布策略
- 不建议把开发机的 `config/ai_config.yaml` 直接发布（即使加密）。
- 更安全的做法：
  - 发布包内提供 `config/ai_config.example.yaml`
  - 首次启动引导用户填写，并在本机生成/使用 secret.key

---

## 13. 测试与质量保障

- 单元/集成测试：`tests/`（pytest）
- 建议的覆盖点：
  - `.vnai` 的保存/加载/兼容性（schema 演进）
  - `StepGenerator` JSON 解析鲁棒性
  - Integrator 的目录结构与 `.vngproj` 输出对齐
  - 批量生成的中止/失败续跑/进度一致性

---

## 14. 后续演进建议（不影响 V2.1 发布）

- 在 UI 中提供“模板化 prompt 管理”和“版本化参数 preset”。
- 引入更强的结构化约束（JSON Schema / pydantic 输出校验与自动修复）。
- 将 MasterAgent 与 StepGenerator 融合：
  - StepGenerator 负责内容结构化
  - MasterAgent 负责并发与资源生成调度
- 增强安全：可选接入 Windows DPAPI/Credential Manager 作为密钥托管方案。
