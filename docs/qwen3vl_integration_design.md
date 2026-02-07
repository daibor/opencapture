# Qwen3-VL 图片理解集成技术方案

## 一、项目背景

OpenCapture 是一个自动捕捉用户操作行为的工具，能够记录键盘输入和鼠标操作，并在鼠标事件时自动截图。本方案旨在集成 Qwen3-VL 视觉语言模型，实现对截图的自动理解和分析，生成结构化的操作描述。

## 二、技术架构

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      OpenCapture 系统                        │
│                                                              │
│  ┌──────────────┐  触发  ┌──────────────────┐               │
│  │ MouseCapture ├────────→│  ImageAnalyzer   │               │
│  │   (截图)     │         │   (图片分析器)   │               │
│  └──────────────┘         └────────┬────────┘               │
│                                    │                         │
│                           ┌────────▼────────┐                │
│                           │  AnalysisQueue  │                │
│                           │   (分析队列)     │                │
│                           └────────┬────────┘                │
│                                    │                         │
│                           ┌────────▼────────┐                │
│                           │  Qwen3VLClient  │                │
│                           │   (模型客户端)   │                │
│                           └────────┬────────┘                │
└────────────────────────────────────┼─────────────────────────┘
                                     │ HTTP/gRPC
                            ┌────────▼────────┐
                            │   Qwen3-VL API  │
                            │   (本地部署)     │
                            └─────────────────┘
```

### 2.2 数据流程

1. **截图触发**：用户鼠标操作（点击/双击/拖拽）触发截图
2. **图片保存**：截图保存为 WebP 格式
3. **分析入队**：图片路径和上下文信息加入分析队列
4. **异步处理**：后台线程从队列取出任务进行处理
5. **模型调用**：调用本地 Qwen3-VL API 进行图片理解
6. **结果存储**：分析结果保存为 JSONL 格式

## 三、Qwen3-VL 部署方案

### 3.1 方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **Ollama** | 简单易用、管理方便、支持量化 | 需要额外安装 | ⭐⭐⭐⭐⭐ |
| **vLLM** | 性能优秀、批处理能力强 | 配置复杂 | ⭐⭐⭐⭐ |
| **Transformers** | 灵活性高、可定制 | 内存占用大 | ⭐⭐⭐ |
| **LMDeploy** | 推理速度快、支持量化 | 文档较少 | ⭐⭐⭐ |

### 3.2 推荐方案：Ollama 部署

#### 安装步骤

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.ai/install.sh | sh

# 下载 Qwen2-VL 模型（7B 版本）
ollama pull qwen2-vl:7b

# 启动服务
ollama serve
```

#### API 配置

- 默认端口：11434
- API 端点：`http://localhost:11434/api/generate`
- 健康检查：`http://localhost:11434/api/tags`

### 3.3 备选方案：vLLM 部署

```bash
# 安装 vLLM
pip install vllm

# 启动服务
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2-VL-7B-Instruct \
    --port 8000 \
    --gpu-memory-utilization 0.8 \
    --max-model-len 4096
```

## 四、核心模块设计

### 4.1 项目结构

```
opencapture/
├── src/
│   ├── auto_capture.py       # 主模块（需修改）
│   ├── image_analyzer.py     # 新增：图片分析模块
│   ├── qwen_client.py        # 新增：Qwen3-VL 客户端
│   ├── config.py            # 新增：配置管理
│   └── __init__.py
├── config/
│   └── qwen_config.yaml     # 新增：模型配置文件
└── requirements.txt          # 需更新依赖
```

### 4.2 ImageAnalyzer 模块

**功能职责**：
- 管理图片分析队列
- 构建分析提示词
- 调用模型 API
- 保存分析结果

**核心方法**：

```python
class ImageAnalyzer:
    async def analyze_image(image_path: str, context: Dict) -> Dict
    def _build_prompt(context: Dict) -> str
    def _save_analysis(data: Dict) -> None
    async def process_queue() -> None
```

### 4.3 Qwen3VLClient 模块

**功能职责**：
- 封装 Qwen3-VL API 调用
- 处理图片编码
- 解析模型响应
- 错误处理和重试

**核心方法**：

```python
class Qwen3VLClient:
    async def analyze(image_path: str, prompt: str) -> Dict
    async def health_check() -> bool
    def _encode_image(image_path: str) -> str
    def _parse_response(response: str) -> Dict
```

