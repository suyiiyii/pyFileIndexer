"""Tests for database merge functionality."""

import datetime
import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from base import Base
from database import DatabaseManager
from db_merge import merge_databases
from models import FileHash, FileMeta


@pytest.fixture
def temp_db_files():
    """Create temporary database files for testing."""
    temp_files = []
    for i in range(3):
        temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False)
        temp_file.close()
        temp_files.append(temp_file.name)

    yield temp_files

    # Cleanup
    for temp_file in temp_files:
        try:
            os.unlink(temp_file)
        except:
            pass


def create_test_database(db_path: str, machine_name: str, num_files: int = 5):
    """
    Create a test database with sample data.

    Args:
        db_path: Path to database file
        machine_name: Machine name for the files
        num_files: Number of files to create
    """
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        timestamp = datetime.datetime.now()

        for i in range(num_files):
            # Create hash
            file_hash = FileHash(
                md5=f"md5_{machine_name}_{i}",
                sha1=f"sha1_{machine_name}_{i}",
                sha256=f"sha256_{machine_name}_{i}",
                size=1024 * (i + 1),
            )
            session.add(file_hash)
            session.flush()

            # Create file metadata
            file_meta = FileMeta(
                hash_id=file_hash.id,
                name=f"file_{i}.txt",
                path=f"/test/{machine_name}/file_{i}.txt",
                machine=machine_name,
                created=timestamp,
                modified=timestamp,
                scanned=timestamp,
                operation="ADD",
                is_archived=0,
                archive_path=None,
            )
            session.add(file_meta)

        session.commit()
    finally:
        session.close()
        engine.dispose()


def test_merge_two_databases(temp_db_files):
    """Test merging two databases with different files."""
    source_db1 = temp_db_files[0]
    source_db2 = temp_db_files[1]
    target_db = temp_db_files[2]

    # Create source databases
    create_test_database(source_db1, "machine1", num_files=3)
    create_test_database(source_db2, "machine2", num_files=3)

    # Initialize target database manager
    target_manager = DatabaseManager()
    target_manager.init(f"sqlite:///{target_db}")

    # Merge databases
    stats = merge_databases([source_db1, source_db2], target_manager)

    # Verify statistics
    assert stats["total_files_processed"] == 6
    assert stats["files_added"] == 6
    assert stats["files_skipped"] == 0
    assert stats["hashes_added"] == 6
    assert stats["hashes_reused"] == 0

    # Verify data in target database
    with target_manager.session_scope() as session:
        file_count = session.query(FileMeta).count()
        hash_count = session.query(FileHash).count()
        assert file_count == 6
        assert hash_count == 6

        # Verify machines
        machine1_files = session.query(FileMeta).filter_by(machine="machine1").count()
        machine2_files = session.query(FileMeta).filter_by(machine="machine2").count()
        assert machine1_files == 3
        assert machine2_files == 3


def test_merge_with_duplicate_hashes(temp_db_files):
    """Test merging databases with duplicate hash values."""
    source_db1 = temp_db_files[0]
    source_db2 = temp_db_files[1]
    target_db = temp_db_files[2]

    # Create source database 1
    engine1 = create_engine(f"sqlite:///{source_db1}")
    Base.metadata.create_all(engine1)
    Session1 = sessionmaker(bind=engine1)
    session1 = Session1()

    timestamp = datetime.datetime.now()

    # Same hash in both databases
    file_hash1 = FileHash(
        md5="same_md5",
        sha1="same_sha1",
        sha256="same_sha256",
        size=1024,
    )
    session1.add(file_hash1)
    session1.flush()

    file_meta1 = FileMeta(
        hash_id=file_hash1.id,
        name="duplicate.txt",
        path="/test/machine1/duplicate.txt",
        machine="machine1",
        created=timestamp,
        modified=timestamp,
        scanned=timestamp,
        operation="ADD",
    )
    session1.add(file_meta1)
    session1.commit()
    session1.close()
    engine1.dispose()

    # Create source database 2 with same hash but different path
    engine2 = create_engine(f"sqlite:///{source_db2}")
    Base.metadata.create_all(engine2)
    Session2 = sessionmaker(bind=engine2)
    session2 = Session2()

    file_hash2 = FileHash(
        md5="same_md5",
        sha1="same_sha1",
        sha256="same_sha256",
        size=1024,
    )
    session2.add(file_hash2)
    session2.flush()

    file_meta2 = FileMeta(
        hash_id=file_hash2.id,
        name="duplicate.txt",
        path="/test/machine2/duplicate.txt",
        machine="machine2",
        created=timestamp,
        modified=timestamp,
        scanned=timestamp,
        operation="ADD",
    )
    session2.add(file_meta2)
    session2.commit()
    session2.close()
    engine2.dispose()

    # Initialize target database manager
    target_manager = DatabaseManager()
    target_manager.init(f"sqlite:///{target_db}")

    # Merge databases
    stats = merge_databases([source_db1, source_db2], target_manager)

    # Verify statistics - hash should be reused
    assert stats["total_files_processed"] == 2
    assert stats["files_added"] == 2
    assert stats["hashes_added"] == 1  # First time added
    assert stats["hashes_reused"] == 1  # Second time reused

    # Verify data in target database
    with target_manager.session_scope() as session:
        file_count = session.query(FileMeta).count()
        hash_count = session.query(FileHash).count()
        assert file_count == 2  # Two different files
        assert hash_count == 1  # But same hash


