import argparse
import datetime
import hashlib
import logging
import os
import queue
import threading
from pathlib import Path
from typing import Any, Optional, Union

import database
from config import settings
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


def get_metadata(file: Path) -> FileMeta:
    """获取文件的元数据。"""
    stat = file.stat()
    # Dynaconf settings: use attribute access, not .get()
    scanned = getattr(settings, "SCANNED", None)
    if scanned is None:
        raise ValueError("SCANNED not set in settings!")
    machine = getattr(settings, "MACHINE_NAME", "Unknown")
    meta = FileMeta(
        name=file.name,
        path=str(file.absolute()),
        machine=machine,
        created=datetime.datetime.fromtimestamp(stat.st_ctime),
        modified=datetime.datetime.fromtimestamp(stat.st_mtime),
        scanned=scanned,
    )
    return meta


lock = threading.Lock()


def scan_file(file: Path):
    """扫描单个文件，将文件信息和哈希信息保存到数据库。"""
    meta = get_metadata(file)
    # 默认操作为添加
    meta.operation = "ADD"  # type: ignore[attr-defined]
    # 如果文件的元数据和大小没有被修改，则不再扫描
    with lock:
        meta_in_db = database.get_file_by_path(file.absolute().as_posix())
        if meta_in_db:
            # 如果文件大小没有变化
            hash_id = getattr(meta_in_db, "hash_id", None)
            if hash_id is not None:
                hash_in_db = database.get_hash_by_id(hash_id)
                if file.stat().st_size == getattr(hash_in_db, "size", None):
                    # 如果文件的创建时间和修改时间没有变化
                    if getattr(meta, "created", None) == getattr(
                        meta_in_db, "created", None
                    ) and getattr(meta, "modified", None) == getattr(
                        meta_in_db, "modified", None
                    ):
                        logger.info(f"Skipping: {file}")
                        return
            meta.operation = "MOD"  # type: ignore[attr-defined]
    # 获取文件哈希
    hashes = get_hashes(file)
    # 写入数据库
    with lock:
        database.add(meta, FileHash(**hashes, size=file.stat().st_size))


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
    logger.info("文件扫描结束。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="pyFileIndexer")
    parser.add_argument("path", type=str, help="The path to scan.")
    parser.add_argument("--machine_name", type=str, help="The machine name.")
    parser.add_argument(
        "--db_path", type=str, help="The database path.", default="indexer.db"
    )
    parser.add_argument(
        "--log_path", type=str, help="The log path.", default="indexer.log"
    )
    args = parser.parse_args()

    # 传入的机器名称覆盖配置文件中的机器名称
    if args.machine_name:
        setattr(settings, "MACHINE_NAME", args.machine_name)

    database.init("sqlite:///" + str(args.db_path))
    # database.init("sqlite:///:memory:")
    # database.init("sqlite:///test.db")
    # database.create_tables()
    init_file_logger(args.log_path)

    try:
        scan(args.path)
    except KeyboardInterrupt:
        stop_event.set()
        logger.error("KeyboardInterrupt")
    finally:
        logger.info("扫描完成。")
