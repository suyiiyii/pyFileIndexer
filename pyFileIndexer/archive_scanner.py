import logging
import tarfile
import zipfile
from pathlib import Path
from typing import Generator, Optional, Union
import datetime

import rarfile

from .models import FileMeta
from .cached_config import cached_config
from .metrics import metrics

logger = logging.getLogger(__name__)

# 检查 RAR 工具可用性
RAR_TOOL_AVAILABLE = False
try:
    rarfile.tool_setup()
    RAR_TOOL_AVAILABLE = True
    logger.info(f"RAR support enabled using tool: {rarfile.UNRAR_TOOL}")
except rarfile.RarCannotExec:
    logger.warning(
        "RAR support disabled: No extraction tool found. "
        "Install 'unar' (recommended), 'unrar', or '7z' to enable RAR support. "
        "macOS: brew install unar | Linux: apt-get install unar"
    )

# 支持的压缩包格式
SUPPORTED_ARCHIVE_FORMATS = {
    ".zip": "zip",
    ".tar": "tar",
    ".tar.gz": "tar",
    ".tgz": "tar",
    ".tar.bz2": "tar",
    ".tbz2": "tar",
    ".tar.xz": "tar",
    ".txz": "tar",
    ".rar": "rar",
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

    def __init__(
        self,
        name: str,
        size: int,
        modified: datetime.datetime,
        is_dir: bool = False,
        data_reader: Optional[callable] = None,
    ):
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

    def __init__(
        self, archive_path: Union[str, Path], max_file_size: Optional[int] = None
    ):
        self.archive_path = Path(archive_path)
        self.max_file_size = max_file_size or 100 * 1024 * 1024  # 100MB

    def scan_entries(self) -> Generator[ArchiveEntry, None, None]:
        """扫描压缩包内的文件条目"""
        raise NotImplementedError

    def create_virtual_path(self, internal_path: str) -> str:
        """创建虚拟路径格式：archive_path::internal_path"""
        return f"{self.archive_path.as_posix()}::{internal_path}"

    def create_file_meta(
        self, entry: ArchiveEntry, machine: str, scanned: datetime.datetime
    ) -> FileMeta:
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
            archive_path=str(self.archive_path.absolute()),
        )
        return meta


class ZipArchiveScanner(ArchiveScanner):
    """ZIP文件扫描器"""

    def _decode_filename(self, zip_info: zipfile.ZipInfo) -> str:
        """
        正确解码 ZIP 文件名，处理中文编码问题

        Args:
            zip_info: ZipInfo 对象

        Returns:
            正确解码的文件名
        """
        # 检查 UTF-8 标志位（bit 11）
        if zip_info.flag_bits & 0x800:
            # 文件名已经是 UTF-8 编码
            return zip_info.filename

        # 没有 UTF-8 标志，可能是 GBK 等其他编码
        # 先获取原始字节（通过 cp437 重新编码）
        try:
            raw_bytes = zip_info.filename.encode("cp437")
        except (UnicodeEncodeError, UnicodeDecodeError):
            # 如果 cp437 编码失败，返回原文件名
            return zip_info.filename

        # 尝试多种编码解码
        encodings = ["gbk", "gb18030", "utf-8", "big5"]
        for encoding in encodings:
            try:
                decoded = raw_bytes.decode(encoding)
                # 成功解码，返回结果
                return decoded
            except (UnicodeDecodeError, LookupError):
                continue

        # 所有编码都失败，返回原文件名
        logger.warning(f"Cannot decode filename: {zip_info.filename!r}")
        return zip_info.filename

    def scan_entries(self) -> Generator[ArchiveEntry, None, None]:
        fails = 0
        threshold = getattr(cached_config, "archive_entry_fail_threshold", 50)
        try:
            with zipfile.ZipFile(self.archive_path, "r") as zip_file:
                try:
                    entries = zip_file.infolist()
                except Exception as e:
                    logger.error(
                        f"Error listing entries in ZIP {self.archive_path}: {e}"
                    )
                    metrics.inc_errors("archive_list")
                    return
                for info in entries:
                    try:
                        # 解码文件名
                        decoded_filename = self._decode_filename(info)

                        # 跳过目录
                        if info.is_dir():
                            continue

                        # 跳过过大的文件
                        if info.file_size > self.max_file_size:
                            logger.warning(
                                f"Skipping large file in ZIP: {decoded_filename} ({info.file_size} bytes)"
                            )
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
                                name=decoded_filename,
                                size=info.file_size,
                                modified=modified,
                                data_reader=make_reader(data),
                            )
                            yield entry
                        except (zipfile.BadZipFile, zipfile.LargeZipFile, Exception) as e:
                            logger.warning(
                                f"Error reading file {decoded_filename} from ZIP: {e}"
                            )
                            metrics.inc_errors("archive_entry_read")
                            fails += 1
                            if fails >= threshold:
                                logger.warning(
                                    f"Too many entry read failures in ZIP, skipping archive: {self.archive_path}"
                                )
                                break
                            continue
                    except Exception as e:
                        # 捕获处理单个条目时的任何未预期异常
                        logger.warning(
                            f"Unexpected error processing entry in ZIP {self.archive_path}: {e}"
                        )
                        fails += 1
                        if fails >= threshold:
                            logger.warning(
                                f"Too many failures in ZIP, skipping archive: {self.archive_path}"
                            )
                            break
                        continue
        except (zipfile.BadZipFile, Exception) as e:
            logger.error(f"Error scanning ZIP file {self.archive_path}: {e}")
            metrics.inc_errors("archive_open")


