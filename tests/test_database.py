import threading
import time
from pathlib import Path

import pytest

from pyFileIndexer.database import DatabaseManager
from pyFileIndexer.models import FileHash, FileMeta


class TestDatabaseManager:
    """测试 DatabaseManager 数据库管理器"""

    @pytest.mark.unit
    @pytest.mark.database
    def test_database_manager_singleton(self):
        """测试 DatabaseManager 单例模式"""
        db_manager1 = DatabaseManager()
        db_manager2 = DatabaseManager()

        assert db_manager1 is db_manager2

    @pytest.mark.unit
    @pytest.mark.database
    def test_database_initialization(self, test_db_path):
        """测试数据库初始化"""
        db_manager = DatabaseManager()
        db_manager.init(f"sqlite:///{test_db_path}")

        assert db_manager.engine is not None
        assert db_manager.Session is not None
        assert test_db_path.exists()

    @pytest.mark.unit
    @pytest.mark.database
    def test_memory_database_initialization(self):
        """测试内存数据库初始化"""
        db_manager = DatabaseManager()
        db_manager.init("sqlite:///:memory:")

        assert db_manager.engine is not None
        assert db_manager.Session is not None

    @pytest.mark.unit
    @pytest.mark.database
    def test_session_factory(self, memory_db_manager):
        """测试会话工厂方法"""
        session = memory_db_manager.session_factory()
        assert session is not None
        session.close()

    @pytest.mark.unit
    @pytest.mark.database
    def test_session_factory_without_init(self):
        """测试未初始化时调用会话工厂"""
        db_manager = DatabaseManager()
        # 重置初始化状态
        db_manager.engine = None
        db_manager.Session = None

        with pytest.raises(RuntimeError, match="Database is not initialized"):
            db_manager.session_factory()

    @pytest.mark.unit
    @pytest.mark.database
    def test_add_hash(self, memory_db_manager, sample_file_hash):
        """测试添加哈希信息"""
        hash_id = memory_db_manager.add_hash(sample_file_hash)

        assert hash_id is not None
        retrieved_hash = memory_db_manager.get_hash_by_id(hash_id)
        assert retrieved_hash is not None
        assert retrieved_hash.md5 == sample_file_hash.md5

    @pytest.mark.unit
    @pytest.mark.database
    def test_add_file(self, memory_db_manager, sample_file_meta):
        """测试添加文件信息"""
        file_id = memory_db_manager.add_file(sample_file_meta)

        assert file_id is not None
        retrieved_file = memory_db_manager.get_file_by_name(sample_file_meta.name)
        assert retrieved_file is not None
        assert retrieved_file.path == sample_file_meta.path

    @pytest.mark.unit
    @pytest.mark.database
    def test_get_file_by_name(self, memory_db_manager):
        """测试根据文件名查询文件"""
        # 添加测试文件
        file_meta = FileMeta(
            hash_id=1,
            name="unique_test_file.txt",
            path="/test/unique_test_file.txt",
            machine="test_machine",
            operation="ADD",
        )
        memory_db_manager.add_file(file_meta)

        # 查询测试
        retrieved_file = memory_db_manager.get_file_by_name("unique_test_file.txt")
        assert retrieved_file is not None
        assert retrieved_file.name == "unique_test_file.txt"

        # 查询不存在的文件
        not_found = memory_db_manager.get_file_by_name("nonexistent.txt")
        assert not_found is None

    @pytest.mark.unit
    @pytest.mark.database
    def test_get_file_by_path(self, memory_db_manager):
        """测试根据文件路径查询文件"""
        # 添加测试文件
        file_meta = FileMeta(
            hash_id=1,
            name="path_test.txt",
            path="/unique/path/path_test.txt",
            machine="test_machine",
            operation="ADD",
        )
        memory_db_manager.add_file(file_meta)

        # 查询测试
        retrieved_file = memory_db_manager.get_file_by_path(
            "/unique/path/path_test.txt"
        )
        assert retrieved_file is not None
        assert retrieved_file.path == "/unique/path/path_test.txt"

        # 查询不存在的路径
        not_found = memory_db_manager.get_file_by_path("/nonexistent/path.txt")
        assert not_found is None

    @pytest.mark.unit
    @pytest.mark.database
    def test_get_hash_by_id(self, memory_db_manager):
        """测试根据哈希ID查询哈希信息"""
        # 添加测试哈希
        file_hash = FileHash(
            size=2048,
            md5="test_md5_by_id",
            sha1="test_sha1_by_id",
            sha256="test_sha256_by_id",
        )
        hash_id = memory_db_manager.add_hash(file_hash)

        # 查询测试
        retrieved_hash = memory_db_manager.get_hash_by_id(hash_id)
        assert retrieved_hash is not None
        assert retrieved_hash.md5 == "test_md5_by_id"

        # 查询不存在的ID
        not_found = memory_db_manager.get_hash_by_id(99999)
        assert not_found is None

    @pytest.mark.unit
    @pytest.mark.database
    def test_get_hash_by_hash(self, memory_db_manager):
        """测试根据哈希值查询哈希信息"""
        # 添加测试哈希
        file_hash = FileHash(
            size=4096,
            md5="unique_md5_hash",
            sha1="unique_sha1_hash",
            sha256="unique_sha256_hash",
        )
        memory_db_manager.add_hash(file_hash)

        # 查询测试
        hash_dict = {
            "md5": "unique_md5_hash",
            "sha1": "unique_sha1_hash",
            "sha256": "unique_sha256_hash",
        }
        retrieved_hash = memory_db_manager.get_hash_by_hash(hash_dict)
        assert retrieved_hash is not None
        assert retrieved_hash.md5 == "unique_md5_hash"

        # 查询不存在的哈希
        nonexistent_hash = {
            "md5": "nonexistent",
            "sha1": "nonexistent",
            "sha256": "nonexistent",
        }
        not_found = memory_db_manager.get_hash_by_hash(nonexistent_hash)
        assert not_found is None

    @pytest.mark.unit
    @pytest.mark.database
    def test_add_file_with_new_hash(self, memory_db_manager):
        """测试添加文件和新哈希"""
        file_hash = FileHash(
            size=1024,
            md5="new_hash_md5",
            sha1="new_hash_sha1",
            sha256="new_hash_sha256",
        )

        file_meta = FileMeta(
            name="new_file.txt",
            path="/test/new_file.txt",
            machine="test_machine",
            operation="ADD",
        )

        memory_db_manager.add(file_meta, file_hash)

        # 验证文件和哈希都被添加
        retrieved_file = memory_db_manager.get_file_by_name("new_file.txt")
        assert retrieved_file is not None

        retrieved_hash = memory_db_manager.get_hash_by_id(retrieved_file.hash_id)
        assert retrieved_hash is not None
        assert retrieved_hash.md5 == "new_hash_md5"

    @pytest.mark.unit
    @pytest.mark.database
    def test_add_file_with_existing_hash(self, memory_db_manager):
        """测试添加文件时使用已存在的哈希"""
        # 先添加一个哈希
        existing_hash = FileHash(
            size=2048,
            md5="existing_md5",
            sha1="existing_sha1",
            sha256="existing_sha256",
        )
        hash_id = memory_db_manager.add_hash(existing_hash)

        # 创建相同哈希值的新哈希对象
        duplicate_hash = FileHash(
            size=2048,
            md5="existing_md5",
            sha1="existing_sha1",
            sha256="existing_sha256",
        )

        # 添加使用相同哈希的文件
        file_meta = FileMeta(
            name="duplicate_content.txt",
            path="/test/duplicate_content.txt",
            machine="test_machine",
            operation="ADD",
        )

        memory_db_manager.add(file_meta, duplicate_hash)

        # 验证文件使用了已存在的哈希
        retrieved_file = memory_db_manager.get_file_by_name("duplicate_content.txt")
        assert retrieved_file.hash_id == hash_id

    @pytest.mark.unit
    @pytest.mark.database
    def test_add_file_without_hash(self, memory_db_manager):
        """测试只添加文件信息（不添加哈希）"""
        file_meta = FileMeta(
            hash_id=1,  # 假设已存在的哈希ID
            name="no_hash_file.txt",
            path="/test/no_hash_file.txt",
            machine="test_machine",
            operation="ADD",
        )

        memory_db_manager.add(file_meta, None)

        retrieved_file = memory_db_manager.get_file_by_name("no_hash_file.txt")
        assert retrieved_file is not None
        assert retrieved_file.hash_id == 1


