#!/usr/bin/env python3
"""
增强版 AutoCapture - 集成 Qwen3-VL 图片理解
这是一个示例文件，展示如何集成新的分析功能
"""

import asyncio
import threading
from pathlib import Path
from datetime import datetime
import argparse
import signal
import sys

# 导入原始模块（假设已重构为可导入的形式）
from auto_capture import WindowTracker, KeyLogger, MouseCapture, AutoCapture

# 导入新模块
from config import Config, init_config
from image_analyzer import ImageAnalyzer
from qwen_client import Qwen3VLClient


class MouseCaptureEnhanced(MouseCapture):
    """增强版鼠标捕获器，集成图片分析功能"""

    def __init__(self, output_dir, image_analyzer=None):
        """
        初始化增强版鼠标捕获器

        Args:
            output_dir: 输出目录
            image_analyzer: 图片分析器实例
        """
        super().__init__(output_dir)
        self.image_analyzer = image_analyzer
        self.analysis_loop = None

    def _capture_and_save(self, action_type, position, end_position=None):
        """
        重写截图保存方法，添加分析功能

        Args:
            action_type: 操作类型
            position: 起始位置
            end_position: 结束位置（拖拽时使用）
        """
        # 调用父类方法执行截图
        file_path = super()._capture_and_save(action_type, position, end_position)

        # 如果有分析器，添加到分析队列
        if self.image_analyzer and file_path:
            # 准备上下文信息
            context = {
                "action_type": action_type,
                "window_title": self.current_window_title,
                "window_app": self.current_window_app,
                "position": position,
                "end_position": end_position,
                "timestamp": datetime.now().isoformat()
            }

            # 在事件循环中添加任务
            if self.analysis_loop:
                asyncio.run_coroutine_threadsafe(
                    self.image_analyzer.add_to_queue(file_path, context),
                    self.analysis_loop
                )

        return file_path


