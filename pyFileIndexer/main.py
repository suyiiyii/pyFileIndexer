import argparse
import datetime
import hashlib
import logging
import os
import queue
import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional, Union

from archive_scanner import (
    calculate_hash_from_data,
    create_archive_scanner,
    is_archive_file,
)
from cached_config import cached_config
from config import settings
from database import db_manager
from models import FileHash, FileMeta
from tqdm import tqdm

stop_event = threading.Event()
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
stream_hander = logging.StreamHandler()

formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(funcName)s - %(message)s"
)
stream_hander.setFormatter(formatter)
logger.addHandler(stream_hander)


def signal_handler(signum, frame):
    """处理中断信号 (Ctrl+C)"""
    logger.warning(f"收到中断信号 {signum}，正在停止扫描...")
    stop_event.set()
    # 给线程一些时间来响应 stop_event
    # 如果再次按 Ctrl+C，则强制退出
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(1))


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
    """Calculate MD5, SHA1, and SHA256 hashes of a file using hashlib with optimized I/O."""
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()

    # 优化：增大读取缓冲区从256KB到2MB，减少系统调用次数
    chunk_size = 1024 * 1024 * 2  # 2MB

    with open(file_path, "rb", buffering=chunk_size) as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            # 单次循环更新所有哈希算法，提高效率
            md5.update(chunk)
            sha1.update(chunk)
            sha256.update(chunk)

    return {
        "md5": md5.hexdigest(),
        "sha1": sha1.hexdigest(),
        "sha256": sha256.hexdigest(),
    }


def get_metadata(file: Path, stat_result: os.stat_result | None = None) -> FileMeta:
    """获取文件的元数据，提供合理默认值。"""
    if stat_result is None:
        stat_result = file.stat()

    # 优先使用缓存配置，但在测试环境中允许 mock 覆盖
    # 这样既提升了性能，又保持了测试兼容性
    try:
        # 首先尝试从 settings 获取（支持测试中的 mock）
        scanned = getattr(settings, "SCANNED", cached_config.scanned)
        machine = getattr(settings, "MACHINE_NAME", cached_config.machine_name)

        # 如果配置的是字符串时间，尝试解析
        if isinstance(scanned, str):
            try:
                scanned = datetime.datetime.fromisoformat(scanned)
            except ValueError:
                scanned = cached_config.scanned
    except Exception:
        # 如果出现任何问题，回退到缓存配置
        scanned = cached_config.scanned
        machine = cached_config.machine_name

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
    try:
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
        if cached_config.scan_archives and is_archive_file(file):
            scan_archive_file(file)
    except Exception as e:
        logger.error(f"Failed to scan file {file}: {type(e).__name__}: {e}")


def scan_archive_file(archive_path: Path):
    """扫描压缩包内的文件"""
    logger.info(f"Scanning archive: {archive_path}")

    # 检查压缩包大小限制
    max_size = cached_config.max_archive_size
    if archive_path.stat().st_size > max_size:
        logger.warning(
            f"Skipping large archive: {archive_path} ({archive_path.stat().st_size} bytes)"
        )
        return

    max_archive_file_size = cached_config.max_archive_file_size
    scanner = create_archive_scanner(archive_path, max_archive_file_size)
    if not scanner:
        logger.warning(f"Cannot create scanner for archive: {archive_path}")
        return

    try:
        machine = cached_config.machine_name
        scanned = cached_config.scanned

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
    current_file = None
    while not stop_event.is_set():
        try:
            file = filepaths.get()
            if file == Path():  # Dummy Path signals end
                break
            current_file = file
            logger.info(f"Scanning: {file}")
            scan_file(file)
            if pbar:
                pbar.update(1)
        except Exception as e:
            logger.exception(f"Unexpected error in worker thread while processing {current_file}: {type(e).__name__}: {e}")
            if pbar:
                pbar.update(1)
        finally:
            filepaths.task_done()
    logger.info("扫描工作线程结束。")


