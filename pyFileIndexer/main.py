import argparse
import datetime
import hashlib
import logging
import os
import queue
import threading
from pathlib import Path
from typing import Any, Optional, Union

from config import settings
from database import db_manager
from models import FileHash, FileMeta
from tqdm import tqdm
from archive_scanner import (
    is_archive_file,
    create_archive_scanner,
    calculate_hash_from_data,
)

stop_event = threading.Event()
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
stream_hander = logging.StreamHandler()

formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(funcName)s - %(message)s"
)
stream_hander.setFormatter(formatter)
logger.addHandler(stream_hander)


def init_file_logger(log_path: str):
    file_hander = logging.FileHandler(log_path, encoding="utf-8")
    file_hander.setFormatter(formatter)
    logger.addHandler(file_hander)


ignore_file = ".ignore"
ignore_dirs: set[str] = set()
ignore_partials_dirs: set[str] = set()
if os.path.exists(ignore_file):
    with open(ignore_file) as f:
        for line in f:
            line = line.strip()
            if line:
                if line.startswith("#"):
                    continue
                if "/" in line:
                    ignore_partials_dirs.add(line)
                else:
                    ignore_dirs.add(line)


def human_size(
    bytes: int, units: list[str] = ["B", "KB", "MB", "GB", "TB", "PB", "EB"]
) -> str:
    if bytes < 1024:
        return str(bytes) + units[0]
    return human_size(bytes >> 10, units[1:])


def get_hashes(file_path: Union[str, Path]) -> dict[str, str]:
    """Calculate MD5, SHA1, and SHA256 hashes of a file using hashlib."""
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(1024 * 256)
            if not chunk:
                break
            md5.update(chunk)
            sha1.update(chunk)
            sha256.update(chunk)

    return {
        "md5": md5.hexdigest(),
        "sha1": sha1.hexdigest(),
        "sha256": sha256.hexdigest(),
    }


def get_metadata(file: Path, stat_result: os.stat_result = None) -> FileMeta:
    """获取文件的元数据，提供合理默认值。"""
    if stat_result is None:
        stat_result = file.stat()

    # 提供合理的默认值，而不是严格要求配置
    scanned = getattr(settings, "SCANNED", datetime.datetime.now())
    machine = getattr(settings, "MACHINE_NAME", "localhost")

    # 如果配置的是字符串时间，尝试解析
    if isinstance(scanned, str):
        try:
            scanned = datetime.datetime.fromisoformat(scanned)
        except ValueError:
            scanned = datetime.datetime.now()

    meta = FileMeta(
        name=file.name,
        path=str(file.absolute()),
        machine=machine,
        created=datetime.datetime.fromtimestamp(stat_result.st_ctime),
        modified=datetime.datetime.fromtimestamp(stat_result.st_mtime),
        scanned=scanned,
    )
    return meta


lock = threading.Lock()


class BatchProcessor:
    """批量文件处理器"""

    def __init__(self, batch_size: int = 200):
        self.batch_size = batch_size
        self.batch_data = []
        self.lock = threading.Lock()

    def add_file(self, file_meta, file_hash, operation):
        """添加文件到批量处理队列"""
        with self.lock:
            self.batch_data.append(
                {"file_meta": file_meta, "file_hash": file_hash, "operation": operation}
            )

            # 检查是否需要刷新批量
            if len(self.batch_data) >= self.batch_size:
                self._flush_batch()

    def _flush_batch(self):
        """刷新当前批量到数据库"""
        if not self.batch_data:
            return

        try:
            db_manager.add_files_batch(self.batch_data.copy())
            logger.info(f"批量处理了 {len(self.batch_data)} 个文件")
            self.batch_data.clear()
        except Exception as e:
            logger.error(f"批量处理失败: {e}")
            raise

    def flush(self):
        """强制刷新剩余的数据"""
        with self.lock:
            self._flush_batch()

    def clear(self):
        """清空批量数据（用于测试或重置）"""
        with self.lock:
            self.batch_data.clear()


# 全局批量处理器
batch_processor = BatchProcessor()


