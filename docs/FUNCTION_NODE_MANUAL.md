# 功能节点（Function Node）完全操作手册

本文档面向 VNEngine 设计器与运行时的“功能节点”，用于在剧情流程中**以高自由度脚本**实现各种元行为/特效/自动化（如文件检测、文件复制、触发重启/退出、修改变量等）。

> 重要安全提示：
> - 功能节点的脚本在运行时执行。
> - 默认提供“安全模式”（受限 import + 文件系统操作限定在工程目录）。
> - 如果你开启 `allow_unsafe_function_scripts: true`，脚本将获得几乎完全的 Python 能力（包括 `import os/shutil` 等），这相当于“运行任意代码”。请仅对可信工程使用。

---

## 1. 概念与定位

- **功能节点是一种没有入边/出边的节点**，它不参与剧情连线。
- **功能节点必须绑定到一个宿主节点**（文本/选择/条件）才会生效。
- 运行时在“进入宿主节点”时触发功能节点执行。

### 1.1 触发时机（重要）

- 图模式（flow_nodes）下：
  - 当进入宿主节点时触发。
  - 若宿主是文本节点并且存在多条子对白：仅在进入第 1 条子对白时触发一次（不会每条子对白都重复触发）。

---

## 2. 在设计器中创建/绑定/解绑

### 2.1 创建功能节点

1. 在画布空白处右键。
2. 选择“添加功能节点”。
3. 新建的功能节点显示“未绑定”。

### 2.2 绑定到宿主节点

- 将功能节点**拖拽到**文本/选择/条件节点上方，松开鼠标。
- 若发生碰撞（覆盖）会自动绑定，并显示：`绑定: <宿主id>`。

> 说明：绑定关系会随工程保存并在加载时恢复。

### 2.3 解绑

两种方式：
- 在功能节点上右键，选择“解绑功能节点”。
- 选中功能节点，在属性面板的“功能”页点击“解绑”。

---

## 3. 功能节点属性编辑（规则系统）

选中功能节点后，属性面板会显示“功能”页：

- `绑定到`：显示当前宿主节点 id。
- `规则列表`：一组按顺序执行的规则。
- `规则字段`：
  - `启用`：关闭后该规则不执行。
  - `条件`：Python 表达式；为空视为 True。
  - `动作`：Python 脚本（多行）。

### 3.3 条件表达式应该怎么写（很重要）

`条件`字段是一个 **Python 表达式**（expression），引擎会用 `eval()` 求值：

- 你要写的是“能返回 True/False（或 truthy/falsy）”的表达式。
- **不能**写 `if/for/while/def/import/赋值` 这类语句（statement）。
- 为空（或全是空白）视为 `True`。
- 设计器里条件输入框支持多行；**运行时会把换行当作空格处理**（方便写长表达式）。

可用变量与含义：

- `engine`：引擎 API（建议只用 `engine.xxx` 与运行时交互）
- `entry`：当前宿主节点的 entry 快照 dict（建议只读）
- `vars`：变量表快照 dict（建议只读）
- `host_node_id`：宿主节点 id
- `function_node`：当前功能节点 dict
- `rule_index`：规则索引（从 0 开始）

推荐写法（示例）：

```python
# 1) 最常见：根据变量判断
engine.get_var('love', 0) >= 10 and engine.get_var('flag', 0) == 1

# 2) 读取 entry 的字段（例如只在特定 speaker 时触发）
(entry.get('speaker') or '') in ('旁白', '系统')

# 3) 文件存在性（安全模式建议走 engine.fs；不写绝对路径）
engine.fs.exists('output/build_done.flag')

# 4) 长表达式建议用括号分行（换行会当空格，逻辑更清晰）
(
  engine.get_var('stage', 0) >= 3
  and (entry.get('hide_textbox') is not True)
  and engine.fs.exists('resources/audios/click.wav')
)
```

不推荐写法：

```python
# ❌ 语句：会报错（条件里不要写）
if engine.get_var('x', 0) > 0:
  True

# ❌ import 也是语句（条件里不要写）
import os
```

建议：如果你需要复杂判断（比如需要读一个 JSON、遍历目录、正则解析等），把复杂逻辑放在 `动作` 里执行，然后用 `engine.set_var()` 把结果写到变量里，条件只做简单比较。

### 3.1 执行顺序

- 同一功能节点内：规则按列表顺序执行。
- 同一宿主节点上绑定多个功能节点：目前按加载顺序执行（通常是工程保存时 nodes 列表顺序）。

