# OpenCapture 代码审查：流程分析与问题清单

## 一、整体流程

### 1. 入口 (`run.py`)

```
python run.py          →  run_capture()   → 采集模式
python run.py --analyze →  run_analyze()  → 分析模式
```

`main()` 通过 argparse 判断运行模式。无 `--analyze/--image/--audio` 等参数时进入采集模式，否则进入分析模式（asyncio）。

### 2. 采集模式流程

```
AutoCapture.run()
  │
  ├─ _check_accessibility()     # 检查 macOS 辅助功能权限，无权限则弹框等待
  │
  ├─ start()
  │   ├─ WindowTracker.start()  # 注册 NSWorkspace 通知，监听应用切换
  │   ├─ keyboard.Listener      # pynput 键盘监听，回调 → KeyLogger.on_key_press()
  │   ├─ mouse.Listener         # pynput 鼠标监听，回调 → MouseCapture.on_click()
  │   └─ MicrophoneCapture.start()  # (可选) Core Audio 麦克风监听
  │
  └─ NSRunLoop 主循环            # 每 0.1s 运转一次，分发 macOS 通知
      └─ Ctrl+C / SIGTERM → stop()
```

#### 2.1 鼠标截图流程

```
on_click(x, y, button, pressed)
  │
  ├─ pressed=True  → 记录按下坐标、时间
  │
  └─ pressed=False → 判断行为类型
      │
      ├─ 距离 > 10px        → drag（拖拽）
      ├─ 400ms 内近距重复点击 → dblclick（双击）
      └─ 其他               → click（单击）
      │
      ├─ _get_window_at_point(x,y)  # 通过 CGWindowList 确定点击目标窗口
      │
      └─ 启动新线程 → _capture_and_save()
          ├─ _get_active_window_bounds()     # 获取活跃窗口边框
          ├─ mss.grab(monitors[0])            # 截取全部屏幕
          ├─ 绘制蓝色窗口边框
          ├─ (拖拽) 绘制半透明灰色选区
          ├─ 保存 WebP 文件 (质量=80)
          └─ key_logger.log_screenshot()      # 写入日志
```

文件命名：`{action}_{HHmmss}_{ms}_{button}_x{X}_y{Y}.webp`

#### 2.2 键盘记录流程

```
on_key_press(key)
  │
  ├─ 映射按键 → 字符（特殊键用 macOS 符号如 ⌘⇧⌥）
  │
  ├─ 加锁
  │   ├─ _update_window_state()    # 每次按键都查询当前窗口（⚠️ 性能问题）
  │   ├─ 窗口切换 或 超过20s      → _flush_line()  # 写入上一行
  │   └─ 追加字符到 current_line
  │
  └─ 写入格式：[HH:MM:SS] ⌨️ {按键内容}
```

日志按应用分组，窗口切换时写入窗口头（三个换行分隔）：
```
[2026-02-08 14:30:00] Chrome | GitHub (com.google.Chrome)
[14:30:05] ⌨️ git commit -m "fix bug"
[14:30:15] 📷 click (500,300) click_143015_123_left_x500_y300.webp
```

#### 2.3 窗口追踪流程

```
WindowTracker.start()
  ├─ 获取初始窗口信息
  ├─ 注册 NSWorkspaceDidActivateApplicationNotification
  └─ 通知回调 → _handle_app_activation()
      └─ KeyLogger.on_window_activated()
          ├─ 刷新旧应用的键盘缓冲
          └─ 写入新应用的窗口头
```

#### 2.4 麦克风监听流程

```
MicrophoneCapture.start()
  └─ 启动 monitor 线程
      ├─ 注册 3 层 Core Audio 属性监听器
      │   ├─ 设备运行状态 (kAudioDevicePropertyDeviceIsRunningSomewhere)
      │   ├─ 系统进程列表 (kAudioHardwarePropertyProcessObjectList)
      │   └─ 每进程输入状态 (kAudioProcessPropertyIsRunningInput)
      │
      ├─ CFRunLoop 主循环（分发回调）
      └─ 每 2s 轮询兜底
```

录制触发逻辑：
```
外部应用使用麦克风
  → _on_device_running_changed() / _on_process_input_changed()
  → _try_start_recording()
      ├─ _get_mic_clients()          # 查找使用麦克风的外部进程
      ├─ sounddevice.RawInputStream  # 开始录音
      └─ _audio_writer 线程          # 队列写入 WAV

所有外部客户端离开
  → _schedule_stop()                 # 防抖 (默认 300ms)
  → _stop_recording()
      ├─ 停止音频流
      ├─ 关闭 WAV 文件
      ├─ 短于 min_duration → 删除
      └─ 重命名为 mic_HHmmss_ms_app_durN.wav
```

