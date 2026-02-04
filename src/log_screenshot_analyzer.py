#!/usr/bin/env python3
"""
日志和截图综合分析器
使用 Ollama + Qwen3-VL 在本地分析日志和截图内容
优化用于 16GB 内存环境
"""

import asyncio
import aiohttp
import base64
import json
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: datetime
    window_title: str
    window_app: str
    content: str
    screenshots: List[str] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class AnalysisResult:
    """分析结果"""
    timestamp: str
    window_title: str
    window_app: str
    log_content: str
    screenshots: List[str]
    analysis: Dict[str, Any]
    inference_time: float


class LogScreenshotAnalyzer:
    """日志和截图综合分析器"""

    def __init__(
        self,
        api_url: str = "http://localhost:11434",
        model: str = "qwen3-vl:4b",  # 适合 16GB 内存
        timeout: int = 120,
        max_retries: int = 3
    ):
        """
        初始化分析器

        Args:
            api_url: Ollama API 地址
            model: 模型名称 (qwen3-vl:4b 约 3.3GB，适合 16GB 内存)
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self.api_url = api_url
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def health_check(self) -> bool:
        """检查 Ollama 服务和模型是否可用"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(
                f"{self.api_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    models = [m.get("name") for m in data.get("models", [])]

                    if self.model in models:
                        logger.info(f"✅ Ollama 服务正常，模型 {self.model} 已加载")
                        return True
                    else:
                        logger.warning(f"⚠️ 模型 {self.model} 未找到")
                        logger.info(f"可用模型: {models}")
                        return False
        except Exception as e:
            logger.error(f"❌ 健康检查失败: {e}")
            return False

    def parse_log_file(self, log_path: Path) -> List[LogEntry]:
        """
        解析日志文件

        Args:
            log_path: 日志文件路径

        Returns:
            List[LogEntry]: 日志条目列表
        """
        if not log_path.exists():
            logger.error(f"日志文件不存在: {log_path}")
            return []

        entries = []

        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 按窗口块分割（三个换行符）
        blocks = content.split("\n\n\n")

        for block in blocks:
            if not block.strip():
                continue

            lines = block.strip().split("\n")
            if not lines:
                continue

            # 尝试两种格式：
            # 格式1: [2026-02-01 10:23:40] Visual Studio Code | index.ts (com.microsoft.VSCode)
            # 格式2: [2026-02-01 10:23:40] App Name (bundle.id)
            # 格式3: [2026-02-01 10:23:40] 纯文本内容

            entry = None

            for line in lines:
                # 尝试解析窗口标题行 (带竖线格式)
                header_match = re.match(
                    r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.+?) \| (.+?) \((.+?)\)',
                    line
                )
                if header_match:
                    timestamp_str, app_name, title, bundle_id = header_match.groups()
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    entry = LogEntry(
                        timestamp=timestamp,
                        window_title=title,
                        window_app=f"{app_name} ({bundle_id})",
                        content="",
                        screenshots=[],
                        raw_text=block
                    )
                    continue

                # 尝试解析窗口标题行 (简单格式)
                simple_header = re.match(
                    r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.+?) \((.+?)\)',
                    line
                )
                if simple_header:
                    timestamp_str, app_name, bundle_id = simple_header.groups()
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    entry = LogEntry(
                        timestamp=timestamp,
                        window_title=app_name,
                        window_app=bundle_id,
                        content="",
                        screenshots=[],
                        raw_text=block
                    )
                    continue

                # 尝试解析带文本内容的窗口标题行
                content_header = re.match(
                    r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.+)',
                    line
                )
                if content_header and not line.startswith('[') or (content_header and '(' not in line):
                    if entry is None:
                        timestamp_str, content_text = content_header.groups()
                        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                        entry = LogEntry(
                            timestamp=timestamp,
                            window_title="未知",
                            window_app="未知",
                            content=content_text,
                            screenshots=[],
                            raw_text=block
                        )
                    else:
                        entry.content += "\n" + content_header.group(2)
                    continue

                # 解析截图记录
                screenshot_match = re.search(r'📷 \w+ \([^)]+\) (.+\.webp)', line)
                if screenshot_match:
                    if entry:
                        entry.screenshots.append(screenshot_match.group(1))
                    continue

                # 解析时间戳行内容
                time_content = re.match(r'\[(\d{2}:\d{2}:\d{2})\] (.+)', line)
                if time_content:
                    if entry:
                        content = time_content.group(2)
                        if not content.startswith('📷'):
                            entry.content += "\n" + content
                    continue

                # 其他内容
                if entry and line.strip():
                    entry.content += "\n" + line

            if entry:
                entry.content = entry.content.strip()
                entries.append(entry)

        logger.info(f"解析了 {len(entries)} 个日志条目")
        return entries

    def _encode_image(self, image_path: str) -> Optional[str]:
        """将图片编码为 base64"""
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"图片编码失败 {image_path}: {e}")
            return None

    def _parse_mouse_info(self, image_path: str) -> Dict[str, Any]:
        """
        从文件名解析鼠标操作信息

        文件名格式: action_HHmmss_ms_button_x<X>_y<Y>.webp
        """
        filename = Path(image_path).stem
        info = {"action": "unknown", "x": None, "y": None, "button": "left"}

        # 解析操作类型
        if filename.startswith("click_"):
            info["action"] = "click"
        elif filename.startswith("dblclick_"):
            info["action"] = "double_click"
        elif filename.startswith("drag_"):
            info["action"] = "drag"

        # 解析坐标
        x_match = re.search(r'_x(-?\d+)', filename)
        y_match = re.search(r'_y(-?\d+)', filename)
        if x_match:
            info["x"] = int(x_match.group(1))
        if y_match:
            info["y"] = int(y_match.group(1))

        # 解析按键
        if "_right_" in filename:
            info["button"] = "right"

        return info

    def _build_prompt(
        self,
        log_entry: Optional[LogEntry],
        analysis_type: str = "comprehensive",
        mouse_info: Optional[Dict] = None
    ) -> str:
        """
        构建分析提示词

        Args:
            log_entry: 日志条目（可为 None）
            analysis_type: 分析类型
            mouse_info: 鼠标操作信息

        Returns:
            str: 提示词
        """
        # 构建鼠标位置描述
        mouse_desc = ""
        if mouse_info and mouse_info.get("x") is not None:
            action_map = {
                "click": "单击",
                "double_click": "双击",
                "drag": "拖拽",
                "unknown": "点击"
            }
            action = action_map.get(mouse_info.get("action", "unknown"), "点击")
            button = "右键" if mouse_info.get("button") == "right" else "左键"
            x, y = mouse_info.get("x"), mouse_info.get("y")
            mouse_desc = f"\n\n**鼠标操作**: 用户在屏幕坐标 ({x}, {y}) 处进行了{button}{action}操作。请特别关注该位置附近的 UI 元素。"

        # 纯截图分析（带鼠标位置）
        if analysis_type == "screenshot_only" or log_entry is None:
            return f"""分析这张屏幕截图，用中文详细描述。{mouse_desc}

请描述：
1. 屏幕上有哪些应用窗口（如终端、浏览器、编辑器、聊天软件等）
2. 每个窗口显示的具体内容（代码、网页、聊天记录、文件名等）
3. 根据鼠标点击位置，用户正在操作什么、想要做什么

直接输出描述文字，不要用 JSON 格式。"""

        # 纯日志分析
        if analysis_type == "log_only":
            return f"""请分析以下用户输入记录：

## 上下文
- 窗口: {log_entry.window_title}
- 应用: {log_entry.window_app}

## 输入内容
```
{log_entry.content}
```

请分析用户正在做什么，以简洁的 JSON 格式返回：
{{
  "activity": "用户活动描述",
  "purpose": "操作目的",
  "commands": ["识别到的命令或快捷键"]
}}"""

        # 综合分析（有日志和截图）
        return f"""请分析以下用户活动记录和对应的截图。{mouse_desc}

## 上下文信息
- 窗口: {log_entry.window_title}
- 应用: {log_entry.window_app}
- 时间: {log_entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")}

## 用户输入记录
```
{log_entry.content}
```

请根据截图和日志内容，分析：
1. 用户正在做什么任务
2. 当前界面显示的主要内容
3. 用户的操作意图
4. 可能的下一步操作

以简洁的 JSON 格式返回：
{{
  "task": "用户当前任务描述",
  "interface": "界面内容描述",
  "intent": "用户意图",
  "next_action": "可能的下一步"
}}"""

    async def analyze_with_images(
        self,
        prompt: str,
        image_paths: List[str],
        temperature: float = 0.3,  # 低温度更稳定
        max_tokens: int = 2048  # 输出 token 数
    ) -> Dict[str, Any]:
        """
        使用图片进行分析

        Args:
            prompt: 提示词
            image_paths: 图片路径列表
            temperature: 温度参数
            max_tokens: 最大输出 token 数

        Returns:
            Dict: 分析结果
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        # 编码图片
        images = []
        for path in image_paths:
            encoded = self._encode_image(path)
            if encoded:
                images.append(encoded)

        # 构建请求
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": images if images else None,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 4096,  # 上下文窗口大小，适合 16GB 内存
            }
        }

        # 如果没有图片，移除 images 字段
        if not images:
            del payload["images"]

        start_time = datetime.now()

        for attempt in range(self.max_retries):
            try:
                async with self.session.post(
                    f"{self.api_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        response_text = result.get("response", "")

                        # 尝试解析 JSON
                        parsed = self._parse_json_response(response_text)

                        inference_time = (datetime.now() - start_time).total_seconds()

                        return {
                            "success": True,
                            "analysis": parsed,
                            "raw_response": response_text,
                            "inference_time": inference_time,
                            "model": self.model
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"API 错误 {response.status}: {error_text}")

            except asyncio.TimeoutError:
                logger.warning(f"请求超时 (尝试 {attempt + 1}/{self.max_retries})")
            except Exception as e:
                logger.error(f"请求失败: {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        return {
            "success": False,
            "error": "达到最大重试次数",
            "inference_time": (datetime.now() - start_time).total_seconds()
        }

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """解析模型返回的 JSON"""
        # 清理 markdown 代码块
        response = re.sub(r'```json\s*', '', response)
        response = re.sub(r'```\s*', '', response)

        # 尝试提取 JSON
        try:
            # 查找 JSON 对象
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        # 返回原始响应
        return {"raw_response": response}

    async def analyze_log_entry(
        self,
        log_entry: LogEntry,
        log_dir: Path
    ) -> AnalysisResult:
        """
        分析单个日志条目

        Args:
            log_entry: 日志条目
            log_dir: 日志所在目录

        Returns:
            AnalysisResult: 分析结果
        """
        # 获取截图完整路径
        image_paths = []
        for screenshot in log_entry.screenshots[:2]:  # 限制最多 2 张图片节省内存
            full_path = log_dir / screenshot
            if full_path.exists():
                image_paths.append(str(full_path))

        # 根据有无截图选择分析类型
        if image_paths:
            analysis_type = "comprehensive"
        elif log_entry.content.strip():
            analysis_type = "log_only"
        else:
            return AnalysisResult(
                timestamp=log_entry.timestamp.isoformat(),
                window_title=log_entry.window_title,
                window_app=log_entry.window_app,
                log_content=log_entry.content,
                screenshots=log_entry.screenshots,
                analysis={"note": "无内容可分析"},
                inference_time=0
            )

        prompt = self._build_prompt(log_entry, analysis_type)
        result = await self.analyze_with_images(prompt, image_paths)

        return AnalysisResult(
            timestamp=log_entry.timestamp.isoformat(),
            window_title=log_entry.window_title,
            window_app=log_entry.window_app,
            log_content=log_entry.content,
            screenshots=log_entry.screenshots,
            analysis=result.get("analysis", {}),
            inference_time=result.get("inference_time", 0)
        )

    async def analyze_screenshot(
        self,
        image_path: str,
        context: Optional[Dict] = None,
        save_txt: bool = False
    ) -> Dict[str, Any]:
        """
        分析单张截图

        Args:
            image_path: 截图路径
            context: 可选的上下文信息
            save_txt: 是否保存描述到同名 txt 文件

        Returns:
            Dict: 分析结果
        """
        if not Path(image_path).exists():
            return {"error": f"图片不存在: {image_path}"}

        # 解析鼠标操作信息
        mouse_info = self._parse_mouse_info(image_path)

        if context:
            log_entry = LogEntry(
                timestamp=datetime.now(),
                window_title=context.get("window_title", "未知"),
                window_app=context.get("window_app", "未知"),
                content=context.get("content", ""),
                screenshots=[image_path]
            )
            prompt = self._build_prompt(log_entry, "comprehensive", mouse_info)
        else:
            prompt = self._build_prompt(None, "screenshot_only", mouse_info)

        result = await self.analyze_with_images(prompt, [image_path])

        # 保存描述到同名 txt 文件
        if save_txt and result.get("success"):
            self._save_description_txt(image_path, result)

        return result

    def _save_description_txt(self, image_path: str, result: Dict):
        """
        保存描述到同名 txt 文件

        Args:
            image_path: 图片路径
            result: 完整的分析结果
        """
        txt_path = Path(image_path).with_suffix(".txt")

        # 优先使用 raw_response（纯文本描述）
        description = ""

        if "raw_response" in result:
            description = result["raw_response"]
        elif "analysis" in result:
            analysis = result["analysis"]
            # 如果是 JSON 格式的分析结果，提取关键信息
            description_parts = []
            if "content" in analysis:
                description_parts.append(analysis["content"])
            if "interface_type" in analysis:
                description_parts.append(f"界面类型: {analysis['interface_type']}")
            if "activity" in analysis:
                description_parts.append(f"用户活动: {analysis['activity']}")
            if "task" in analysis:
                description_parts.append(f"任务: {analysis['task']}")
            if "interface" in analysis:
                description_parts.append(f"界面: {analysis['interface']}")
            if "intent" in analysis:
                description_parts.append(f"意图: {analysis['intent']}")
            if "raw_response" in analysis:
                description_parts.append(analysis["raw_response"])
            description = "\n".join(description_parts) if description_parts else str(analysis)

        if not description:
            description = str(result)

        try:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(description.strip())
            logger.info(f"已保存: {txt_path.name}")
        except Exception as e:
            logger.error(f"保存 txt 失败: {e}")

    async def analyze_images_batch(
        self,
        image_dir: Path,
        limit: Optional[int] = None,
        skip_existing: bool = True
    ) -> int:
        """
        批量分析目录中的图片，每张图片生成同名 txt 文件

        Args:
            image_dir: 图片目录
            limit: 限制分析数量
            skip_existing: 是否跳过已有 txt 的图片

        Returns:
            int: 成功分析的数量
        """
        # 查找所有图片
        image_files = list(image_dir.glob("*.webp")) + list(image_dir.glob("*.png"))

        if skip_existing:
            # 过滤掉已有 txt 的图片
            image_files = [
                f for f in image_files
                if not f.with_suffix(".txt").exists()
            ]

        if limit:
            image_files = image_files[:limit]

        if not image_files:
            logger.info("没有需要分析的图片")
            return 0

        logger.info(f"开始分析 {len(image_files)} 张图片...")

        success_count = 0
        for i, image_file in enumerate(image_files):
            logger.info(f"[{i+1}/{len(image_files)}] {image_file.name}")

            result = await self.analyze_screenshot(
                str(image_file),
                save_txt=True
            )

            if result.get("success"):
                success_count += 1

            # 短暂休息避免内存压力
            await asyncio.sleep(0.5)

        logger.info(f"完成！成功: {success_count}/{len(image_files)}")
        return success_count

    async def analyze_day(
        self,
        date_dir: Path,
        limit: Optional[int] = None,
        save_results: bool = True
    ) -> List[AnalysisResult]:
        """
        分析某一天的所有日志和截图

        Args:
            date_dir: 日期目录
            limit: 限制分析条目数
            save_results: 是否保存结果

        Returns:
            List[AnalysisResult]: 分析结果列表
        """
        # 查找日志文件
        log_files = list(date_dir.glob("*.log"))
        if not log_files:
            logger.warning(f"未找到日志文件: {date_dir}")
            return []

        results = []
        total_time = 0

        for log_file in log_files:
            entries = self.parse_log_file(log_file)

            if limit:
                entries = entries[:limit]

            logger.info(f"开始分析 {len(entries)} 个条目...")

            for i, entry in enumerate(entries):
                logger.info(f"[{i+1}/{len(entries)}] 分析: {entry.window_title}")

                result = await self.analyze_log_entry(entry, date_dir)
                results.append(result)
                total_time += result.inference_time

                logger.info(f"  ✓ 耗时: {result.inference_time:.2f}s")

                # 每次分析后短暂休息，避免内存压力
                await asyncio.sleep(0.5)

        # 保存结果
        if save_results and results:
            output_file = date_dir / "ai_analysis.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(
                    [
                        {
                            "timestamp": r.timestamp,
                            "window_title": r.window_title,
                            "window_app": r.window_app,
                            "log_content": r.log_content,
                            "screenshots": r.screenshots,
                            "analysis": r.analysis,
                            "inference_time": r.inference_time
                        }
                        for r in results
                    ],
                    f,
                    indent=2,
                    ensure_ascii=False
                )
            logger.info(f"结果已保存: {output_file}")

        logger.info(f"\n分析完成！共 {len(results)} 条，总耗时: {total_time:.2f}s")
        return results


async def main():
    """主函数 - 示例用法"""
    import argparse

    parser = argparse.ArgumentParser(
        description="日志和截图综合分析器 (Qwen3-VL)"
    )
    parser.add_argument(
        "-d", "--dir",
        default="~/auto-capture",
        help="数据目录 (默认: ~/auto-capture)"
    )
    parser.add_argument(
        "--date",
        help="分析指定日期 (格式: YYYY-MM-DD，默认: today)"
    )
    parser.add_argument(
        "--image",
        help="分析单张截图"
    )
    parser.add_argument(
        "--images",
        action="store_true",
        help="批量分析图片，每张生成同名 txt 文件"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="限制分析条目数"
    )
    parser.add_argument(
        "--model",
        default="qwen3-vl:4b",
        help="模型名称 (默认: qwen3-vl:4b)"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:11434",
        help="Ollama API 地址"
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="不跳过已有 txt 的图片"
    )

    args = parser.parse_args()

    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("日志和截图综合分析器")
    print(f"模型: {args.model}")
    print(f"API: {args.api_url}")
    print("=" * 60)

    async with LogScreenshotAnalyzer(
        api_url=args.api_url,
        model=args.model
    ) as analyzer:
        # 健康检查
        if not await analyzer.health_check():
            print("\n请确保 Ollama 正在运行且模型已加载:")
            print(f"  ollama serve")
            print(f"  ollama pull {args.model}")
            return

        # 分析单张图片
        if args.image:
            print(f"\n分析截图: {args.image}")
            result = await analyzer.analyze_screenshot(args.image, save_txt=True)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return

        # 确定目录
        data_dir = Path(args.dir).expanduser()

        if args.date:
            date_str = args.date
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")

        date_dir = data_dir / date_str

        if not date_dir.exists():
            print(f"\n目录不存在: {date_dir}")
            print(f"可用日期:")
            for d in sorted(data_dir.iterdir()):
                if d.is_dir() and re.match(r'\d{4}-\d{2}-\d{2}', d.name):
                    print(f"  - {d.name}")
            return

        print(f"\n分析日期: {date_str}")
        print(f"目录: {date_dir}")

        # 批量分析图片（每张生成同名 txt）
        if args.images:
            print("\n模式: 批量分析图片 -> txt")
            count = await analyzer.analyze_images_batch(
                date_dir,
                limit=args.limit,
                skip_existing=not args.no_skip
            )
            print(f"\n完成！共分析 {count} 张图片")
            return

        # 分析日志+截图
        results = await analyzer.analyze_day(
            date_dir,
            limit=args.limit,
            save_results=True
        )

        # 显示摘要
        print("\n" + "=" * 60)
        print("分析摘要")
        print("=" * 60)

        for i, r in enumerate(results[:5]):  # 显示前 5 个
            print(f"\n[{i+1}] {r.window_title}")
            print(f"    时间: {r.timestamp}")
            if r.analysis:
                task = r.analysis.get("task") or r.analysis.get("activity", "")
                if task:
                    print(f"    任务: {task}")


if __name__ == "__main__":
    asyncio.run(main())
