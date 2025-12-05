"""Data Transfer Objects for database queries.

DTOs provide a clean separation between SQLAlchemy ORM layer and business logic.
They are simple dataclasses that can be safely passed across session boundaries.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class FileHashDTO:
    """Hash information DTO - immutable snapshot of FileHash ORM object."""

    id: int
    size: int
    md5: str
    sha1: str
    sha256: str

    @classmethod
    def from_orm(cls, obj) -> "FileHashDTO":
        """Create DTO from SQLAlchemy ORM object.

        Args:
            obj: FileHash ORM instance

        Returns:
            FileHashDTO with all attributes copied
        """
        return cls(
            id=obj.id,
            size=obj.size,
            md5=obj.md5,
            sha1=obj.sha1,
            sha256=obj.sha256,
        )


@dataclass
class FileMetaDTO:
    """File metadata DTO - immutable snapshot of FileMeta ORM object."""

    id: int
    hash_id: Optional[int]
    name: str
    path: str
    machine: str
    created: datetime
    modified: datetime
    scanned: datetime
    operation: str
    is_archived: int
    archive_path: Optional[str]

    @classmethod
    def from_orm(cls, obj) -> "FileMetaDTO":
        """Create DTO from SQLAlchemy ORM object.

        Args:
            obj: FileMeta ORM instance

        Returns:
            FileMetaDTO with all attributes copied
        """
        return cls(
            id=obj.id,
            hash_id=obj.hash_id,
            name=obj.name,
            path=obj.path,
            machine=obj.machine,
            created=obj.created,
            modified=obj.modified,
            scanned=obj.scanned,
            operation=obj.operation,
            is_archived=getattr(obj, "is_archived", 0),
            archive_path=getattr(obj, "archive_path", None),
        )


@dataclass
class FileWithHashDTO:
    """Combined file metadata and hash DTO."""

    meta: FileMetaDTO
    hash: Optional[FileHashDTO]

    @classmethod
    def from_orm(cls, file_meta, file_hash) -> "FileWithHashDTO":
        """Create DTO from pair of ORM objects.

        Args:
            file_meta: FileMeta ORM instance
            file_hash: FileHash ORM instance or None

        Returns:
            FileWithHashDTO containing both DTOs
        """
        return cls(
            meta=FileMetaDTO.from_orm(file_meta),
            hash=FileHashDTO.from_orm(file_hash) if file_hash else None,
        )