### 3.2 并行语义

- 功能节点脚本在后台线程执行，以避免阻塞游戏主循环。
- 需要修改游戏状态（如变量/重启/退出）时，应使用 `engine` 提供的 API，它会把动作排队到主线程执行。

---

## 4. 脚本运行环境

在 `动作`/`条件` 中可用的变量：

- `engine`：引擎脚本 API（推荐只通过它与运行时交互）。
- `entry`：宿主节点 entry 的快照 dict（只读建议）。
- `vars`：变量表快照 dict（只读建议）。
- `host_node_id`：宿主节点 id。
- `function_node`：当前功能节点 dict（含 rules/bound_to 等）。
- `rule_index`：当前规则在规则列表中的索引（从 0 开始）。

### 4.1 两种模式

#### A) 安全模式（默认）

- `import` 受限（仅允许 `math/random/re/time`）。
- 提供强大文件操作能力：通过 `engine.fs` 完成。
- 所有文件系统操作默认限制在 `function_script_fs_root` 目录下（默认工程目录）。

#### B) 完全自由模式（不安全）

在工程 `game_config` 中配置：

```yaml
game_config:
  allow_unsafe_function_scripts: true
```

- 脚本可进行任意 Python `import`（包括 `os/shutil/subprocess` 等）。
- `engine.fs` 同样可用，但不再限制根目录。

---

## 5. engine API 参考

### 5.1 engine.log(*args)

输出日志：

```python
engine.log("hello", 123)
```

### 5.2 engine.set_var(name, value)

在主线程设置变量（推荐）：

```python
engine.set_var("favor", 10)
```

### 5.3 engine.get_var(name, default=None)

读取变量（从当前变量表读取，线程安全尽力而为）：

```python
v = engine.get_var("favor", 0)
```

### 5.4 engine.request_exit()

请求退出游戏。

### 5.5 engine.request_restart(reset_globals=False)

请求重启游戏（可选是否重置全局变量）。

---

### 5.6 engine.ui（UI / 交互）

#### 5.6.1 engine.ui.toast(text, duration=2.0)

在屏幕底部显示一个短暂提示（不阻塞剧情）。

```python
engine.ui.toast("保存成功", duration=2.0)
```

#### 5.6.2 engine.ui.alert(text, title="提示")

弹出一个**模态提示框**（会吞掉输入，直到玩家按任意键/点击关闭）。脚本本身不会等待（不支持 await），但玩家在提示框期间无法继续操作。

```python
engine.ui.alert("检测到配置异常，请检查日志", title="警告")
```

#### 5.6.3 engine.ui.set_cursor(style, lock=False)

切换系统鼠标样式。`style` 支持：`"arrow" | "hand" | "ibeam" | "wait" | "crosshair"`。

- `lock=False`：临时切换一次；引擎的自动“手型/箭头”逻辑仍可能覆盖。
- `lock=True`：锁定鼠标样式，直到调用 `engine.ui.clear_cursor_lock()`。

```python
engine.ui.set_cursor("wait", lock=True)
```

#### 5.6.4 engine.ui.clear_cursor_lock()

解除鼠标样式锁定。

#### 5.6.5 engine.ui.show_image(path, x, y, width, height, duration=0.0, *, key=None, alpha=255, z=1000.0) -> key

在游戏画面上层显示一张图片（**高于对话框/选择按钮等**，属于最顶层叠加层）。

- 坐标系：使用工程的渲染坐标（`render_surface`），不是窗口像素；例如工程 1280×720，那么 `x/y/width/height` 也是 1280×720 坐标系。
- `duration`：
  - `> 0`：持续指定秒数后自动消失
  - `<= 0`：一直显示，直到 `hide_image/clear_images`
- `key`：可选，自定义标识；不传会自动生成并返回。
- `alpha`：0~255。
- `z`：同为脚本图片时的绘制顺序（小的先画，大的后画）。

```python
# 在 (80, 60) 位置显示 320x180 图片，2 秒后消失
engine.ui.show_image(
    "resources/images/logo.png",
    x=80, y=60,
    width=320, height=180,
    duration=2.0,
)
```

#### 5.6.6 engine.ui.hide_image(key)

按 `key` 隐藏图片：

```python
engine.ui.show_image(
  "resources/images/warn.png",
  200, 120, 400, 220,
  duration=0,
  key="warn",
)
engine.time.set_timeout(1.2, "engine.ui.hide_image('warn')")
```