### 3. 分析模式流程

```
run_analyze()
  └─ Analyzer(config)
      ├─ LLMRouter     # 管理多个 LLM 客户端
      ├─ ReportGenerator
      └─ ReportAggregator

analyze_day(date_str)
  ├─ preflight_check()              # 检查 LLM 服务可用性
  ├─ analyze_images_batch()         # 批量分析截图 → 每张生成 .txt
  ├─ analyze_audios_batch()         # 批量转录音频 → 每个生成 .txt
  └─ generate_reports_for_date()
      ├─ parse_log_file()           # 解析日志 → KeyboardSession 列表
      ├─ load_image_analyses()      # 加载 .txt 分析结果
      ├─ generate_daily_summary()   # LLM 生成日报摘要
      ├─ generate_daily_report()    # 生成 YYYY-MM-DD.md
      └─ generate_images_report()   # 生成 YYYY-MM-DD_images.md
```

---

## 二、问题清单

### P0 — 严重问题（可能导致崩溃或数据丢失）— 已修复

#### 1. mss 截图实例非线程安全

**位置**: `src/opencapture/auto_capture.py`

`MouseCapture.__init__` 中创建了一个 `self._sct = mss.mss()` 实例，但 `_capture_and_save()` 在独立线程中运行。快速连续点击时，多个线程会同时调用 `self._sct.grab()`，而 mss 不是线程安全的，可能导致截图损坏或段错误。

**建议**: 在每个线程中创建独立的 `mss.mss()` 实例，或用锁保护 `grab()` 调用。

#### 2. aiohttp Session 泄漏

**位置**: `src/opencapture/llm_client.py` 全文

`BaseLLMClient` 实现了 `__aenter__`/`__aexit__` 用于关闭 session，但 `LLMRouter._init_clients()` 直接实例化客户端，不通过 context manager。同样 `ASRClient` 也有此问题。分析完成后 session 不会被关闭，导致连接泄漏和 `ResourceWarning`。

**建议**: 在 `LLMRouter` 上实现 `close()` 方法，在分析结束后关闭所有客户端 session。

#### 3. ASRClient 文件句柄泄漏

**位置**: `src/opencapture/llm_client.py`

```python
data.add_field("file", open(audio_path, "rb"), ...)
```

文件以 `open()` 直接传入 `FormData`，但没有在 finally 中关闭。如果请求异常，文件句柄会泄漏。

**建议**: 用 `with open(...)` 或在 finally 中显式关闭。

#### 4. 双击产生冗余截图

**位置**: `src/opencapture/auto_capture.py`

双击检测发生在第二次释放时，但第一次释放已经触发了一次 click 截图。结果是每次双击会产生两张截图（一张 click + 一张 dblclick），浪费存储并导致日志有误导性记录。

**建议**: 延迟第一次点击的截图（等待双击判定窗口过期后再触发），或在检测到双击时取消/删除第一次的 click 截图。

### P1 — 中等问题（性能或正确性隐患）

#### 5. 每次按键都查询窗口状态

**位置**: `src/opencapture/auto_capture.py`

```python
def on_key_press(self, key):
    ...
    with self._lock:
        self._update_window_state()  # 每次按键都调用
```

`_update_window_state()` 通过 `NSWorkspace.frontmostApplication()` 和 `AXUIElement` API 查询窗口信息。这些是 IPC 调用，每次几毫秒。高速打字时（>10次/秒）会造成不必要的开销。而且 `WindowTracker` 已经通过通知机制维护了窗口状态。

**建议**: 删除 `on_key_press` 中的 `_update_window_state()` 调用，完全依赖 `WindowTracker` 推送的窗口状态。

#### 6. 窗口信息查询逻辑重复

**位置**: `src/opencapture/auto_capture.py`（WindowTracker 和 KeyLogger 两处）

`WindowTracker._get_window_title()` 和 `KeyLogger._get_window_title()` 是完全相同的两套实现。`_get_active_window_info()` 也在两个类中重复。

**建议**: 提取为公共函数，或让 KeyLogger 完全依赖 WindowTracker 的数据。

#### 7. 全屏截图在多显示器下效率低

**位置**: `src/opencapture/auto_capture.py`

```python
monitor = self._sct.monitors[0]  # monitors[0] 是所有显示器的合并区域
screenshot = self._sct.grab(monitor)
```

多显示器环境下，每次截图都抓取全部屏幕的拼接图像，即使用户只在一个屏幕上操作。对于双 4K 显示器，单张截图原始数据约 64MB。

**建议**: 根据点击坐标判断所在显示器，只截取该显示器。

#### 8. 线程列表无上限增长

