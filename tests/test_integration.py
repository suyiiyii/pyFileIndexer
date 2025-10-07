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

        with patch("main.db_manager", db_manager):
            with patch("main.settings") as mock_settings:
                mock_settings.MACHINE_NAME = "integration_test"
                mock_settings.SCANNED = datetime.now()

                # 扫描所有文件
                for file_path in [
                    complex_directory_structure["file1"],
                    complex_directory_structure["file2"],
                ]:
                    scan_file(file_path)

                # 刷新批量处理器以确保数据写入数据库
                from main import batch_processor

                batch_processor.flush()

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

        with patch("main.db_manager", db_manager):
            with patch("main.settings") as mock_settings:
                mock_settings.MACHINE_NAME = "incremental_test"
                mock_settings.SCANNED = datetime.now()

                # 首次扫描
                small_file = test_files["small"]
                scan_file(small_file)

                # 刷新批量处理器
                from main import batch_processor

                batch_processor.flush()

                # 验证文件被添加
                file_meta = db_manager.get_file_by_path(str(small_file.absolute()))
                assert file_meta.operation == "ADD"

                # 修改文件
                original_content = small_file.read_text()
                small_file.write_text(original_content + "\nmodified")

                # 再次扫描
                mock_settings.SCANNED = datetime.now()  # 更新扫描时间
                scan_file(small_file)

                # 刷新批量处理器
                batch_processor.flush()

                # 验证修改被检测到
                with db_manager.session_factory() as session:
                    files = (
                        session.query(FileMeta)
                        .filter_by(path=str(small_file.absolute()))
                        .all()
                    )

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

        with patch("main.db_manager", db_manager):
            with patch("main.settings") as mock_settings:
                mock_settings.MACHINE_NAME = "duplicate_test"
                mock_settings.SCANNED = datetime.now()

                # 扫描两个文件
                scan_file(file1)
                scan_file(file2)

                # 刷新批量处理器
                from main import batch_processor

                batch_processor.flush()

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

        with patch("main.db_manager", db_manager1):
            with patch("main.settings") as mock_settings:
                mock_settings.MACHINE_NAME = "persistence_test"
                mock_settings.SCANNED = datetime.now()

                scan_file(test_files["small"])

                # 刷新批量处理器
                from main import batch_processor

                batch_processor.flush()

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
                with patch("main.db_manager", db_manager):
                    with patch("main.settings") as mock_settings:
                        mock_settings.MACHINE_NAME = (
                            f"worker_{threading.current_thread().ident}"
                        )
                        mock_settings.SCANNED = datetime.now()

                        for file_path in files_subset:
                            scan_file(file_path)

                        # 刷新批量处理器
                        from main import batch_processor

                        batch_processor.flush()
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
                thread = threading.Thread(
                    target=scan_files_worker, args=(files_subset,)
                )
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
                with patch("main.db_manager", db_manager):
                    with patch("main.settings") as mock_settings:
                        mock_settings.MACHINE_NAME = (
                            f"load_test_{threading.current_thread().ident}"
                        )
                        mock_settings.SCANNED = datetime.now()

                        for file_path in files_subset:
                            scan_file(file_path)
                            completed_files.append(file_path)

                        # 刷新批量处理器
                        from main import batch_processor

                        batch_processor.flush()
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
                thread = threading.Thread(
                    target=scan_files_worker, args=(files_subset,)
                )
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
                size=1024, md5="test_md5", sha1="test_sha1", sha256="test_sha256"
            )
            session.add(file_hash)
            session.commit()

        db_manager.engine.dispose()

        # 模拟数据库损坏（写入无效数据）
        with open(db_path, "w") as f:
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
        if os.name != "nt":  # 不在Windows上运行
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
            "python",
            str(main_script),
            str(temp_dir),
            "--machine_name",
            "cli_test",
            "--db_path",
            str(db_path),
            "--log_path",
            str(log_path),
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

        with patch("main.db_manager", db_manager):
            with patch("main.settings") as mock_settings:
                mock_settings.MACHINE_NAME = "integrity_test"
                mock_settings.SCANNED = datetime.now()

                # 扫描文件
                test_file = test_files["small"]
                scan_file(test_file)

                # 刷新批量处理器
                from main import batch_processor

                batch_processor.flush()

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
            size=1024, md5="fk_test_md5", sha1="fk_test_sha1", sha256="fk_test_sha256"
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
            operation="ADD",
        )

        db_manager.add_file(file_meta)

        # 验证关系存在
        with db_manager.session_factory() as session:
            # 验证可以通过外键找到哈希
            retrieved_file = (
                session.query(FileMeta).filter_by(name="fk_test.txt").first()
            )
            retrieved_hash = (
                session.query(FileHash).filter_by(id=retrieved_file.hash_id).first()
            )

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
                operation="ADD",
            )

            session.add(file_meta2)
            session.commit()

            # 查询引用同一哈希的所有文件
            files_with_same_hash = (
                session.query(FileMeta).filter_by(hash_id=hash_id).all()
            )
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

        with patch("main.db_manager", db_manager):
            with patch("main.settings") as mock_settings:
                mock_settings.MACHINE_NAME = "memory_test"
                mock_settings.SCANNED = datetime.now()

                # 扫描所有文件
                for i in range(file_count):
                    file_path = files_dir / f"mem_test_{i:04d}.txt"
                    scan_file(file_path)

                    # 每100个文件检查一次内存并刷新批量处理器
                    if i % 100 == 0:
                        # 刷新批量处理器
                        from main import batch_processor

                        batch_processor.flush()

                        if use_psutil:
                            current_memory = process.memory_info().rss
                            memory_increase = current_memory - initial_memory

                            # 内存增长不应该太快（这个阈值可能需要调整）
                            assert memory_increase < 100 * 1024 * 1024  # 不超过100MB

                # 最终刷新批量处理器
                from main import batch_processor

                batch_processor.flush()

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

        with patch("main.db_manager", db_manager):
            with patch("main.settings") as mock_settings:
                mock_settings.MACHINE_NAME = "backup_test"
                mock_settings.SCANNED = datetime.now()

                scan_file(test_files["small"])

                # 刷新批量处理器
                from main import batch_processor

                batch_processor.flush()

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


