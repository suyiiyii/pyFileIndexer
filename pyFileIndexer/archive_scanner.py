import logging
import tarfile
import zipfile
from pathlib import Path
from typing import Generator, Optional, Union
import datetime

import rarfile

from models import FileMeta

logger = logging.getLogger(__name__)

# 支持的压缩包格式
SUPPORTED_ARCHIVE_FORMATS = {
    '.zip': 'zip',
    '.tar': 'tar',
    '.tar.gz': 'tar',
    '.tgz': 'tar',
    '.tar.bz2': 'tar',
    '.tbz2': 'tar',
    '.tar.xz': 'tar',
    '.txz': 'tar',
    '.rar': 'rar'
}


def is_archive_file(file_path: Union[str, Path]) -> bool:
    """检查文件是否为支持的压缩包格式"""
    file_path = Path(file_path)

    for ext in SUPPORTED_ARCHIVE_FORMATS:
        if file_path.name.lower().endswith(ext):
            return True
    return False


def get_archive_type(file_path: Union[str, Path]) -> Optional[str]:
    """获取压缩包类型"""
    file_path = Path(file_path)

    for ext, archive_type in SUPPORTED_ARCHIVE_FORMATS.items():
        if file_path.name.lower().endswith(ext):
            return archive_type
    return None


class ArchiveEntry:
    """压缩包内文件条目"""

    def __init__(self, name: str, size: int, modified: datetime.datetime,
                 is_dir: bool = False, data_reader: Optional[callable] = None):
        self.name = name
        self.size = size
        self.modified = modified
        self.is_dir = is_dir
        self.data_reader = data_reader

    def read_data(self) -> bytes:
        """读取文件数据"""
        if self.data_reader:
            return self.data_reader()
        return b""


class ArchiveScanner:
    """压缩包扫描器基类"""

    def __init__(self, archive_path: Union[str, Path], max_file_size: Optional[int] = None):
        self.archive_path = Path(archive_path)
        self.max_file_size = max_file_size or 100 * 1024 * 1024  # 100MB

    def scan_entries(self) -> Generator[ArchiveEntry, None, None]:
        """扫描压缩包内的文件条目"""
        raise NotImplementedError

    def create_virtual_path(self, internal_path: str) -> str:
        """创建虚拟路径格式：archive_path::internal_path"""
        return f"{self.archive_path.as_posix()}::{internal_path}"

    def create_file_meta(self, entry: ArchiveEntry, machine: str,
                        scanned: datetime.datetime) -> FileMeta:
        """为压缩包内文件创建FileMeta对象"""
        virtual_path = self.create_virtual_path(entry.name)

        meta = FileMeta(
            name=Path(entry.name).name,
            path=virtual_path,
            machine=machine,
            created=entry.modified,  # 使用压缩包内的修改时间作为创建时间
            modified=entry.modified,
            scanned=scanned,
            is_archived=1,
            archive_path=str(self.archive_path.absolute())
        )
        return meta


class ZipArchiveScanner(ArchiveScanner):
    """ZIP文件扫描器"""

    def scan_entries(self) -> Generator[ArchiveEntry, None, None]:
        try:
            with zipfile.ZipFile(self.archive_path, 'r') as zip_file:
                for info in zip_file.filelist:
                    # 跳过目录
                    if info.is_dir():
                        continue

                    # 跳过过大的文件
                    if info.file_size > self.max_file_size:
                        logger.warning(f"Skipping large file in ZIP: {info.filename} ({info.file_size} bytes)")
                        continue

                    # 获取修改时间
                    try:
                        modified = datetime.datetime(*info.date_time)
                    except (ValueError, TypeError):
                        modified = datetime.datetime.now()

                    # 直接读取数据而不是创建延迟读取器
                    try:
                        data = zip_file.read(info.filename)

                        def make_reader(file_data):
                            return lambda: file_data

                        entry = ArchiveEntry(
                            name=info.filename,
                            size=info.file_size,
                            modified=modified,
                            data_reader=make_reader(data)
                        )
                        yield entry
                    except Exception as e:
                        logger.error(f"Error reading file {info.filename} from ZIP: {e}")
                        continue
        except Exception as e:
            logger.error(f"Error scanning ZIP file {self.archive_path}: {e}")


