import threading
from typing import TYPE_CHECKING, Any, Optional
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance  # 原子赋值
        return cls._instance

    def __init__(self):
        # 添加二次检查，确保线程安全
        if hasattr(self, '_initialized') and self._initialized:
            return

        with self.__class__._lock:
            if hasattr(self, '_initialized') and self._initialized:
                return

            self.engine = None
            self.Session = None
            self.session_lock = threading.Lock()
            self._initialized = True

    def init(self, db_url: str):
        """初始化数据库连接，支持多线程安全。"""
        if db_url.startswith("sqlite"):
            # SQLite 特殊配置，支持多线程
            self.engine = create_engine(
                db_url,
                poolclass=StaticPool,
                connect_args={
                    'check_same_thread': False,  # 允许跨线程使用
                    'timeout': 20  # 设置超时
                },
                echo=False
            )
        else:
            # 其他数据库的标准配置
            self.engine = create_engine(db_url)

        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session_scope(self):
        """提供事务作用域的会话管理。"""
        if self.Session is None:
            raise RuntimeError("Database is not initialized.")

        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def session_factory(self):
        """会话工厂方法 - 保持向后兼容"""
        if self.Session is None:
            raise RuntimeError("Database is not initialized.")
        return self.Session()

    def get_file_by_name(self, name: str) -> Optional["FileMeta"]:
        """根据文件名查询文件信息。"""
        from models import FileMeta

        session = self.session_factory()
        try:
            result = session.query(FileMeta).filter_by(name=name).first()
            if result:
                session.refresh(result)  # 刷新对象状态
                session.expunge(result)  # 从会话中分离，使其可以在会话外使用
            return result
        finally:
            session.close()

    def get_file_by_path(self, path: str) -> Optional["FileMeta"]:
        """根据文件路径查询文件信息。"""
        from models import FileMeta

        session = self.session_factory()
        try:
            result = session.query(FileMeta).filter_by(path=path).first()
            if result:
                session.refresh(result)  # 刷新对象状态
                session.expunge(result)
            return result
        finally:
            session.close()

    def get_hash_by_id(self, hash_id: int) -> Optional["FileHash"]:
        """根据哈希 ID 查询哈希信息。"""
        from models import FileHash

        session = self.session_factory()
        try:
            result = session.query(FileHash).filter_by(id=hash_id).first()
            if result:
                session.refresh(result)  # 刷新对象状态
                session.expunge(result)  # 分离对象
            return result
        finally:
            session.close()

    def get_hash_by_hash(self, hash: dict[str, str]) -> Optional["FileHash"]:
        """根据哈希查询哈希信息。"""
        from models import FileHash

        session = self.session_factory()
        try:
            result = session.query(FileHash).filter_by(**hash).first()
            if result:
                session.refresh(result)  # 刷新对象状态
                session.expunge(result)
            return result
        finally:
            session.close()

    def add_file(self, file: "FileMeta") -> Any:
        """添加文件信息。"""
        with self.session_scope() as session:
            session.add(file)
            session.flush()  # 获取ID但不提交
            file_id = file.id
            return file_id

    def add_hash(self, hash: "FileHash") -> Any:
        """添加哈希信息。"""
        with self.session_scope() as session:
            session.add(hash)
            session.flush()  # 获取ID但不提交
            hash_id = hash.id
            return hash_id

    def add(self, file: "FileMeta", hash: Optional["FileHash"] = None):
        """添加文件信息和哈希信息。"""
        with self.session_scope() as session:
            if hash is not None:
                # 如果哈希信息已经存在，则直接使用已有的哈希信息
                # 在运行时，这些属性是实际值而不是Column对象
                hash_dict = {"md5": hash.md5, "sha1": hash.sha1, "sha256": hash.sha256}  # type: ignore
                if hash_in_db := self.get_hash_by_hash(hash_dict):  # type: ignore
                    file.hash_id = hash_in_db.id  # type: ignore
                else:
                    session.add(hash)
                    session.flush()  # 获取ID
                    file.hash_id = hash.id  # type: ignore
            session.add(file)

    def update_file(self, file: "FileMeta", hash: Optional["FileHash"] = None):
        """更新现有文件信息。"""
        from models import FileMeta
        with self.session_scope() as session:
            # 查找现有的文件记录
            existing_file = session.query(FileMeta).filter_by(path=file.path).first()
            if existing_file:
                # 更新现有记录的字段
                existing_file.name = file.name
                existing_file.created = file.created
                existing_file.modified = file.modified
                existing_file.scanned = file.scanned
                existing_file.operation = file.operation
                existing_file.machine = file.machine

                if hash is not None:
                    # 如果哈希信息已经存在，则直接使用已有的哈希信息
                    hash_dict = {"md5": hash.md5, "sha1": hash.sha1, "sha256": hash.sha256}  # type: ignore
                    if hash_in_db := self.get_hash_by_hash(hash_dict):  # type: ignore
                        existing_file.hash_id = hash_in_db.id  # type: ignore
                    else:
                        session.add(hash)
                        session.flush()  # 获取ID
                        existing_file.hash_id = hash.id  # type: ignore
            else:
                # 如果不存在，则添加新记录
                session.add(file)
                if hash is not None:
                    session.add(hash)


# 创建全局单例实例
db_manager = DatabaseManager()
