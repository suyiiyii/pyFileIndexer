import threading
from typing import TYPE_CHECKING, Any, Optional
from contextlib import contextmanager

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
            # SQLite 配置，支持多线程，优化磁盘数据库性能
            self.engine = create_engine(
                db_url,
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

    def get_file_with_hash_by_path(self, path: str) -> Optional[tuple["FileMeta", Optional["FileHash"]]]:
        """根据文件路径查询文件信息和对应的哈希信息（一次查询）。"""
        from models import FileMeta, FileHash

        session = self.session_factory()
        try:
            result = session.query(FileMeta, FileHash).outerjoin(
                FileHash, FileMeta.hash_id == FileHash.id
            ).filter(FileMeta.path == path).first()

            if result:
                file_meta, file_hash = result
                if file_meta:
                    session.expunge(file_meta)
                if file_hash:
                    session.expunge(file_hash)
                return (file_meta, file_hash)
            return None
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

    def get_files_paginated(self, page: int = 1, per_page: int = 20, filters: Optional[dict] = None) -> dict:
        """分页查询文件列表"""
        from models import FileMeta, FileHash
        import logging

        logger = logging.getLogger(__name__)

        try:
            with self.session_scope() as session:
                query = session.query(FileMeta, FileHash).outerjoin(
                    FileHash, FileMeta.hash_id == FileHash.id
                )

                # 应用过滤器
                if filters:
                    if filters.get('name'):
                        query = query.filter(FileMeta.name.contains(filters['name']))
                    if filters.get('path'):
                        query = query.filter(FileMeta.path.contains(filters['path']))
                    if filters.get('machine'):
                        query = query.filter(FileMeta.machine == filters['machine'])
                    if filters.get('min_size') is not None:
                        query = query.filter(FileHash.size >= filters['min_size'])
                    if filters.get('max_size') is not None:
                        query = query.filter(FileHash.size <= filters['max_size'])
                    if filters.get('hash_value'):
                        hash_value = filters['hash_value']
                        query = query.filter(
                            (FileHash.md5 == hash_value) |
                            (FileHash.sha1 == hash_value) |
                            (FileHash.sha256 == hash_value)
                        )

                # 计算总数
                total = query.count()
                logger.debug(f"Total files found: {total}")

                # 分页
                offset = (page - 1) * per_page
                results = query.offset(offset).limit(per_page).all()
                logger.debug(f"Retrieved {len(results)} files for page {page}")

                # 分离对象
                files = []
                for file_meta, file_hash in results:
                    try:
                        if file_meta:
                            session.expunge(file_meta)
                        if file_hash:
                            session.expunge(file_hash)
                        files.append((file_meta, file_hash))
                    except Exception as e:
                        logger.error(f"Error processing file record: {e}")
                        continue

                return {
                    'files': files,
                    'total': total,
                    'page': page,
                    'per_page': per_page,
                    'pages': (total + per_page - 1) // per_page
                }

        except Exception as e:
            logger.error(f"Error in get_files_paginated: {e}")
            raise

    def search_files(self, query: str, search_type: str = 'name') -> list:
        """搜索文件"""
        from models import FileMeta, FileHash

        with self.session_scope() as session:
            db_query = session.query(FileMeta, FileHash).outerjoin(
                FileHash, FileMeta.hash_id == FileHash.id
            )

            if search_type == 'name':
                db_query = db_query.filter(FileMeta.name.contains(query))
            elif search_type == 'path':
                db_query = db_query.filter(FileMeta.path.contains(query))
            elif search_type == 'hash':
                db_query = db_query.filter(
                    (FileHash.md5 == query) |
                    (FileHash.sha1 == query) |
                    (FileHash.sha256 == query)
                )

            results = db_query.all()

            # 分离对象
            files = []
            for file_meta, file_hash in results:
                if file_meta:
                    session.expunge(file_meta)
                if file_hash:
                    session.expunge(file_hash)
                files.append((file_meta, file_hash))

            return files

    def get_statistics(self) -> dict:
        """获取统计信息"""
        from models import FileMeta, FileHash
        from sqlalchemy import func

        with self.session_scope() as session:
            # 总文件数
            total_files = session.query(FileMeta).count()

            # 总大小
            total_size = session.query(func.sum(FileHash.size)).scalar() or 0

            # 按机器统计
            machine_stats = session.query(
                FileMeta.machine,
                func.count(FileMeta.id)
            ).group_by(FileMeta.machine).all()

            # 重复文件统计
            duplicate_hashes = session.query(
                FileHash.md5,
                func.count(FileMeta.id).label('count')
            ).join(FileMeta, FileMeta.hash_id == FileHash.id)\
             .group_by(FileHash.md5)\
             .having(func.count(FileMeta.id) > 1).all()

            return {
                'total_files': total_files,
                'total_size': total_size,
                'machine_stats': {machine: count for machine, count in machine_stats},
                'duplicate_files': len(duplicate_hashes)
            }

    def find_duplicate_files(self) -> list:
        """查找重复文件"""
        from models import FileMeta, FileHash
        from sqlalchemy import func

        with self.session_scope() as session:
            # 查找有多个文件的哈希值
            duplicate_hashes = session.query(FileHash.md5)\
                .join(FileMeta, FileMeta.hash_id == FileHash.id)\
                .group_by(FileHash.md5)\
                .having(func.count(FileMeta.id) > 1).all()

            duplicates = []
            for (md5_hash,) in duplicate_hashes:
                files = session.query(FileMeta, FileHash)\
                    .join(FileHash, FileMeta.hash_id == FileHash.id)\
                    .filter(FileHash.md5 == md5_hash).all()

                # 分离对象
                file_group = []
                for file_meta, file_hash in files:
                    session.expunge(file_meta)
                    session.expunge(file_hash)
                    file_group.append((file_meta, file_hash))

                duplicates.append({
                    'hash': md5_hash,
                    'files': file_group
                })

            return duplicates

    def close(self):
        """关闭数据库连接，释放资源"""
        if self.engine is not None:
            self.engine.dispose()
            self.engine = None
            self.Session = None


# 创建全局单例实例
db_manager = DatabaseManager()
