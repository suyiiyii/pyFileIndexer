import argparse
import datetime
import hashlib
import logging
import os
import queue
import signal
import time
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional, Union

from archive_scanner import (
    calculate_hash_from_data,
    create_archive_scanner,
    is_archive_file,
    get_archive_type,
)
from cached_config import cached_config
from config import settings
from database import db_manager
from models import FileHash, FileMeta
from tqdm import tqdm
from metrics import metrics

stop_event = threading.Event()
logger = logging.getLogger()
logger.setLevel(logging.INFO)
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
            t0 = time.time()
            count = len(self.batch_data)
            db_manager.add_files_batch(self.batch_data.copy())
            logger.info(f"批量处理了 {len(self.batch_data)} 个文件")
            self.batch_data.clear()
            try:
                metrics.inc_db_writes(count)
                metrics.observe_db_flush(time.time() - t0, count)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"批量处理失败: {e}")
            try:
                metrics.inc_errors("db_flush")
            except Exception:
                pass
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
            meta.operation = "MOD"  # type: ignore[attr-defined]

        # 获取文件哈希
        hashes = get_hashes(file)
        file_hash = FileHash(**hashes, size=file_stat.st_size)

        # 添加到批量处理队列
        batch_processor.add_file(meta, file_hash, meta.operation)
        try:
            metrics.inc_bytes(file_stat.st_size)
        except Exception:
            pass

        # 如果启用了压缩包扫描并且是压缩包文件，扫描内部文件
        if cached_config.scan_archives and is_archive_file(file):
            scan_archive_file(file)
    except Exception as e:
        logger.error(f"Failed to scan file {file}: {type(e).__name__}: {e}")
        try:
            metrics.inc_errors("scan_file")
        except Exception:
            pass


def scan_archive_file(archive_path: Path):
    """扫描压缩包内的文件"""
    logger.info(f"Scanning archive: {archive_path}")
    try:
        archive_type = get_archive_type(archive_path) or "unknown"
        metrics.inc_archives(archive_type)
    except Exception:
        archive_type = "unknown"

    # 检查压缩包大小限制
    max_size = cached_config.max_archive_size
    if archive_path.stat().st_size > max_size:
        logger.warning(
            f"Skipping large archive: {archive_path} ({archive_path.stat().st_size} bytes)"
        )
        try:
            metrics.inc_errors("archive_skip")
        except Exception:
            pass
        return

    max_archive_file_size = cached_config.max_archive_file_size
    scanner = create_archive_scanner(archive_path, max_archive_file_size)
    if not scanner:
        logger.warning(f"Cannot create scanner for archive: {archive_path}")
        try:
            metrics.inc_errors("archive_skip")
        except Exception:
            pass
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
                    try:
                        metrics.inc_archive_entries(archive_type)
                        metrics.inc_bytes(entry.size)
                    except Exception:
                        pass

                except Exception as e:
                    logger.error(f"Error processing archived file {entry.name}: {e}")
                    try:
                        metrics.inc_errors("archive_read")
                    except Exception:
                        pass
                    continue

            except Exception as e:
                logger.error(f"Error processing archive entry {entry.name}: {e}")
                continue

    except Exception as e:
        logger.error(f"Error scanning archive {archive_path}: {e}")
        try:
            metrics.inc_errors("scan_archive")
        except Exception:
            pass


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
            logger.debug(f"Scanning: {file}")
            t0 = time.time()
            scan_file(file)
            try:
                metrics.inc_files()
                metrics.observe_file_duration(time.time() - t0)
            except Exception:
                pass
            if pbar:
                pbar.update(1)
        except Exception as e:
            logger.exception(f"Unexpected error in worker thread while processing {current_file}: {type(e).__name__}: {e}")
            try:
                metrics.inc_errors("worker")
            except Exception:
                pass
            if pbar:
                pbar.update(1)
        finally:
            filepaths.task_done()
    logger.info("扫描工作线程结束。")


def should_skip_directory(path: Path) -> bool:
    """检查目录是否应该跳过。"""
    if not cached_config.skip_rules_enabled:
        return False
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