class AutoCaptureEnhanced(AutoCapture):
    """增强版 AutoCapture，集成 Qwen3-VL 分析功能"""

    def __init__(self, output_dir="~/auto-capture", config_path=None):
        """
        初始化增强版 AutoCapture

        Args:
            output_dir: 输出目录
            config_path: 配置文件路径
        """
        # 初始化配置
        self.config = init_config(config_path)

        # 覆盖输出目录
        if output_dir != "~/auto-capture":
            self.config.set("capture.output_dir", output_dir)

        output_dir = self.config.get("capture.output_dir")

        # 调用父类初始化
        super().__init__(output_dir)

        # 初始化分析器
        self.image_analyzer = None
        self.analysis_thread = None
        self.analysis_loop = None

        if self.config.is_analysis_enabled():
            self._init_analyzer()

    def _init_analyzer(self):
        """初始化图片分析器"""
        print("正在初始化图片分析器...")

        # 创建分析器
        self.image_analyzer = ImageAnalyzer(
            output_dir=Path(self.config.get("capture.output_dir")),
            qwen_config=self.config.get_qwen_config(),
            queue_size=self.config.get("analyzer.queue_size"),
            batch_size=self.config.get("analyzer.batch_size")
        )

        # 启动异步事件循环线程
        def run_analysis_loop():
            """在独立线程中运行异步事件循环"""
            self.analysis_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.analysis_loop)

            # 启动分析器
            self.analysis_loop.run_until_complete(
                self.image_analyzer.start()
            )

            # 保持事件循环运行
            self.analysis_loop.run_forever()

        self.analysis_thread = threading.Thread(
            target=run_analysis_loop,
            daemon=True,
            name="AnalysisThread"
        )
        self.analysis_thread.start()

        # 等待分析器启动
        import time
        time.sleep(2)

        # 重新创建鼠标捕获器，使用增强版本
        self.mouse_capture = MouseCaptureEnhanced(
            self.output_dir,
            self.image_analyzer
        )
        self.mouse_capture.analysis_loop = self.analysis_loop

        print("图片分析器初始化完成")

    def start(self):
        """启动捕获和分析"""
        super().start()

        # 输出分析器状态
        if self.image_analyzer:
            print("\n图片分析功能已启用")
            print(f"  - 模型: {self.config.get('qwen.model')}")
            print(f"  - API: {self.config.get('qwen.api_url')}")
            print(f"  - 队列大小: {self.config.get('analyzer.queue_size')}")
        else:
            print("\n图片分析功能未启用")

    def stop(self):
        """停止捕获和分析"""
        print("\n正在停止...")

        # 停止父类组件
        super().stop()

        # 停止分析器
        if self.image_analyzer and self.analysis_loop:
            # 停止分析器
            future = asyncio.run_coroutine_threadsafe(
                self.image_analyzer.stop(),
                self.analysis_loop
            )
            future.result(timeout=5)

            # 停止事件循环
            self.analysis_loop.call_soon_threadsafe(self.analysis_loop.stop)

            # 等待线程结束
            if self.analysis_thread:
                self.analysis_thread.join(timeout=5)

            # 输出统计信息
            stats = self.image_analyzer.get_stats()
            print("\n分析统计:")
            print(f"  - 总分析数: {stats['total_analyzed']}")
            print(f"  - 成功: {stats['success_count']}")
            print(f"  - 失败: {stats['error_count']}")
            print(f"  - 平均推理时间: {stats['avg_inference_time']:.2f}s")

        print("已停止")

    def run(self):
        """运行主循环"""
        print("\n增强版 AutoCapture 正在运行...")
        print("按 Ctrl+C 停止\n")

        try:
            while True:
                import time
                time.sleep(1)

                # 定期输出状态
                if self.image_analyzer and int(time.time()) % 60 == 0:
                    stats = self.image_analyzer.get_stats()
                    print(f"[状态] 队列: {stats['queue_size']} | "
                          f"已分析: {stats['total_analyzed']} | "
                          f"成功率: {stats['success_count']}/{stats['total_analyzed']}")

        except KeyboardInterrupt:
            pass


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="增强版 AutoCapture - 带图片理解功能的自动截图工具"
    )
    parser.add_argument(
        "-d", "--dir",
        default="~/auto-capture",
        help="存储目录 (默认: ~/auto-capture)"
    )
    parser.add_argument(
        "-c", "--config",
        help="配置文件路径 (YAML 或 JSON)"
    )
    parser.add_argument(
        "--no-analysis",
        action="store_true",
        help="禁用图片分析功能"
    )
    parser.add_argument(
        "--analyze-existing",
        help="分析已存在的图片 (格式: YYYY-MM-DD 或 today)"
    )
    parser.add_argument(
        "--generate-config",
        help="生成示例配置文件"
    )

    args = parser.parse_args()

    # 生成配置文件
    if args.generate_config:
        from config import generate_example_config
        generate_example_config(args.generate_config)
        return

    # 分析已存在的图片
    if args.analyze_existing:
        analyze_date = args.analyze_existing
        if analyze_date == "today":
            analyze_date = datetime.now().strftime("%Y-%m-%d")

        print(f"分析日期 {analyze_date} 的图片...")

        config = init_config(args.config)
        if args.no_analysis:
            print("错误: --no-analysis 与 --analyze-existing 冲突")
            return

        output_dir = Path(args.dir).expanduser()
        analyzer = ImageAnalyzer(
            output_dir=output_dir,
            qwen_config=config.get_qwen_config()
        )

        # 运行分析
        async def run_analysis():
            await analyzer.start()
            await analyzer.analyze_existing_images(analyze_date)
            await analyzer.stop()

        asyncio.run(run_analysis())
        return

    # 正常运行模式
    print("=" * 60)
    print("增强版 AutoCapture - Qwen3-VL 集成")
    print("=" * 60)

    # 如果指定了 --no-analysis，禁用分析
    if args.no_analysis:
        config = init_config(args.config)
        config.set("qwen.enabled", False)
        capture = AutoCaptureEnhanced(args.dir)
    else:
        capture = AutoCaptureEnhanced(args.dir, args.config)

    def signal_handler(signum, frame):
        """信号处理器"""
        print("\n接收到中断信号")
        capture.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    capture.start()
    capture.run()
    capture.stop()


if __name__ == "__main__":
    main()