class TarArchiveScanner(ArchiveScanner):
    """TAR文件扫描器"""

    def scan_entries(self) -> Generator[ArchiveEntry, None, None]:
        fails = 0
        threshold = getattr(cached_config, "archive_entry_fail_threshold", 50)
        try:
            with tarfile.open(self.archive_path, "r:*") as tar_file:
                try:
                    members = tar_file.getmembers()
                except Exception as e:
                    logger.error(
                        f"Error listing entries in TAR {self.archive_path}: {e}"
                    )
                    metrics.inc_errors("archive_list")
                    return
                for member in members:
                    try:
                        # 跳过目录
                        if member.isdir():
                            continue

                        # 跳过非常规文件
                        if not member.isfile():
                            continue

                        # 跳过过大的文件
                        if member.size > self.max_file_size:
                            logger.warning(
                                f"Skipping large file in TAR: {member.name} ({member.size} bytes)"
                            )
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
                                    data_reader=make_reader(data),
                                )
                                yield entry
                            else:
                                logger.warning(
                                    f"Cannot extract file {member.name} from TAR"
                                )
                        except (tarfile.ReadError, Exception) as e:
                            logger.warning(f"Error reading file {member.name} from TAR: {e}")
                            metrics.inc_errors("archive_entry_read")
                            fails += 1
                            if fails >= threshold:
                                logger.warning(
                                    f"Too many entry read failures in TAR, skipping archive: {self.archive_path}"
                                )
                                break
                            continue
                    except Exception as e:
                        # 捕获处理单个条目时的任何未预期异常
                        logger.warning(
                            f"Unexpected error processing entry in TAR {self.archive_path}: {e}"
                        )
                        fails += 1
                        if fails >= threshold:
                            logger.warning(
                                f"Too many failures in TAR, skipping archive: {self.archive_path}"
                            )
                            break
                        continue
        except (tarfile.ReadError, Exception) as e:
            logger.error(f"Error scanning TAR file {self.archive_path}: {e}")
            metrics.inc_errors("archive_open")


class RarArchiveScanner(ArchiveScanner):
    """RAR文件扫描器"""

    def scan_entries(self) -> Generator[ArchiveEntry, None, None]:
        fails = 0
        threshold = getattr(cached_config, "archive_entry_fail_threshold", 50)
        try:
            with rarfile.RarFile(self.archive_path) as rar_file:
                try:
                    infos = rar_file.infolist()
                except (rarfile.Error, Exception) as e:
                    logger.error(
                        f"Error listing entries in RAR {self.archive_path}: {e}"
                    )
                    metrics.inc_errors("archive_list")
                    return
                for info in infos:
                    try:
                        # 跳过目录
                        if info.is_dir():
                            continue

                        # 跳过过大的文件
                        if info.file_size > self.max_file_size:
                            logger.warning(
                                f"Skipping large file in RAR: {info.filename} ({info.file_size} bytes)"
                            )
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
                                data_reader=make_reader(data),
                            )
                            yield entry
                        except (
                            rarfile.BadRarFile,
                            rarfile.NeedFirstVolume,
                            rarfile.RarCRCError,
                            rarfile.Error,
                            Exception,
                        ) as e:
                            logger.warning(
                                f"Error reading file {info.filename} from RAR: {e}"
                            )
                            metrics.inc_errors("archive_entry_read")
                            fails += 1
                            if fails >= threshold:
                                logger.warning(
                                    f"Too many entry read failures in RAR, skipping archive: {self.archive_path}"
                                )
                                break
                            continue
                    except Exception as e:
                        # 捕获处理单个条目时的任何未预期异常
                        logger.warning(
                            f"Unexpected error processing entry in RAR {self.archive_path}: {e}"
                        )
                        fails += 1
                        if fails >= threshold:
                            logger.warning(
                                f"Too many failures in RAR, skipping archive: {self.archive_path}"
                            )
                            break
                        continue
        except (rarfile.Error, Exception) as e:
            logger.error(f"Error scanning RAR file {self.archive_path}: {e}")
            metrics.inc_errors("archive_open")


def create_archive_scanner(
    archive_path: Union[str, Path], max_file_size: Optional[int] = None
) -> Optional[ArchiveScanner]:
    """创建适当的压缩包扫描器"""
    archive_type = get_archive_type(archive_path)

    if archive_type == "zip":
        return ZipArchiveScanner(archive_path, max_file_size)
    elif archive_type == "tar":
        return TarArchiveScanner(archive_path, max_file_size)
    elif archive_type == "rar":
        if not RAR_TOOL_AVAILABLE:
            logger.warning(
                f"Skipping RAR file {archive_path}: RAR extraction tool not available. "
                "Install 'unar', 'unrar', or '7z' to enable RAR support."
            )
            return None
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