class TestDatabaseConcurrency:
    """测试数据库并发操作"""

    @pytest.mark.unit
    @pytest.mark.database
    def test_concurrent_session_creation(self, memory_db_manager, thread_count):
        """测试并发创建会话"""
        sessions = []
        errors = []

        def create_session():
            try:
                session = memory_db_manager.session_factory()
                sessions.append(session)
                time.sleep(0.1)  # 模拟一些工作
                session.close()
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(thread_count):
            thread = threading.Thread(target=create_session)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        assert len(errors) == 0
        assert len(sessions) == thread_count

    @pytest.mark.unit
    @pytest.mark.database
    def test_session_lock_protection(self, memory_db_manager):
        """测试会话锁保护"""
        results = []
        start_time = time.time()

        def locked_operation(duration):
            with memory_db_manager.session_lock:
                time.sleep(duration)
                results.append(time.time() - start_time)

        # 启动两个线程，第二个应该等待第一个完成
        thread1 = threading.Thread(target=locked_operation, args=(0.2,))
        thread2 = threading.Thread(target=locked_operation, args=(0.1,))

        thread1.start()
        time.sleep(0.05)  # 确保thread1先获得锁
        thread2.start()

        thread1.join()
        thread2.join()

        # 验证执行顺序（第一个结果应该小于第二个）
        assert len(results) == 2
        assert results[0] < results[1]