**位置**: `src/opencapture/auto_capture.py`

```python
thread.start()
self._active_threads.append(thread)
# 清理已完成的线程
self._active_threads = [t for t in self._active_threads if t.is_alive()]
```

清理只在新点击时触发。如果用户疯狂点击后停止，列表中可能积累大量已完成但未清理的 Thread 对象。

**建议**: 使用线程池（`concurrent.futures.ThreadPoolExecutor`），或定期清理。

#### 9. MicrophoneCapture 防抖存在竞态

**位置**: `src/opencapture/mic_capture.py`

```python
def _schedule_stop(self):
    self._cancel_timer("stop")      # 取消旧 timer（加锁）
    with self._lock:                 # 重新加锁创建新 timer
        self._stop_timer = threading.Timer(...)
```

`_cancel_timer` 和创建新 timer 之间有短暂的无锁窗口，Core Audio 回调可能在此期间触发，导致意外行为。

**建议**: 将取消和创建放在同一个锁作用域内。

### P2 — 值得关注的问题

#### 10. 密码输入无过滤

键盘记录器对所有输入一视同仁，包括密码字段。虽然这在某些使用场景下是有意为之，但如果用户不注意，敏感信息（密码、token）会被明文记录在日志中。

**建议**: 至少在文档中明确提示这一风险。可考虑检测密码输入框（通过 Accessibility API 的 `AXRoleDescription` 属性）并自动屏蔽。

#### 11. 无磁盘空间管理

程序持续写入截图（每张约 50-200KB）和日志，无任何清理机制。按每天 500 次点击估算，每天约 50-100MB，一个月就是 1.5-3GB。

**建议**: 增加配置项：最大保留天数 / 最大存储空间，定期清理旧数据。

#### 12. Linux 支持不完整

**位置**: `src/opencapture/auto_capture.py`

~~`auto_capture.py` 在模块顶部无条件导入 macOS 专用模块。~~

**已修复**: 重构后已改为 `if sys.platform == "darwin"` 条件导入。`mic_capture.py` 也加入了平台检查。

#### 13. Ollama 模型名匹配过于严格

**位置**: `src/opencapture/llm_client.py`

```python
if self.model in models:
```

Ollama 列出的模型名可能带有版本标签（如 `qwen2-vl:7b` vs `qwen2-vl:latest`）。严格字符串匹配可能导致 health check 误报失败。

**建议**: 用前缀匹配或同时检查不带标签的名称。

#### 14. Config 路径展开不完整

**位置**: `src/opencapture/config.py`

`_expand_all()` 只展开了 `capture.output_dir`。如果用户在其他路径配置项中使用 `~`（如 `logging.file`），不会被展开。

#### 15. 日志编码兼容性

日志中使用了 emoji 字符（⌨️📷🎤）和 macOS 键盘符号（⌘⇧⌥⌃），在某些终端或日志分析工具中可能显示异常。`report_generator.py` 中的解析也依赖这些 emoji 来识别行类型。

#### 16. 窗口头写入可能丢失标题

**位置**: `src/opencapture/auto_capture.py`

`_ensure_app_header()` 只比较应用名（`_current_app_name != _last_header_app`）。如果用户在同一应用的不同窗口间切换（如 Chrome 的两个 tab），不会写入新的窗口头，日志中的窗口标题信息不准确。

**建议**: 同时比较窗口标题。

#### 17. ~~install.sh 配置文件目标路径不一致~~

**已移除**: `install.sh` 已在重构中删除。现在通过 `pip install opencapture` 安装，配置文件示例打包在 `src/opencapture/config/example.yaml` 中。

---

## 三、架构总结

### 做得好的部分

- **事件驱动的麦克风监听**: 三层 Core Audio 监听器 + 轮询兜底，设计周全
- **线程安全意识**: KeyLogger 的所有日志写入都通过 `_lock` 保护
- **隐私保护设计**: `privacy.allow_online` 默认关闭，远程分析需要显式确认
- **窗口归属准确性**: 鼠标点击时通过坐标查 CGWindowList 确定目标窗口，而非简单取前台应用
- **安装体验**: 三种分发方式（pip install / clone+run.py / PyInstaller .app），LaunchAgent 自启动

### 需要改进的部分

- **线程模型**: 每次截图开新线程，不如用线程池；mss 的线程安全问题需要解决
- **重复代码**: WindowTracker 和 KeyLogger 中的窗口查询逻辑完全重复
- **平台抽象缺失**: macOS API 调用散落在各处，无法扩展到其他平台
- **资源生命周期**: aiohttp session、文件句柄的关闭不够严谨
- **可观测性**: 缺少结构化日志，全靠 print 输出，难以排查线上问题