def should_skip_directory(path: Path) -> bool:
    """检查目录是否应该跳过。"""
    if path.name in ignore_dirs:
        return True
    if path.name.startswith("."):
        logger.info(f"Skipping start with . : {path}")
        return True
    if path.name.startswith("_"):
        logger.info(f"Skipping start with _ : {path}")
        return True
    for ignore_partial in ignore_partials_dirs:
        if ignore_partial in path.as_posix():
            return True
    return False


def scan_directory(directory: Path, output_queue: "queue.Queue[Path]", executor: Optional[ThreadPoolExecutor] = None):
    """遍历目录下的所有文件，支持多线程并发遍历子目录。"""
    if stop_event.is_set():
        return

    logger.debug(f"队列大小：{output_queue.qsize()}")
    subdirs = []

    try:
        for path in directory.iterdir():
            logger.debug(f":开始遍历 {path}")
            try:
                if path.is_dir():
                    if should_skip_directory(path):
                        continue
                    subdirs.append(path)
                else:
                    logger.debug(f":添加到扫描队列 {path}")
                    output_queue.put(path)
            except Exception as e:
                logger.error(f"Error processing path {path}: {type(e).__name__}: {e}")
    except Exception as e:
        logger.error(f"Error iterating directory {directory}: {type(e).__name__}: {e}")
        return

    # 并发处理子目录
    if executor and subdirs:
        futures = [executor.submit(scan_directory, subdir, output_queue, executor) for subdir in subdirs]
        # 等待所有子目录扫描完成
        for i, future in enumerate(futures):
            try:
                future.result()
            except Exception as e:
                logger.error(f"Error scanning subdirectory {subdirs[i]}: {type(e).__name__}: {e}")


def scan(path: Union[str, Path]):
    """扫描指定目录。"""
    if not os.path.exists(path):
        logger.error(f"Path not exists: {path}")
        return
    if isinstance(path, str):
        path = Path(path)
    # 更新扫描时间到缓存
    scan_time = datetime.datetime.now()
    cached_config.update_scanned_time(scan_time)
    setattr(settings, "SCANNED", scan_time)

    # 使用生产者消费者模型，先扫描目录，在对获取到的元数据进行处理
    filepaths: "queue.Queue[Path]" = queue.Queue(-1)

    num_threads = os.cpu_count() or 1

    # 第一阶段：使用独立的线程池并发遍历目录
    logger.info(f"使用 {num_threads} 个线程进行目录遍历")
    with ThreadPoolExecutor(max_workers=num_threads) as dir_executor:
        scan_directory(path, filepaths, dir_executor)

    logger.info(f"目录遍历完成，共发现 {filepaths.qsize()} 个文件")

    # 为每个worker线程添加终止信号
    for _ in range(num_threads):
        filepaths.put(Path())  # Dummy Path to signal end

    # 第二阶段：启动多个worker线程处理文件（使用独立的线程，不是线程池）
    logger.info(f"启动 {num_threads} 个worker线程处理文件")
    workers = []
    with tqdm(total=filepaths.qsize() - num_threads) as pbar:  # 减去终止信号数量
        for i in range(num_threads):
            worker = threading.Thread(
                target=scan_file_worker,
                args=(filepaths, pbar),
                name=f"FileWorker-{i}"
            )
            worker.start()
            workers.append(worker)

        # 等待所有worker线程完成
        for worker in workers:
            worker.join()

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
        cached_config.update_machine_name(args.machine_name)

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

        # 注册信号处理器
        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)

        try:
            scan(args.path)
        except KeyboardInterrupt:
            # 第一次 Ctrl+C 由 signal_handler 处理
            # 这里捕获是为了避免堆栈输出
            logger.warning("扫描已中断")
        finally:
            if stop_event.is_set():
                logger.info("扫描已被用户中断。")
            else:
                logger.info("扫描完成。")
