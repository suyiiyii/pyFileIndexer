import datetime
import io
import os
import tempfile
import zipfile
import tarfile
from pathlib import Path


from pyFileIndexer.archive_scanner import (
    is_archive_file,
    get_archive_type,
    ArchiveEntry,
    ZipArchiveScanner,
    TarArchiveScanner,
    create_archive_scanner,
    calculate_hash_from_data,
)


class TestArchiveDetection:
    """测试压缩包检测功能"""

    def test_is_archive_file(self):
        """测试压缩包文件检测"""
        assert is_archive_file("test.zip")
        assert is_archive_file("TEST.ZIP")  # 大小写不敏感
        assert is_archive_file("test.tar")
        assert is_archive_file("test.tar.gz")
        assert is_archive_file("test.tgz")
        assert is_archive_file("test.tar.bz2")
        assert is_archive_file("test.tbz2")
        assert is_archive_file("test.tar.xz")
        assert is_archive_file("test.txz")
        assert is_archive_file("test.rar")

        # 非压缩包文件
        assert not is_archive_file("test.txt")
        assert not is_archive_file("test.py")
        assert not is_archive_file("test")

    def test_get_archive_type(self):
        """测试获取压缩包类型"""
        assert get_archive_type("test.zip") == "zip"
        assert get_archive_type("test.tar") == "tar"
        assert get_archive_type("test.tar.gz") == "tar"
        assert get_archive_type("test.rar") == "rar"
        assert get_archive_type("test.txt") is None


class TestArchiveEntry:
    """测试压缩包条目"""

    def test_archive_entry_creation(self):
        """测试创建压缩包条目"""
        modified = datetime.datetime.now()
        entry = ArchiveEntry("test.txt", 100, modified)

        assert entry.name == "test.txt"
        assert entry.size == 100
        assert entry.modified == modified
        assert not entry.is_dir

    def test_archive_entry_with_data_reader(self):
        """测试带数据读取器的压缩包条目"""
        test_data = b"Hello, World!"
        reader = lambda: test_data

        entry = ArchiveEntry(
            "test.txt", len(test_data), datetime.datetime.now(), data_reader=reader
        )
        assert entry.read_data() == test_data


class TestZipArchiveScanner:
    """测试ZIP压缩包扫描器"""

    def create_test_zip(self, files_data):
        """创建测试用的ZIP文件"""
        temp_file = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        with zipfile.ZipFile(temp_file.name, "w") as zip_file:
            for filename, data in files_data.items():
                zip_file.writestr(filename, data)
        return temp_file.name

    def test_zip_scanner_creation(self):
        """测试ZIP扫描器创建"""
        zip_path = self.create_test_zip({"test.txt": "Hello"})
        try:
            scanner = ZipArchiveScanner(zip_path)
            assert scanner.archive_path == Path(zip_path)
        finally:
            os.unlink(zip_path)

    def test_zip_scan_entries(self):
        """测试扫描ZIP文件条目"""
        files_data = {
            "file1.txt": "Content of file 1",
            "dir/file2.txt": "Content of file 2",
            "file3.py": "print('Hello')",
        }

        zip_path = self.create_test_zip(files_data)
        try:
            scanner = ZipArchiveScanner(zip_path)
            entries = list(scanner.scan_entries())

            assert len(entries) == 3
            entry_names = [entry.name for entry in entries]
            assert "file1.txt" in entry_names
            assert "dir/file2.txt" in entry_names
            assert "file3.py" in entry_names

            # 测试读取文件数据
            file1_entry = next(entry for entry in entries if entry.name == "file1.txt")
            assert file1_entry.read_data().decode() == "Content of file 1"

        finally:
            os.unlink(zip_path)

    def test_zip_virtual_path(self):
        """测试虚拟路径创建"""
        zip_path = self.create_test_zip({"test.txt": "Hello"})
        try:
            scanner = ZipArchiveScanner(zip_path)
            virtual_path = scanner.create_virtual_path("test.txt")
            expected = f"{Path(zip_path).as_posix()}::test.txt"
            assert virtual_path == expected
        finally:
            os.unlink(zip_path)

    def test_zip_large_file_skip(self):
        """测试跳过过大文件"""
        # 创建一个大的数据字符串（超过默认限制）
        large_data = "x" * (200 * 1024 * 1024)  # 200MB
        zip_path = self.create_test_zip({"large.txt": large_data, "small.txt": "small"})

        try:
            scanner = ZipArchiveScanner(zip_path)
            entries = list(scanner.scan_entries())

            # 应该只有小文件被扫描
            assert len(entries) == 1
            assert entries[0].name == "small.txt"

        finally:
            os.unlink(zip_path)


