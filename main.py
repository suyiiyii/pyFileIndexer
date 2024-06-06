import hashlib
from models import FileHash, FileMeta, session_factory
import datetime
import time
from pathlib import Path
from datetime import datetime


ignore_file = '.ignore'
ignore_dirs = set()
with open(ignore_file) as f:
    for line in f:
        line = line.strip()
        if line:
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
    meta = FileMeta(
        name=file.name,
        path=file.absolute().as_posix(),
        created=datetime.fromtimestamp(stat.st_ctime),
        modified=datetime.fromtimestamp(stat.st_mtime),
        scanned=datetime.now(),
    )
    return meta


def scan_file(file: Path):
    '''扫描单个文件，将文件信息和哈希信息保存到数据库。'''
    meta = get_metadata(file)

    with session_factory() as session:

        # 如果文件的元数据和大小没有被修改，则不再扫描
        meta_in_db = (
            session.query(FileMeta).filter_by(path=file.absolute().as_posix()).first()
        )
        if meta_in_db:
            if file.stat().st_size == session.get(FileHash, meta_in_db.hash_id).size:
                meta.hash_id = meta_in_db.hash_id
                meta.scanned = meta_in_db.scanned
                if meta == meta_in_db:
                    print(f'Skipping: {file}')
                    return

        # 获取文件哈希
        hashes = get_hashes(file)
        # 查询哈希信息是否存在
        hash_info = (
            session.query(FileHash)
            .filter_by(
                md5=hashes['md5'],
                sha1=hashes['sha1'],
                sha256=hashes['sha256'],
            )
            .first()
        )

        # 如果哈希信息不存在，则创建
        if not hash_info:
            hash_info = FileHash(
                size=file.stat().st_size,
                md5=hashes['md5'],
                sha1=hashes['sha1'],
                sha256=hashes['sha256'],
            )
            session.add(hash_info)
            session.commit()

        meta.hash_id = hash_info.id
        session.add(meta)
        session.commit()


def scan_directory(directory: Path):
    '''扫描目录下的所有文件。'''
    for path in directory.iterdir():
        print(f'Scanning: {path}')
        if path.is_dir():
            if path.name in ignore_dirs:
                continue
            scan_directory(path)
        else:
            scan_file(path)


if __name__ == '__main__':
    scan_directory(Path(r'C:\Users\suyiiyii\Documents'))
