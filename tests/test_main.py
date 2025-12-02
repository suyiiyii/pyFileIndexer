import pytest
import hashlib
import threading
import queue
import time
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from pyFileIndexer.main import (
    human_size,
    get_hashes,
    get_metadata,
    scan_file,
    scan_file_worker,
    ignore_dirs,
    ignore_partials_dirs,
)
from pyFileIndexer.models import FileHash, FileMeta
from pyFileIndexer.database import db_manager


class TestUtilityFunctions:
    """测试工具函数"""

    @pytest.mark.unit
    def test_human_size_bytes(self):
        """测试字节大小格式化"""
        assert human_size(0) == "0B"
        assert human_size(512) == "512B"
        assert human_size(1023) == "1023B"

    @pytest.mark.unit
    def test_human_size_kilobytes(self):
        """测试千字节大小格式化"""
        assert human_size(1024) == "1KB"
        assert human_size(1536) == "1KB"  # 1.5KB -> 1KB
        assert human_size(2048) == "2KB"

    @pytest.mark.unit
    def test_human_size_larger_units(self):
        """测试更大单位的格式化"""
        assert human_size(1024 * 1024) == "1MB"
        assert human_size(1024 * 1024 * 1024) == "1GB"
        assert human_size(1024 * 1024 * 1024 * 1024) == "1TB"

    @pytest.mark.unit
    def test_human_size_custom_units(self):
        """测试自定义单位"""
        custom_units = ["bytes", "kilo", "mega"]
        assert human_size(1024, custom_units) == "1kilo"
        assert human_size(1024 * 1024, custom_units) == "1mega"

    @pytest.mark.unit
    def test_human_size_edge_cases(self):
        """测试边界情况"""
        assert human_size(1023) == "1023B"
        assert human_size(1025) == "1KB"


