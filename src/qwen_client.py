#!/usr/bin/env python3
"""
Qwen3-VL 客户端模块
用于调用本地部署的 Qwen3-VL 模型进行图片分析
"""

import aiohttp
import asyncio
import base64
import json
import logging
from typing import Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class Qwen3VLClient:
    """Qwen3-VL 模型客户端"""

    def __init__(
        self,
        api_url: str = "http://localhost:11434",
        model: str = "qwen2-vl:7b",
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        初始化 Qwen3-VL 客户端

        Args:
            api_url: API 服务地址
            model: 模型名称
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self.api_url = api_url
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self.session:
            await self.session.close()

    async def health_check(self) -> bool:
        """
        检查服务健康状态

        Returns:
            bool: 服务是否可用
        """
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(
                f"{self.api_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # 检查模型是否在列表中
                    models = [m.get("name") for m in data.get("models", [])]
                    if self.model in models:
                        logger.info(f"Qwen3-VL 服务正常，模型 {self.model} 已加载")
                        return True
                    else:
                        logger.warning(f"模型 {self.model} 未找到，可用模型: {models}")
                        return False
                return False
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False

    def _encode_image(self, image_path: str) -> str:
        """
        将图片编码为 base64

        Args:
            image_path: 图片路径

        Returns:
            str: base64 编码的图片数据
        """
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"图片编码失败: {e}")
            raise

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """
        解析模型响应

        Args:
            response: 模型原始响应

        Returns:
            Dict: 解析后的结果
        """
        try:
            # 尝试提取 JSON 内容
            # 有时模型会返回带有额外文本的 JSON
            import re
            json_pattern = r'\{[^{}]*\}'
            matches = re.findall(json_pattern, response)

            if matches:
                # 尝试解析找到的第一个 JSON
                for match in matches:
                    try:
                        return json.loads(match)
                    except json.JSONDecodeError:
                        continue

            # 如果没有找到有效的 JSON，尝试直接解析
            return json.loads(response)

        except Exception:
            # 返回原始响应
            return {
                "raw_response": response,
                "parse_error": True
            }

    async def analyze(
        self,
        image_path: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> Dict[str, Any]:
        """
        分析图片

        Args:
            image_path: 图片路径
            prompt: 提示词
            temperature: 温度参数
            max_tokens: 最大token数

        Returns:
            Dict: 分析结果
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        # 编码图片
        try:
            image_base64 = self._encode_image(image_path)
        except Exception as e:
            return {
                "error": f"图片编码失败: {e}",
                "success": False
            }

        # 构建请求
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_base64],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        # 重试逻辑
        for attempt in range(self.max_retries):
            try:
                async with self.session.post(
                    f"{self.api_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        parsed = self._parse_response(result.get("response", ""))
                        parsed["success"] = True
                        parsed["model"] = self.model
                        parsed["total_duration"] = result.get("total_duration", 0) / 1e9  # 转换为秒
                        return parsed
                    else:
                        error_msg = f"API 返回错误: {response.status}"
                        logger.error(error_msg)

            except asyncio.TimeoutError:
                logger.warning(f"请求超时 (尝试 {attempt + 1}/{self.max_retries})")

            except Exception as e:
                logger.error(f"请求失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")

            # 指数退避
            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        return {
            "error": "达到最大重试次数",
            "success": False
        }

    async def batch_analyze(
        self,
        image_paths: list,
        prompt: str,
        batch_size: int = 5
    ) -> list:
        """
        批量分析图片

        Args:
            image_paths: 图片路径列表
            prompt: 提示词
            batch_size: 批处理大小

        Returns:
            list: 分析结果列表
        """
        results = []

        # 创建批次
        for i in range(0, len(image_paths), batch_size):
            batch = image_paths[i:i + batch_size]

            # 并发处理批次内的图片
            tasks = [
                self.analyze(path, prompt)
                for path in batch
            ]

            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)

            # 批次间延迟，避免过载
            if i + batch_size < len(image_paths):
                await asyncio.sleep(1)

        return results


class Qwen3VLClientSync:
    """同步版本的 Qwen3-VL 客户端（供兼容性使用）"""

    def __init__(self, *args, **kwargs):
        self.async_client = Qwen3VLClient(*args, **kwargs)

    def analyze(self, image_path: str, prompt: str) -> Dict[str, Any]:
        """同步分析接口"""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.async_client.analyze(image_path, prompt)
            )
        finally:
            loop.close()

    def health_check(self) -> bool:
        """同步健康检查"""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.async_client.health_check()
            )
        finally:
            loop.close()


# 测试代码
async def test_client():
    """测试客户端功能"""
    async with Qwen3VLClient() as client:
        # 健康检查
        is_healthy = await client.health_check()
        print(f"服务状态: {'正常' if is_healthy else '异常'}")

        if is_healthy:
            # 测试分析
            test_image = "test.png"  # 需要准备测试图片
            if Path(test_image).exists():
                result = await client.analyze(
                    test_image,
                    "请描述这张图片的内容"
                )
                print(f"分析结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
            else:
                print(f"测试图片 {test_image} 不存在")


if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 运行测试
    asyncio.run(test_client())