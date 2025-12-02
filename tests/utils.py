"""
测试工具函数模块

提供测试中常用的工具函数和辅助类
"""

import hashlib
import os
import threading
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta


class TestTimer:
    """测试计时器，用于性能测试"""

    def __init__(self):
        self.start_time = None
        self.end_time = None

    def start(self):
        """开始计时"""
        self.start_time = time.time()

    def stop(self):
        """停止计时"""
        self.end_time = time.time()

    @property
    def elapsed(self) -> float:
        """获取经过的时间（秒）"""
        if self.start_time is None:
            return 0.0
        end = self.end_time if self.end_time else time.time()
        return end - self.start_time

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class FileCreator:
    """文件创建工具，用于生成测试文件"""

    @staticmethod
    def create_text_file(path: Path, content: str) -> Path:
        """创建文本文件"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    @staticmethod
    def create_binary_file(path: Path, size: int, pattern: bytes = b"\x00") -> Path:
        """创建指定大小的二进制文件"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            # 如果pattern长度为1，重复pattern
            if len(pattern) == 1:
                f.write(pattern * size)
            else:
                # 如果pattern长度大于1，重复pattern直到达到指定大小
                full_patterns = size // len(pattern)
                remainder = size % len(pattern)
                f.write(pattern * full_patterns)
                if remainder:
                    f.write(pattern[:remainder])
        return path

    @staticmethod
    def create_random_file(path: Path, size: int) -> Path:
        """创建指定大小的随机内容文件"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(os.urandom(size))
        return path

    @staticmethod
    def create_structured_directory(
        base_path: Path, structure: Dict[str, Any]
    ) -> Dict[str, Path]:
        """
        根据结构描述创建目录和文件

        structure示例:
        {
            "file1.txt": "content1",
            "subdir": {
                "file2.txt": "content2",
                "file3.bin": {"type": "binary", "size": 1024}
            }
        }
        """
        created_paths = {}

        def create_item(current_path: Path, name: str, item):
            item_path = current_path / name

            if isinstance(item, str):
                # 创建文本文件
                FileCreator.create_text_file(item_path, item)
                created_paths[name] = item_path
            elif isinstance(item, dict):
                if "type" in item:
                    # 文件配置
                    if item["type"] == "binary":
                        size = item.get("size", 1024)
                        pattern = item.get("pattern", b"\x00")
                        FileCreator.create_binary_file(item_path, size, pattern)
                    elif item["type"] == "random":
                        size = item.get("size", 1024)
                        FileCreator.create_random_file(item_path, size)
                    created_paths[name] = item_path
                else:
                    # 目录
                    item_path.mkdir(parents=True, exist_ok=True)
                    created_paths[name] = item_path
                    for sub_name, sub_item in item.items():
                        create_item(item_path, sub_name, sub_item)

        base_path.mkdir(parents=True, exist_ok=True)
        for name, item in structure.items():
            create_item(base_path, name, item)

        return created_paths


class HashVerifier:
    """哈希验证工具"""

    @staticmethod
    def calculate_file_hashes(file_path: Path) -> Dict[str, str]:
        """计算文件的所有哈希值"""
        hashes = {
            "md5": hashlib.md5(),
            "sha1": hashlib.sha1(),
            "sha256": hashlib.sha256(),
        }

        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                for hash_obj in hashes.values():
                    hash_obj.update(chunk)

        return {name: hash_obj.hexdigest() for name, hash_obj in hashes.items()}

    @staticmethod
    def verify_hashes(file_path: Path, expected_hashes: Dict[str, str]) -> bool:
        """验证文件哈希是否匹配"""
        actual_hashes = HashVerifier.calculate_file_hashes(file_path)

        for hash_type, expected in expected_hashes.items():
            if actual_hashes.get(hash_type) != expected:
                return False

        return True

    @staticmethod
    def are_files_identical(file1: Path, file2: Path) -> bool:
        """检查两个文件是否内容相同"""
        hashes1 = HashVerifier.calculate_file_hashes(file1)
        hashes2 = HashVerifier.calculate_file_hashes(file2)
        return hashes1 == hashes2


class DatabaseInspector:
    """数据库检查工具"""

    def __init__(self, db_manager):
        self.db_manager = db_manager

    def get_file_count(self) -> int:
        """获取文件数量"""
        with self.db_manager.session_factory() as session:
            from pyFileIndexer.models import FileMeta

            return session.query(FileMeta).count()

    def get_hash_count(self) -> int:
        """获取哈希数量"""
        with self.db_manager.session_factory() as session:
            from pyFileIndexer.models import FileHash

            return session.query(FileHash).count()

    def get_duplicate_files(self) -> List[List[str]]:
        """获取重复文件列表"""
        with self.db_manager.session_factory() as session:
            from pyFileIndexer.models import FileMeta, FileHash
            from sqlalchemy import func

            # 查找有多个文件引用的哈希
            duplicate_hashes = (
                session.query(FileMeta.hash_id)
                .group_by(FileMeta.hash_id)
                .having(func.count(FileMeta.id) > 1)
                .all()
            )

            duplicates = []
            for (hash_id,) in duplicate_hashes:
                files = session.query(FileMeta).filter_by(hash_id=hash_id).all()
                file_paths = [f.path for f in files]
                duplicates.append(file_paths)

            return duplicates

    def get_files_by_machine(self, machine_name: str) -> List[str]:
        """获取指定机器的文件列表"""
        with self.db_manager.session_factory() as session:
            from pyFileIndexer.models import FileMeta

            files = session.query(FileMeta).filter_by(machine=machine_name).all()
            return [f.path for f in files]

    def get_files_by_operation(self, operation: str) -> List[str]:
        """获取指定操作类型的文件列表"""
        with self.db_manager.session_factory() as session:
            from pyFileIndexer.models import FileMeta

            files = session.query(FileMeta).filter_by(operation=operation).all()
            return [f.path for f in files]


class ThreadSafeCounter:
    """线程安全计数器"""

    def __init__(self, initial_value: int = 0):
        self.value = initial_value
        self.lock = threading.Lock()

    def increment(self, amount: int = 1) -> int:
        """递增计数器并返回新值"""
        with self.lock:
            self.value += amount
            return self.value

    def decrement(self, amount: int = 1) -> int:
        """递减计数器并返回新值"""
        with self.lock:
            self.value -= amount
            return self.value

    def get(self) -> int:
        """获取当前值"""
        with self.lock:
            return self.value

    def reset(self, value: int = 0) -> int:
        """重置计数器"""
        with self.lock:
            old_value = self.value
            self.value = value
            return old_value


class MemoryMonitor:
    """内存监控工具"""

    def __init__(self):
        try:
            import psutil

            self.psutil = psutil
            self.process = psutil.Process()
            self.available = True
        except ImportError:
            self.available = False

    def get_memory_usage(self) -> Optional[int]:
        """获取当前内存使用量（字节）"""
        if not self.available:
            return None
        return self.process.memory_info().rss

    def get_memory_percent(self) -> Optional[float]:
        """获取内存使用百分比"""
        if not self.available:
            return None
        return self.process.memory_percent()


class TestEnvironment:
    """测试环境管理器"""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.created_files: List[Path] = []
        self.created_dirs: List[Path] = []

    def create_file(self, relative_path: str, content: str = "") -> Path:
        """创建文件并记录以便清理"""
        file_path = self.base_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        self.created_files.append(file_path)
        return file_path

    def create_directory(self, relative_path: str) -> Path:
        """创建目录并记录以便清理"""
        dir_path = self.base_path / relative_path
        dir_path.mkdir(parents=True, exist_ok=True)
        self.created_dirs.append(dir_path)
        return dir_path

    def cleanup(self):
        """清理创建的文件和目录"""
        # 删除文件
        for file_path in self.created_files:
            if file_path.exists():
                file_path.unlink()

        # 删除目录（从最深层开始）
        for dir_path in sorted(
            self.created_dirs, key=lambda p: len(p.parts), reverse=True
        ):
            if dir_path.exists() and not any(dir_path.iterdir()):
                dir_path.rmdir()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


class MockSettings:
    """模拟设置对象"""

    def __init__(self, **kwargs):
        self.values = kwargs

    def __getattr__(self, name):
        if name in self.values:
            return self.values[name]
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )

    def get(self, name, default=None):
        return self.values.get(name, default)

    def set(self, name, value):
        self.values[name] = value


def wait_for_condition(
    condition_func, timeout: float = 5.0, interval: float = 0.1
) -> bool:
    """
    等待条件成立

    Args:
        condition_func: 返回布尔值的函数
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）

    Returns:
        条件是否在超时前成立
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        if condition_func():
            return True
        time.sleep(interval)
    return False


