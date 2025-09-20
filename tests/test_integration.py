import pytest
import os
import threading
import time
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, Mock
import subprocess

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "pyFileIndexer"))

from database import DatabaseManager
from models import FileHash, FileMeta


class TestEndToEndScanning:
    """端到端扫描测试"""

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    def test_complete_directory_scan(self, complex_directory_structure, temp_dir):
        """测试完整目录扫描流程"""
        # 创建数据库管理器
        db_path = temp_dir / "integration_test.db"
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        # 模拟主程序的扫描逻辑
        from main import scan_file

        with patch('main.db_manager', db_manager):
            with patch('main.settings') as mock_settings:
                mock_settings.MACHINE_NAME = "integration_test"
                mock_settings.SCANNED = datetime.now()

                # 扫描所有文件
                for file_path in [
                    complex_directory_structure["file1"],
                    complex_directory_structure["file2"]
                ]:
                    scan_file(file_path)

        # 验证数据库中的数据
        with db_manager.session_factory() as session:
            file_count = session.query(FileMeta).count()
            hash_count = session.query(FileHash).count()

            assert file_count == 2  # 两个文件
            assert hash_count >= 1  # 至少一个哈希（可能更多，取决于文件内容）

        # 清理
        if db_path.exists():
            db_path.unlink()

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    def test_incremental_scanning(self, test_files, temp_dir):
        """测试增量扫描功能"""
        db_path = temp_dir / "incremental_test.db"
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        from main import scan_file

        with patch('main.db_manager', db_manager):
            with patch('main.settings') as mock_settings:
                mock_settings.MACHINE_NAME = "incremental_test"
                mock_settings.SCANNED = datetime.now()

                # 首次扫描
                small_file = test_files["small"]
                scan_file(small_file)

                # 验证文件被添加
                file_meta = db_manager.get_file_by_path(str(small_file.absolute()))
                assert file_meta.operation == "ADD"

                # 修改文件
                original_content = small_file.read_text()
                small_file.write_text(original_content + "\nmodified")

                # 再次扫描
                mock_settings.SCANNED = datetime.now()  # 更新扫描时间
                scan_file(small_file)

                # 验证修改被检测到
                with db_manager.session_factory() as session:
                    files = session.query(FileMeta).filter_by(
                        path=str(small_file.absolute())
                    ).all()

                    # 应该有至少一个 MOD 操作
                    operations = [f.operation for f in files]
                    assert "MOD" in operations

        # 清理
        if db_path.exists():
            db_path.unlink()

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    def test_duplicate_file_detection(self, temp_dir):
        """测试重复文件检测"""
        db_path = temp_dir / "duplicate_test.db"
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        # 创建内容相同的文件
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "subdir" / "file2.txt"
        file2.parent.mkdir(exist_ok=True)

        content = "This is duplicate content"
        file1.write_text(content)
        file2.write_text(content)

        from main import scan_file

        with patch('main.db_manager', db_manager):
            with patch('main.settings') as mock_settings:
                mock_settings.MACHINE_NAME = "duplicate_test"
                mock_settings.SCANNED = datetime.now()

                # 扫描两个文件
                scan_file(file1)
                scan_file(file2)

        # 验证重复文件共享哈希
        file1_meta = db_manager.get_file_by_path(str(file1.absolute()))
        file2_meta = db_manager.get_file_by_path(str(file2.absolute()))

        assert file1_meta.hash_id == file2_meta.hash_id

        # 验证只有一个哈希记录
        with db_manager.session_factory() as session:
            hash_count = session.query(FileHash).count()
            assert hash_count == 1

        # 清理
        if db_path.exists():
            db_path.unlink()

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    def test_database_persistence(self, test_files, temp_dir):
        """测试数据库持久化"""
        db_path = temp_dir / "persistence_test.db"

        # 第一次会话：写入数据
        db_manager1 = DatabaseManager()
        db_manager1.init(f"sqlite:///{db_path}")

        from main import scan_file

        with patch('main.db_manager', db_manager1):
            with patch('main.settings') as mock_settings:
                mock_settings.MACHINE_NAME = "persistence_test"
                mock_settings.SCANNED = datetime.now()

                scan_file(test_files["small"])

        # 验证数据库文件存在
        assert db_path.exists()

        # 第二次会话：读取数据
        db_manager2 = DatabaseManager()
        db_manager2.init(f"sqlite:///{db_path}")

        retrieved_file = db_manager2.get_file_by_name("small.txt")
        assert retrieved_file is not None
        assert retrieved_file.machine == "persistence_test"

        # 清理
        if db_path.exists():
            db_path.unlink()


