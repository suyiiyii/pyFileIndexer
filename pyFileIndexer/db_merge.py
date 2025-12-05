"""Database merge functionality for combining multiple indexer databases."""

import logging
from pathlib import Path
from typing import Union

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tqdm import tqdm

from .models import FileHash, FileMeta
from .database import DatabaseManager

logger = logging.getLogger(__name__)


def merge_databases(
    source_db_paths: list[Union[str, Path]], target_db_manager: DatabaseManager
) -> dict:
    """
    Merge multiple source databases into a target database.

    Args:
        source_db_paths: List of paths to source database files
        target_db_manager: Target DatabaseManager instance (already initialized)

    Returns:
        dict: Statistics about the merge operation
            - total_files_processed: Total files read from source databases
            - files_added: New files added to target
            - hashes_added: New hashes added to target
            - hashes_reused: Existing hashes reused
            - files_skipped: Files skipped (already exist with same data)
    """
    stats = {
        "total_files_processed": 0,
        "files_added": 0,
        "hashes_added": 0,
        "hashes_reused": 0,
        "files_skipped": 0,
    }

    for source_path in source_db_paths:
        source_path = Path(source_path)
        if not source_path.exists():
            logger.error(f"Source database not found: {source_path}")
            continue

        logger.info(f"Merging from: {source_path}")
        source_stats = _merge_single_database(source_path, target_db_manager)

        # Accumulate statistics
        for key in stats:
            stats[key] += source_stats.get(key, 0)

    return stats


def _merge_single_database(
    source_db_path: Path, target_db_manager: DatabaseManager
) -> dict:
    """
    Merge a single source database into the target database.

    Args:
        source_db_path: Path to source database file
        target_db_manager: Target DatabaseManager instance

    Returns:
        dict: Statistics for this merge operation
    """
    stats = {
        "total_files_processed": 0,
        "files_added": 0,
        "hashes_added": 0,
        "hashes_reused": 0,
        "files_skipped": 0,
    }

    # Create read-only connection to source database
    source_engine = create_engine(
        f"sqlite:///{source_db_path}",
        connect_args={"check_same_thread": False},
    )
    SourceSession = sessionmaker(bind=source_engine)
    source_session = SourceSession()

    try:
        # Get total count for progress bar
        total_files = source_session.query(FileMeta).count()
        logger.info(f"Found {total_files} files in source database")

        if total_files == 0:
            logger.warning("No files found in source database")
            return stats

        # Process files in batches
        batch_size = 200
        batch_data = []

        with tqdm(
            total=total_files, desc=f"Merging {source_db_path.name}", unit="files"
        ) as pbar:
            # Query all files with their hashes
            files_query = (
                source_session.query(FileMeta, FileHash)
                .outerjoin(FileHash, FileMeta.hash_id == FileHash.id)
                .yield_per(batch_size)
            )

            for file_meta, file_hash in files_query:
                stats["total_files_processed"] += 1

                # Check if file already exists in target database
                dto = target_db_manager.get_file_with_hash_by_path(file_meta.path)

                if dto:
                    # Check if file data is identical
                    if (
                        dto.hash
                        and file_hash
                        and dto.hash.md5 == file_hash.md5
                        and dto.hash.sha1 == file_hash.sha1
                        and dto.hash.sha256 == file_hash.sha256
                        and dto.meta.machine == file_meta.machine
                    ):
                        # File already exists with same data, skip
                        stats["files_skipped"] += 1
                        pbar.update(1)
                        continue

                # Create new FileMeta and FileHash objects for target database
                new_file_meta = FileMeta(
                    name=file_meta.name,
                    path=file_meta.path,
                    machine=file_meta.machine,
                    created=file_meta.created,
                    modified=file_meta.modified,
                    scanned=file_meta.scanned,
                    operation=file_meta.operation,
                    is_archived=getattr(file_meta, "is_archived", 0),
                    archive_path=getattr(file_meta, "archive_path", None),
                )

                if file_hash:
                    new_file_hash = FileHash(
                        md5=file_hash.md5,
                        sha1=file_hash.sha1,
                        sha256=file_hash.sha256,
                        size=file_hash.size,
                    )

                    batch_data.append(
                        {
                            "file_meta": new_file_meta,
                            "file_hash": new_file_hash,
                            "operation": "ADD",
                        }
                    )
                else:
                    # File without hash (shouldn't happen normally, but handle it)
                    logger.warning(f"File without hash: {file_meta.path}")
                    batch_data.append(
                        {
                            "file_meta": new_file_meta,
                            "file_hash": None,
                            "operation": "ADD",
                        }
                    )

                # Flush batch when it reaches batch_size
                if len(batch_data) >= batch_size:
                    _flush_batch(batch_data, target_db_manager, stats)
                    batch_data.clear()

                pbar.update(1)

            # Flush remaining data
            if batch_data:
                _flush_batch(batch_data, target_db_manager, stats)

    except Exception as e:
        logger.error(f"Error merging database {source_db_path}: {e}")
        raise
    finally:
        source_session.close()
        source_engine.dispose()

    return stats


def _flush_batch(batch_data: list, target_db_manager: DatabaseManager, stats: dict):
    """
    Flush a batch of files to the target database.

    Args:
        batch_data: List of file data to insert
        target_db_manager: Target database manager
        stats: Statistics dictionary to update
    """
    try:
        # Get existing hashes to determine reuse vs new
        hash_data = []
        for item in batch_data:
            if item["file_hash"]:
                hash_data.append(
                    {
                        "md5": item["file_hash"].md5,
                        "sha1": item["file_hash"].sha1,
                        "sha256": item["file_hash"].sha256,
                    }
                )

        existing_hashes = target_db_manager.get_existing_hashes_batch(hash_data)

        # Count new vs reused hashes
        for item in batch_data:
            if item["file_hash"]:
                hash_key = (
                    item["file_hash"].md5,
                    item["file_hash"].sha1,
                    item["file_hash"].sha256,
                )
                if hash_key in existing_hashes:
                    stats["hashes_reused"] += 1
                else:
                    stats["hashes_added"] += 1

        # Add files using batch operation
        target_db_manager.add_files_batch(batch_data)
        stats["files_added"] += len(batch_data)

    except Exception as e:
        logger.error(f"Error flushing batch: {e}")
        raise
