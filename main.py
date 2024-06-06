import hashlib
from database import (
    add_file,
    add_hash,
    get_file_by_path,
    get_hash_by_hash,
    get_hash_by_id,
)
from models import FileHash, FileMeta
import datetime
import time
from pathlib import Path
from datetime import datetime
import logging
import os
from config import settings


logger = logging.getLogger()
logger.setLevel(logging.INFO)

file_hander = logging.FileHandler('scan.log', encoding='utf-8')
stream_hander = logging.StreamHandler()

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_hander.setFormatter(formatter)
stream_hander.setFormatter(formatter)

logger.addHandler(file_hander)
logger.addHandler(stream_hander)

ignore_file = '.ignore'
ignore_dirs = set()
ignore_partials_dirs = set()
with open(ignore_file) as f:
    for line in f:
        line = line.strip()
        if line:
            if line.startswith('#'):
                continue
            if '/' in line:
                ignore_partials_dirs.add(line)
            else:
                ignore_dirs.add(line)


def human_size(bytes, units=['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB']):
    return str(bytes) + units[0] if bytes < 1024 else human_size(bytes >> 10, units[1:])


def get_hashes(file_path: str | Path):
    '''Calculate MD5, SHA1, and SHA256 hashes of a file using hashlib.'''
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()

    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(1024 * 256)
            if not chunk:
                break
            md5.update(chunk)
            sha1.update(chunk)
            sha256.update(chunk)

    return {
        'md5': md5.hexdigest(),
        'sha1': sha1.hexdigest(),
        'sha256': sha256.hexdigest(),
    }


def get_metadata(file: Path):
    '''获取文件的元数据。'''
    stat = file.stat()
    assert settings.get("SCANNED") is not None
    meta = FileMeta(
        name=file.name,
        path=file.absolute().as_posix(),
        machine=settings.MACHINE_NAME,
        created=datetime.fromtimestamp(stat.st_ctime),
        modified=datetime.fromtimestamp(stat.st_mtime),
        scanned=settings.get("SCANNED"),
    )
    return meta


def scan_file(file: Path):
    '''扫描单个文件，将文件信息和哈希信息保存到数据库。'''
    meta = get_metadata(file)

    # 如果文件的元数据和大小没有被修改，则不再扫描
    meta_in_db = get_file_by_path(file.absolute().as_posix())
    if meta_in_db:
        if file.stat().st_size == get_hash_by_id(meta_in_db.hash_id).size:
            meta.hash_id = meta_in_db.hash_id
            meta.scanned = meta_in_db.scanned
            if meta == meta_in_db:
                logger.info(f'Skipping: {file}')
                return

    # 获取文件哈希
    hashes = get_hashes(file)

    # 如果哈希信息已经存在，则直接使用
    hash_info = get_hash_by_hash(hashes)
    # 如果哈希信息不存在，则创建
    if hash_info is not None:
        meta.hash_id = hash_info.id
    else:
        hash_info = FileHash(size=file.stat().st_size, **hashes)
        meta.hash_id = add_hash(hash_info)

    add_file(meta)


def scan_directory(directory: Path):
    '''扫描目录下的所有文件。'''
    for path in directory.iterdir():
        logger.info(f'Scanning: {path}')
        try:
            if path.is_dir():
                if path.name in ignore_dirs:
                    continue
                if path.name.startswith('.'):
                    logger.info(f'Skipping start with . : {path}')
                    continue
                if path.name.startswith('_'):
                    logger.info(f'Skipping start with _ : {path}')
                    continue
                skip = False
                for ignore_partial in ignore_partials_dirs:
                    if ignore_partial in path.as_posix():
                        skip = True
                        continue
                if skip:
                    continue
                scan_directory(path)
            else:
                scan_file(path)
        except IOError as e:
            logger.error(f'Error: {e}')
            logger.error(e)


def scan(path: str | Path):
    '''扫描指定目录。'''
    if not os.path.exists(path):
        logger.error(f'Path not exists: {path}')
        return
    if isinstance(path, str):
        path = Path(path)
    settings.set("SCANNED", datetime.now())
    scan_directory(path)


if __name__ == '__main__':
    scan(r'C:\Users\suyiiyii\Desktop')
    # scan_directory(Path(r'C:\Users\suyiiyii\Documents'))