def test_merge_skip_existing_files(temp_db_files):
    """Test that identical files are skipped during merge."""
    source_db = temp_db_files[0]
    target_db = temp_db_files[1]

    # Create source database
    create_test_database(source_db, "machine1", num_files=3)

    # Initialize target database and add same data
    target_manager = DatabaseManager()
    target_manager.init(f"sqlite:///{target_db}")
    create_test_database(target_db, "machine1", num_files=3)

    # Get initial counts
    with target_manager.session_scope() as session:
        initial_file_count = session.query(FileMeta).count()
        initial_hash_count = session.query(FileHash).count()

    # Merge - should skip all files
    stats = merge_databases([source_db], target_manager)

    # Verify all files were skipped
    assert stats["total_files_processed"] == 3
    assert stats["files_skipped"] == 3
    assert stats["files_added"] == 0

    # Verify counts haven't changed
    with target_manager.session_scope() as session:
        final_file_count = session.query(FileMeta).count()
        final_hash_count = session.query(FileHash).count()
        assert final_file_count == initial_file_count
        assert final_hash_count == initial_hash_count


def test_merge_with_archived_files(temp_db_files):
    """Test merging databases with archived files."""
    source_db = temp_db_files[0]
    target_db = temp_db_files[1]

    # Create source database with archived files
    engine = create_engine(f"sqlite:///{source_db}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    timestamp = datetime.datetime.now()

    # Create archived file
    file_hash = FileHash(
        md5="archive_md5",
        sha1="archive_sha1",
        sha256="archive_sha256",
        size=2048,
    )
    session.add(file_hash)
    session.flush()

    file_meta = FileMeta(
        hash_id=file_hash.id,
        name="file.txt",
        path="/archive.zip::file.txt",
        machine="machine1",
        created=timestamp,
        modified=timestamp,
        scanned=timestamp,
        operation="ADD",
        is_archived=1,
        archive_path="/archive.zip",
    )
    session.add(file_meta)
    session.commit()
    session.close()
    engine.dispose()

    # Initialize target database manager
    target_manager = DatabaseManager()
    target_manager.init(f"sqlite:///{target_db}")

    # Merge databases
    stats = merge_databases([source_db], target_manager)

    # Verify statistics
    assert stats["total_files_processed"] == 1
    assert stats["files_added"] == 1

    # Verify archived file properties
    with target_manager.session_scope() as session:
        file = session.query(FileMeta).filter_by(is_archived=1).first()
        assert file is not None
        assert file.archive_path == "/archive.zip"
        assert file.path == "/archive.zip::file.txt"


def test_merge_nonexistent_source(temp_db_files):
    """Test merging with a nonexistent source database."""
    target_db = temp_db_files[0]
    nonexistent_db = "/tmp/nonexistent_db_12345.db"

    # Initialize target database manager
    target_manager = DatabaseManager()
    target_manager.init(f"sqlite:///{target_db}")

    # Merge should not raise exception but log error
    stats = merge_databases([nonexistent_db], target_manager)

    # No files should be processed
    assert stats["total_files_processed"] == 0
    assert stats["files_added"] == 0


def test_merge_empty_source_database(temp_db_files):
    """Test merging an empty source database."""
    source_db = temp_db_files[0]
    target_db = temp_db_files[1]

    # Create empty source database
    engine = create_engine(f"sqlite:///{source_db}")
    Base.metadata.create_all(engine)
    engine.dispose()

    # Initialize target database manager
    target_manager = DatabaseManager()
    target_manager.init(f"sqlite:///{target_db}")

    # Merge
    stats = merge_databases([source_db], target_manager)

    # Verify no files processed
    assert stats["total_files_processed"] == 0
    assert stats["files_added"] == 0

    # Verify target is still empty
    with target_manager.session_scope() as session:
        file_count = session.query(FileMeta).count()
        assert file_count == 0