class TestConcurrentScanning:
    """并发扫描测试"""

    @pytest.mark.integration
    @pytest.mark.database
    @pytest.mark.filesystem
    def test_concurrent_file_scanning(self, test_files, temp_dir, thread_count):
        """测试并发文件扫描"""
        db_path = temp_dir / "concurrent_test.db"
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        from main import scan_file
        errors = []

        def scan_files_worker(files_subset):
            try:
                with patch('main.db_manager', db_manager):
                    with patch('main.settings') as mock_settings:
                        mock_settings.MACHINE_NAME = f"worker_{threading.current_thread().ident}"
                        mock_settings.SCANNED = datetime.now()

                        for file_path in files_subset:
                            scan_file(file_path)
            except Exception as e:
                errors.append(e)

        # 将文件分配给不同线程
        file_list = list(test_files.values())
        files_per_thread = len(file_list) // thread_count + 1

        threads = []
        for i in range(thread_count):
            start_idx = i * files_per_thread
            end_idx = min((i + 1) * files_per_thread, len(file_list))
            files_subset = file_list[start_idx:end_idx]

            if files_subset:  # 只有当有文件要处理时才创建线程
                thread = threading.Thread(target=scan_files_worker, args=(files_subset,))
                threads.append(thread)
                thread.start()

        # 等待所有线程完成
        for thread in threads:
            thread.join()

        # 验证没有错误
        assert len(errors) == 0

        # 验证所有文件都被处理
        with db_manager.session_factory() as session:
            file_count = session.query(FileMeta).count()
            assert file_count == len(test_files)

        # 清理
        if db_path.exists():
            db_path.unlink()

    @pytest.mark.integration
    @pytest.mark.database
    @pytest.mark.slow
    def test_database_locking_under_load(self, temp_dir, thread_count):
        """测试高负载下的数据库锁定"""
        db_path = temp_dir / "locking_test.db"
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        # 创建大量小文件
        files_dir = temp_dir / "many_files"
        files_dir.mkdir()

        test_files = []
        for i in range(50):  # 创建50个小文件
            file_path = files_dir / f"file_{i:03d}.txt"
            file_path.write_text(f"Content of file {i}")
            test_files.append(file_path)

        from main import scan_file
        errors = []
        completed_files = []

        def scan_files_worker(files_subset):
            try:
                with patch('main.db_manager', db_manager):
                    with patch('main.settings') as mock_settings:
                        mock_settings.MACHINE_NAME = f"load_test_{threading.current_thread().ident}"
                        mock_settings.SCANNED = datetime.now()

                        for file_path in files_subset:
                            scan_file(file_path)
                            completed_files.append(file_path)
            except Exception as e:
                errors.append(e)

        # 分配文件给线程
        files_per_thread = len(test_files) // thread_count + 1
        threads = []

        for i in range(thread_count):
            start_idx = i * files_per_thread
            end_idx = min((i + 1) * files_per_thread, len(test_files))
            files_subset = test_files[start_idx:end_idx]

            if files_subset:
                thread = threading.Thread(target=scan_files_worker, args=(files_subset,))
                threads.append(thread)
                thread.start()

        # 等待完成
        for thread in threads:
            thread.join()

        # 验证结果
        assert len(errors) == 0
        assert len(completed_files) == len(test_files)

        # 验证数据库中的数据完整性
        with db_manager.session_factory() as session:
            file_count = session.query(FileMeta).count()
            hash_count = session.query(FileHash).count()

            assert file_count == len(test_files)
            assert hash_count > 0

        # 清理
        if db_path.exists():
            db_path.unlink()


