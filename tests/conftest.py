import tempfile
from pathlib import Path
from datetime import datetime
from typing import Generator, Dict, Any, Optional
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
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
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
        operation="ADD",
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
    binary_file.write_bytes(b"\x00\x01\x02\x03" * 256)
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


# 命令行集成测试相关的fixtures
@pytest.fixture
def cli_main_script_path() -> Path:
    """返回主脚本的路径"""
    return Path(__file__).parent.parent / "pyFileIndexer" / "main.py"


@pytest.fixture
def cli_test_directory(temp_dir: Path) -> Dict[str, Path]:
    """创建完整的CLI测试目录结构"""
    # 创建主测试目录
    test_root = temp_dir / "cli_test_root"
    test_root.mkdir(exist_ok=True)

    result = {"root": test_root}

    # 创建各种类型的文件
    files = {
        "text1.txt": "Hello World from text1",
        "text2.txt": "Hello World from text2",
        "duplicate1.txt": "Duplicate content",
        "duplicate2.txt": "Duplicate content",  # 与duplicate1.txt内容相同
        "empty.txt": "",
        "large.txt": "X" * 50000,  # 50KB文件
    }

    for filename, content in files.items():
        file_path = test_root / filename
        file_path.write_text(content)
        result[filename] = file_path

    # 创建二进制文件
    binary_file = test_root / "binary.bin"
    binary_file.write_bytes(b"\x00\x01\x02\x03\x04\x05" * 1000)
    result["binary.bin"] = binary_file

    # 创建子目录和嵌套文件
    subdir1 = test_root / "subdir1"
    subdir1.mkdir(exist_ok=True)
    result["subdir1"] = subdir1

    subfile1 = subdir1 / "nested1.txt"
    subfile1.write_text("Nested file content 1")
    result["nested1.txt"] = subfile1

    # 创建更深层的嵌套
    subdir2 = subdir1 / "deeper"
    subdir2.mkdir(exist_ok=True)
    result["deeper"] = subdir2

    subfile2 = subdir2 / "deep_nested.txt"
    subfile2.write_text("Deep nested content")
    result["deep_nested.txt"] = subfile2

    # 创建应该被忽略的目录和文件
    ignore_dir1 = test_root / "node_modules"
    ignore_dir1.mkdir(exist_ok=True)
    result["node_modules"] = ignore_dir1

    ignore_file1 = ignore_dir1 / "should_be_ignored.js"
    ignore_file1.write_text("console.log('ignored');")
    result["should_be_ignored.js"] = ignore_file1

    # 创建以点开头的目录（应该被忽略）
    dot_dir = test_root / ".git"
    dot_dir.mkdir(exist_ok=True)
    result[".git"] = dot_dir

    dot_file = dot_dir / "config"
    dot_file.write_text("git config content")
    result["git_config"] = dot_file

    # 创建以下划线开头的目录（应该被忽略）
    underscore_dir = test_root / "_cache"
    underscore_dir.mkdir(exist_ok=True)
    result["_cache"] = underscore_dir

    underscore_file = underscore_dir / "cache_file.tmp"
    underscore_file.write_text("cache content")
    result["cache_file.tmp"] = underscore_file

    return result


@pytest.fixture
def cli_ignore_file_content() -> str:
    """返回用于CLI测试的.ignore文件内容"""
    return """# CLI测试忽略规则
node_modules
__pycache__
.DS_Store
/temp/
/logs/
*.log
*.tmp"""


@pytest.fixture
def cli_test_with_ignore(
    cli_test_directory: Dict[str, Path], cli_ignore_file_content: str
) -> Dict[str, Path]:
    """创建包含.ignore文件的CLI测试目录"""
    test_root = cli_test_directory["root"]

    # 创建.ignore文件
    ignore_file = test_root / ".ignore"
    ignore_file.write_text(cli_ignore_file_content)
    cli_test_directory[".ignore"] = ignore_file

    # 创建应该被忽略的额外文件
    temp_dir = test_root / "temp"
    temp_dir.mkdir(exist_ok=True)
    cli_test_directory["temp"] = temp_dir

    temp_file = temp_dir / "temp_file.txt"
    temp_file.write_text("This should be ignored")
    cli_test_directory["temp_file.txt"] = temp_file

    # 创建.log文件（应该被忽略）
    log_file = test_root / "app.log"
    log_file.write_text("Log content")
    cli_test_directory["app.log"] = log_file

    return cli_test_directory


# 压缩包测试相关的fixtures
@pytest.fixture
def archive_test_files() -> Dict[str, str]:
    """定义压缩包内的测试文件结构和内容"""
    return {
        # 基本文件
        "readme.txt": "This is a readme file in the archive",
        "config.json": '{"name": "test", "version": "1.0"}',
        "empty.txt": "",
        # 子目录中的文件
        "docs/guide.md": "# User Guide\n\nThis is a guide.",
        "docs/api.txt": "API documentation content",
        # 更深层嵌套
        "src/main/java/App.java": "public class App { }",
        "src/test/TestApp.java": "public class TestApp { }",
        # 二进制文件内容（模拟）
        "data/binary.bin": "binary_content_placeholder",
        # 重复内容文件（用于测试哈希共享）
        "duplicate1.txt": "duplicate content for testing",
        "copy/duplicate2.txt": "duplicate content for testing",
        # 特殊字符文件名
        "files/中文文件.txt": "Chinese filename test",
        "files/spécial-chars.txt": "Special characters test",
    }