### 4.4 配置管理

```yaml
# config/qwen_config.yaml
qwen:
  api_url: "http://localhost:11434"
  model: "qwen2-vl:7b"
  timeout: 30
  max_retries: 3

analysis:
  enabled: true
  batch_size: 5
  queue_size: 100
  save_raw_response: false

prompts:
  click: "描述用户点击的界面元素和可能的意图"
  drag: "描述拖拽操作的起始和结束位置，分析操作目的"
  dblclick: "描述双击的目标元素，推测打开或激活的内容"
```

## 五、提示词工程

### 5.1 基础提示词模板

```python
PROMPT_TEMPLATE = """请分析这张截图并提供以下信息：

1. **应用识别**
   - 应用程序名称
   - 界面类型（主界面/对话框/菜单等）

2. **操作分析**
   - 用户操作位置：{action_position}
   - 操作类型：{action_type}
   - 被操作的UI元素

3. **内容理解**
   - 界面主要内容
   - 可见的文本信息
   - 重要的视觉元素

4. **意图推测**
   - 用户可能的操作意图
   - 预期的操作结果

请以 JSON 格式返回，包含以下字段：
{{
  "application": "应用名称",
  "interface_type": "界面类型",
  "action_target": "操作目标",
  "content_summary": "内容摘要",
  "user_intent": "用户意图"
}}
"""
```

### 5.2 场景化提示词

```python
SCENE_PROMPTS = {
    "code_editor": "重点分析代码内容、编辑位置、语法高亮",
    "browser": "识别网页内容、链接、表单元素",
    "terminal": "分析命令行输入、输出结果、错误信息",
    "document": "提取文档标题、段落内容、格式信息"
}
```

## 六、数据存储设计

### 6.1 分析结果格式 (JSONL)

```json
{
  "timestamp": "2024-02-03T10:30:45.123456",
  "image_path": "2024-02-03/click_103045_123_left_x800_y600.webp",
  "action": {
    "type": "click",
    "position": {"x": 800, "y": 600},
    "button": "left"
  },
  "window": {
    "title": "Visual Studio Code",
    "application": "com.microsoft.VSCode"
  },
  "analysis": {
    "application": "Visual Studio Code",
    "interface_type": "代码编辑器",
    "action_target": "函数定义",
    "content_summary": "Python代码文件，包含类定义和方法实现",
    "user_intent": "查看或修改函数实现",
    "extracted_text": ["def analyze_image", "async def", "return Dict"],
    "confidence": 0.92
  },
  "model_info": {
    "name": "qwen2-vl:7b",
    "inference_time": 1.23
  }
}
```

### 6.2 存储结构

```
~/opencapture/
├── 2024-02-03/
│   ├── keys.log               # 键盘日志
│   ├── images/                # 截图文件
│   │   ├── click_*.webp
│   │   └── drag_*.webp
│   ├── analysis.jsonl         # 分析结果
│   └── summary.json          # 每日汇总
```

## 七、性能优化策略

### 7.1 异步处理

- 使用 asyncio 进行异步 I/O
- 分析任务与截图操作解耦
- 队列缓冲，避免阻塞主线程

### 7.2 批处理

```python
async def batch_analyze(self, images: List[str], batch_size: int = 5):
    """批量分析图片，提高吞吐量"""
    batches = [images[i:i+batch_size] for i in range(0, len(images), batch_size)]
    results = await asyncio.gather(*[
        self._process_batch(batch) for batch in batches
    ])
    return results
```

### 7.3 缓存策略

- 相似图片检测（使用 imagehash）
- 结果缓存（Redis/内存）
- 提示词模板缓存

### 7.4 资源管理

```python
# 限制并发数
SEMAPHORE = asyncio.Semaphore(3)

async def analyze_with_limit(self, image_path):
    async with SEMAPHORE:
        return await self.analyze_image(image_path)
```

## 八、错误处理

### 8.1 错误类型

| 错误类型 | 处理策略 | 重试次数 |
|---------|---------|---------|
| 网络超时 | 指数退避重试 | 3次 |
| 模型过载 | 队列缓存，延迟处理 | 5次 |
| 图片损坏 | 记录错误，跳过 | 0次 |
| API异常 | 降级到基础描述 | 2次 |