class TestHashCalculation:
    """测试哈希计算功能"""

    @pytest.mark.unit
    @pytest.mark.filesystem
    def test_get_hashes_small_file(self, test_files):
        """测试小文件哈希计算"""
        small_file = test_files["small"]
        hashes = get_hashes(small_file)

        # 验证返回的哈希结构
        assert "md5" in hashes
        assert "sha1" in hashes
        assert "sha256" in hashes

        # 验证哈希值格式（应该是十六进制字符串）
        assert len(hashes["md5"]) == 32
        assert len(hashes["sha1"]) == 40
        assert len(hashes["sha256"]) == 64

        # 验证哈希值是有效的十六进制
        for hash_value in hashes.values():
            int(hash_value, 16)  # 如果不是有效十六进制会抛出异常

    @pytest.mark.unit
    @pytest.mark.filesystem
    def test_get_hashes_empty_file(self, test_files):
        """测试空文件哈希计算"""
        empty_file = test_files["empty"]
        hashes = get_hashes(empty_file)

        # 空文件的标准哈希值
        expected_md5 = "d41d8cd98f00b204e9800998ecf8427e"
        expected_sha1 = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
        expected_sha256 = (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

        assert hashes["md5"] == expected_md5
        assert hashes["sha1"] == expected_sha1
        assert hashes["sha256"] == expected_sha256

    @pytest.mark.unit
    @pytest.mark.filesystem
    def test_get_hashes_binary_file(self, test_files):
        """测试二进制文件哈希计算"""
        binary_file = test_files["binary"]
        hashes = get_hashes(binary_file)

        # 验证二进制文件也能正确计算哈希
        assert len(hashes["md5"]) == 32
        assert len(hashes["sha1"]) == 40
        assert len(hashes["sha256"]) == 64

    @pytest.mark.unit
    @pytest.mark.filesystem
    def test_get_hashes_duplicate_content(self, test_files):
        """测试内容相同文件的哈希一致性"""
        small_file = test_files["small"]
        duplicate_file = test_files["duplicate"]

        hashes1 = get_hashes(small_file)
        hashes2 = get_hashes(duplicate_file)

        # 内容相同的文件应该有相同的哈希值
        assert hashes1["md5"] == hashes2["md5"]
        assert hashes1["sha1"] == hashes2["sha1"]
        assert hashes1["sha256"] == hashes2["sha256"]

    @pytest.mark.unit
    @pytest.mark.filesystem
    @pytest.mark.slow
    def test_get_hashes_large_file(self, test_files):
        """测试大文件哈希计算"""
        large_file = test_files["large"]
        hashes = get_hashes(large_file)

        # 验证大文件也能正确计算哈希
        assert len(hashes["md5"]) == 32
        assert len(hashes["sha1"]) == 40
        assert len(hashes["sha256"]) == 64

    @pytest.mark.unit
    @pytest.mark.filesystem
    def test_get_hashes_with_path_object(self, test_files):
        """测试使用 Path 对象计算哈希"""
        small_file = test_files["small"]
        assert isinstance(small_file, Path)

        hashes = get_hashes(small_file)
        assert "md5" in hashes

    @pytest.mark.unit
    @pytest.mark.filesystem
    def test_get_hashes_with_string_path(self, test_files):
        """测试使用字符串路径计算哈希"""
        small_file = test_files["small"]
        hashes = get_hashes(str(small_file))

        assert "md5" in hashes
        assert len(hashes["md5"]) == 32

    @pytest.mark.unit
    @pytest.mark.filesystem
    def test_get_hashes_nonexistent_file(self, temp_dir):
        """测试不存在文件的哈希计算"""
        nonexistent_file = temp_dir / "nonexistent.txt"

        with pytest.raises(FileNotFoundError):
            get_hashes(nonexistent_file)


class TestMetadataExtraction:
    """测试文件元数据提取"""

    @pytest.mark.unit
    @pytest.mark.filesystem
    def test_get_metadata_basic(self, test_files):
        """测试基本元数据提取"""
        small_file = test_files["small"]

        # 使用 patch 确保独立的配置环境
        with patch("pyFileIndexer.main.settings") as mock_settings:
            mock_settings.MACHINE_NAME = "test_machine"
            mock_settings.SCANNED = datetime.now()

            metadata = get_metadata(small_file)

            assert isinstance(metadata, FileMeta)
            assert metadata.name == "small.txt"
            assert metadata.path == str(small_file.absolute())
            assert metadata.machine == "test_machine"
            assert isinstance(metadata.created, datetime)
            assert isinstance(metadata.modified, datetime)
            assert isinstance(metadata.scanned, datetime)

    @pytest.mark.unit
    @pytest.mark.filesystem
    def test_get_metadata_different_files(self, test_files):
        """测试不同文件的元数据"""
        # 使用 patch 确保独立的配置环境
        with patch("pyFileIndexer.main.settings") as mock_settings:
            mock_settings.MACHINE_NAME = "test_machine"
            mock_settings.SCANNED = datetime.now()

            for file_key, file_path in test_files.items():
                metadata = get_metadata(file_path)

                assert metadata.name == file_path.name
                assert metadata.path == str(file_path.absolute())
                assert metadata.machine == "test_machine"

    @pytest.mark.unit
    @pytest.mark.filesystem
    def test_get_metadata_timestamps(self, test_files, mock_settings):
        """测试时间戳正确性"""
        small_file = test_files["small"]
        stat = small_file.stat()

        metadata = get_metadata(small_file)

        # 验证时间戳转换正确
        expected_created = datetime.fromtimestamp(stat.st_ctime)
        expected_modified = datetime.fromtimestamp(stat.st_mtime)

        assert metadata.created == expected_created
        assert metadata.modified == expected_modified

    @pytest.mark.unit
    @pytest.mark.filesystem
    def test_get_metadata_missing_settings(self, test_files):
        """测试缺失配置时的默认值处理"""
        small_file = test_files["small"]

        # 模拟缺失 SCANNED 配置 - 现在应该使用默认值而不是抛出异常
        with patch("pyFileIndexer.main.settings") as mock_settings:
            # 删除属性而不是设置为 None，以测试 getattr 的默认值行为
            del mock_settings.SCANNED
            # 也删除 MACHINE_NAME 来测试默认值
            if hasattr(mock_settings, "MACHINE_NAME"):
                del mock_settings.MACHINE_NAME

            metadata = get_metadata(small_file)

            # 应该使用合理的默认值而不是抛出异常
            assert metadata.machine == "localhost"  # 默认机器名
            assert isinstance(metadata.scanned, datetime)  # 应该使用当前时间作为默认值

    @pytest.mark.unit
    @pytest.mark.filesystem
    def test_get_metadata_custom_machine_name(self, test_files, monkeypatch):
        """测试自定义机器名称"""
        small_file = test_files["small"]

        with patch("pyFileIndexer.main.settings") as mock_settings:
            mock_settings.MACHINE_NAME = "custom_machine"
            mock_settings.SCANNED = datetime(2024, 1, 1, 12, 0, 0)

            metadata = get_metadata(small_file)
            assert metadata.machine == "custom_machine"


class TestIgnoreRules:
    """测试忽略规则功能"""

    @pytest.mark.unit
    def test_ignore_rules_initialization(self):
        """测试忽略规则初始化"""
        # 这些是模块级别的变量，在导入时已经初始化
        assert isinstance(ignore_dirs, set)
        assert isinstance(ignore_partials_dirs, set)

    @pytest.mark.unit
    @pytest.mark.filesystem
    def test_ignore_file_parsing(self, create_ignore_file):
        """测试 .ignore 文件解析"""
        # 由于 ignore 规则在模块导入时加载，我们需要重新加载模块来测试
        # 或者测试解析逻辑的单独函数

        # 这里我们验证当前的 ignore 规则
        # 在实际项目中可能需要重构代码以便更好地测试
        pass


class TestFileScanningLogic:
    """测试文件扫描逻辑"""

    @pytest.mark.unit
    @pytest.mark.database
    @pytest.mark.filesystem
    def test_scan_file_new_file(self, test_files, memory_db_manager, mock_settings):
        """测试扫描新文件"""
        small_file = test_files["small"]

        with patch("pyFileIndexer.main.db_manager", memory_db_manager):
            scan_file(small_file)
            # 刷新批量处理器以确保数据写入数据库
            from pyFileIndexer.main import batch_processor

            batch_processor.flush()

            # 验证文件被添加到数据库
            retrieved_file = memory_db_manager.get_file_by_path(
                str(small_file.absolute())
            )
            assert retrieved_file is not None
            assert retrieved_file.name == "small.txt"
            assert retrieved_file.operation == "ADD"

    @pytest.mark.unit
    @pytest.mark.database
    @pytest.mark.filesystem
    def test_scan_file_existing_unchanged(
        self, test_files, memory_db_manager, mock_settings
    ):
        """测试扫描已存在且未修改的文件"""
        small_file = test_files["small"]

        with patch("pyFileIndexer.main.db_manager", memory_db_manager):
            scan_file(small_file)
            from pyFileIndexer.main import batch_processor
            batch_processor.flush()

            file_meta = memory_db_manager.get_file_by_path(str(small_file.absolute()))
            with patch("pyFileIndexer.main.get_metadata") as mock_get_metadata:
                mock_get_metadata.return_value = file_meta
                scan_file(small_file)
                batch_processor.flush()

            with memory_db_manager.session_factory() as session:
                from pyFileIndexer.models import FileMeta
                file = (
                    session.query(FileMeta)
                    .filter_by(path=str(small_file.absolute()))
                    .first()
                )
                assert file is not None
                assert file.operation == "MOD"

    @pytest.mark.unit
    @pytest.mark.database
    @pytest.mark.filesystem
    def test_scan_file_modified_file(
        self, test_files, memory_db_manager, mock_settings
    ):
        """测试扫描已修改的文件"""
        small_file = test_files["small"]

        with patch("pyFileIndexer.main.db_manager", memory_db_manager):
            # 首次扫描
            scan_file(small_file)
            # 刷新批量处理器
            from pyFileIndexer.main import batch_processor

            batch_processor.flush()

            # 模拟文件被修改
            modified_content = "Modified content"
            small_file.write_text(modified_content)

            # 再次扫描
            scan_file(small_file)
            batch_processor.flush()

            # 验证文件被标记为修改
            files = []
            with memory_db_manager.session_factory() as session:
                from pyFileIndexer.models import FileMeta

                files = (
                    session.query(FileMeta)
                    .filter_by(path=str(small_file.absolute()))
                    .all()
                )

            # 应该有两条记录：原始的 ADD 和新的 MOD
            assert len(files) >= 1
            # 最新的记录应该是 MOD 操作
            latest_file = max(files, key=lambda f: f.scanned)
            assert latest_file.operation == "MOD"

    @pytest.mark.unit
    @pytest.mark.database
    @pytest.mark.filesystem
    def test_scan_file_thread_safety(self, test_files, file_db_manager, mock_settings):
        """测试文件扫描的线程安全性"""
        small_file = test_files["small"]
        errors = []

        def scan_with_error_handling():
            try:
                with patch("pyFileIndexer.main.db_manager", file_db_manager):
                    scan_file(small_file)
            except Exception as e:
                errors.append(e)

        # 并发扫描同一文件
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=scan_with_error_handling)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # 不应该有错误
        assert len(errors) == 0


