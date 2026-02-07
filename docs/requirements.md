# Auto Capture 需求文档

## 项目概述

一个用于自动收集用户输入行为的工具，记录键盘按键序列和鼠标点击截图，用于行为分析、操作回溯等场景。

---

## 功能需求

### 1. 键盘行为记录

#### 1.1 监听范围
- 监听系统全局键盘事件
- 仅记录 `keydown` 事件，忽略 `keyup` 事件
- 记录所有按键，包括：
  - 字母、数字、符号
  - 功能键（F1-F12）
  - 修饰键（Shift、Ctrl、Alt/Option、Cmd/Win）
  - 特殊键（Enter、Tab、Space、Backspace、Delete、Esc 等）
  - 方向键

#### 1.2 窗口聚合规则
- 按当前活跃窗口聚合键盘输入
- 每次切换活跃窗口时，开始新的记录块
- 记录块头部包含窗口信息：
  - 应用名称（如 `Visual Studio Code`）
  - 窗口标题（如 `index.ts - my-project`）
  - 应用 Bundle ID（如 `com.microsoft.VSCode`，仅 macOS）
  - 切换时间戳

#### 1.3 时间聚类规则
- 在同一窗口内，连续按键（间隔 ≤ 20 秒）记录在同一行
- 按键间隔 > 20 秒时，新起一行记录
- 每行开头标注该行首个按键的时间戳

#### 1.4 日志格式示例

统一日志文件，以三个换行分隔不同窗口，截图也记录在日志中：

```
[2026-02-01 10:23:40] Visual Studio Code | index.ts - my-project (com.microsoft.VSCode)
[10:23:45] hello world↩
[10:23:50] ⌘s
[10:23:51] 📷 click (800,600) click_102351_123_left_x800_y600.webp


[2026-02-01 10:25:32] Terminal | zsh (com.apple.Terminal)
[10:25:35] npm run dev↩
[10:25:40] 📷 click (500,400) click_102540_456_left_x500_y400.webp
[10:26:00] ⌃c


[2026-02-01 10:26:05] Google Chrome | GitHub - my-project (com.google.Chrome)
[10:26:10] ⌘t
[10:26:12] 📷 drag (100,200)->(500,400) drag_102612_789_left_x100_y200_to_x500_y400.webp
[10:26:15] stackoverflow.com↩
```

#### 1.5 按键表示规范（使用 macOS 键盘符号）
| 按键类型 | 符号 | 说明 |
|---------|------|------|
| 可打印字符 | `a`, `1`, `@` | 直接显示 |
| 空格 | ` ` | 空格字符 |
| Command | `⌘` | |
| Control | `⌃` | |
| Option/Alt | `⌥` | |
| Shift | `⇧` | |
| Caps Lock | `⇪` | |
| Enter | `↩` | |
| Tab | `⇥` | |
| Escape | `⎋` | |
| Backspace | `⌫` | |
| Delete | `⌦` | |
| 方向键 | `↑` `↓` `←` `→` | |
| Home/End | `↖` `↘` | |
| Page Up/Down | `⇞` `⇟` | |
| 功能键 | `F1` - `F12` | |

---

### 2. 鼠标行为截图

#### 2.1 触发条件
- 监听系统全局鼠标事件（按下与释放）
- 左键、右键、中键均触发
- 支持三种行为类型：单击、双击、拖拽

#### 2.2 行为检测逻辑

```
鼠标按下 (pressed=True)
  └─ 记录 press_time, press_x, press_y

鼠标释放 (pressed=False)
  ├─ 计算与按下位置的距离
  ├─ 距离 > 10px → 拖拽
  └─ 距离 ≤ 10px → 点击
        ├─ 与上次点击间隔 < 400ms 且距离 < 5px → 双击
        └─ 否则 → 单击
```

#### 2.3 截图要求
- 截取完整屏幕（多显示器时截取所有屏幕拼接图像）
- 图片格式：WebP（有损压缩，质量 80%，体积约为 PNG 的 1/10）
- 鼠标光标在截图中自然可见，无需额外标记
- **活跃窗口标注**：在截图上绘制蓝色线框突出当前活跃窗口
  - 边框颜色：蓝色（`rgb(0, 120, 255)`）
  - 边框宽度：3px
- **拖拽操作**：在截图上绘制半透明灰色矩形标注拖拽区域
  - 矩形范围：从按下位置到释放位置
  - 填充颜色：灰色，透明度 30%（`rgba(128, 128, 128, 0.3)`）
  - 边框：深灰色 2px

#### 2.4 多显示器坐标处理
- 获取显示器布局信息（各屏幕的 left/top 偏移）
- 将鼠标绝对坐标转换为拼接图像中的相对坐标
- 公式：`图像坐标 = 鼠标坐标 - 拼接图像原点偏移`

#### 2.5 截图命名规则

| 行为类型 | 文件名格式 |
|---------|-----------|
| 单击 | `click_<时间戳>_<毫秒>_<按键>_x<X>_y<Y>.webp` |
| 双击 | `dblclick_<时间戳>_<毫秒>_<按键>_x<X>_y<Y>.webp` |
| 拖拽 | `drag_<时间戳>_<毫秒>_<按键>_x<X1>_y<Y1>_to_x<X2>_y<Y2>.webp` |