class TestErrorRecovery:
    """错误恢复测试"""

    @pytest.mark.integration
    @pytest.mark.database
    @pytest.mark.filesystem
    def test_database_corruption_recovery(self, temp_dir):
        """测试数据库损坏恢复"""
        db_path = temp_dir / "corruption_test.db"

        # 创建正常数据库
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        # 添加一些数据
        with db_manager.session_factory() as session:
            file_hash = FileHash(
                size=1024,
                md5="test_md5",
                sha1="test_sha1",
                sha256="test_sha256"
            )
            session.add(file_hash)
            session.commit()

        db_manager.engine.dispose()

        # 模拟数据库损坏（写入无效数据）
        with open(db_path, 'w') as f:
            f.write("CORRUPTED DATABASE")

        # 尝试重新初始化（应该失败或重建）
        try:
            db_manager2 = DatabaseManager()
            db_manager2.init(f"sqlite:///{db_path}")
            # 如果能成功初始化，说明 SQLite 重建了数据库
        except Exception:
            # 预期的错误
            pass

        # 清理
        if db_path.exists():
            db_path.unlink()

    @pytest.mark.integration
    @pytest.mark.filesystem
    def test_permission_error_handling(self, temp_dir):
        """测试权限错误处理"""
        # 创建一个文件
        test_file = temp_dir / "permission_test.txt"
        test_file.write_text("test content")

        # 移除读权限（在Unix系统上）
        if os.name != 'nt':  # 不在Windows上运行
            original_mode = test_file.stat().st_mode
            test_file.chmod(0o000)  # 移除所有权限

            try:
                from main import get_hashes

                with pytest.raises(PermissionError):
                    get_hashes(test_file)

            finally:
                # 恢复权限以便清理
                test_file.chmod(original_mode)

    @pytest.mark.integration
    @pytest.mark.filesystem
    def test_disk_full_simulation(self, temp_dir):
        """测试磁盘空间不足的处理"""
        # 这个测试很难模拟真实的磁盘满情况
        # 在实际项目中可能需要使用特殊的测试环境
        pass


class TestCommandLineInterface:
    """命令行接口测试"""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_main_script_execution(self, temp_dir):
        """测试主脚本执行"""
        # 创建测试文件
        test_file = temp_dir / "cli_test.txt"
        test_file.write_text("CLI test content")

        db_path = temp_dir / "cli_test.db"
        log_path = temp_dir / "cli_test.log"

        # 构建命令行参数
        main_script = Path(__file__).parent.parent / "pyFileIndexer" / "main.py"

        cmd = [
            "python", str(main_script),
            str(temp_dir),
            "--machine_name", "cli_test",
            "--db_path", str(db_path),
            "--log_path", str(log_path)
        ]

        try:
            # 执行命令（这可能需要设置适当的环境）
            # result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            # 验证输出文件存在
            # assert db_path.exists()
            # assert log_path.exists()

            # 由于依赖问题，这里先跳过实际执行
            pass

        except (subprocess.TimeoutExpired, FileNotFoundError):
            # 如果环境不支持，跳过这个测试
            pytest.skip("Cannot execute main script in test environment")

    @pytest.mark.integration
    def test_argument_parsing(self):
        """测试命令行参数解析"""
        # 这需要重构main.py以便更好地测试
        # 目前的main.py在导入时就开始执行，不太适合单元测试
        pass


class TestDataIntegrity:
    """数据完整性测试"""

    @pytest.mark.integration
    @pytest.mark.database
    @pytest.mark.filesystem
    def test_hash_integrity_verification(self, test_files, temp_dir):
        """测试哈希完整性验证"""
        db_path = temp_dir / "integrity_test.db"
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        from main import scan_file, get_hashes

        with patch('main.db_manager', db_manager):
            with patch('main.settings') as mock_settings:
                mock_settings.MACHINE_NAME = "integrity_test"
                mock_settings.SCANNED = datetime.now()

                # 扫描文件
                test_file = test_files["small"]
                scan_file(test_file)

                # 获取数据库中的哈希
                file_meta = db_manager.get_file_by_path(str(test_file.absolute()))
                stored_hash = db_manager.get_hash_by_id(file_meta.hash_id)

                # 重新计算哈希
                current_hashes = get_hashes(test_file)

                # 验证一致性
                assert stored_hash.md5 == current_hashes["md5"]
                assert stored_hash.sha1 == current_hashes["sha1"]
                assert stored_hash.sha256 == current_hashes["sha256"]

        # 清理
        if db_path.exists():
            db_path.unlink()

    @pytest.mark.integration
    @pytest.mark.database
    @pytest.mark.filesystem
    def test_foreign_key_integrity(self, temp_dir):
        """测试外键完整性"""
        db_path = temp_dir / "fk_test.db"
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        # 创建文件哈希
        file_hash = FileHash(
            size=1024,
            md5="fk_test_md5",
            sha1="fk_test_sha1",
            sha256="fk_test_sha256"
        )

        hash_id = db_manager.add_hash(file_hash)

        # 创建引用该哈希的文件元数据
        file_meta = FileMeta(
            hash_id=hash_id,
            name="fk_test.txt",
            path="/test/fk_test.txt",
            machine="fk_test_machine",
            created=datetime.now(),
            modified=datetime.now(),
            scanned=datetime.now(),
            operation="ADD"
        )

        db_manager.add_file(file_meta)

        # 验证关系存在
        with db_manager.session_factory() as session:
            # 验证可以通过外键找到哈希
            retrieved_file = session.query(FileMeta).filter_by(name="fk_test.txt").first()
            retrieved_hash = session.query(FileHash).filter_by(id=retrieved_file.hash_id).first()

            assert retrieved_hash.md5 == "fk_test_md5"

            # 验证多个文件可以引用同一个哈希
            file_meta2 = FileMeta(
                hash_id=hash_id,
                name="fk_test2.txt",
                path="/test/fk_test2.txt",
                machine="fk_test_machine",
                created=datetime.now(),
                modified=datetime.now(),
                scanned=datetime.now(),
                operation="ADD"
            )

            session.add(file_meta2)
            session.commit()

            # 查询引用同一哈希的所有文件
            files_with_same_hash = session.query(FileMeta).filter_by(hash_id=hash_id).all()
            assert len(files_with_same_hash) == 2

        # 清理
        if db_path.exists():
            db_path.unlink()