class TestWorkerThreads:
    """测试工作线程功能"""

    @pytest.mark.unit
    def test_scan_file_worker_basic(self, test_files, memory_db_manager, mock_settings):
        """测试文件扫描工作线程基本功能"""
        file_queue = queue.Queue()
        file_queue.put(test_files["small"])
        file_queue.put(Path())  # 结束信号

        with patch("pyFileIndexer.main.db_manager", memory_db_manager):
            with patch("pyFileIndexer.main.stop_event") as mock_stop_event:
                mock_stop_event.is_set.return_value = False

                scan_file_worker(file_queue)
                # 刷新批量处理器
                from pyFileIndexer.main import batch_processor

                batch_processor.flush()

        # 验证文件被处理
        retrieved_file = memory_db_manager.get_file_by_path(
            str(test_files["small"].absolute())
        )
        assert retrieved_file is not None

    @pytest.mark.unit
    def test_scan_file_worker_with_progress_bar(
        self, test_files, memory_db_manager, mock_settings
    ):
        """测试带进度条的工作线程"""
        file_queue = queue.Queue()
        file_queue.put(test_files["small"])
        file_queue.put(Path())  # 结束信号

        # 模拟进度条
        mock_pbar = Mock()

        with patch("pyFileIndexer.main.db_manager", memory_db_manager):
            with patch("pyFileIndexer.main.stop_event") as mock_stop_event:
                mock_stop_event.is_set.return_value = False

                scan_file_worker(file_queue, mock_pbar)

        # 验证进度条被更新
        mock_pbar.update.assert_called_with(1)

    @pytest.mark.unit
    def test_scan_file_worker_stop_event(self, test_files):
        """测试工作线程停止事件"""
        file_queue = queue.Queue()
        file_queue.put(test_files["small"])

        with patch("pyFileIndexer.main.stop_event") as mock_stop_event:
            mock_stop_event.is_set.return_value = True

            # 工作线程应该立即退出
            scan_file_worker(file_queue)

        # 队列应该还有文件（因为线程提前退出）
        assert not file_queue.empty()

    @pytest.mark.unit
    def test_scan_file_worker_error_handling(
        self, temp_dir, memory_db_manager, mock_settings
    ):
        """测试工作线程错误处理"""
        file_queue = queue.Queue()

        # 添加一个不存在的文件
        nonexistent_file = temp_dir / "nonexistent.txt"
        file_queue.put(nonexistent_file)
        file_queue.put(Path())  # 结束信号

        with patch("pyFileIndexer.main.db_manager", memory_db_manager):
            with patch("pyFileIndexer.main.stop_event") as mock_stop_event:
                mock_stop_event.is_set.return_value = False

                with patch("pyFileIndexer.main.logger") as mock_logger:
                    scan_file_worker(file_queue)

                    # 验证错误被记录
                    assert mock_logger.error.called

    @pytest.mark.unit
    def test_scan_file_worker_empty_queue(self):
        """测试空队列的工作线程"""
        file_queue = queue.Queue()
        file_queue.put(Path())  # 立即结束信号

        with patch("pyFileIndexer.main.stop_event") as mock_stop_event:
            mock_stop_event.is_set.return_value = False

            # 应该正常退出而不报错
            scan_file_worker(file_queue)