#### 5.6.7 engine.ui.clear_images()

清空所有脚本图片叠加层。

#### 5.6.8 engine.ui.lock_input(seconds)

锁定玩家输入：在持续时间内（游戏模式中）玩家的键盘/鼠标输入会被吞掉（不影响窗口关闭事件）。

```python
engine.ui.lock_input(1.0)  # 1 秒内无法按键/点击
```

#### 5.6.9 engine.ui.lock_input_until(expr, timeout=0.0)

锁定输入直到条件满足。

- `expr` 是 Python 表达式，环境里提供 `vars`（变量表的快照）。
- 条件表达式异常会被视为 `False`（继续锁定）。
- `timeout>0` 可作为兜底：超时后自动解除锁定。

```python
# 直到 vars["phase"] >= 3 才允许玩家继续操作（最多锁 10 秒）
engine.ui.lock_input_until("vars.get('phase', 0) >= 3", timeout=10.0)
```

#### 5.6.10 engine.ui.unlock_input()

立即解除输入锁。

#### 5.6.11 engine.ui.toggle_fullscreen()

切换全屏/窗口模式（等同于 F11）。

```python
engine.ui.toggle_fullscreen()
```

#### 5.6.12 engine.ui.set_fullscreen(enabled=True)

显式设置全屏状态：

```python
engine.ui.set_fullscreen(True)   # 强制全屏
engine.ui.set_fullscreen(False)  # 恢复窗口
```

#### 5.6.13 engine.ui.is_fullscreen() -> bool

返回当前是否全屏。

#### 5.6.14 engine.ui.is_input_locked() -> bool

返回当前是否处于输入锁定。

---

### 5.7 engine.fx（临时特效）

#### 5.7.1 engine.fx.shake(duration=0.25, strength=6.0, decay=True)

窗口/画面抖动（通过最终 blit 偏移实现）。

```python
engine.fx.shake(duration=0.35, strength=8)
```

#### 5.7.2 engine.fx.flash(color=(255,255,255), duration=0.18, alpha=180)

全屏闪光（常用于点击反馈、受击、切换提示等）。

```python
engine.fx.flash(color=(255, 255, 255), duration=0.12, alpha=160)
```

---

### 5.8 engine.audio（运行时音频控制）

> 安全模式下：路径同样受 `function_script_fs_root` 限制，且禁止绝对路径。

#### 5.8.1 engine.audio.play_sfx(path, delay=0.0)

播放一次音效（会走引擎的音量混合：`master_volume * sfx_volume`）。

```python
engine.audio.play_sfx("resources/audios/click.wav")
engine.audio.play_sfx("resources/audios/click.wav", delay=0.2)
```

#### 5.8.2 engine.audio.stop_sfx()

停止当前正在播放的音效。

#### 5.8.3 engine.audio.play_bgm(path, loop=True, fade=False)

强制切换/播放 BGM。

```python
engine.audio.play_bgm("resources/audios/bgm.ogg", loop=True, fade=True)
```

#### 5.8.4 engine.audio.stop_bgm()

停止 BGM。

---

### 5.9 engine.time（延迟/定时执行）

> 设计目标：不阻塞主循环；脚本会在后台线程执行。

#### 5.9.1 engine.time.set_timeout(seconds, script) -> timer_id

延迟执行一段脚本（一次性）。

```python
tid = engine.time.set_timeout(0.5, "engine.ui.toast('0.5s 到了')")
```

#### 5.9.2 engine.time.set_interval(seconds, script, repeat=-1) -> timer_id

循环执行脚本：

- `repeat=-1`：无限次
- `repeat=3`：执行 3 次

```python
tid = engine.time.set_interval(1.0, "engine.ui.toast('tick')", repeat=3)
```

#### 5.9.3 engine.time.clear_timer(timer_id) -> bool

取消定时器。

---

## 6. engine.fs 文件系统 API 参考（重点）

> 在安全模式下，所有路径默认相对于 `function_script_fs_root`。

### 6.1 路径解析

- 相对路径：相对 `function_script_fs_root`。
- 绝对路径：
  - 安全模式：禁止。
  - 不安全模式：允许。

可用：

- `engine.fs.abspath(path)`：返回解析后的绝对路径字符串。

### 6.2 基础查询

- `engine.fs.exists(path) -> bool`
- `engine.fs.is_file(path) -> bool`
- `engine.fs.is_dir(path) -> bool`