class TarArchiveScanner(ArchiveScanner):
    """TAR文件扫描器"""

    def scan_entries(self) -> Generator[ArchiveEntry, None, None]:
        try:
            with tarfile.open(self.archive_path, 'r:*') as tar_file:
                for member in tar_file.getmembers():
                    # 跳过目录
                    if member.isdir():
                        continue

                    # 跳过非常规文件
                    if not member.isfile():
                        continue

                    # 跳过过大的文件
                    if member.size > self.max_file_size:
                        logger.warning(f"Skipping large file in TAR: {member.name} ({member.size} bytes)")
                        continue

                    # 获取修改时间
                    try:
                        modified = datetime.datetime.fromtimestamp(member.mtime)
                    except (ValueError, OSError):
                        modified = datetime.datetime.now()

                    # 直接读取数据
                    try:
                        extracted_file = tar_file.extractfile(member)
                        if extracted_file:
                            data = extracted_file.read()

                            def make_reader(file_data):
                                return lambda: file_data

                            entry = ArchiveEntry(
                                name=member.name,
                                size=member.size,
                                modified=modified,
                                data_reader=make_reader(data)
                            )
                            yield entry
                        else:
                            logger.warning(f"Cannot extract file {member.name} from TAR")
                    except Exception as e:
                        logger.error(f"Error reading file {member.name} from TAR: {e}")
                        continue
        except Exception as e:
            logger.error(f"Error scanning TAR file {self.archive_path}: {e}")


class RarArchiveScanner(ArchiveScanner):
    """RAR文件扫描器"""

    def scan_entries(self) -> Generator[ArchiveEntry, None, None]:
        try:
            with rarfile.RarFile(self.archive_path) as rar_file:
                for info in rar_file.infolist():
                    # 跳过目录
                    if info.is_dir():
                        continue

                    # 跳过过大的文件
                    if info.file_size > self.max_file_size:
                        logger.warning(f"Skipping large file in RAR: {info.filename} ({info.file_size} bytes)")
                        continue

                    # 获取修改时间
                    try:
                        modified = info.date_time
                        if not isinstance(modified, datetime.datetime):
                            modified = datetime.datetime.now()
                    except (ValueError, AttributeError):
                        modified = datetime.datetime.now()

                    # 直接读取数据
                    try:
                        data = rar_file.read(info.filename)

                        def make_reader(file_data):
                            return lambda: file_data

                        entry = ArchiveEntry(
                            name=info.filename,
                            size=info.file_size,
                            modified=modified,
                            data_reader=make_reader(data)
                        )
                        yield entry
                    except Exception as e:
                        logger.error(f"Error reading file {info.filename} from RAR: {e}")
                        continue
        except Exception as e:
            logger.error(f"Error scanning RAR file {self.archive_path}: {e}")


def create_archive_scanner(archive_path: Union[str, Path], max_file_size: Optional[int] = None) -> Optional[ArchiveScanner]:
    """创建适当的压缩包扫描器"""
    archive_type = get_archive_type(archive_path)

    if archive_type == 'zip':
        return ZipArchiveScanner(archive_path, max_file_size)
    elif archive_type == 'tar':
        return TarArchiveScanner(archive_path, max_file_size)
    elif archive_type == 'rar':
        return RarArchiveScanner(archive_path, max_file_size)
    else:
        logger.warning(f"Unsupported archive type for {archive_path}")
        return None


def calculate_hash_from_data(data: bytes) -> dict[str, str]:
    """从字节数据计算文件哈希"""
    import hashlib

    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()

    md5.update(data)
    sha1.update(data)
    sha256.update(data)

    return {
        "md5": md5.hexdigest(),
        "sha1": sha1.hexdigest(),
        "sha256": sha256.hexdigest(),
    }