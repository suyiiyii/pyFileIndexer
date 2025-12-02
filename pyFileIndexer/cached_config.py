"""
配置缓存模块 - 解决 Dynaconf 访问性能问题

这个模块提供了一个缓存层，避免重复调用 getattr(settings, ...)
从而显著提升性能。根据 profiling 结果，配置访问是主要性能瓶颈。
"""

import datetime
import threading
from typing import Optional

from .config import settings


class CachedConfig:
    """配置缓存类，提供高性能的配置访问"""

    _instance: Optional["CachedConfig"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "CachedConfig":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return

        with self._lock:
            if hasattr(self, "_initialized"):
                return

            # 初始化时缓存所有常用配置
            self._machine_name: str = getattr(settings, "MACHINE_NAME", "localhost")
            self._scanned: datetime.datetime = self._parse_scanned_time()
            self._scan_archives: bool = getattr(settings, "SCAN_ARCHIVES", True)
            self._max_archive_size: int = getattr(
                settings, "MAX_ARCHIVE_SIZE", 9223372036854775807
            )
            self._max_archive_file_size: int = getattr(
                settings, "MAX_ARCHIVE_FILE_SIZE", 9223372036854775807
            )
            self._skip_rules_enabled: bool = getattr(settings, "ENABLE_IGNORE_RULES", False)

            # 标记已初始化
            self._initialized = True

    def _parse_scanned_time(self) -> datetime.datetime:
        """解析 SCANNED 配置，处理字符串格式"""
        scanned = getattr(settings, "SCANNED", datetime.datetime.now())

        if isinstance(scanned, str):
            try:
                return datetime.datetime.fromisoformat(scanned)
            except ValueError:
                return datetime.datetime.now()
        elif isinstance(scanned, datetime.datetime):
            return scanned
        else:
            return datetime.datetime.now()

    @property
    def machine_name(self) -> str:
        """获取机器名称"""
        return self._machine_name

    @property
    def scanned(self) -> datetime.datetime:
        """获取扫描时间"""
        return self._scanned

    @property
    def scan_archives(self) -> bool:
        """是否扫描压缩包"""
        return self._scan_archives

    @property
    def max_archive_size(self) -> int:
        """最大压缩包大小"""
        return self._max_archive_size

    @property
    def max_archive_file_size(self) -> int:
        """压缩包内文件最大大小"""
        return self._max_archive_file_size

    @property
    def skip_rules_enabled(self) -> bool:
        return self._skip_rules_enabled

    def update_machine_name(self, machine_name: str) -> None:
        """更新机器名称（支持命令行参数覆盖）"""
        self._machine_name = machine_name

    def update_scanned_time(self, scanned_time: datetime.datetime) -> None:
        """更新扫描时间"""
        self._scanned = scanned_time

    def reload_config(self) -> None:
        """重新加载配置（如果需要动态更新）"""
        with self._lock:
            self._machine_name = getattr(settings, "MACHINE_NAME", "localhost")
            self._scanned = self._parse_scanned_time()
            self._scan_archives = getattr(settings, "SCAN_ARCHIVES", True)
            self._max_archive_size = getattr(
                settings, "MAX_ARCHIVE_SIZE", 9223372036854775807
            )
            self._max_archive_file_size = getattr(
                settings, "MAX_ARCHIVE_FILE_SIZE", 9223372036854775807
            )
            self._skip_rules_enabled = getattr(settings, "ENABLE_IGNORE_RULES", False)


# 创建全局单例实例
cached_config = CachedConfig()