### 6.3 目录

- `engine.fs.mkdir(path, parents=True, exist_ok=True) -> str`
- `engine.fs.listdir(path=".", pattern=None, recursive=False) -> list[str]`
- `engine.fs.glob(pattern) -> list[str]`

### 6.4 读写

- `engine.fs.read_text(path, encoding="utf-8") -> str`
- `engine.fs.write_text(path, content, encoding="utf-8", append=False) -> str`
- `engine.fs.read_bytes(path) -> bytes`
- `engine.fs.write_bytes(path, content: bytes, append=False) -> str`

### 6.5 复制/移动/删除

- `engine.fs.copy(src, dst, overwrite=True) -> str`
- `engine.fs.copytree(src_dir, dst_dir, overwrite=True) -> str`
- `engine.fs.move(src, dst, overwrite=True) -> str`
- `engine.fs.remove(path, missing_ok=True) -> bool`
- `engine.fs.delete(path, missing_ok=True, recursive=False) -> bool`：更直观的“删除”接口。
  - 默认只删除文件；若 `path` 是目录，需显式传 `recursive=True`。
- `engine.fs.open(path) -> str`：用系统默认程序打开文件/目录。
  - Windows 下：例如 `.txt` 通常会用记事本打开。
  - 安全模式下会限制可打开的文件类型（禁止 `.exe/.bat/.ps1` 等可执行/脚本类型；不在白名单的扩展名也会拒绝）。

---

## 7. 典型脚本示例

### 7.1 判断文件是否存在

条件：

```python
engine.fs.exists("output/build_done.flag")
```

动作：

```python
if engine.fs.exists("resources/audios/click.wav"):
    engine.log("音效存在")
else:
    engine.log("音效不存在")
```

### 7.2 复制文件到指定目录

```python
src = "resources/audios/click.wav"
dst = "output/cache/click.wav"
engine.fs.copy(src, dst, overwrite=True)
engine.log("copied", src, "->", dst)
```

### 7.3 写入日志文件

```python
engine.fs.write_text("logs/function_node.log", "entered node\n", append=True)

### 7.3.1 打开日志文件（系统默认方式）

> 用途：在本地调试时，自动打开刚写入的日志文件。

```python
log_path = "logs/function_node.log"
engine.fs.write_text(log_path, "entered node\n", append=True)
engine.fs.open(log_path)
```

### 7.3.2 删除某个临时文件

```python
tmp = "output/tmp/debug.txt"
engine.fs.delete(tmp, missing_ok=True)
engine.ui.toast("已清理临时文件", duration=1.2)
```
```

### 7.4 修改变量并触发条件分支

```python
engine.set_var("favor", engine.get_var("favor", 0) + 1)
engine.log("favor++")
```

### 7.5 根据某文件存在与否进行重启/退出

```python
if engine.fs.exists("output/restart.flag"):
    engine.request_restart(reset_globals=False)
```

### 7.6 完整脚本示例：进入节点时“提示 + 闪光 + 抖动 + 延迟音效”

用途：用于按钮确认、剧情关键点“触发反馈”，并演示延迟执行。

```python
# 进入宿主节点时：立即给出轻量反馈
engine.ui.toast("触发事件：准备执行…", duration=1.6)
engine.fx.flash(color=(255, 255, 255), duration=0.12, alpha=150)
engine.fx.shake(duration=0.28, strength=7, decay=True)

# 200ms 后播放一个 click 音效（路径在安全模式下必须位于 function_script_fs_root 内）
engine.audio.play_sfx("resources/audios/click.wav", delay=0.2)

# 1s 后再弹出一个模态提示（会吞掉输入直到玩家关闭）
engine.time.set_timeout(1.0, "engine.ui.alert('事件已执行完成', title='提示')")
```

### 7.7 完整脚本示例：轮询文件标志（每 0.5s 检测一次，检测到就拷贝并提示）

用途：与外部工具联动（例如打包/生成器写入 flag 文件），检测成功后把产物复制到缓存目录。

