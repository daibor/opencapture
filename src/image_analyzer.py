#!/usr/bin/env python3
"""
图片分析模块
负责调度图片分析任务，管理分析队列，保存分析结果
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from collections import deque
import hashlib

from .qwen_client import Qwen3VLClient

logger = logging.getLogger(__name__)


class ImageAnalyzer:
    """图片分析器"""

    def __init__(
        self,
        output_dir: Path,
        qwen_config: Optional[Dict] = None,
        queue_size: int = 100,
        batch_size: int = 5
    ):
        """
        初始化图片分析器

        Args:
            output_dir: 输出目录
            qwen_config: Qwen3-VL 配置
            queue_size: 队列最大大小
            batch_size: 批处理大小
        """
        self.output_dir = Path(output_dir)
        self.queue_size = queue_size
        self.batch_size = batch_size

        # 初始化 Qwen 客户端
        qwen_config = qwen_config or {}
        self.qwen_client = Qwen3VLClient(**qwen_config)

        # 分析队列
        self.analysis_queue = asyncio.Queue(maxsize=queue_size)
        self.pending_tasks = deque(maxlen=queue_size)

        # 运行状态
        self.running = False
        self.process_task = None

        # 统计信息
        self.stats = {
            "total_analyzed": 0,
            "success_count": 0,
            "error_count": 0,
            "avg_inference_time": 0.0,
            "total_inference_time": 0.0
        }

        # 缓存最近的分析结果，避免重复分析相似图片
        self.recent_hashes = deque(maxlen=100)

    async def start(self):
        """启动分析器"""
        if not self.running:
            self.running = True
            # 检查服务健康状态
            is_healthy = await self.qwen_client.health_check()
            if not is_healthy:
                logger.warning("Qwen3-VL 服务不可用，分析功能将被禁用")
                self.running = False
                return False

            # 启动处理任务
            self.process_task = asyncio.create_task(self.process_queue())
            logger.info("图片分析器已启动")
            return True

    async def stop(self):
        """停止分析器"""
        if self.running:
            self.running = False
            # 等待队列处理完成
            await self.analysis_queue.join()
            if self.process_task:
                self.process_task.cancel()
                try:
                    await self.process_task
                except asyncio.CancelledError:
                    pass
            logger.info("图片分析器已停止")

    def _build_prompt(self, context: Dict) -> str:
        """
        根据上下文构建分析提示词

        Args:
            context: 上下文信息

        Returns:
            str: 提示词
        """
        action_type = context.get("action_type", "unknown")
        window_title = context.get("window_title", "未知窗口")
        window_app = context.get("window_app", "未知应用")

        # 基础提示词模板
        base_prompt = f"""请分析这张截图，当前窗口是 "{window_title}" (应用: {window_app})。

请提供以下信息：
1. 界面类型和主要功能区域
2. 用户操作的具体位置和目标元素
3. 当前界面的内容和状态
4. 用户可能的操作意图

"""

        # 根据操作类型添加特定分析
        action_prompts = {
            "click": "用户执行了点击操作，请特别关注点击位置的UI元素和可能触发的功能。",
            "dblclick": "用户执行了双击操作，请分析双击目标可能打开或激活的内容。",
            "drag": "用户执行了拖拽操作，请描述拖拽的起始和结束位置，分析可能的选择、移动或调整大小操作。"
        }

        prompt = base_prompt + action_prompts.get(action_type, "")

        # 添加 JSON 格式要求
        prompt += """
