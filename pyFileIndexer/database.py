from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models import FileMeta, FileHash

Base = declarative_base()


engine = None
Session = None


def init(db_url: str):
    '''初始化数据库连接。'''
    global engine, Session
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)


def session_factory():
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
