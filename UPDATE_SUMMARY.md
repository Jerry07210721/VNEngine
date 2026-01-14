# VNEngine 更新说明 - 可选Agent功能

## 🔧 问题修复

### 1. SignalBus错误修复
**问题**: `'SignalBus' object has no attribute 'progress_updated'`

**原因**: AIGenerationThread尝试连接`signal_bus.progress_updated`信号，但SignalBus只定义了`progress_update`

**解决方案**:
- ✅ 在SignalBus中添加`progress_updated = pyqtSignal(float, str)`信号（简化版）
- ✅ 在`emit_progress()`方法中同时触发两个信号以保持兼容性

---

## ✨ 新增功能：可选Agent

### UI更新
现在每个资源生成模块都有**启用/禁用复选框**：

#### 1. 图像生成配置
```
☑ 启用图像生成  [默认：勾选]
  - 服务商: SDXL / 通义万相 / MidJourney
  - API Key: ****
  - App ID: [MidJourney需要]
  - Base URL: https://api.mmchat.xyz/open/v1
```

#### 2. TTS配置
```
☐ 启用语音合成  [默认：不勾选]
  - 服务商: GPT-SoVITS / Bert-VITS2 / Azure / OpenAI / 阿里云
  - API Key: ****
  - Base URL: http://127.0.0.1:9880
  - Region: eastus
```

#### 3. 音乐生成配置
```
☐ 启用BGM生成  [默认：不勾选]
  - 服务商: Suno AI / MusicGen
  - x-token: ****
  - x-userId: default_user
  - Base URL: https://dzwlai.com/apiuser
```

---

## 📋 使用场景

### 场景1：只生成剧情和人设
```
✅ LLM配置（必需）
☐ 图像生成  [取消勾选]
☐ TTS配置   [取消勾选]
☐ 音乐生成  [取消勾选]

结果：只生成角色人设和剧本文本，不生成任何资源
```

### 场景2：剧情 + 立绘 + 背景（无语音和BGM）
```
✅ LLM配置（必需）
☑ 图像生成  [勾选，填写API Key]
☐ TTS配置   [取消勾选]
☐ 音乐生成  [取消勾选]

结果：生成完整剧本 + 角色立绘 + 背景图，跳过语音和BGM
```

### 场景3：完整生成
```
✅ LLM配置（必需）
☑ 图像生成  [勾选]
☑ TTS配置   [勾选]
☑ 音乐生成  [勾选]

结果：生成完整游戏（人设、剧本、立绘、背景、CG、语音、BGM）
```

---

## 🔄 工作原理

### 1. 复选框控制
- 勾选复选框 → 启用输入框
- 取消勾选 → 禁用输入框（变灰）

### 2. 参数构建逻辑
```python
# 只有复选框勾选 AND API Key有值时，才添加配置
if self.enable_image_check.isChecked() and self.image_key_edit.text():
    generation_params["api_configs"]["image"] = {...}
```

### 3. Agent初始化逻辑
```python
# StoryMasterAgent根据配置决定是否创建子Agent
if "image" in api_configs:
    self.portrait_agent = PortraitDiffAgent(...)  # 创建立绘Agent
else:
    self.portrait_agent = None  # 不创建
```

### 4. 资源生成逻辑
```python
# 只有Agent存在时才执行生成
if self.portrait_agent:
    # 生成立绘
else:
    self.logger.info("跳过立绘生成（未配置图像API）")
```

---

## 🎯 默认配置

| 模块 | 默认状态 | 原因 |
|-----|---------|------|
| LLM | 必需 | 生成剧情的核心 |
| 图像生成 | ☑ 启用 | 视觉小说的主要资源 |
| TTS | ☐ 禁用 | 可选，本地部署需配置 |
| BGM | ☐ 禁用 | 可选，需要付费API |

---

## 📁 更新的文件

| 文件 | 更新内容 |
|------|---------|
| `signal_bus.py` | 添加`progress_updated`信号 |
| `ai_generation_dialog.py` | 添加3个复选框 + 3个toggle函数 |
| `ai_generation_dialog.py` | 更新参数构建逻辑（根据复选框状态） |
| `story_master_agent.py` | 已支持可选Agent（检查配置后创建） |

---

## 🧪 测试步骤

1. **启动程序**
   ```bash
   cd K:\VNEngine
   python main.py
   ```

2. **打开AI生成对话框**
   - 点击"AI游戏生成"菜单

3. **测试场景1：只生成剧情**
   - 基础设置：填写游戏名称、主题
   - API配置：只填LLM API Key
   - 取消勾选：☐ 图像生成
   - 点击"开始生成"
   - 预期：只生成剧本JSON，跳过所有资源

4. **测试场景2：剧情+视觉**
   - 勾选：☑ 启用图像生成
   - 填写图像API配置
   - 取消勾选TTS和音乐
   - 预期：生成剧本+立绘+背景

5. **测试错误处理**
   - 观察控制台日志
   - 应该看到类似：`跳过语音生成（未配置TTS API）`

---

## 💡 提示

### 节省测试时间
- 取消勾选TTS和BGM（生成最慢）
- 减少角色数量（1-2个）
- 选择"短篇"剧情长度

### 调试模式
查看日志了解跳过了哪些Agent：
```
[StoryMasterAgent] 跳过视觉资源生成（未配置图像生成API）
[StoryMasterAgent] 跳过音频资源生成（未配置TTS/音乐生成API）
```

---

## ❓ 常见问题

**Q: 为什么图像生成默认勾选，TTS默认不勾选？**  
A: 视觉小说的核心是图像，而语音是可选增强功能。且TTS通常需要本地部署或付费API。

**Q: 如果我勾选了但没填API Key会怎样？**  
A: 不会添加到配置中，相当于不勾选。检查逻辑：`isChecked() AND has_api_key()`

**Q: 我可以只生成剧本吗？**  
A: 可以！取消勾选所有资源生成复选框即可。

**Q: 如何恢复完整生成？**  
A: 全部勾选 + 填写所有API配置即可。
