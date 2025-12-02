import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "pyFileIndexer"))

from models import FileHash, FileMeta
from database import Base


class TestFileHash:
    """测试 FileHash 数据模型"""

    @pytest.mark.unit
    def test_file_hash_creation(self, sample_file_hash):
        """测试 FileHash 对象创建"""
        assert sample_file_hash.size == 1024
        assert sample_file_hash.md5 == "d41d8cd98f00b204e9800998ecf8427e"
        assert sample_file_hash.sha1 == "da39a3ee5e6b4b0d3255bfef95601890afd80709"
        assert (
            sample_file_hash.sha256
            == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

    @pytest.mark.unit
    def test_file_hash_with_different_values(self):
        """测试使用不同值创建 FileHash"""
        file_hash = FileHash(
            size=2048,
            md5="5d41402abc4b2a76b9719d911017c592",
            sha1="aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d",
            sha256="2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
        )

        assert file_hash.size == 2048
        assert file_hash.md5 == "5d41402abc4b2a76b9719d911017c592"
        assert file_hash.sha1 == "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d"
        assert (
            file_hash.sha256
            == "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
        )

    @pytest.mark.unit
    @pytest.mark.database
    def test_file_hash_database_persistence(self, memory_db_manager):
        """测试 FileHash 在数据库中的持久化"""
        # 创建 FileHash 对象
        file_hash = FileHash(
            size=1024, md5="test_md5", sha1="test_sha1", sha256="test_sha256"
        )

        # 保存到数据库
        with memory_db_manager.session_factory() as session:
            session.add(file_hash)
            session.commit()

            # 查询验证
            retrieved_hash = session.query(FileHash).filter_by(md5="test_md5").first()
            assert retrieved_hash is not None
            assert retrieved_hash.size == 1024
            assert retrieved_hash.md5 == "test_md5"
            assert retrieved_hash.sha1 == "test_sha1"
            assert retrieved_hash.sha256 == "test_sha256"

    @pytest.mark.unit
    def test_file_hash_table_name(self):
        """测试 FileHash 表名"""
        assert FileHash.__tablename__ == "file_hash"

    @pytest.mark.unit
    def test_file_hash_with_zero_size(self):
        """测试零大小文件的 FileHash"""
        file_hash = FileHash(
            size=0,
            md5="d41d8cd98f00b204e9800998ecf8427e",  # 空文件的 MD5
            sha1="da39a3ee5e6b4b0d3255bfef95601890afd80709",  # 空文件的 SHA1
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",  # 空文件的 SHA256
        )

        assert file_hash.size == 0
        assert file_hash.md5 == "d41d8cd98f00b204e9800998ecf8427e"


class TestFileMeta:
    """测试 FileMeta 数据模型"""

    @pytest.mark.unit
    def test_file_meta_creation(self, sample_file_meta):
        """测试 FileMeta 对象创建"""
        assert sample_file_meta.hash_id == 1
        assert sample_file_meta.name == "test_file.txt"
        assert sample_file_meta.path == "/tmp/test_file.txt"
        assert sample_file_meta.machine == "test_machine"
        assert sample_file_meta.operation == "ADD"

    @pytest.mark.unit
    def test_file_meta_with_datetime(self):
        """测试 FileMeta 的时间字段"""
        created_time = datetime(2024, 1, 1, 10, 0, 0)
        modified_time = datetime(2024, 1, 1, 11, 0, 0)
        scanned_time = datetime(2024, 1, 1, 12, 0, 0)

        file_meta = FileMeta(
            hash_id=1,
            name="test.txt",
            path="/test/test.txt",
            machine="test_machine",
            created=created_time,
            modified=modified_time,
            scanned=scanned_time,
            operation="ADD",
        )

        assert file_meta.created == created_time
        assert file_meta.modified == modified_time
        assert file_meta.scanned == scanned_time

    @pytest.mark.unit
    @pytest.mark.database
    def test_file_meta_database_persistence(self, memory_db_manager):
        """测试 FileMeta 在数据库中的持久化"""
        # 创建 FileMeta 对象
        file_meta = FileMeta(
            hash_id=1,
            name="test.txt",
            path="/test/test.txt",
            machine="test_machine",
            created=datetime(2024, 1, 1, 10, 0, 0),
            modified=datetime(2024, 1, 1, 11, 0, 0),
            scanned=datetime(2024, 1, 1, 12, 0, 0),
            operation="ADD",
        )

        # 保存到数据库
        with memory_db_manager.session_factory() as session:
            session.add(file_meta)
            session.commit()

            # 查询验证
            retrieved_meta = session.query(FileMeta).filter_by(name="test.txt").first()
            assert retrieved_meta is not None
            assert retrieved_meta.hash_id == 1
            assert retrieved_meta.name == "test.txt"
            assert retrieved_meta.path == "/test/test.txt"
            assert retrieved_meta.machine == "test_machine"
            assert retrieved_meta.operation == "ADD"

    @pytest.mark.unit
    def test_file_meta_table_name(self):
        """测试 FileMeta 表名"""
        assert FileMeta.__tablename__ == "file_meta"

    @pytest.mark.unit
    def test_file_meta_with_different_operations(self):
        """测试不同操作类型的 FileMeta"""
        # 测试 ADD 操作
        add_meta = FileMeta(
            hash_id=1,
            name="add_file.txt",
            path="/test/add_file.txt",
            machine="test_machine",
            operation="ADD",
        )
        assert add_meta.operation == "ADD"

        # 测试 MOD 操作
        mod_meta = FileMeta(
            hash_id=2,
            name="mod_file.txt",
            path="/test/mod_file.txt",
            machine="test_machine",
            operation="MOD",
        )
        assert mod_meta.operation == "MOD"

    @pytest.mark.unit
    def test_file_meta_with_long_path(self):
        """测试长路径的 FileMeta"""
        long_path = "/very/long/path/with/many/subdirectories/and/a/very/long/filename_that_might_be_problematic.txt"

        file_meta = FileMeta(
            hash_id=1,
            name="very_long_filename_that_might_be_problematic.txt",
            path=long_path,
            machine="test_machine",
            operation="ADD",
        )

        assert file_meta.path == long_path
        assert file_meta.name == "very_long_filename_that_might_be_problematic.txt"

    @pytest.mark.unit
    def test_file_meta_with_special_characters(self):
        """测试包含特殊字符的 FileMeta"""
        special_name = "测试文件_with-special&chars.txt"
        special_path = "/path/with spaces/测试文件_with-special&chars.txt"

        file_meta = FileMeta(
            hash_id=1,
            name=special_name,
            path=special_path,
            machine="test_machine",
            operation="ADD",
        )

        assert file_meta.name == special_name
        assert file_meta.path == special_path


class TestModelRelationships:
    """测试数据模型之间的关系"""

    @pytest.mark.unit
    @pytest.mark.database
    def test_hash_id_relationship(self, memory_db_manager):
        """测试 FileMeta 和 FileHash 之间的关系"""
        # 创建 FileHash
        file_hash = FileHash(
            size=1024, md5="test_md5", sha1="test_sha1", sha256="test_sha256"
        )

        with memory_db_manager.session_factory() as session:
            session.add(file_hash)
            session.commit()

            # 创建 FileMeta 引用 FileHash
            file_meta = FileMeta(
                hash_id=file_hash.id,
                name="test.txt",
                path="/test/test.txt",
                machine="test_machine",
                operation="ADD",
            )

            session.add(file_meta)
            session.commit()

            # 验证关系
            retrieved_meta = session.query(FileMeta).filter_by(name="test.txt").first()
            retrieved_hash = (
                session.query(FileHash).filter_by(id=retrieved_meta.hash_id).first()
            )

            assert retrieved_meta.hash_id == file_hash.id
            assert retrieved_hash.md5 == "test_md5"

    @pytest.mark.unit
    @pytest.mark.database
    def test_multiple_files_same_hash(self, memory_db_manager):
        """测试多个文件共享同一个哈希值"""
        # 创建一个 FileHash
        file_hash = FileHash(
            size=1024, md5="shared_md5", sha1="shared_sha1", sha256="shared_sha256"
        )

        with memory_db_manager.session_factory() as session:
            session.add(file_hash)
            session.commit()

            # 创建两个 FileMeta 引用同一个 FileHash
            file_meta1 = FileMeta(
                hash_id=file_hash.id,
                name="file1.txt",
                path="/path1/file1.txt",
                machine="machine1",
                operation="ADD",
            )

            file_meta2 = FileMeta(
                hash_id=file_hash.id,
                name="file2.txt",
                path="/path2/file2.txt",
                machine="machine2",
                operation="ADD",
            )

            session.add_all([file_meta1, file_meta2])
            session.commit()

            # 验证两个文件共享同一个哈希
            files_with_same_hash = (
                session.query(FileMeta).filter_by(hash_id=file_hash.id).all()
            )
            assert len(files_with_same_hash) == 2
            assert files_with_same_hash[0].hash_id == files_with_same_hash[1].hash_id