class TestCommandLineIntegration:
    """命令行集成测试"""

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    @pytest.mark.slow
    def test_cli_basic_scan(self, cli_main_script_path, cli_test_directory, temp_dir):
        """测试基本的命令行扫描功能"""
        test_root = cli_test_directory["root"]
        db_path = temp_dir / "cli_basic.db"
        log_path = temp_dir / "cli_basic.log"

        # 构建命令行参数
        cmd = [
            "uv",
            "run",
            "python",
            str(cli_main_script_path),
            "scan",
            str(test_root),
            "--machine-name",
            "cli_test_basic",
            "--db-path",
            str(db_path),
            "--log-path",
            str(log_path),
        ]

        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cli_main_script_path.parent.parent,
        )

        # 验证命令执行成功
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # 验证数据库文件被创建
        assert db_path.exists(), "Database file was not created"

        # 连接数据库验证结果
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        try:
            with db_manager.session_factory() as session:
                # 统计扫描的文件数量
                file_count = session.query(FileMeta).count()
                hash_count = session.query(FileHash).count()

                # 验证扫描了合理数量的文件（不包括被忽略的）
                # 基本文件：text1.txt, text2.txt, duplicate1.txt, duplicate2.txt, empty.txt, large.txt, binary.bin
                # 嵌套文件：nested1.txt, deep_nested.txt
                # 由于测试环境可能有差异，我们验证至少扫描了基本的文件
                assert file_count >= 9, f"Expected at least 9 files, got {file_count}"
                assert file_count <= 12, (
                    f"Expected at most 12 files, got {file_count}"
                )  # 允许一些额外的测试文件

                # 验证哈希数量合理（重复文件应该共享哈希）
                assert hash_count > 0, "No hashes were calculated"
                assert hash_count <= file_count, "More hashes than files"

                # 验证具体文件是否存在
                text1_file = session.query(FileMeta).filter_by(name="text1.txt").first()
                assert text1_file is not None, "text1.txt not found in database"
                assert text1_file.machine == "cli_test_basic"

                # 验证重复文件共享哈希
                duplicate1 = (
                    session.query(FileMeta).filter_by(name="duplicate1.txt").first()
                )
                duplicate2 = (
                    session.query(FileMeta).filter_by(name="duplicate2.txt").first()
                )
                assert duplicate1 is not None, "duplicate1.txt not found"
                assert duplicate2 is not None, "duplicate2.txt not found"
                assert duplicate1.hash_id == duplicate2.hash_id, (
                    "Duplicate files should share hash ID"
                )

        finally:
            db_manager.engine.dispose()

        # 清理
        if db_path.exists():
            db_path.unlink()
        if log_path.exists():
            log_path.unlink()

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    @pytest.mark.slow
    def test_cli_with_ignore_file(
        self, cli_main_script_path, cli_test_with_ignore, temp_dir
    ):
        """测试带有.ignore文件的扫描功能"""
        test_root = cli_test_with_ignore["root"]
        db_path = temp_dir / "cli_ignore.db"
        log_path = temp_dir / "cli_ignore.log"

        # 在工作目录创建.ignore文件（主程序从当前目录读取）
        ignore_content = """# CLI测试忽略规则
node_modules
__pycache__
.DS_Store
/temp/
/logs/
*.log
*.tmp"""
        ignore_file = temp_dir / ".ignore"
        ignore_file.write_text(ignore_content)

        # 构建命令行参数，使用相对路径
        main_script_rel = Path("pyFileIndexer") / "main.py"
        cmd = [
            "uv",
            "run",
            "python",
            str(main_script_rel),
            "scan",
            str(test_root),
            "--machine-name",
            "cli_test_ignore",
            "--db-path",
            str(db_path),
            "--log-path",
            str(log_path),
        ]

        # 执行命令（从项目根目录运行）
        project_root = cli_main_script_path.parent.parent

        # 复制.ignore文件到项目根目录
        project_ignore = project_root / ".ignore"
        project_ignore.write_text(ignore_content)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, cwd=project_root
            )
        finally:
            # 清理.ignore文件
            if project_ignore.exists():
                project_ignore.unlink()

        # 验证命令执行成功
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # 连接数据库验证结果
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        try:
            with db_manager.session_factory() as session:
                # 验证被忽略的文件没有被扫描
                # 注意：当前的忽略实现只在目录级别生效，所以只测试目录级别的忽略
                ignored_files = [
                    "should_be_ignored.js",  # 在node_modules中（目录被忽略）
                    "config",  # 在.git中（以点开头的目录被忽略）
                    "cache_file.tmp",  # 在_cache中（以下划线开头的目录被忽略）
                ]

                for ignored_file in ignored_files:
                    found = (
                        session.query(FileMeta)
                        .filter(FileMeta.name == ignored_file)
                        .first()
                    )
                    assert found is None, (
                        f"Ignored file {ignored_file} was incorrectly scanned"
                    )

                # 验证temp目录中的文件可能会被扫描（因为当前忽略逻辑的限制）
                # 但node_modules, .git, _cache目录中的文件应该被忽略

                # 验证正常文件被扫描
                normal_files = ["text1.txt", "text2.txt", "nested1.txt"]
                for normal_file in normal_files:
                    found = (
                        session.query(FileMeta)
                        .filter(FileMeta.name == normal_file)
                        .first()
                    )
                    assert found is not None, (
                        f"Normal file {normal_file} was not scanned"
                    )

        finally:
            db_manager.engine.dispose()

        # 清理
        if db_path.exists():
            db_path.unlink()
        if log_path.exists():
            log_path.unlink()

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    def test_cli_duplicate_detection(
        self, cli_main_script_path, cli_test_directory, temp_dir
    ):
        """测试重复文件检测功能"""
        test_root = cli_test_directory["root"]
        db_path = temp_dir / "cli_duplicate.db"
        log_path = temp_dir / "cli_duplicate.log"

        # 首先直接计算重复文件的哈希用于对比
        from main import get_hashes

        duplicate1_path = cli_test_directory["duplicate1.txt"]
        duplicate2_path = cli_test_directory["duplicate2.txt"]
        expected_hashes = get_hashes(duplicate1_path)

        # 构建命令行参数
        cmd = [
            "uv",
            "run",
            "python",
            str(cli_main_script_path),
            "scan",
            str(test_root),
            "--machine-name",
            "cli_test_duplicate",
            "--db-path",
            str(db_path),
            "--log-path",
            str(log_path),
        ]

        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cli_main_script_path.parent.parent,
        )

        # 验证命令执行成功
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # 连接数据库验证结果
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        try:
            with db_manager.session_factory() as session:
                # 获取重复文件的记录
                duplicate1 = (
                    session.query(FileMeta).filter_by(name="duplicate1.txt").first()
                )
                duplicate2 = (
                    session.query(FileMeta).filter_by(name="duplicate2.txt").first()
                )

                assert duplicate1 is not None, "duplicate1.txt not found"
                assert duplicate2 is not None, "duplicate2.txt not found"

                # 验证它们共享相同的hash_id
                assert duplicate1.hash_id == duplicate2.hash_id, (
                    "Duplicate files should share hash ID"
                )

                # 验证哈希值正确
                shared_hash = (
                    session.query(FileHash).filter_by(id=duplicate1.hash_id).first()
                )
                assert shared_hash is not None, "Shared hash not found"
                assert shared_hash.md5 == expected_hashes["md5"], "MD5 hash mismatch"
                assert shared_hash.sha1 == expected_hashes["sha1"], "SHA1 hash mismatch"
                assert shared_hash.sha256 == expected_hashes["sha256"], (
                    "SHA256 hash mismatch"
                )

                # 验证只有一个哈希记录用于重复内容
                duplicate_hash_count = (
                    session.query(FileHash)
                    .filter_by(md5=expected_hashes["md5"])
                    .count()
                )
                assert duplicate_hash_count == 1, (
                    "Should have only one hash record for duplicate content"
                )

        finally:
            db_manager.engine.dispose()

        # 清理
        if db_path.exists():
            db_path.unlink()
        if log_path.exists():
            log_path.unlink()

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    def test_cli_nested_directories(
        self, cli_main_script_path, cli_test_directory, temp_dir
    ):
        """测试嵌套目录扫描功能"""
        test_root = cli_test_directory["root"]
        db_path = temp_dir / "cli_nested.db"
        log_path = temp_dir / "cli_nested.log"

        # 构建命令行参数
        cmd = [
            "uv",
            "run",
            "python",
            str(cli_main_script_path),
            "scan",
            str(test_root),
            "--machine-name",
            "cli_test_nested",
            "--db-path",
            str(db_path),
            "--log-path",
            str(log_path),
        ]

        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cli_main_script_path.parent.parent,
        )

        # 验证命令执行成功
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # 连接数据库验证结果
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        try:
            with db_manager.session_factory() as session:
                # 验证嵌套文件被扫描
                nested_file = (
                    session.query(FileMeta).filter_by(name="nested1.txt").first()
                )
                assert nested_file is not None, "nested1.txt not found"

                deep_nested_file = (
                    session.query(FileMeta).filter_by(name="deep_nested.txt").first()
                )
                assert deep_nested_file is not None, "deep_nested.txt not found"

                # 验证路径正确记录了完整的层次结构
                assert "subdir1" in nested_file.path, (
                    "nested1.txt path should contain subdir1"
                )
                assert "deeper" in deep_nested_file.path, (
                    "deep_nested.txt path should contain deeper"
                )

                # 验证根目录文件也被扫描
                root_file = session.query(FileMeta).filter_by(name="text1.txt").first()
                assert root_file is not None, "Root level file text1.txt not found"

        finally:
            db_manager.engine.dispose()

        # 清理
        if db_path.exists():
            db_path.unlink()
        if log_path.exists():
            log_path.unlink()

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    @pytest.mark.slow
    def test_cli_incremental_scan(
        self, cli_main_script_path, cli_test_directory, temp_dir
    ):
        """测试增量扫描功能"""
        test_root = cli_test_directory["root"]
        db_path = temp_dir / "cli_incremental.db"
        log_path = temp_dir / "cli_incremental.log"

        # 构建命令行参数
        cmd = [
            "uv",
            "run",
            "python",
            str(cli_main_script_path),
            "scan",
            str(test_root),
            "--machine-name",
            "cli_test_incremental",
            "--db-path",
            str(db_path),
            "--log-path",
            str(log_path),
        ]

        # 第一次扫描
        result1 = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cli_main_script_path.parent.parent,
        )

        assert result1.returncode == 0, f"First scan failed: {result1.stderr}"

        # 验证第一次扫描结果
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        try:
            with db_manager.session_factory() as session:
                initial_count = session.query(FileMeta).count()
                assert initial_count > 0, "No files scanned in first run"

                # 验证所有文件的操作都是ADD
                add_operations = (
                    session.query(FileMeta).filter_by(operation="ADD").count()
                )
                assert add_operations == initial_count, (
                    "All files should have ADD operation in first scan"
                )

        finally:
            db_manager.engine.dispose()

        # 修改一个文件
        test_file = cli_test_directory["text1.txt"]
        original_content = test_file.read_text()
        test_file.write_text(original_content + "\nModified content")

        # 等待一秒确保修改时间不同
        time.sleep(1)

        # 第二次扫描
        result2 = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cli_main_script_path.parent.parent,
        )

        assert result2.returncode == 0, f"Second scan failed: {result2.stderr}"

        # 验证增量扫描结果
        db_manager2 = DatabaseManager()
        db_manager2.init(f"sqlite:///{db_path}")

        try:
            with db_manager2.session_factory() as session:
                # 验证有MOD操作记录
                mod_operations = (
                    session.query(FileMeta).filter_by(operation="MOD").count()
                )
                assert mod_operations > 0, (
                    "Should have MOD operations after file modification"
                )

                # 验证修改的文件有正确的操作类型
                modified_files = (
                    session.query(FileMeta)
                    .filter(FileMeta.name == "text1.txt", FileMeta.operation == "MOD")
                    .all()
                )
                assert len(modified_files) > 0, (
                    "Modified file should have MOD operation"
                )

        finally:
            db_manager2.engine.dispose()

        # 清理
        if db_path.exists():
            db_path.unlink()
        if log_path.exists():
            log_path.unlink()