class TestDatabaseErrors:
    """测试数据库错误处理"""

    @pytest.mark.unit
    @pytest.mark.database
    def test_invalid_database_path(self):
        """测试无效数据库路径"""
        db_manager = DatabaseManager()

        # 测试无效路径（这可能会创建文件，但不会立即失败）
        try:
            db_manager.init("sqlite:///invalid/path/test.db")
            # 如果没有错误，说明SQLite创建了路径
        except Exception:
            # 这是预期的行为
            pass

    @pytest.mark.unit
    @pytest.mark.database
    def test_database_operation_without_commit(self, memory_db_manager):
        """测试未提交的数据库操作"""
        file_hash = FileHash(
            size=1024,
            md5="uncommitted_md5",
            sha1="uncommitted_sha1",
            sha256="uncommitted_sha256",
        )

        # 添加但不提交
        with memory_db_manager.session_factory() as session:
            session.add(file_hash)
            # 不调用 commit()

        # 在新会话中查询应该找不到
        with memory_db_manager.session_factory() as session:
            result = session.query(FileHash).filter_by(md5="uncommitted_md5").first()
            assert result is None

    @pytest.mark.unit
    @pytest.mark.database
    def test_duplicate_hash_insertion(self, memory_db_manager):
        """测试重复插入相同哈希（应该通过add方法处理）"""
        hash1 = FileHash(
            size=1024,
            md5="duplicate_md5",
            sha1="duplicate_sha1",
            sha256="duplicate_sha256",
        )

        hash2 = FileHash(
            size=1024,
            md5="duplicate_md5",
            sha1="duplicate_sha1",
            sha256="duplicate_sha256",
        )

        # 第一次添加
        id1 = memory_db_manager.add_hash(hash1)

        # 第二次添加相同哈希（在实际使用中通过get_hash_by_hash避免）
        id2 = memory_db_manager.add_hash(hash2)

        # 应该有两个不同的ID（因为这是直接插入）
        assert id1 != id2

        # 但通过add方法应该能正确处理重复
        file_meta = FileMeta(
            name="test_duplicate.txt",
            path="/test/test_duplicate.txt",
            machine="test_machine",
            operation="ADD",
        )

        duplicate_hash = FileHash(
            size=1024,
            md5="duplicate_md5",
            sha1="duplicate_sha1",
            sha256="duplicate_sha256",
        )

        memory_db_manager.add(file_meta, duplicate_hash)

        # 文件应该使用已存在的哈希
        retrieved_file = memory_db_manager.get_file_by_name("test_duplicate.txt")
        assert retrieved_file.hash_id == id1
