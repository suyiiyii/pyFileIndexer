"""
测试数据样本

提供各种测试场景所需的样本数据
"""

from datetime import datetime

# 示例文件哈希数据
SAMPLE_HASHES = [
    {
        "size": 1024,
        "md5": "5d41402abc4b2a76b9719d911017c592",
        "sha1": "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d",
        "sha256": "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
    },
    {
        "size": 2048,
        "md5": "098f6bcd4621d373cade4e832627b4f6",
        "sha1": "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3",
        "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    },
    {
        "size": 0,
        "md5": "d41d8cd98f00b204e9800998ecf8427e",
        "sha1": "da39a3ee5e6b4b0d3255bfef95601890afd80709",
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    },
]

# 示例文件元数据
SAMPLE_FILE_METAS = [
    {
        "hash_id": 1,
        "name": "document.txt",
        "path": "/home/user/documents/document.txt",
        "machine": "laptop",
        "created": datetime(2024, 1, 1, 10, 0, 0),
        "modified": datetime(2024, 1, 1, 10, 30, 0),
        "scanned": datetime(2024, 1, 1, 12, 0, 0),
        "operation": "ADD",
    },
    {
        "hash_id": 1,  # 同样的哈希ID，表示重复文件
        "name": "document_copy.txt",
        "path": "/backup/documents/document_copy.txt",
        "machine": "server",
        "created": datetime(2024, 1, 2, 9, 0, 0),
        "modified": datetime(2024, 1, 2, 9, 0, 0),
        "scanned": datetime(2024, 1, 2, 14, 0, 0),
        "operation": "ADD",
    },
    {
        "hash_id": 2,
        "name": "image.jpg",
        "path": "/home/user/pictures/image.jpg",
        "machine": "laptop",
        "created": datetime(2024, 1, 3, 15, 0, 0),
        "modified": datetime(2024, 1, 3, 15, 0, 0),
        "scanned": datetime(2024, 1, 3, 16, 0, 0),
        "operation": "ADD",
    },
    {
        "hash_id": 2,
        "name": "image.jpg",
        "path": "/home/user/pictures/image.jpg",
        "machine": "laptop",
        "created": datetime(2024, 1, 3, 15, 0, 0),
        "modified": datetime(2024, 1, 4, 10, 0, 0),  # 修改时间不同
        "scanned": datetime(2024, 1, 4, 11, 0, 0),
        "operation": "MOD",
    },
]

# 测试目录结构
TEST_DIRECTORY_STRUCTURE = {
    "documents": {
        "file1.txt": "This is the content of file 1",
        "file2.txt": "This is the content of file 2",
        "subdirectory": {
            "nested_file.txt": "Nested file content",
            "binary_file.bin": {"type": "binary", "size": 1024, "pattern": b"\x41\x42"},
        },
    },
    "images": {
        "photo1.jpg": {"type": "random", "size": 2048},
        "photo2.jpg": {"type": "random", "size": 4096},
    },
    "duplicates": {
        "original.txt": "Duplicate content",
        "copy1.txt": "Duplicate content",
        "copy2.txt": "Duplicate content",
    },
    "node_modules": {  # 应该被忽略的目录
        "package.json": '{"name": "test"}',
        "lib": {"index.js": "module.exports = {}"},
    },
    ".git": {  # 应该被忽略的目录
        "config": "git config content"
    },
}

# 测试用的忽略规则
TEST_IGNORE_RULES = """
# 测试忽略规则文件
node_modules
.git
__pycache__
*.tmp
*.log

# 包含路径分隔符的规则
/temp/
/cache/
/build/

# 注释应该被忽略
# 这是一个注释行
"""

# 测试配置
TEST_CONFIGS = {
    "basic": {
        "MACHINE_NAME": "test_machine",
        "SCANNED": datetime(2024, 1, 1, 12, 0, 0),
        "LOG_LEVEL": "DEBUG",
    },
    "production": {
        "MACHINE_NAME": "prod_server",
        "SCANNED": datetime(2024, 1, 1, 0, 0, 0),
        "LOG_LEVEL": "INFO",
    },
    "minimal": {"MACHINE_NAME": "minimal_test"},
}

# 性能测试数据
PERFORMANCE_TEST_SIZES = [
    1024,  # 1KB
    10 * 1024,  # 10KB
    100 * 1024,  # 100KB
    1024 * 1024,  # 1MB
    10 * 1024 * 1024,  # 10MB (仅在需要时使用)
]

# 并发测试配置
CONCURRENCY_TEST_CONFIG = {
    "thread_counts": [1, 2, 4, 8],
    "file_counts": [10, 50, 100],
    "timeout": 30.0,
}

# 数据库测试数据
DATABASE_TEST_DATA = {
    "small_dataset": {
        "file_count": 10,
        "hash_count": 8,  # 有些文件内容相同
        "machines": ["laptop", "desktop"],
    },
    "medium_dataset": {
        "file_count": 100,
        "hash_count": 80,
        "machines": ["laptop", "desktop", "server"],
    },
    "large_dataset": {
        "file_count": 1000,
        "hash_count": 800,
        "machines": ["laptop", "desktop", "server", "backup"],
    },
}

# 错误测试场景
ERROR_TEST_SCENARIOS = [
    {
        "name": "permission_denied",
        "description": "测试权限被拒绝的情况",
        "file_permission": 0o000,
    },
    {
        "name": "file_not_found",
        "description": "测试文件不存在的情况",
        "file_exists": False,
    },
    {
        "name": "disk_full",
        "description": "测试磁盘空间不足的情况",
        "simulate_disk_full": True,
    },
    {
        "name": "database_locked",
        "description": "测试数据库被锁定的情况",
        "lock_database": True,
    },
]

# 真实世界的文件类型分布（用于更真实的测试）
REALISTIC_FILE_DISTRIBUTION = {
    "documents": {
        "extensions": [".txt", ".doc", ".docx", ".pdf", ".rtf"],
        "size_range": (1024, 1024 * 1024),  # 1KB - 1MB
        "count": 20,
    },
    "images": {
        "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp"],
        "size_range": (100 * 1024, 10 * 1024 * 1024),  # 100KB - 10MB
        "count": 15,
    },
    "videos": {
        "extensions": [".mp4", ".avi", ".mov", ".mkv"],
        "size_range": (50 * 1024 * 1024, 2 * 1024 * 1024 * 1024),  # 50MB - 2GB
        "count": 5,
    },
    "code": {
        "extensions": [".py", ".js", ".html", ".css", ".java", ".cpp"],
        "size_range": (512, 100 * 1024),  # 512B - 100KB
        "count": 30,
    },
    "archives": {
        "extensions": [".zip", ".tar", ".gz", ".rar"],
        "size_range": (1024 * 1024, 100 * 1024 * 1024),  # 1MB - 100MB
        "count": 10,
    },
}

# 预期的测试结果
EXPECTED_TEST_RESULTS = {
    "empty_file_hashes": {
        "md5": "d41d8cd98f00b204e9800998ecf8427e",
        "sha1": "da39a3ee5e6b4b0d3255bfef95601890afd80709",
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    },
    "hello_world_hashes": {
        "md5": "ed076287532e86365e841e92bfc50d8c",
        "sha1": "2aae6c35c94fcfb415dbe95f408b9ce91ee846ed",
        "sha256": "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
    },
}