def scan_file(file: Path):
    """扫描单个文件，收集文件信息并添加到批量处理队列。"""
    # 优化：只调用一次 file.stat()
    file_stat = file.stat()
    meta = get_metadata(file, file_stat)
    # 默认操作为添加
    meta.operation = "ADD"  # type: ignore[attr-defined]

    # 检查文件是否已存在（优化：一次查询获取文件和哈希信息）
    result = db_manager.get_file_with_hash_by_path(file.absolute().as_posix())
    if result:
        meta_in_db, hash_in_db = result
        if hash_in_db and file_stat.st_size == getattr(hash_in_db, "size", None):
            # 如果文件的创建时间和修改时间没有变化
            if getattr(meta, "created", None) == getattr(
                meta_in_db, "created", None
            ) and getattr(meta, "modified", None) == getattr(
                meta_in_db, "modified", None
            ):
                logger.info(f"Skipping: {file}")
                return
        # 文件有变化，标记为修改
        meta.operation = "MOD"  # type: ignore[attr-defined]

    # 获取文件哈希
    hashes = get_hashes(file)
    file_hash = FileHash(**hashes, size=file_stat.st_size)

    # 添加到批量处理队列
    batch_processor.add_file(meta, file_hash, meta.operation)

    # 如果启用了压缩包扫描并且是压缩包文件，扫描内部文件
    if getattr(settings, "SCAN_ARCHIVES", True) and is_archive_file(file):
        scan_archive_file(file)


def scan_archive_file(archive_path: Path):
    """扫描压缩包内的文件"""
    logger.info(f"Scanning archive: {archive_path}")

    # 检查压缩包大小限制
    max_size = getattr(settings, "MAX_ARCHIVE_SIZE", 500 * 1024 * 1024)  # 默认500MB
    if archive_path.stat().st_size > max_size:
        logger.warning(
            f"Skipping large archive: {archive_path} ({archive_path.stat().st_size} bytes)"
        )
        return

    max_archive_file_size = getattr(
        settings, "MAX_ARCHIVE_FILE_SIZE", 100 * 1024 * 1024
    )
    scanner = create_archive_scanner(archive_path, max_archive_file_size)
    if not scanner:
        logger.warning(f"Cannot create scanner for archive: {archive_path}")
        return

    try:
        machine = getattr(settings, "MACHINE_NAME", "localhost")
        scanned = getattr(settings, "SCANNED", datetime.datetime.now())

        for entry in scanner.scan_entries():
            try:
                # 检查虚拟路径是否已存在
                virtual_path = scanner.create_virtual_path(entry.name)
                existing_result = db_manager.get_file_with_hash_by_path(virtual_path)

                # 创建文件元数据
                file_meta = scanner.create_file_meta(entry, machine, scanned)
                file_meta.operation = "ADD"  # type: ignore[attr-defined]

                if existing_result:
                    # 文件已存在，检查是否需要更新
                    existing_meta, existing_hash = existing_result
                    if (
                        existing_hash
                        and entry.size == getattr(existing_hash, "size", None)
                        and getattr(file_meta, "modified", None)
                        == getattr(existing_meta, "modified", None)
                    ):
                        logger.debug(
                            f"Skipping unchanged archived file: {virtual_path}"
                        )
                        continue
                    file_meta.operation = "MOD"  # type: ignore[attr-defined]

                # 计算文件哈希
                try:
                    data = entry.read_data()
                    hashes = calculate_hash_from_data(data)
                    file_hash = FileHash(**hashes, size=entry.size)

                    # 添加到批量处理队列
                    batch_processor.add_file(file_meta, file_hash, file_meta.operation)
                    logger.debug(f"Added archived file: {virtual_path}")

                except Exception as e:
                    logger.error(f"Error processing archived file {entry.name}: {e}")
                    continue

            except Exception as e:
                logger.error(f"Error processing archive entry {entry.name}: {e}")
                continue

    except Exception as e:
        logger.error(f"Error scanning archive {archive_path}: {e}")


