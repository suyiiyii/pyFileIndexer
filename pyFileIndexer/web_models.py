from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel


class FileHashResponse(BaseModel):
    id: Optional[int] = None
    size: int
    md5: str
    sha1: str
    sha256: str


class FileMetaResponse(BaseModel):
    id: Optional[int] = None
    hash_id: Optional[int] = None
    name: str
    path: str
    machine: str
    created: datetime
    modified: datetime
    scanned: datetime
    operation: str


class FileWithHashResponse(BaseModel):
    meta: FileMetaResponse
    hash: Optional[FileHashResponse] = None


class PaginatedFilesResponse(BaseModel):
    files: List[FileWithHashResponse]
    total: int
    page: int
    per_page: int
    pages: int


class StatisticsResponse(BaseModel):
    total_files: int
    total_size: int
    machine_stats: Dict[str, int]
    duplicate_files: int


class DuplicateFileGroup(BaseModel):
    hash: str
    files: List[FileWithHashResponse]


class DuplicateFilesResponse(BaseModel):
    duplicates: List[DuplicateFileGroup]
    total_groups: int  # 总重复组数
    total_files: int  # 本页的总重复文件数
    page: int
    per_page: int
    pages: int  # 总页数


class SearchFiltersRequest(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    machine: Optional[str] = None
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    hash_value: Optional[str] = None


class TreeFileInfo(BaseModel):
    name: str
    size: int
    modified: datetime
    hash: Optional[FileHashResponse] = None


class TreeDataResponse(BaseModel):
    current_path: str
    directories: List[str]
    files: List[TreeFileInfo]
