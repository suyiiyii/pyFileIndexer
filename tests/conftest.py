import tempfile
from pathlib import Path
from datetime import datetime
from typing import Generator, Dict, Any
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "pyFileIndexer"))

from database import DatabaseManager, Base
from models import FileHash, FileMeta
from config import settings


@pytest.fixture(scope="session")
def temp_dir() -> Generator[Path, None, None]:
    """创建临时目录用于测试"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def test_db_path(temp_dir: Path) -> Path:
    """创建测试数据库文件路径"""
    return temp_dir / "test.db"


@pytest.fixture
def memory_db_manager() -> Generator[DatabaseManager, None, None]:
    """创建内存数据库管理器"""
    db_manager = DatabaseManager()
    db_manager.init("sqlite:///:memory:")
    yield db_manager
    # 清理
    if db_manager.engine:
        db_manager.engine.dispose()


@pytest.fixture
def file_db_manager(test_db_path: Path) -> Generator[DatabaseManager, None, None]:
    """创建文件数据库管理器"""
    db_manager = DatabaseManager()
    db_manager.init(f"sqlite:///{test_db_path}")
    yield db_manager
    # 清理
    if db_manager.engine:
        db_manager.engine.dispose()
    if test_db_path.exists():
        test_db_path.unlink()


@pytest.fixture
def sample_file_hash() -> FileHash:
    """创建示例文件哈希对象"""
    return FileHash(
        size=1024,
        md5="d41d8cd98f00b204e9800998ecf8427e",
        sha1="da39a3ee5e6b4b0d3255bfef95601890afd80709",
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


@pytest.fixture
def sample_file_meta() -> FileMeta:
    """创建示例文件元数据对象"""
    return FileMeta(
        hash_id=1,
        name="test_file.txt",
        path="/tmp/test_file.txt",
        machine="test_machine",
        created=datetime(2024, 1, 1, 12, 0, 0),
        modified=datetime(2024, 1, 1, 12, 0, 0),
        scanned=datetime(2024, 1, 1, 12, 0, 0),
        operation="ADD"
    )


@pytest.fixture
def test_files(temp_dir: Path) -> Dict[str, Path]:
    """创建测试文件"""
    files = {}

    # 创建不同大小的测试文件
    small_file = temp_dir / "small.txt"
    small_file.write_text("Hello World")
    files["small"] = small_file

    # 创建较大的文件
    large_file = temp_dir / "large.txt"
    large_file.write_text("X" * 10000)
    files["large"] = large_file

    # 创建空文件
    empty_file = temp_dir / "empty.txt"
    empty_file.touch()
    files["empty"] = empty_file

    # 创建二进制文件
    binary_file = temp_dir / "binary.bin"
    binary_file.write_bytes(b'\x00\x01\x02\x03' * 256)
    files["binary"] = binary_file

    # 创建重复内容的文件
    duplicate_file = temp_dir / "duplicate.txt"
    duplicate_file.write_text("Hello World")  # 与 small.txt 内容相同
    files["duplicate"] = duplicate_file

    return files


@pytest.fixture
def mock_settings(monkeypatch) -> None:
    """模拟配置设置"""
    # 使用环境变量而不是直接设置属性
    monkeypatch.setenv("DYNACONF_MACHINE_NAME", "test_machine")
    monkeypatch.setenv("DYNACONF_SCANNED", "2024-01-01T12:00:00")


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch, temp_dir):
    """设置测试环境"""
    # 设置临时工作目录
    monkeypatch.chdir(temp_dir)

    # 设置环境变量
    monkeypatch.setenv("DYNACONF_MACHINE_NAME", "test_machine")
    monkeypatch.setenv("DYNACONF_SCANNED", "2024-01-01T12:00:00")


@pytest.fixture
def ignore_file_content() -> str:
    """返回 .ignore 文件的测试内容"""
    return """# 测试忽略文件
node_modules
.git
__pycache__
/temp/
/cache/
*.log
*.tmp"""


@pytest.fixture
def create_ignore_file(temp_dir: Path, ignore_file_content: str) -> Path:
    """创建 .ignore 文件"""
    ignore_file = temp_dir / ".ignore"
    ignore_file.write_text(ignore_file_content)
    return ignore_file


@pytest.fixture
def complex_directory_structure(temp_dir: Path) -> Dict[str, Path]:
    """创建复杂的目录结构用于测试"""
    structure = {}

    # 创建主目录
    main_dir = temp_dir / "main"
    main_dir.mkdir()
    structure["main"] = main_dir

    # 创建子目录
    sub_dir = main_dir / "subdir"
    sub_dir.mkdir()
    structure["subdir"] = sub_dir

    # 创建需要忽略的目录
    ignore_dir = main_dir / "node_modules"
    ignore_dir.mkdir()
    structure["ignore_dir"] = ignore_dir

    # 在各目录中创建文件
    (main_dir / "file1.txt").write_text("content1")
    (sub_dir / "file2.txt").write_text("content2")
    (ignore_dir / "file3.txt").write_text("content3")

    structure["file1"] = main_dir / "file1.txt"
    structure["file2"] = sub_dir / "file2.txt"
    structure["file3"] = ignore_dir / "file3.txt"

    return structure


# 用于并发测试的工具
@pytest.fixture
def thread_count() -> int:
    """返回用于并发测试的线程数"""
    return 4


# 用于性能测试的配置
@pytest.fixture
def performance_test_size() -> int:
    """返回性能测试的数据大小"""
    return 1000  # 可以根据需要调整