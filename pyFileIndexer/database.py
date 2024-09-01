import threading
from typing import TYPE_CHECKING

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

if TYPE_CHECKING:
    from models import FileMeta, FileHash

Base = declarative_base()

engine = None
Session = None
SessionLock = threading.Lock()


def init(db_url: str):
    '''初始化数据库连接。'''
    global engine, Session
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)


def init_memory_db():
    '''初始化内存数据库。'''
    # TODO: 目前会覆盖上一次的数据库
    global engine, Session
    engine = create_engine('sqlite:///:memory:')
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)


def save_memory_db_to_disk(disk_db_url: str):
    '''将内存数据库保存到磁盘。'''
    if engine is None:
        raise RuntimeError("Memory database is not initialized.")
    session = Session()
    disk_engine = create_engine(disk_db_url)
    Base.metadata.create_all(disk_engine)
    Disksession = sessionmaker(bind=disk_engine)
    with Disksession() as disk_session:
        from models import FileMeta, FileHash
        for file in session.query(FileMeta).all():
            file_dict = file.__dict__
            file_dict.pop('_sa_instance_state')
            disk_session.add(FileMeta(**file_dict))
        for hash in session.query(FileHash).all():
            hash_dict = hash.__dict__
            hash_dict.pop('_sa_instance_state')
            disk_session.add(FileHash(**hash_dict))
        disk_session.commit()



def session_factory():
    with SessionLock:
        return Session()


def get_file_by_name(name: str) -> "FileMeta":
    '''根据文件名查询文件信息。'''
    from models import FileMeta

    with session_factory() as session:
        return session.query(FileMeta).filter_by(name=name).first()


def get_file_by_path(path: str) -> "FileMeta":
    '''根据文件路径查询文件信息。'''
    from models import FileMeta

    with session_factory() as session:
        return session.query(FileMeta).filter_by(path=path).first()


def get_hash_by_id(hash_id: int) -> "FileHash":
    '''根据哈希 ID 查询哈希信息。'''
    from models import FileHash

    with session_factory() as session:
        return session.query(FileHash).filter_by(id=hash_id).first()


def get_hash_by_hash(hash: dict[str, str]) -> "FileHash":
    '''根据哈希查询哈希信息。'''
    from models import FileHash

    with session_factory() as session:
        return session.query(FileHash).filter_by(**hash).first()


def add_file(file: "FileMeta") -> int:
    '''添加文件信息。'''
    with session_factory() as session:
        session.add(file)
        session.commit()
        return file.id


def add_hash(hash: "FileHash") -> int:
    '''添加哈希信息。'''
    with session_factory() as session:
        session.add(hash)
        session.commit()
        return hash.id


def add(file: "FileMeta", hash: "FileHash" = None):
    '''添加文件信息和哈希信息。'''
    with session_factory() as session:
        if hash is not None:
            # 如果哈希信息已经存在，则直接使用已有的哈希信息
            if hash_in_db := get_hash_by_hash(
                    {"md5": hash.md5, "sha1": hash.sha1, "sha256": hash.sha256}
            ):
                file.hash_id = hash_in_db.id
            else:
                session.add(hash)
                session.commit()
                file.hash_id = hash.id
        session.add(file)
        session.commit()