### 8.2 降级策略

```python
async def analyze_with_fallback(self, image_path):
    try:
        # 尝试使用 Qwen3-VL
        return await self.qwen_client.analyze(image_path)
    except ModelUnavailableError:
        # 降级到 OCR + 规则
        return await self.ocr_fallback(image_path)
    except Exception as e:
        # 最终降级：仅保存元数据
        return self.metadata_only(image_path)
```

## 九、监控和日志

### 9.1 性能指标

```python
METRICS = {
    "analysis_count": 0,
    "success_rate": 0.0,
    "avg_inference_time": 0.0,
    "queue_length": 0,
    "error_count": 0
}
```

### 9.2 日志级别

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('qwen_analysis.log'),
        logging.StreamHandler()
    ]
)
```

## 十、实施计划

### 第一阶段：基础集成（1周）
1. 部署 Qwen3-VL 本地服务
2. 实现 Qwen3VLClient 基础功能
3. 完成 ImageAnalyzer 核心逻辑
4. 修改 MouseCapture 集成接口

### 第二阶段：功能完善（1周）
1. 优化提示词模板
2. 实现批处理和队列管理
3. 添加错误处理和重试机制
4. 完善日志和监控

### 第三阶段：性能优化（3天）
1. 实现缓存机制
2. 优化并发处理
3. 添加相似图片检测
4. 性能测试和调优

### 第四阶段：高级功能（可选）
1. 多模型支持（GPT-4V、Claude等）
2. 实时分析展示界面
3. 行为模式识别
4. 自动生成操作文档

## 十一、测试方案

### 11.1 单元测试

```python
# test_qwen_client.py
async def test_analyze_image():
    client = Qwen3VLClient()
    result = await client.analyze("test_image.png", "描述图片")
    assert "application" in result
    assert result["confidence"] > 0.5
```

### 11.2 集成测试

- 模拟鼠标操作触发截图
- 验证分析结果保存
- 测试错误恢复机制
- 性能压力测试

### 11.3 测试用例

| 场景 | 输入 | 预期结果 |
|------|------|---------|
| 代码编辑器点击 | IDE截图+点击位置 | 识别代码元素 |
| 浏览器拖拽 | 网页截图+拖拽轨迹 | 识别选择文本 |
| 文档双击 | 文档截图+双击位置 | 识别打开操作 |

## 十二、安全和隐私

### 12.1 数据安全

- 所有数据本地处理，不上传云端
- 敏感信息自动脱敏
- 加密存储选项

### 12.2 隐私保护

```python
PRIVACY_FILTERS = [
    r"password|pwd|secret",  # 密码相关
    r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}",  # 信用卡
    r"\d{3}-\d{2}-\d{4}",  # SSN
]
```

## 十三、配置示例

### 13.1 最小配置

```python
# config.py
QWEN_CONFIG = {
    "enabled": True,
    "api_url": "http://localhost:11434",
    "model": "qwen2-vl:7b"
}
```

### 13.2 完整配置

```python
# config.py
QWEN_CONFIG = {
    "enabled": True,
    "api_url": "http://localhost:11434",
    "model": "qwen2-vl:7b",
    "timeout": 30,
    "max_retries": 3,
    "batch_size": 5,
    "queue_size": 100,
    "cache_enabled": True,
    "cache_ttl": 3600,
    "save_raw_response": False,
    "privacy_mode": True,
    "log_level": "INFO"
}
```

## 十四、总结

本方案提供了一个完整的 Qwen3-VL 集成解决方案，主要特点：

1. **无侵入集成**：最小化修改现有代码
2. **异步处理**：不影响原有截图性能
3. **灵活部署**：支持多种部署方式
4. **可扩展性**：预留多模型支持接口
5. **隐私保护**：本地处理，数据安全

通过该方案，OpenCapture 将从简单的行为记录工具升级为智能的操作理解系统，为后续的行为分析、操作回放、文档生成等高级功能奠定基础。

## 附录：相关资源

- [Qwen2-VL GitHub](https://github.com/QwenLM/Qwen2-VL)
- [Ollama 文档](https://ollama.ai/docs)
- [vLLM 文档](https://docs.vllm.ai/)
- [OpenCapture 项目](https://github.com/yourusername/opencapture)