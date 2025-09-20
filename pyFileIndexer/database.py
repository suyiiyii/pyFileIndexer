import threading
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

if TYPE_CHECKING:
    from models import FileHash, FileMeta

Base = declarative_base()


class DatabaseManager:
    """数据库管理器单例类"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.engine = None
        self.Session = None
        self.session_lock = threading.Lock()
        self._initialized = True

    def init(self, db_url: str):
        """初始化数据库连接，直接连接到磁盘数据库。"""
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)

    def session_factory(self):
        """会话工厂方法"""
        if self.Session is None:
            raise RuntimeError("Database is not initialized.")
        with self.session_lock:
            return self.Session()

    def get_file_by_name(self, name: str) -> Optional["FileMeta"]:
        """根据文件名查询文件信息。"""
        from models import FileMeta

        with self.session_factory() as session:
            return session.query(FileMeta).filter_by(name=name).first()

    def get_file_by_path(self, path: str) -> Optional["FileMeta"]:
        """根据文件路径查询文件信息。"""
        from models import FileMeta

        with self.session_factory() as session:
            return session.query(FileMeta).filter_by(path=path).first()

    def get_hash_by_id(self, hash_id: int) -> Optional["FileHash"]:
        """根据哈希 ID 查询哈希信息。"""
        from models import FileHash

        with self.session_factory() as session:
            return session.query(FileHash).filter_by(id=hash_id).first()

    def get_hash_by_hash(self, hash: dict[str, str]) -> Optional["FileHash"]:
        """根据哈希查询哈希信息。"""
        from models import FileHash

        with self.session_factory() as session:
            return session.query(FileHash).filter_by(**hash).first()

    def add_file(self, file: "FileMeta") -> Any:
        """添加文件信息。"""
        with self.session_factory() as session:
            session.add(file)
            session.commit()
            return file.id

    def add_hash(self, hash: "FileHash") -> Any:
        """添加哈希信息。"""
        with self.session_factory() as session:
            session.add(hash)
            session.commit()
            return hash.id

    def add(self, file: "FileMeta", hash: Optional["FileHash"] = None):
        """添加文件信息和哈希信息。"""
        with self.session_factory() as session:
            if hash is not None:
                # 如果哈希信息已经存在，则直接使用已有的哈希信息
                # 在运行时，这些属性是实际值而不是Column对象
                hash_dict = {"md5": hash.md5, "sha1": hash.sha1, "sha256": hash.sha256}  # type: ignore
                if hash_in_db := self.get_hash_by_hash(hash_dict):  # type: ignore
                    file.hash_id = hash_in_db.id  # type: ignore
                else:
                    session.add(hash)
                    session.commit()
                    file.hash_id = hash.id  # type: ignore
            session.add(file)
            session.commit()


# 创建全局单例实例
db_manager = DatabaseManager()