def scan_directory(directory: Path, file_queue: "queue.Queue[Path]", dir_queue: "queue.Queue[Path]", pbar: Optional["tqdm[Any]"] = None):
    """遍历单个目录，将文件放入file_queue，子目录放入dir_queue（非递归，BFS方式）。"""
    if stop_event.is_set():
        return

    logger.debug(f"正在扫描目录: {directory}")
    metrics.inc_dirs()

    try:
        for path in directory.iterdir():
            if stop_event.is_set():
                break

            try:
                if path.is_dir():
                    if should_skip_directory(path):
                        logger.debug(f"跳过目录: {path}")
                        continue
                    logger.debug(f"发现子目录: {path}")
                    dir_queue.put(path)  # 将子目录放入目录队列
                else:
                    logger.debug(f"发现文件: {path}")
                    file_queue.put(path)  # 将文件放入文件队列
                    # 更新进度条总数
                    if pbar is not None:
                        with lock:
                            pbar.total = (pbar.total or 0) + 1
            except Exception as e:
                logger.error(f"Error processing path {path}: {type(e).__name__}: {e}")
    except Exception as e:
        logger.error(f"Error iterating directory {directory}: {type(e).__name__}: {e}")


def scan(path: Union[str, Path]):
    """扫描指定目录（使用BFS队列方式，避免递归死锁）。"""
    start_ts = time.time()
    metrics.set_scan_in_progress(1)
    if not os.path.exists(path):
        logger.error(f"Path not exists: {path}")
        metrics.set_scan_in_progress(0)
        return
    if isinstance(path, str):
        path = Path(path)
    # 更新扫描时间到缓存
    scan_time = datetime.datetime.now()
    cached_config.update_scanned_time(scan_time)
    setattr(settings, "SCANNED", scan_time)

    # 使用两个队列：目录队列和文件队列
    dir_queue: "queue.Queue[Path]" = queue.Queue()
    file_queue: "queue.Queue[Path]" = queue.Queue()

    # 将根目录放入目录队列
    dir_queue.put(path)

    num_threads = os.cpu_count() or 1

    logger.info(f"使用 {num_threads} 个线程并行进行目录遍历和文件处理")

    # 创建全局进度条
    pbar = tqdm(
        total=0,
        desc="扫描文件",
        unit="files",
        position=0,
        leave=True
    )

    # 每3秒强制刷新一次进度条
    refresh_stop_event = threading.Event()

    def _force_refresh():
        while not refresh_stop_event.is_set() and not stop_event.is_set():
            time.sleep(3)
            try:
                pbar.refresh()
                try:
                    metrics.set_queue_size(file_queue.qsize())
                    metrics.set_workers(sum(1 for w in workers if w.is_alive()))
                except Exception:
                    pass
            except Exception:
                pass

    refresh_thread = threading.Thread(target=_force_refresh, name="ProgressRefresher", daemon=True)
    refresh_thread.start()

    # 启动文件处理worker线程（在后台持续工作）
    workers = []

    for i in range(num_threads):
        worker = threading.Thread(
            target=scan_file_worker,
            args=(file_queue, pbar),
            name=f"FileWorker-{i}"
        )
        worker.start()
        workers.append(worker)

    # 同时进行目录遍历（BFS方式）
    with ThreadPoolExecutor(max_workers=num_threads) as dir_executor:
        # 使用集合跟踪未完成的futures，避免列表无限增长
        pending_futures = set()

        while not stop_event.is_set():
            # 清理已完成的futures
            pending_futures = {f for f in pending_futures if not f.done()}

            # 尝试从目录队列获取目录
            try:
                directory = dir_queue.get(timeout=0.1)
                # 提交目录扫描任务并记录future
                future = dir_executor.submit(scan_directory, directory, file_queue, dir_queue, pbar)
                pending_futures.add(future)
                dir_queue.task_done()
            except queue.Empty:
                # 目录队列为空
                # 检查是否所有已提交的任务都完成了
                if dir_queue.empty() and len(pending_futures) == 0:
                    # 所有任务完成，目录遍历结束
                    break
                # 还有任务在执行或队列中可能会有新的目录，继续等待
                continue
            except Exception as e:
                logger.error(f"Error submitting directory scan task: {e}")
                dir_queue.task_done()

    logger.info("目录遍历完成，等待文件处理完成...")

    # 为每个worker线程添加终止信号
    for _ in range(num_threads):
        file_queue.put(Path())  # Dummy Path to signal end

    # 等待所有worker线程完成
    for worker in workers:
        worker.join()

    # 停止刷新线程并关闭进度条
    refresh_stop_event.set()
    try:
        refresh_thread.join(timeout=1)
    except Exception:
        pass
    pbar.close()

    # 刷新剩余的批量数据
    batch_processor.flush()
    logger.info("文件扫描结束。")
    metrics.set_scan_in_progress(0)
    try:
        metrics.observe_scan_duration(time.time() - start_ts)
    except Exception:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="pyFileIndexer - A file indexing system for tracking files across storage locations"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    subparsers.required = True

    # Scan 子命令
    scan_parser = subparsers.add_parser("scan", help="Scan directory and index files")
    scan_parser.add_argument("path", type=str, help="The directory path to scan")
    scan_parser.add_argument(
        "--machine-name", type=str, dest="machine_name", help="The machine name"
    )
    scan_parser.add_argument(
        "--db-path",
        type=str,
        dest="db_path",
        help="The database path (default: indexer.db)",
        default="indexer.db",
    )
    scan_parser.add_argument(
        "--log-path",
        type=str,
        dest="log_path",
        help="The log path (default: indexer.log)",
        default="indexer.log",
    )
    scan_parser.add_argument(
        "--metrics-port",
        type=int,
        dest="metrics_port",
        help="Prometheus metrics port (0 to auto-select)",
        default=0,
    )
    scan_parser.add_argument(
        "--metrics-host",
        type=str,
        dest="metrics_host",
        help="Prometheus metrics host",
        default="0.0.0.0",
    )
    scan_parser.add_argument(
        "--disable-metrics",
        action="store_true",
        help="Disable metrics server",
        default=False,
    )

    # Serve 子命令
    serve_parser = subparsers.add_parser("serve", help="Start web server")
    serve_parser.add_argument(
        "--db-path",
        type=str,
        dest="db_path",
        help="The database path (default: indexer.db)",
        default="indexer.db",
    )
    serve_parser.add_argument(
        "--log-path",
        type=str,
        dest="log_path",
        help="The log path (default: indexer.log)",
        default="indexer.log",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        help="Web server port (default: 8000)",
        default=8000,
    )
    serve_parser.add_argument(
        "--host",
        type=str,
        help="Web server host (default: 0.0.0.0)",
        default="0.0.0.0",
    )

    # Merge 子命令
    merge_parser = subparsers.add_parser("merge", help="Merge multiple databases")
    merge_parser.add_argument(
        "--source",
        type=str,
        nargs="+",
        required=True,
        help="Source database files to merge",
    )
    merge_parser.add_argument(
        "--output",
        type=str,
        dest="db_path",
        help="Output database path (default: merged.db)",
        default="merged.db",
    )
    merge_parser.add_argument(
        "--log-path",
        type=str,
        dest="log_path",
        help="The log path (default: indexer.log)",
        default="indexer.log",
    )

    args = parser.parse_args()

    # 初始化数据库和日志
    db_manager.init("sqlite:///" + str(args.db_path))
    init_file_logger(args.log_path)

    if args.command == "scan":
        # 传入的机器名称覆盖配置文件中的机器名称
        if args.machine_name:
            setattr(settings, "MACHINE_NAME", args.machine_name)
            cached_config.update_machine_name(args.machine_name)

        metrics.init(cached_config.machine_name)
        if not getattr(args, "disable_metrics", False):
            try:
                if not metrics.enabled():
                    logger.info("Prometheus client not installed, metrics disabled")
                else:
                    start_port = args.metrics_port if args.metrics_port and args.metrics_port > 0 else 9000
                    max_port = start_port + 100
                    started = False
                    for port in range(start_port, max_port + 1):
                        try:
                            metrics.start_http_server(port, args.metrics_host)
                            logger.info(f"Metrics listening on {args.metrics_host}:{port}")
                            started = True
                            break
                        except Exception:
                            continue
                    if not started:
                        logger.warning("Metrics server start failed on all candidate ports")
            except Exception as e:
                logger.warning(f"Metrics server start failed: {e}")

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

    elif args.command == "serve":
        # Web 服务器模式
        from web_server import start_web_server

        start_web_server(args.db_path, args.host, args.port)

    elif args.command == "merge":
        # 数据库合并模式
        from db_merge import merge_databases

        logger.info("开始合并数据库...")
        logger.info(f"源数据库: {args.source}")
        logger.info(f"目标数据库: {args.db_path}")

        try:
            stats = merge_databases(args.source, db_manager)
            logger.info("数据库合并完成！")
            logger.info("统计信息:")
            logger.info(f"  处理文件总数: {stats['total_files_processed']}")
            logger.info(f"  添加文件数: {stats['files_added']}")
            logger.info(f"  跳过文件数: {stats['files_skipped']}")
            logger.info(f"  新增哈希数: {stats['hashes_added']}")
            logger.info(f"  复用哈希数: {stats['hashes_reused']}")
        except Exception as e:
            logger.error(f"合并失败: {e}")
            sys.exit(1)