class TestTarArchiveScanner:
    """测试TAR压缩包扫描器"""

    def create_test_tar(self, files_data):
        """创建测试用的TAR文件"""
        temp_file = tempfile.NamedTemporaryFile(suffix=".tar", delete=False)
        with tarfile.open(temp_file.name, "w") as tar_file:
            for filename, data in files_data.items():
                info = tarfile.TarInfo(name=filename)
                info.size = len(data.encode())
                tar_file.addfile(info, io.BytesIO(data.encode()))
        return temp_file.name

    def test_tar_scan_entries(self):
        """测试扫描TAR文件条目"""
        files_data = {
            "file1.txt": "Content of file 1",
            "dir/file2.txt": "Content of file 2",
        }

        tar_path = self.create_test_tar(files_data)
        try:
            scanner = TarArchiveScanner(tar_path)
            entries = list(scanner.scan_entries())

            assert len(entries) == 2
            entry_names = [entry.name for entry in entries]
            assert "file1.txt" in entry_names
            assert "dir/file2.txt" in entry_names

        finally:
            os.unlink(tar_path)


class TestArchiveScannerFactory:
    """测试压缩包扫描器工厂"""

    def test_create_zip_scanner(self):
        """测试创建ZIP扫描器"""
        scanner = create_archive_scanner("test.zip")
        assert isinstance(scanner, ZipArchiveScanner)

    def test_create_tar_scanner(self):
        """测试创建TAR扫描器"""
        scanner = create_archive_scanner("test.tar")
        assert isinstance(scanner, TarArchiveScanner)

        scanner = create_archive_scanner("test.tar.gz")
        assert isinstance(scanner, TarArchiveScanner)

    def test_create_unsupported_scanner(self):
        """测试不支持的格式返回None"""
        scanner = create_archive_scanner("test.txt")
        assert scanner is None


class TestHashCalculation:
    """测试哈希计算"""

    def test_calculate_hash_from_data(self):
        """测试从数据计算哈希"""
        test_data = b"Hello, World!"
        hashes = calculate_hash_from_data(test_data)

        assert "md5" in hashes
        assert "sha1" in hashes
        assert "sha256" in hashes

        # 验证哈希值长度
        assert len(hashes["md5"]) == 32
        assert len(hashes["sha1"]) == 40
        assert len(hashes["sha256"]) == 64

    def test_empty_data_hash(self):
        """测试空数据的哈希计算"""
        hashes = calculate_hash_from_data(b"")

        assert hashes["md5"] == "d41d8cd98f00b204e9800998ecf8427e"
        assert hashes["sha1"] == "da39a3ee5e6b4b0d3255bfef95601890afd80709"


class TestFileMetaCreation:
    """测试文件元数据创建"""

    def test_create_file_meta(self):
        """测试创建压缩包内文件的元数据"""
        zip_path = "/test/archive.zip"
        scanner = ZipArchiveScanner(zip_path)

        modified = datetime.datetime.now()
        scanned = datetime.datetime.now()
        entry = ArchiveEntry("test.txt", 100, modified)

        meta = scanner.create_file_meta(entry, "test-machine", scanned)

        assert meta.name == "test.txt"
        assert meta.path == f"{zip_path}::test.txt"
        assert meta.machine == "test-machine"
        assert meta.is_archived == 1
        assert meta.archive_path == str(Path(zip_path).absolute())
        assert meta.created == modified
        assert meta.modified == modified
        assert meta.scanned == scanned