示例：
```
click_103045_123_left_x800_y600.webp
dblclick_103046_456_left_x800_y600.webp
drag_103050_789_left_x100_y200_to_x500_y400.webp
```

---

### 3. 数据存储

#### 3.1 目录结构

```
<存储根目录>/
├── 2026-02-01/
│   ├── 2026-02-01.log        # 当日日志（键盘+截图记录）
│   ├── click_103045_123_left_x800_y600.webp
│   ├── dblclick_103046_456_left_x800_y600.webp
│   └── ...
├── 2026-02-02/
│   ├── 2026-02-02.log
│   └── ...
└── ...
```

#### 3.2 存储规则
- 按日期（本地时区）自动创建目录
- 日期格式：`YYYY-MM-DD`
- 跨日自动切换到新目录
- 键盘日志追加写入，不覆盖

#### 3.3 默认存储位置
- 可配置，默认建议：`~/opencapture/`

---

## 非功能需求

### 4. 系统权限

#### 4.1 macOS
- 需要「辅助功能」权限 - 用于全局键鼠监听
- 需要「屏幕录制」权限 - 用于截图
- 首次运行应提示用户授权

#### 4.2 Windows
- 可能需要管理员权限运行

#### 4.3 Linux
- 可能需要 X11 或 Wayland 相关权限
- 可能需要加入 `input` 用户组

---

### 5. 活跃窗口检测

#### 5.1 需获取的窗口信息
| 信息 | 说明 | 示例 |
|------|------|------|
| 应用名称 | 当前活跃应用的显示名称 | `Google Chrome` |
| 窗口标题 | 当前窗口的标题栏文字 | `GitHub - my-project` |
| Bundle ID | 应用唯一标识（macOS） | `com.google.Chrome` |
| 进程名 | 进程名称（Windows/Linux） | `chrome.exe` |

#### 5.2 检测方式
- 通过系统事件监听窗口切换（非轮询）
- 窗口切换事件触发时，更新当前窗口上下文并插入分隔块
- 启动时获取一次当前活跃窗口作为初始状态

#### 5.3 平台事件监听
| 平台 | 事件监听方式 | 窗口信息获取 |
|------|-------------|-------------|
| macOS | `NSWorkspaceDidActivateApplicationNotification` 或 Accessibility API `kAXFocusedWindowChangedNotification` | `NSWorkspace.frontmostApplication` + AX API 获取窗口标题 |
| Windows | `SetWinEventHook` + `EVENT_SYSTEM_FOREGROUND` | `GetForegroundWindow` + `GetWindowText` |
| Linux (X11) | 监听 `_NET_ACTIVE_WINDOW` 属性变化 | `XGetInputFocus` + `XFetchName` |
| Linux (Wayland) | 受限，compositor 相关 | 各 compositor 实现不同 |

---

### 6. 性能要求

#### 6.1 资源占用
- CPU 占用率应保持在较低水平（空闲时 < 1%）
- 内存占用应控制在合理范围（< 100MB）

#### 6.2 响应性
- 键盘记录应实时写入或定期批量写入（延迟 < 1 秒）
- 截图操作不应阻塞主监听线程
- 高频点击时应有节流机制（可配置，默认建议 100ms）

---

### 7. 可配置项

| 配置项 | 说明 | 默认值 |
|-------|------|--------|
| `storageDir` | 数据存储根目录 | `~/opencapture/` |
| `keyClusterInterval` | 键盘聚类时间间隔（秒） | `20` |
| `screenshotThrottle` | 截图节流间隔（毫秒） | `100` |
| `dragThreshold` | 拖拽判定距离阈值（像素） | `10` |
| `doubleClickInterval` | 双击判定时间间隔（毫秒） | `400` |
| `doubleClickDistance` | 双击判定距离阈值（像素） | `5` |
| `enableKeyboard` | 是否启用键盘记录 | `true` |
| `enableMouse` | 是否启用鼠标截图 | `true` |
| `enableWindowTracking` | 是否启用窗口追踪 | `true` |

---

### 8. 使用方式

#### 8.1 作为 CLI 工具
```bash
# 启动监听
opencapture start

# 停止监听
opencapture stop

# 查看状态
opencapture status
```

#### 8.2 作为 Node.js 模块
```javascript
const autoCapture = require('opencapture');

autoCapture.start({
  storageDir: '~/my-captures/',
  keyClusterInterval: 30
});

// 停止
autoCapture.stop();
```

---

## 隐私与安全提示

> ⚠️ 本工具会记录所有键盘输入，包括密码等敏感信息。
>
> - 请确保存储目录的访问权限
> - 建议定期清理历史数据
> - 请勿在公共或共享设备上使用
> - 仅供个人行为分析、操作回溯等合法用途

---

## 版本记录

| 版本 | 日期 | 说明 |
|-----|------|------|
| 0.1.0 | - | 初始需求定义 |