def generate_test_data(count: int, prefix: str = "test") -> List[Dict[str, Any]]:
    """
    生成测试数据

    Args:
        count: 生成数据的数量
        prefix: 数据前缀

    Returns:
        测试数据列表
    """
    data = []
    for i in range(count):
        data.append(
            {
                "id": i,
                "name": f"{prefix}_{i:04d}",
                "content": f"Test content for {prefix} item {i}",
                "timestamp": datetime.now() - timedelta(days=i),
                "size": (i + 1) * 1024,
                "hash": hashlib.md5(f"{prefix}_{i}".encode()).hexdigest(),
            }
        )
    return data


class ProgressTracker:
    """进度追踪器"""

    def __init__(self, total: int):
        self.total = total
        self.current = 0
        self.start_time = time.time()
        self.lock = threading.Lock()

    def update(self, amount: int = 1):
        """更新进度"""
        with self.lock:
            self.current += amount

    def get_progress(self) -> Dict[str, Any]:
        """获取进度信息"""
        with self.lock:
            elapsed = time.time() - self.start_time
            percentage = (self.current / self.total) * 100 if self.total > 0 else 0

            if self.current > 0 and elapsed > 0:
                rate = self.current / elapsed
                eta = (self.total - self.current) / rate if rate > 0 else 0
            else:
                rate = 0
                eta = 0

            return {
                "current": self.current,
                "total": self.total,
                "percentage": percentage,
                "elapsed": elapsed,
                "rate": rate,
                "eta": eta,
            }

    def is_complete(self) -> bool:
        """检查是否完成"""
        with self.lock:
            return self.current >= self.total