请以 JSON 格式返回分析结果，包含以下字段：
{
  "interface_type": "界面类型描述",
  "action_target": "操作目标元素",
  "action_purpose": "操作目的",
  "content_summary": "内容摘要",
  "ui_elements": ["可见的主要UI元素列表"],
  "next_possible_actions": ["可能的后续操作"]
}
"""

        return prompt

    def _calculate_image_hash(self, image_path: str) -> str:
        """
        计算图片哈希值（用于去重）

        Args:
            image_path: 图片路径

        Returns:
            str: 哈希值
        """
        try:
            with open(image_path, "rb") as f:
                # 只读取前 1MB 用于计算哈希
                data = f.read(1024 * 1024)
                return hashlib.md5(data).hexdigest()
        except Exception as e:
            logger.error(f"计算图片哈希失败: {e}")
            return ""

    async def add_to_queue(
        self,
        image_path: str,
        context: Dict[str, Any]
    ) -> bool:
        """
        添加分析任务到队列

        Args:
            image_path: 图片路径
            context: 上下文信息

        Returns:
            bool: 是否成功加入队列
        """
        if not self.running:
            logger.warning("分析器未运行，跳过任务")
            return False

        # 检查图片是否存在
        if not Path(image_path).exists():
            logger.error(f"图片文件不存在: {image_path}")
            return False

        # 计算哈希，检查是否重复
        image_hash = self._calculate_image_hash(image_path)
        if image_hash and image_hash in self.recent_hashes:
            logger.debug(f"跳过重复图片: {image_path}")
            return False

        # 构建任务
        task = {
            "image_path": image_path,
            "context": context,
            "timestamp": datetime.now().isoformat(),
            "hash": image_hash
        }

        try:
            # 尝试非阻塞添加到队列
            self.analysis_queue.put_nowait(task)
            self.recent_hashes.append(image_hash)
            logger.debug(f"任务已加入队列: {image_path}")
            return True
        except asyncio.QueueFull:
            logger.warning(f"队列已满，丢弃任务: {image_path}")
            return False

    async def process_queue(self):
        """处理分析队列"""
        logger.info("开始处理分析队列")

        while self.running:
            try:
                # 收集批次任务
                batch = []
                timeout = 2.0  # 等待超时

                # 获取第一个任务
                try:
                    task = await asyncio.wait_for(
                        self.analysis_queue.get(),
                        timeout=timeout
                    )
                    batch.append(task)
                except asyncio.TimeoutError:
                    continue

                # 尝试收集更多任务形成批次
                while len(batch) < self.batch_size:
                    try:
                        task = self.analysis_queue.get_nowait()
                        batch.append(task)
                    except asyncio.QueueEmpty:
                        break

                # 处理批次
                if batch:
                    await self._process_batch(batch)

            except Exception as e:
                logger.error(f"队列处理错误: {e}")
                await asyncio.sleep(1)

    async def _process_batch(self, batch: List[Dict]):
        """
        处理一批分析任务

        Args:
            batch: 任务批次
        """
        logger.info(f"处理批次，包含 {len(batch)} 个任务")

        for task in batch:
            try:
                # 分析单个图片
                result = await self._analyze_single(task)

                # 保存结果
                if result:
                    self._save_analysis(result)
                    self.stats["success_count"] += 1
                else:
                    self.stats["error_count"] += 1

            except Exception as e:
                logger.error(f"处理任务失败: {e}")
                self.stats["error_count"] += 1

            finally:
                self.stats["total_analyzed"] += 1
                # 标记任务完成
                self.analysis_queue.task_done()

    async def _analyze_single(self, task: Dict) -> Optional[Dict]:
        """
        分析单个图片

        Args:
            task: 任务信息

        Returns:
            Optional[Dict]: 分析结果
        """
        image_path = task["image_path"]
        context = task["context"]

        # 构建提示词
        prompt = self._build_prompt(context)

        # 记录开始时间
        start_time = datetime.now()

        try:
            # 调用 Qwen3-VL
            analysis = await self.qwen_client.analyze(image_path, prompt)

            if not analysis.get("success", False):
                logger.error(f"分析失败: {analysis.get('error', '未知错误')}")
                return None

            # 计算推理时间
            inference_time = (datetime.now() - start_time).total_seconds()

            # 更新统计
            self.stats["total_inference_time"] += inference_time
            self.stats["avg_inference_time"] = (
                self.stats["total_inference_time"] / max(self.stats["success_count"], 1)
            )

            # 构建完整结果
            result = {
                "timestamp": task["timestamp"],
                "image_path": image_path,
                "image_hash": task.get("hash", ""),
                "context": context,
                "analysis": analysis,
                "inference_time": inference_time,
                "model_info": {
                    "name": self.qwen_client.model,
                    "api_url": self.qwen_client.api_url
                }
            }

            logger.info(
                f"成功分析图片: {Path(image_path).name} "
                f"(耗时: {inference_time:.2f}s)"
            )

            return result

        except Exception as e:
            logger.error(f"分析图片失败 {image_path}: {e}")
            return None

    def _save_analysis(self, result: Dict):
        """
        保存分析结果

        Args:
            result: 分析结果
        """
        try:
            # 确定保存路径
            image_path = Path(result["image_path"])
            date_str = datetime.now().strftime("%Y-%m-%d")
            date_dir = self.output_dir / date_str
            date_dir.mkdir(parents=True, exist_ok=True)

            # 保存到 JSONL 文件
            analysis_file = date_dir / "analysis.jsonl"
            with open(analysis_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")

            logger.debug(f"分析结果已保存: {analysis_file}")

            # 同时保存一份便于查看的格式化 JSON
            pretty_file = date_dir / f"analysis_{Path(image_path).stem}.json"
            with open(pretty_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"保存分析结果失败: {e}")

    def get_stats(self) -> Dict:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            **self.stats,
            "queue_size": self.analysis_queue.qsize(),
            "is_running": self.running
        }

    async def analyze_existing_images(self, date: Optional[str] = None):
        """
        分析已存在的图片（用于补充分析）

        Args:
            date: 日期字符串，格式 YYYY-MM-DD，None 表示今天
        """
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        date_dir = self.output_dir / date
        if not date_dir.exists():
            logger.error(f"日期目录不存在: {date_dir}")
            return

        # 查找所有图片文件
        image_files = list(date_dir.glob("*.webp"))
        logger.info(f"找到 {len(image_files)} 个图片文件待分析")

        for image_file in image_files:
            # 从文件名解析上下文
            context = self._parse_filename_context(image_file.name)
            await self.add_to_queue(str(image_file), context)

        # 等待处理完成
        await self.analysis_queue.join()
        logger.info("补充分析完成")

    def _parse_filename_context(self, filename: str) -> Dict:
        """
        从文件名解析上下文信息

        Args:
            filename: 文件名

        Returns:
            Dict: 上下文信息
        """
        # 文件名格式: action_HHmmss_ms_button_x<X>_y<Y>.webp
        # 或: drag_HHmmss_ms_button_x<X1>_y<Y1>_to_x<X2>_y<Y2>.webp

        parts = filename.replace(".webp", "").split("_")
        context = {
            "action_type": parts[0] if parts else "unknown",
            "filename": filename
        }

        # 尝试解析坐标
        try:
            for i, part in enumerate(parts):
                if part.startswith("x") and i + 1 < len(parts):
                    context["x"] = int(part[1:])
                    context["y"] = int(parts[i + 1][1:]) if parts[i + 1].startswith("y") else None
        except:
            pass

        return context


# 测试代码
async def test_analyzer():
    """测试分析器"""
    output_dir = Path("./test_output")
    output_dir.mkdir(exist_ok=True)

    analyzer = ImageAnalyzer(output_dir)
    await analyzer.start()

    # 添加测试任务
    test_context = {
        "action_type": "click",
        "window_title": "测试窗口",
        "window_app": "test.app"
    }

    # 假设有测试图片
    test_image = "test.webp"
    if Path(test_image).exists():
        await analyzer.add_to_queue(test_image, test_context)
        # 等待处理
        await asyncio.sleep(5)

    # 获取统计
    stats = analyzer.get_stats()
    print(f"统计信息: {json.dumps(stats, indent=2)}")

    await analyzer.stop()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    asyncio.run(test_analyzer())