@pytest.fixture
def create_zip_archive(temp_dir: Path, archive_test_files: Dict[str, str]) -> Path:
    """创建包含测试文件的ZIP压缩包"""
    import zipfile

    zip_path = temp_dir / "test_archive.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path, content in archive_test_files.items():
            if file_path.endswith(".bin"):
                # 二进制文件使用特定的二进制内容
                binary_content = b"\x00\x01\x02\x03\x04\x05" * 100
                zf.writestr(file_path, binary_content)
            else:
                zf.writestr(file_path, content.encode("utf-8"))

    return zip_path


@pytest.fixture
def create_tar_archives(
    temp_dir: Path, archive_test_files: Dict[str, str]
) -> Dict[str, Path]:
    """创建各种TAR格式的压缩包"""
    import tarfile
    import io

    archives = {}
    tar_formats = {
        "tar": ("test_archive.tar", ""),
        "tar.gz": ("test_archive.tar.gz", "gz"),
        "tar.bz2": ("test_archive.tar.bz2", "bz2"),
        "tar.xz": ("test_archive.tar.xz", "xz"),
    }

    for format_name, (filename, compression) in tar_formats.items():
        archive_path = temp_dir / filename
        mode = f"w:{compression}" if compression else "w"

        try:
            with tarfile.open(archive_path, mode) as tf:
                for file_path, content in archive_test_files.items():
                    info = tarfile.TarInfo(name=file_path)

                    if file_path.endswith(".bin"):
                        # 二进制文件
                        binary_content = b"\x00\x01\x02\x03\x04\x05" * 100
                        info.size = len(binary_content)
                        tf.addfile(info, io.BytesIO(binary_content))
                    else:
                        # 文本文件
                        content_bytes = content.encode("utf-8")
                        info.size = len(content_bytes)
                        tf.addfile(info, io.BytesIO(content_bytes))

            archives[format_name] = archive_path
        except Exception as e:
            # 如果某种压缩格式不支持，跳过
            print(f"Skipping {format_name}: {e}")

    return archives


@pytest.fixture
def create_rar_archive(
    temp_dir: Path, archive_test_files: Dict[str, str]
) -> Optional[Path]:
    """创建RAR压缩包（如果可能的话）"""
    try:
        import rarfile

        # RAR文件的创建比较复杂，需要外部工具
        # 这里我们创建一个简单的测试用例，或者跳过
        # 实际项目中可能需要预先准备好的RAR文件
        return None  # 暂时返回None，表示跳过RAR测试
    except ImportError:
        return None


@pytest.fixture
def cli_archive_test_directory(
    temp_dir: Path, create_zip_archive: Path, create_tar_archives: Dict[str, Path]
) -> Dict[str, Path]:
    """创建包含各种压缩包的测试目录"""
    test_root = temp_dir / "archive_test_root"
    test_root.mkdir(exist_ok=True)

    result = {"root": test_root}

    # 复制ZIP文件到测试目录
    zip_dest = test_root / "sample.zip"
    import shutil

    shutil.copy2(create_zip_archive, zip_dest)
    result["zip_file"] = zip_dest

    # 复制TAR文件到测试目录
    for format_name, tar_path in create_tar_archives.items():
        if tar_path.exists():
            dest_name = f"sample.{format_name.replace('.', '_')}"
            dest_path = test_root / dest_name
            shutil.copy2(tar_path, dest_path)
            result[f"tar_{format_name.replace('.', '_')}"] = dest_path

    # 创建一些普通文件以便混合测试
    (test_root / "normal.txt").write_text("Normal file content")
    result["normal_file"] = test_root / "normal.txt"

    (test_root / "duplicate_external.txt").write_text("duplicate content for testing")
    result["duplicate_external"] = test_root / "duplicate_external.txt"

    return result


@pytest.fixture
def large_archive_test_directory(temp_dir: Path) -> Dict[str, Path]:
    """创建用于测试大小限制的压缩包目录"""
    import zipfile

    test_root = temp_dir / "large_archive_test"
    test_root.mkdir(exist_ok=True)

    result = {"root": test_root}

    # 创建一个大的压缩包（超过500MB限制）
    large_zip = test_root / "large_archive.zip"
    with zipfile.ZipFile(large_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        # 写入一个大文件
        large_content = b"X" * (600 * 1024 * 1024)  # 600MB
        zf.writestr("large_file.bin", large_content)

    result["large_zip"] = large_zip

    # 创建一个包含大文件的普通大小压缩包
    normal_zip_large_files = test_root / "normal_with_large_files.zip"
    with zipfile.ZipFile(normal_zip_large_files, "w", zipfile.ZIP_DEFLATED) as zf:
        # 小文件
        zf.writestr("small.txt", "small content")
        # 大文件（超过100MB的单文件限制）
        large_file_content = b"Y" * (150 * 1024 * 1024)  # 150MB
        zf.writestr("large_internal_file.bin", large_file_content)
        # 另一个小文件
        zf.writestr("another_small.txt", "another small content")

    result["normal_zip_large_files"] = normal_zip_large_files

    return result


@pytest.fixture(autouse=True)
def clear_batch_processor():
    """在每个测试前后清理批量处理器"""
    try:
        from main import batch_processor

        batch_processor.clear()
    except ImportError:
        pass

    yield  # 运行测试

    try:
        from main import batch_processor

        batch_processor.clear()
    except ImportError:
        pass