```python
# 轮询一个 flag 文件：存在就执行一次复制，然后停止轮询。
script = """
flag = 'output/build_done.flag'
src = 'output/result.bin'
dst = 'output/cache/result.bin'

if engine.fs.exists(flag) and engine.fs.is_file(src):
  engine.fs.copy(src, dst, overwrite=True)
  engine.ui.toast('已复制产物到缓存目录', duration=2.0)
  engine.fx.flash(color=(120, 255, 160), duration=0.15, alpha=140)
  # 定时器脚本环境内可直接读到 function_node.id（当前定时器的 id）
  engine.time.clear_timer(function_node.get('id'))
"""

# 注意：repeat=-1 表示无限次。这里用 0.5s 轮询。
engine.time.set_interval(0.5, script, repeat=-1)
engine.ui.toast('开始等待 build_done.flag…', duration=1.5)
```

### 7.8 非安全模式（不安全）完整脚本示例

> 前置条件：在工程 `game_config` 中开启：

```yaml
game_config:
  allow_unsafe_function_scripts: true
```

> 强提示：不安全模式等价于“运行任意 Python 代码”。请只在本机可信工程中使用。

#### 7.8.1 读取工程外配置文件并写入变量（允许绝对路径 + 任意 import）

用途：从用户目录读取一个外部配置（比如调试开关/渠道号），并写到变量里供后续条件节点/分支使用。

```python
import json
from pathlib import Path

cfg_path = Path.home() / 'vnengine_debug_config.json'

if cfg_path.exists():
  data = json.loads(cfg_path.read_text(encoding='utf-8'))
  engine.set_var('debug_mode', int(bool(data.get('debug_mode', False))))
  engine.set_var('channel', str(data.get('channel', 'default')))
  engine.ui.toast(f"已载入外部配置: {cfg_path}")
else:
  engine.set_var('debug_mode', 0)
  engine.ui.toast('未找到外部配置，使用默认值')
```

#### 7.8.2 自动备份工程目录到工程外（shutil + 时间戳）

用途：在进入某节点时，把工程目录（或存档目录）做一次快速备份到用户桌面，用于调试/回滚。

```python
import shutil
from datetime import datetime
from pathlib import Path

src = Path.cwd()  # 当前运行目录（通常是工程目录）
dst_root = Path.home() / 'Desktop' / 'VNEngineBackups'
dst_root.mkdir(parents=True, exist_ok=True)

stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
dst = dst_root / f'backup_{stamp}'

try:
  shutil.copytree(src, dst)
  engine.ui.toast(f'备份完成: {dst}', duration=2.2)
except Exception as e:
  engine.ui.alert(f'备份失败: {e}', title='错误')
```

#### 7.8.3 直接使用标准库做复杂判断，然后用变量驱动后续流程

用途：把复杂逻辑（例如目录扫描/统计）放在动作里，最后只写一个布尔变量，让 `条件` 表达式保持简单。

```python
import os
from pathlib import Path

root = Path.cwd() / 'output'
count = 0
if root.exists():
  for dirpath, _, filenames in os.walk(root):
    for f in filenames:
      if f.lower().endswith('.log'):
        count += 1

engine.set_var('log_count', count)
engine.ui.toast(f'output 下日志数量: {count}', duration=1.8)

# 后续的条件可以写：engine.get_var('log_count', 0) > 10
```

---

## 8. 工程配置项（game_config）

在 `.vngproj`（YAML）中：

```yaml
game_config:
  # 允许脚本完全自由（强烈建议只在可信工程开启）
  allow_unsafe_function_scripts: false

  # 安全模式下允许访问的文件系统根目录
  # - 不填：默认工程目录
  # - 可填相对路径：相对工程目录
  # - 可填绝对路径：将以该路径作为根（仍会限制越界）
  function_script_fs_root: "./"
```

---

## 9. 常见问题

### Q1：为什么功能节点属性里没有媒体/背景/UI 等？

因为功能节点是附加行为，渲染/媒体配置应由宿主节点决定；功能节点只负责“进入宿主时额外做什么”。

### Q2：我需要更高级能力（比如 `os`/`subprocess`）怎么办？

- 开启 `allow_unsafe_function_scripts: true`。
- 这将允许脚本执行任意 Python 代码。

### Q3：脚本能否阻塞游戏？

- 脚本在后台线程执行，默认不阻塞主循环。
- 但脚本若进行超长 IO 或死循环，会一直占用后台线程；建议自行加超时/条件控制。

---

## 10. 推荐实践

- 默认保持安全模式，仅使用 `engine` / `engine.fs`。
- 对于可能改变游戏流程的动作（修改变量、重启/退出），优先使用 `engine.set_var/request_restart/request_exit`，避免线程问题。
- 文件操作建议写入 `output/` 或 `logs/`，并避免频繁大文件拷贝。
