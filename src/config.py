#!/usr/bin/env python3
"""
配置管理模块
管理 OpenCapture 和 Qwen3-VL 集成的所有配置
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class Config:
    """配置管理类"""

    # 默认配置
    DEFAULT_CONFIG = {
        # OpenCapture 基础配置
        "capture": {
            "output_dir": "~/auto-capture",
            "cluster_interval": 20,  # 键盘聚类间隔（秒）
            "throttle_ms": 100,  # 截图节流间隔（毫秒）
            "drag_threshold": 10,  # 拖拽判定距离（像素）
            "double_click_interval": 400,  # 双击判定间隔（毫秒）
            "double_click_distance": 5,  # 双击判定距离（像素）
            "window_border_color": [0, 120, 255],  # 窗口边框颜色 RGB
            "window_border_width": 3,  # 边框宽度（像素）
            "image_format": "webp",  # 图片格式
            "image_quality": 80,  # 图片质量 (1-100)
        },

        # Qwen3-VL 配置
        "qwen": {
            "enabled": True,  # 是否启用图片分析
            "api_url": "http://localhost:11434",  # API 地址
            "model": "qwen2-vl:7b",  # 模型名称
            "timeout": 30,  # 请求超时（秒）
            "max_retries": 3,  # 最大重试次数
            "temperature": 0.7,  # 温度参数
            "max_tokens": 2048,  # 最大 token 数
        },

        # 分析器配置
        "analyzer": {
            "queue_size": 100,  # 分析队列大小
            "batch_size": 5,  # 批处理大小
            "save_raw_response": False,  # 是否保存原始响应
            "save_pretty_json": True,  # 是否保存格式化 JSON
            "enable_cache": True,  # 是否启用缓存
            "cache_ttl": 3600,  # 缓存有效期（秒）
        },

        # 隐私配置
        "privacy": {
            "enabled": False,  # 是否启用隐私保护
            "blur_sensitive": True,  # 模糊敏感信息
            "exclude_patterns": [  # 排除的窗口模式
                ".*password.*",
                ".*banking.*",
                ".*private.*"
            ],
            "sensitive_patterns": [  # 敏感信息正则
                r"password|pwd|secret",
                r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}",  # 信用卡
                r"\d{3}-\d{2}-\d{4}",  # SSN
            ]
        },

        # 日志配置
        "logging": {
            "level": "INFO",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "file": "opencapture.log",
            "max_bytes": 10485760,  # 10MB
            "backup_count": 5,
        },

        # 提示词模板
        "prompts": {
            "click": "分析用户点击的界面元素、功能按钮或链接，推测点击意图",
            "dblclick": "分析用户双击的目标，通常是打开文件、应用或激活某个功能",
            "drag": "分析拖拽操作的起点和终点，可能是选择文本、移动元素或调整大小",
            "default": "分析截图内容，识别界面类型、主要元素和可能的用户操作",
        }
    }

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置

        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = self.DEFAULT_CONFIG.copy()

        # 加载配置文件
        if config_path:
            self.load_from_file(config_path)

        # 加载环境变量
        self.load_from_env()

        # 展开路径
        self._expand_paths()

    def load_from_file(self, config_path: str):
        """
        从文件加载配置

        Args:
            config_path: 配置文件路径
        """
        config_path = Path(config_path)
        if not config_path.exists():
            print(f"配置文件不存在: {config_path}")
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                if config_path.suffix == ".json":
                    user_config = json.load(f)
                elif config_path.suffix in [".yaml", ".yml"]:
                    user_config = yaml.safe_load(f)
                else:
                    print(f"不支持的配置文件格式: {config_path.suffix}")
                    return

            # 深度合并配置
            self.config = self._deep_merge(self.config, user_config)
            print(f"已加载配置文件: {config_path}")

        except Exception as e:
            print(f"加载配置文件失败: {e}")

    def load_from_env(self):
        """从环境变量加载配置"""
        # Qwen API 配置
        if "QWEN_API_URL" in os.environ:
            self.config["qwen"]["api_url"] = os.environ["QWEN_API_URL"]

        if "QWEN_MODEL" in os.environ:
            self.config["qwen"]["model"] = os.environ["QWEN_MODEL"]

        # 启用/禁用分析
        if "ENABLE_ANALYSIS" in os.environ:
            self.config["qwen"]["enabled"] = os.environ["ENABLE_ANALYSIS"].lower() == "true"

        # 输出目录
        if "CAPTURE_OUTPUT_DIR" in os.environ:
            self.config["capture"]["output_dir"] = os.environ["CAPTURE_OUTPUT_DIR"]

        # 日志级别
        if "LOG_LEVEL" in os.environ:
            self.config["logging"]["level"] = os.environ["LOG_LEVEL"]

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """
        深度合并两个字典

        Args:
            base: 基础配置
            override: 覆盖配置

        Returns:
            Dict: 合并后的配置
        """
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def _expand_paths(self):
        """展开配置中的路径"""
        # 展开输出目录
        output_dir = self.config["capture"]["output_dir"]
        self.config["capture"]["output_dir"] = str(Path(output_dir).expanduser())

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值

        Args:
            key: 配置键，支持点号分隔的嵌套键
            default: 默认值

        Returns:
            Any: 配置值
        """
        keys = key.split(".")
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any):
        """
        设置配置值

        Args:
            key: 配置键，支持点号分隔的嵌套键
            value: 配置值
        """
        keys = key.split(".")
        config = self.config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def save(self, path: Optional[str] = None):
        """
        保存配置到文件

        Args:
            path: 保存路径，None 则使用初始化时的路径
        """
        save_path = path or self.config_path
        if not save_path:
            print("未指定保存路径")
            return

        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                if save_path.suffix == ".json":
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
                elif save_path.suffix in [".yaml", ".yml"]:
                    yaml.dump(self.config, f, allow_unicode=True)
                else:
                    print(f"不支持的配置文件格式: {save_path.suffix}")
                    return

            print(f"配置已保存: {save_path}")

        except Exception as e:
            print(f"保存配置失败: {e}")

    def to_dict(self) -> Dict:
        """
        获取完整配置字典

        Returns:
            Dict: 配置字典
        """
        return self.config.copy()

    def get_qwen_config(self) -> Dict:
        """
        获取 Qwen 客户端配置

        Returns:
            Dict: Qwen 配置
        """
        return {
            "api_url": self.get("qwen.api_url"),
            "model": self.get("qwen.model"),
            "timeout": self.get("qwen.timeout"),
            "max_retries": self.get("qwen.max_retries"),
        }

    def get_analyzer_config(self) -> Dict:
        """
        获取分析器配置

        Returns:
            Dict: 分析器配置
        """
        return {
            "queue_size": self.get("analyzer.queue_size"),
            "batch_size": self.get("analyzer.batch_size"),
        }

    def is_analysis_enabled(self) -> bool:
        """
        检查是否启用图片分析

        Returns:
            bool: 是否启用
        """
        return self.get("qwen.enabled", False)

    def should_exclude_window(self, window_title: str) -> bool:
        """
        检查窗口是否应该被排除（隐私保护）

        Args:
            window_title: 窗口标题

        Returns:
            bool: 是否排除
        """
        if not self.get("privacy.enabled", False):
            return False

        import re
        patterns = self.get("privacy.exclude_patterns", [])

        for pattern in patterns:
            if re.search(pattern, window_title, re.IGNORECASE):
                return True

        return False


# 全局配置实例
_global_config: Optional[Config] = None


def get_config() -> Config:
    """获取全局配置实例"""
    global _global_config
    if _global_config is None:
        _global_config = Config()
    return _global_config


def init_config(config_path: Optional[str] = None) -> Config:
    """
    初始化全局配置

    Args:
        config_path: 配置文件路径

    Returns:
        Config: 配置实例
    """
    global _global_config
    _global_config = Config(config_path)
    return _global_config


# 生成示例配置文件
def generate_example_config(output_path: str = "config/example.yaml"):
    """
    生成示例配置文件

    Args:
        output_path: 输出路径
    """
    config = Config()
    config.save(output_path)
    print(f"示例配置文件已生成: {output_path}")


if __name__ == "__main__":
    # 生成示例配置
    generate_example_config()

    # 测试配置
    config = Config()
    print("默认配置:")
    print(json.dumps(config.to_dict(), indent=2, ensure_ascii=False))

    # 测试获取配置
    print(f"\nQwen API URL: {config.get('qwen.api_url')}")
    print(f"是否启用分析: {config.is_analysis_enabled()}")
    print(f"输出目录: {config.get('capture.output_dir')}")