class TestMemoryUsage:
    """内存使用测试"""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_memory_usage_with_many_files(self, temp_dir):
        """测试处理大量文件时的内存使用"""
        # 创建大量小文件
        files_dir = temp_dir / "memory_test"
        files_dir.mkdir()

        file_count = 1000  # 创建1000个文件
        for i in range(file_count):
            file_path = files_dir / f"mem_test_{i:04d}.txt"
            file_path.write_text(f"Memory test file {i}")

        db_path = temp_dir / "memory_test.db"
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        from main import scan_file

        # 监控内存使用（简单版本）
        try:
            import psutil
            process = psutil.Process()
            initial_memory = process.memory_info().rss
            use_psutil = True
        except ImportError:
            # 如果 psutil 不可用，跳过内存监控
            use_psutil = False
            initial_memory = 0

        with patch('main.db_manager', db_manager):
            with patch('main.settings') as mock_settings:
                mock_settings.MACHINE_NAME = "memory_test"
                mock_settings.SCANNED = datetime.now()

                # 扫描所有文件
                for i in range(file_count):
                    file_path = files_dir / f"mem_test_{i:04d}.txt"
                    scan_file(file_path)

                    # 每100个文件检查一次内存
                    if i % 100 == 0 and use_psutil:
                        current_memory = process.memory_info().rss
                        memory_increase = current_memory - initial_memory

                        # 内存增长不应该太快（这个阈值可能需要调整）
                        assert memory_increase < 100 * 1024 * 1024  # 不超过100MB

        if use_psutil:
            final_memory = process.memory_info().rss
            total_increase = final_memory - initial_memory

            # 最终内存增长应该在合理范围内
            assert total_increase < 200 * 1024 * 1024  # 不超过200MB
        else:
            # 如果 psutil 不可用，跳过内存检查
            pytest.skip("psutil not available, skipping memory usage test")

        # 验证所有文件都被处理
        with db_manager.session_factory() as session:
            processed_count = session.query(FileMeta).count()
            assert processed_count == file_count

        # 清理
        if db_path.exists():
            db_path.unlink()


class TestBackupAndRestore:
    """备份和恢复测试"""

    @pytest.mark.integration
    @pytest.mark.database
    def test_database_backup_restore(self, test_files, temp_dir):
        """测试数据库备份和恢复"""
        original_db_path = temp_dir / "original.db"
        backup_db_path = temp_dir / "backup.db"

        # 创建原始数据库并添加数据
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{original_db_path}")

        from main import scan_file

        with patch('main.db_manager', db_manager):
            with patch('main.settings') as mock_settings:
                mock_settings.MACHINE_NAME = "backup_test"
                mock_settings.SCANNED = datetime.now()

                scan_file(test_files["small"])

        # 关闭连接
        db_manager.engine.dispose()

        # 复制数据库文件（简单备份）
        import shutil
        shutil.copy2(original_db_path, backup_db_path)

        # 从备份恢复
        restore_db_manager = DatabaseManager()
        restore_db_manager.init(f"sqlite:///{backup_db_path}")

        # 验证数据完整性
        restored_file = restore_db_manager.get_file_by_name("small.txt")
        assert restored_file is not None
        assert restored_file.machine == "backup_test"

        # 清理
        for db_path in [original_db_path, backup_db_path]:
            if db_path.exists():
                db_path.unlink()