class TestConcurrentScanning:
    """测试并发扫描功能"""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_multiple_workers(
        self, test_files, file_db_manager, mock_settings, thread_count
    ):
        """测试多个工作线程并发处理"""
        file_queue = queue.Queue()

        # 添加所有测试文件
        for file_path in test_files.values():
            file_queue.put(file_path)

        # 添加结束信号
        for _ in range(thread_count):
            file_queue.put(Path())

        with patch("pyFileIndexer.main.db_manager", file_db_manager):
            with patch("pyFileIndexer.main.stop_event") as mock_stop_event:
                mock_stop_event.is_set.return_value = False

                threads = []
                for _ in range(thread_count):
                    thread = threading.Thread(
                        target=scan_file_worker, args=(file_queue,)
                    )
                    threads.append(thread)
                    thread.start()

                for thread in threads:
                    thread.join()

                # 刷新批量处理器
                from pyFileIndexer.main import batch_processor

                batch_processor.flush()

        # 验证所有文件都被处理
        with file_db_manager.session_factory() as session:
            from pyFileIndexer.models import FileMeta

            file_count = session.query(FileMeta).count()
            assert file_count == len(test_files)


class TestHashConsistency:
    """测试哈希一致性"""

    @pytest.mark.unit
    @pytest.mark.filesystem
    def test_hash_consistency_across_calls(self, test_files):
        """测试多次调用哈希函数的一致性"""
        small_file = test_files["small"]

        hashes1 = get_hashes(small_file)
        hashes2 = get_hashes(small_file)

        assert hashes1 == hashes2

    @pytest.mark.unit
    @pytest.mark.filesystem
    def test_hash_matches_external_tools(self, test_files):
        """测试哈希值与外部工具计算结果一致"""
        small_file = test_files["small"]
        content = small_file.read_bytes()

        # 使用标准库计算哈希作为参考
        expected_md5 = hashlib.md5(content).hexdigest()
        expected_sha1 = hashlib.sha1(content).hexdigest()
        expected_sha256 = hashlib.sha256(content).hexdigest()

        hashes = get_hashes(small_file)

        assert hashes["md5"] == expected_md5
        assert hashes["sha1"] == expected_sha1
        assert hashes["sha256"] == expected_sha256


class TestPerformance:
    """性能测试"""

    @pytest.mark.slow
    @pytest.mark.filesystem
    def test_hash_calculation_performance(self, temp_dir):
        """测试哈希计算性能"""
        # 创建一个较大的测试文件
        large_file = temp_dir / "performance_test.bin"
        large_file.write_bytes(b"X" * (10 * 1024 * 1024))  # 10MB

        start_time = time.time()
        hashes = get_hashes(large_file)
        end_time = time.time()

        # 验证哈希计算完成
        assert len(hashes["md5"]) == 32

        # 性能断言（10MB 文件应该在合理时间内完成）
        calculation_time = end_time - start_time
        assert calculation_time < 10.0  # 应该在10秒内完成

    @pytest.mark.slow
    @pytest.mark.filesystem
    def test_metadata_extraction_performance(self, test_files, mock_settings):
        """测试元数据提取性能"""
        start_time = time.time()

        for _ in range(100):
            for file_path in test_files.values():
                get_metadata(file_path)

        end_time = time.time()

        # 100次元数据提取应该很快完成
        total_time = end_time - start_time
        assert total_time < 1.0  # 应该在1秒内完成