def scan_file_worker(
    filepaths: "queue.Queue[Path]", pbar: Optional["tqdm[Any]"] = None
):
    """文件扫描工作线程。"""
    logger.info("扫描工作线程启动。")
    while not stop_event.is_set():
        try:
            file = filepaths.get()
            if file == Path():  # Dummy Path signals end
                break
            logger.info(f"Scanning: {file}")
            scan_file(file)
            if pbar:
                pbar.update(1)
        except Exception as e:
            logger.error(f"Error: {e}")
            logger.error(e)
        finally:
            filepaths.task_done()
    logger.info("扫描工作线程结束。")


def scan_directory(directory: Path, output_queue: "queue.Queue[Path]"):
    """遍历目录下的所有文件。"""
    if not stop_event.is_set():
        logger.debug(f"队列大小：{output_queue.qsize()}")
        for path in directory.iterdir():
            logger.debug(f":开始遍历 {path}")
            try:
                if path.is_dir():
                    if path.name in ignore_dirs:
                        continue
                    if path.name.startswith("."):
                        logger.info(f"Skipping start with . : {path}")
                        continue
                    if path.name.startswith("_"):
                        logger.info(f"Skipping start with _ : {path}")
                        continue
                    skip = False
                    for ignore_partial in ignore_partials_dirs:
                        if ignore_partial in path.as_posix():
                            skip = True
                            continue
                    if skip:
                        continue
                    scan_directory(path, output_queue)
                else:
                    logger.debug(f":添加到扫描队列 {path}")
                    output_queue.put(path)
            except IOError as e:
                logger.error(f"Error: {e}")
                logger.error(e)


def scan(path: Union[str, Path]):
    """扫描指定目录。"""
    if not os.path.exists(path):
        logger.error(f"Path not exists: {path}")
        return
    if isinstance(path, str):
        path = Path(path)
    # Dynaconf: set attribute
    setattr(settings, "SCANNED", datetime.datetime.now())
    # 使用生产者消费者模型，先扫描目录，在对获取到的元数据进行处理
    filepaths: "queue.Queue[Path]" = queue.Queue(-1)
    scan_directory(path, filepaths)
    for _ in range(os.cpu_count() or 1):
        filepaths.put(Path())  # Dummy Path to signal end
    with tqdm(total=filepaths.qsize()) as pbar:
        scan_file_worker(filepaths, pbar=pbar)

    # 刷新剩余的批量数据
    batch_processor.flush()
    logger.info("文件扫描结束。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="pyFileIndexer")

    # 创建互斥参数组：扫描模式 vs Web 模式
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("path", nargs="?", type=str, help="The path to scan.")
    mode_group.add_argument("--web", action="store_true", help="Start web server mode.")

    # 通用参数
    parser.add_argument("--machine_name", type=str, help="The machine name.")
    parser.add_argument(
        "--db_path", type=str, help="The database path.", default="indexer.db"
    )
    parser.add_argument(
        "--log_path", type=str, help="The log path.", default="indexer.log"
    )

    # Web 模式专用参数
    parser.add_argument(
        "--port", type=int, help="Web server port (default: 8000).", default=8000
    )
    parser.add_argument(
        "--host",
        type=str,
        help="Web server host (default: 0.0.0.0).",
        default="0.0.0.0",
    )

    args = parser.parse_args()

    # 传入的机器名称覆盖配置文件中的机器名称
    if args.machine_name:
        setattr(settings, "MACHINE_NAME", args.machine_name)

    # 初始化数据库和日志
    db_manager.init("sqlite:///" + str(args.db_path))
    init_file_logger(args.log_path)

    if args.web:
        # Web 服务器模式
        from web_server import start_web_server

        start_web_server(args.db_path, args.host, args.port)
    else:
        # 文件扫描模式
        if not args.path:
            parser.error("Path is required when not using --web mode")

        try:
            scan(args.path)
        except KeyboardInterrupt:
            stop_event.set()
            logger.error("KeyboardInterrupt")
        finally:
            logger.info("扫描完成。")
