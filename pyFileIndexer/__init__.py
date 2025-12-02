"""
pyFileIndexer - 文件索引系统

一个用于扫描目录并创建文件元数据和哈希值 SQLite 数据库的工具。
支持本地、USB、NAS、云存储等多种存储位置的文件跟踪和重复文件检测。

主要功能:
- 目录扫描和文件索引
- 文件哈希计算 (MD5, SHA1, SHA256)
- 重复文件检测
- Web 界面搜索和统计
- 数据库合并
- 归档文件扫描 (ZIP, TAR, RAR)
"""

__version__ = "0.1.0"
__author__ = "suyiiyii <suyiiyii@gmail.com>"

# 导出主要接口
from .main import main
from .database import db_manager
from .models import FileHash, FileMeta
from .config import settings

__all__ = [
    "main",
    "db_manager",
    "FileHash",
    "FileMeta",
    "settings",
    "__version__",
]