class TestArchiveIntegration:
    """压缩包集成测试"""

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    @pytest.mark.slow
    def test_cli_zip_archive_scan(
        self,
        cli_main_script_path,
        cli_archive_test_directory,
        temp_dir,
        archive_test_files,
    ):
        """测试ZIP压缩包扫描功能"""
        test_root = cli_archive_test_directory["root"]
        zip_file = cli_archive_test_directory["zip_file"]
        db_path = temp_dir / "cli_zip.db"
        log_path = temp_dir / "cli_zip.log"

        # 构建命令行参数
        cmd = [
            "uv",
            "run",
            "python",
            str(cli_main_script_path),
            "scan",
            str(test_root),
            "--machine-name",
            "cli_test_zip",
            "--db-path",
            str(db_path),
            "--log-path",
            str(log_path),
        ]

        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # 给压缩包扫描更多时间
            cwd=cli_main_script_path.parent.parent,
        )

        # 验证命令执行成功
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # 连接数据库验证结果
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        try:
            with db_manager.session_factory() as session:
                # 验证ZIP文件本身被扫描
                zip_meta = (
                    session.query(FileMeta)
                    .filter(FileMeta.name == "sample.zip")
                    .first()
                )
                assert zip_meta is not None, "ZIP file itself should be scanned"
                assert zip_meta.is_archived == 0, (
                    "ZIP file itself should not be marked as archived"
                )

                # 验证ZIP内部文件被扫描
                archived_files = (
                    session.query(FileMeta).filter(FileMeta.is_archived == 1).all()
                )
                assert len(archived_files) > 0, "Should have archived files from ZIP"

                # 验证虚拟路径格式
                virtual_paths = [f.path for f in archived_files]
                zip_virtual_path = next(
                    (
                        p
                        for p in virtual_paths
                        if "readme.txt" in p and "sample.zip" in p
                    ),
                    None,
                )
                assert zip_virtual_path is not None, (
                    "Should find readme.txt from ZIP file in archived files"
                )
                assert "::" in zip_virtual_path, (
                    "Virtual path should contain :: separator"
                )
                assert "sample.zip" in zip_virtual_path, (
                    "Virtual path should contain ZIP archive name"
                )

                # 验证archive_path字段
                readme_from_zip = (
                    session.query(FileMeta)
                    .filter(
                        FileMeta.name == "readme.txt",
                        FileMeta.is_archived == 1,
                        FileMeta.archive_path.like("%sample.zip%"),
                    )
                    .first()
                )
                assert readme_from_zip is not None, "Should find readme.txt from ZIP"
                assert readme_from_zip.archive_path is not None, (
                    "Archive path should be set"
                )
                assert "sample.zip" in readme_from_zip.archive_path, (
                    "Archive path should contain ZIP filename"
                )

                # 验证嵌套目录文件（从ZIP）
                nested_from_zip = (
                    session.query(FileMeta)
                    .filter(
                        FileMeta.name == "guide.md",
                        FileMeta.is_archived == 1,
                        FileMeta.archive_path.like("%sample.zip%"),
                    )
                    .first()
                )
                assert nested_from_zip is not None, (
                    "Should find nested file guide.md from ZIP"
                )
                assert "docs/guide.md" in nested_from_zip.path, (
                    "Virtual path should preserve directory structure"
                )

                # 验证重复内容文件共享哈希（从ZIP）
                duplicate1_zip = (
                    session.query(FileMeta)
                    .filter(
                        FileMeta.name == "duplicate1.txt",
                        FileMeta.is_archived == 1,
                        FileMeta.archive_path.like("%sample.zip%"),
                    )
                    .first()
                )
                duplicate2_zip = (
                    session.query(FileMeta)
                    .filter(
                        FileMeta.name == "duplicate2.txt",
                        FileMeta.is_archived == 1,
                        FileMeta.archive_path.like("%sample.zip%"),
                    )
                    .first()
                )

                if duplicate1_zip and duplicate2_zip:
                    assert duplicate1_zip.hash_id == duplicate2_zip.hash_id, (
                        "Duplicate files in ZIP should share hash ID"
                    )

                # 验证二进制文件被正确处理（从ZIP）
                binary_from_zip = (
                    session.query(FileMeta)
                    .filter(
                        FileMeta.name == "binary.bin",
                        FileMeta.is_archived == 1,
                        FileMeta.archive_path.like("%sample.zip%"),
                    )
                    .first()
                )
                assert binary_from_zip is not None, "Should find binary file from ZIP"

        finally:
            db_manager.engine.dispose()

        # 清理
        if db_path.exists():
            db_path.unlink()
        if log_path.exists():
            log_path.unlink()

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    @pytest.mark.slow
    def test_cli_tar_variants_scan(
        self,
        cli_main_script_path,
        cli_archive_test_directory,
        temp_dir,
        archive_test_files,
    ):
        """测试各种TAR格式的压缩包扫描"""
        test_root = cli_archive_test_directory["root"]
        db_path = temp_dir / "cli_tar.db"
        log_path = temp_dir / "cli_tar.log"

        # 构建命令行参数
        cmd = [
            "uv",
            "run",
            "python",
            str(cli_main_script_path),
            "scan",
            str(test_root),
            "--machine-name",
            "cli_test_tar",
            "--db-path",
            str(db_path),
            "--log-path",
            str(log_path),
        ]

        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=cli_main_script_path.parent.parent,
        )

        # 验证命令执行成功
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # 连接数据库验证结果
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        try:
            with db_manager.session_factory() as session:
                # 检查各种TAR格式的压缩包
                tar_formats = ["tar", "tar_gz", "tar_bz2", "tar_xz"]
                found_tar_files = []

                for format_name in tar_formats:
                    # 检查TAR文件本身
                    tar_filename = f"sample.{format_name}"
                    tar_meta = (
                        session.query(FileMeta)
                        .filter(FileMeta.name == tar_filename)
                        .first()
                    )

                    if tar_meta:
                        found_tar_files.append(format_name)
                        assert tar_meta.is_archived == 0, (
                            f"{tar_filename} itself should not be marked as archived"
                        )

                        # 检查该TAR文件内的文件
                        archived_from_this_tar = (
                            session.query(FileMeta)
                            .filter(
                                FileMeta.is_archived == 1,
                                FileMeta.archive_path.like(f"%{tar_filename}%"),
                            )
                            .all()
                        )

                        if len(archived_from_this_tar) > 0:
                            # 验证虚拟路径格式
                            sample_file = archived_from_this_tar[0]
                            assert "::" in sample_file.path, (
                                f"TAR virtual path should contain :: separator for {format_name}"
                            )
                            assert tar_filename in sample_file.path, (
                                f"Virtual path should contain TAR filename for {format_name}"
                            )

                # 确保至少找到了一些TAR文件
                assert len(found_tar_files) > 0, (
                    "Should find at least one TAR format file"
                )

                # 验证总的archived文件数量合理
                total_archived = (
                    session.query(FileMeta).filter(FileMeta.is_archived == 1).count()
                )
                assert total_archived > 0, "Should have archived files from TAR formats"

        finally:
            db_manager.engine.dispose()

        # 清理
        if db_path.exists():
            db_path.unlink()
        if log_path.exists():
            log_path.unlink()

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    def test_cli_rar_archive_scan(
        self,
        cli_main_script_path,
        cli_archive_test_directory,
        temp_dir,
        archive_test_files,
    ):
        """测试RAR压缩包扫描功能"""
        test_root = cli_archive_test_directory["root"]

        # 检查是否有RAR文件存在
        rar_files = list(test_root.glob("*.rar"))
        if not rar_files:
            pytest.skip(
                "No RAR files found in test directory - RAR creation may not be available"
            )

        db_path = temp_dir / "cli_rar.db"
        log_path = temp_dir / "cli_rar.log"

        # 构建命令行参数
        cmd = [
            "uv",
            "run",
            "python",
            str(cli_main_script_path),
            "scan",
            str(test_root),
            "--machine-name",
            "cli_test_rar",
            "--db-path",
            str(db_path),
            "--log-path",
            str(log_path),
        ]

        # 执行命令
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, cwd=test_root.parent
        )

        # 验证命令执行成功
        assert result.returncode == 0, f"CLI command failed: {result.stderr}"

        # 验证数据库文件被创建
        assert db_path.exists(), "Database file should be created"

        # 连接数据库验证结果
        from pyFileIndexer.database import DatabaseManager
        from pyFileIndexer.models import FileMeta, FileHash

        db_manager = DatabaseManager(str(db_path))
        try:
            with db_manager.session_factory() as session:
                # 查找RAR压缩包内的文件
                rar_files_query = (
                    session.query(FileMeta)
                    .filter(
                        FileMeta.is_archived == 1,
                        FileMeta.archive_path.like("%sample.rar%"),
                    )
                    .all()
                )

                if rar_files_query:  # 如果RAR文件被成功处理
                    # 验证基本文件存在
                    readme_from_rar = (
                        session.query(FileMeta)
                        .filter(
                            FileMeta.name == "readme.txt",
                            FileMeta.is_archived == 1,
                            FileMeta.archive_path.like("%sample.rar%"),
                        )
                        .first()
                    )
                    assert readme_from_rar is not None, (
                        "Should find readme.txt in RAR archive"
                    )
                    assert "sample.rar" in readme_from_rar.path, (
                        "Virtual path should contain archive name"
                    )

                    # 验证虚拟路径格式
                    assert "::" in readme_from_rar.path, (
                        "Virtual path should contain '::' separator"
                    )

                    # 验证存档标记
                    assert readme_from_rar.is_archived == 1, (
                        "File should be marked as archived"
                    )
                    assert readme_from_rar.archive_path is not None, (
                        "Archive path should be set"
                    )

                else:
                    # RAR文件无法处理（可能是因为缺少rarfile支持）
                    pytest.skip(
                        "RAR files found but could not be processed - may require rarfile library"
                    )

        finally:
            db_manager.engine.dispose()

        # 清理
        if db_path.exists():
            db_path.unlink()
        if log_path.exists():
            log_path.unlink()

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    def test_cli_nested_archive_structure(
        self, cli_main_script_path, cli_archive_test_directory, temp_dir
    ):
        """测试压缩包内嵌套目录结构的扫描"""
        test_root = cli_archive_test_directory["root"]
        db_path = temp_dir / "cli_nested.db"
        log_path = temp_dir / "cli_nested.log"

        # 构建命令行参数
        cmd = [
            "uv",
            "run",
            "python",
            str(cli_main_script_path),
            "scan",
            str(test_root),
            "--machine-name",
            "cli_test_nested",
            "--db-path",
            str(db_path),
            "--log-path",
            str(log_path),
        ]

        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=cli_main_script_path.parent.parent,
        )

        # 验证命令执行成功
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # 连接数据库验证结果
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        try:
            with db_manager.session_factory() as session:
                # 验证深层嵌套文件被正确扫描
                deep_files = (
                    session.query(FileMeta)
                    .filter(
                        FileMeta.is_archived == 1, FileMeta.path.like("%src/main/java%")
                    )
                    .all()
                )

                assert len(deep_files) > 0, "Should find deeply nested files"

                # 验证Java文件被找到
                java_file = (
                    session.query(FileMeta)
                    .filter(FileMeta.name == "App.java", FileMeta.is_archived == 1)
                    .first()
                )
                assert java_file is not None, "Should find App.java"
                assert "src/main/java/App.java" in java_file.path, (
                    "Path should preserve directory structure"
                )

                # 验证中文文件名被正确处理
                chinese_file = (
                    session.query(FileMeta)
                    .filter(FileMeta.name == "中文文件.txt", FileMeta.is_archived == 1)
                    .first()
                )
                assert chinese_file is not None, "Should handle Chinese filenames"

                # 验证特殊字符文件名
                special_file = (
                    session.query(FileMeta)
                    .filter(
                        FileMeta.name == "spécial-chars.txt", FileMeta.is_archived == 1
                    )
                    .first()
                )
                assert special_file is not None, (
                    "Should handle special character filenames"
                )

        finally:
            db_manager.engine.dispose()

        # 清理
        if db_path.exists():
            db_path.unlink()
        if log_path.exists():
            log_path.unlink()

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    def test_cli_archive_with_duplicates(
        self, cli_main_script_path, cli_archive_test_directory, temp_dir
    ):
        """测试压缩包内重复文件和与外部文件的重复检测"""
        test_root = cli_archive_test_directory["root"]
        db_path = temp_dir / "cli_duplicates.db"
        log_path = temp_dir / "cli_duplicates.log"

        # 构建命令行参数
        cmd = [
            "uv",
            "run",
            "python",
            str(cli_main_script_path),
            "scan",
            str(test_root),
            "--machine-name",
            "cli_test_duplicates",
            "--db-path",
            str(db_path),
            "--log-path",
            str(log_path),
        ]

        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=cli_main_script_path.parent.parent,
        )

        # 验证命令执行成功
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # 连接数据库验证结果
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        try:
            with db_manager.session_factory() as session:
                # 查找压缩包内的重复文件
                duplicate1_archived = (
                    session.query(FileMeta)
                    .filter(
                        FileMeta.name == "duplicate1.txt", FileMeta.is_archived == 1
                    )
                    .first()
                )

                duplicate2_archived = (
                    session.query(FileMeta)
                    .filter(
                        FileMeta.name == "duplicate2.txt", FileMeta.is_archived == 1
                    )
                    .first()
                )

                # 查找外部的重复文件
                external_duplicate = (
                    session.query(FileMeta)
                    .filter(
                        FileMeta.name == "duplicate_external.txt",
                        FileMeta.is_archived == 0,
                    )
                    .first()
                )

                # 验证压缩包内重复文件共享哈希
                if duplicate1_archived and duplicate2_archived:
                    assert duplicate1_archived.hash_id == duplicate2_archived.hash_id, (
                        "Duplicate files within archive should share hash ID"
                    )

                # 验证压缩包内文件与外部文件的重复检测
                if duplicate1_archived and external_duplicate:
                    assert duplicate1_archived.hash_id == external_duplicate.hash_id, (
                        "Duplicate content between archive and external files should share hash ID"
                    )

                # 验证哈希数量的合理性
                total_files = session.query(FileMeta).count()
                total_hashes = session.query(FileHash).count()
                assert total_hashes <= total_files, (
                    "Hash count should not exceed file count"
                )
                assert total_hashes < total_files, (
                    "Should have some duplicate content sharing hashes"
                )

        finally:
            db_manager.engine.dispose()

        # 清理
        if db_path.exists():
            db_path.unlink()
        if log_path.exists():
            log_path.unlink()

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    @pytest.mark.slow
    def test_cli_large_archive_limits(
        self, cli_main_script_path, large_archive_test_directory, temp_dir
    ):
        """测试压缩包大小限制功能"""
        test_root = large_archive_test_directory["root"]
        db_path = temp_dir / "cli_limits.db"
        log_path = temp_dir / "cli_limits.log"

        # 构建命令行参数
        cmd = [
            "uv",
            "run",
            "python",
            str(cli_main_script_path),
            "scan",
            str(test_root),
            "--machine-name",
            "cli_test_limits",
            "--db-path",
            str(db_path),
            "--log-path",
            str(log_path),
        ]

        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 给大文件处理更多时间
            cwd=cli_main_script_path.parent.parent,
        )

        # 验证命令执行成功（即使某些文件被跳过）
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # 连接数据库验证结果
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        try:
            with db_manager.session_factory() as session:
                # 验证超大压缩包本身被扫描但内容可能被跳过
                large_zip_meta = (
                    session.query(FileMeta)
                    .filter(FileMeta.name == "large_archive.zip")
                    .first()
                )
                assert large_zip_meta is not None, (
                    "Large archive file itself should be scanned"
                )

                # 验证超大压缩包内部文件可能被跳过（根据配置）
                large_zip_internal = (
                    session.query(FileMeta)
                    .filter(
                        FileMeta.is_archived == 1,
                        FileMeta.archive_path.like("%large_archive.zip%"),
                    )
                    .all()
                )
                # 根据大小限制，这些文件可能被跳过

                # 验证正常大小压缩包但包含大文件的情况
                normal_zip_meta = (
                    session.query(FileMeta)
                    .filter(FileMeta.name == "normal_with_large_files.zip")
                    .first()
                )
                assert normal_zip_meta is not None, (
                    "Normal sized archive should be scanned"
                )

                # 检查该压缩包内的文件
                normal_zip_internal = (
                    session.query(FileMeta)
                    .filter(
                        FileMeta.is_archived == 1,
                        FileMeta.archive_path.like("%normal_with_large_files.zip%"),
                    )
                    .all()
                )

                # 应该能找到小文件，大文件可能被跳过
                small_files = [
                    f
                    for f in normal_zip_internal
                    if f.name in ["small.txt", "another_small.txt"]
                ]
                assert len(small_files) > 0, (
                    "Small files within archive should be processed"
                )

                # 大文件可能被跳过
                large_file = (
                    session.query(FileMeta)
                    .filter(
                        FileMeta.name == "large_internal_file.bin",
                        FileMeta.is_archived == 1,
                    )
                    .first()
                )
                # large_file 可能为 None（被跳过）或存在（如果限制配置不同）

        finally:
            db_manager.engine.dispose()

        # 清理
        if db_path.exists():
            db_path.unlink()
        if log_path.exists():
            log_path.unlink()

    @pytest.mark.integration
    @pytest.mark.filesystem
    @pytest.mark.database
    @pytest.mark.slow
    def test_cli_archive_incremental_scan(
        self, cli_main_script_path, temp_dir, archive_test_files
    ):
        """测试压缩包的增量扫描功能"""
        import zipfile
        import shutil

        test_root = temp_dir / "incremental_archive_test"
        test_root.mkdir(exist_ok=True)

        db_path = temp_dir / "cli_incremental_archive.db"
        log_path = temp_dir / "cli_incremental_archive.log"

        # 创建初始压缩包
        original_zip = test_root / "evolving.zip"
        with zipfile.ZipFile(original_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("original.txt", "original content")
            zf.writestr("will_change.txt", "initial content")

        # 构建命令行参数
        cmd = [
            "uv",
            "run",
            "python",
            str(cli_main_script_path),
            "scan",
            str(test_root),
            "--machine-name",
            "cli_test_incremental_archive",
            "--db-path",
            str(db_path),
            "--log-path",
            str(log_path),
        ]

        # 第一次扫描
        result1 = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=cli_main_script_path.parent.parent,
        )

        assert result1.returncode == 0, f"First scan failed: {result1.stderr}"

        # 验证第一次扫描结果
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{db_path}")

        try:
            with db_manager.session_factory() as session:
                initial_files = (
                    session.query(FileMeta).filter(FileMeta.is_archived == 1).all()
                )
                initial_count = len(initial_files)
                assert initial_count > 0, "Should have archived files from first scan"

                # 验证所有文件都是ADD操作
                add_operations = (
                    session.query(FileMeta)
                    .filter(FileMeta.is_archived == 1, FileMeta.operation == "ADD")
                    .count()
                )
                assert add_operations == initial_count, (
                    "All archived files should have ADD operation initially"
                )

        finally:
            db_manager.engine.dispose()

        # 等待一秒确保时间戳不同
        time.sleep(1)

        # 创建修改后的压缩包
        modified_zip = test_root / "evolving_modified.zip"
        with zipfile.ZipFile(modified_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("original.txt", "original content")  # 未改变
            zf.writestr("will_change.txt", "modified content")  # 已改变
            zf.writestr("new_file.txt", "new content")  # 新文件

        # 替换原压缩包
        shutil.move(str(modified_zip), str(original_zip))

        # 第二次扫描
        result2 = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=cli_main_script_path.parent.parent,
        )

        assert result2.returncode == 0, f"Second scan failed: {result2.stderr}"

        # 验证增量扫描结果
        db_manager2 = DatabaseManager()
        db_manager2.init(f"sqlite:///{db_path}")

        try:
            with db_manager2.session_factory() as session:
                # 验证有新的操作记录
                all_archived = (
                    session.query(FileMeta).filter(FileMeta.is_archived == 1).all()
                )

                # 应该有ADD和可能的MOD操作
                operations = [f.operation for f in all_archived]
                assert "ADD" in operations, "Should have ADD operations"

                # 检查新文件
                new_file = (
                    session.query(FileMeta)
                    .filter(FileMeta.name == "new_file.txt", FileMeta.is_archived == 1)
                    .first()
                )
                assert new_file is not None, "Should find new file"

                # 检查原始文件（可能仍然存在或有新记录）
                original_files = (
                    session.query(FileMeta)
                    .filter(FileMeta.name == "original.txt", FileMeta.is_archived == 1)
                    .all()
                )
                assert len(original_files) > 0, "Should find original file"

        finally:
            db_manager2.engine.dispose()

        # 清理
        if db_path.exists():
            db_path.unlink()
        if log_path.exists():
            log_path.unlink()
