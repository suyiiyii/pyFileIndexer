import threading
import logging
from typing import Any, Optional
from contextlib import contextmanager

from sqlalchemy import create_engine, tuple_, text, func, inspect as sa_inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine

from base import Base
from models import FileHash, FileMeta


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
        if hasattr(self, "_initialized") and self._initialized:
            return

        with self.__class__._lock:
            if hasattr(self, "_initialized") and self._initialized:
                return

            self.engine: Optional[Engine] = None
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
                    "check_same_thread": False,  # 允许跨线程使用
                    "timeout": 20,  # 设置超时
                },
                echo=False,
            )
        else:
            # 其他数据库的标准配置
            self.engine = create_engine(db_url)

        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

        # 自动迁移 schema
        self._migrate_schema()

    def _migrate_schema(self):
        """自动迁移数据库 schema，添加缺失的列"""
        if self.engine is None:
            return

        # 只处理 SQLite 数据库
        if not str(self.engine.url).startswith("sqlite"):
            return

        try:
            with self.engine.begin() as conn:
                # 检查 file_meta 表结构
                result = conn.execute(text("PRAGMA table_info(file_meta)")).fetchall()
                existing_columns = {row[1] for row in result}

                # 检查并添加 is_archived 列
                if "is_archived" not in existing_columns:
                    conn.execute(
                        text(
                            "ALTER TABLE file_meta ADD COLUMN is_archived INTEGER DEFAULT 0"
                        )
                    )
                    conn.execute(
                        text(
                            "CREATE INDEX ix_file_meta_is_archived ON file_meta (is_archived)"
                        )
                    )

                # 检查并添加 archive_path 列
                if "archive_path" not in existing_columns:
                    conn.execute(
                        text("ALTER TABLE file_meta ADD COLUMN archive_path VARCHAR")
                    )
                    conn.execute(
                        text(
                            "CREATE INDEX ix_file_meta_archive_path ON file_meta (archive_path)"
                        )
                    )

        except Exception as e:
            # 忽略迁移错误，避免影响正常初始化
            logger = logging.getLogger(__name__)
            logger.warning(f"Schema migration warning: {e}")

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

    def get_file_by_name(self, name: str) -> Optional[FileMeta]:
        """根据文件名查询文件信息。"""
        session = self.session_factory()
        try:
            result = session.query(FileMeta).filter_by(name=name).first()
            if result:
                session.refresh(result)  # 刷新对象状态
                session.expunge(result)  # 从会话中分离，使其可以在会话外使用
            return result
        finally:
            session.close()

    def get_file_by_path(self, path: str) -> Optional[FileMeta]:
        """根据文件路径查询文件信息。"""
        session = self.session_factory()
        try:
            result = session.query(FileMeta).filter_by(path=path).first()
            if result:
                session.refresh(result)  # 刷新对象状态
                session.expunge(result)
            return result
        finally:
            session.close()

    def get_file_with_hash_by_path(
        self, path: str
    ) -> Optional[tuple[FileMeta, Optional[FileHash]]]:
        """根据文件路径查询文件信息和对应的哈希信息（一次查询）。"""
        session = self.session_factory()
        try:
            result = (
                session.query(FileMeta, FileHash)
                .outerjoin(FileHash, FileMeta.hash_id == FileHash.id)
                .filter(FileMeta.path == path)
                .first()
            )

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

    def get_hash_by_id(self, hash_id: int) -> Optional[FileHash]:
        """根据哈希 ID 查询哈希信息。"""
        session = self.session_factory()
        try:
            result = session.query(FileHash).filter_by(id=hash_id).first()
            if result:
                session.refresh(result)  # 刷新对象状态
                session.expunge(result)  # 分离对象
            return result
        finally:
            session.close()

    def get_hash_by_hash(self, hash: dict[str, str]) -> Optional[FileHash]:
        """根据哈希查询哈希信息。"""
        session = self.session_factory()
        try:
            result = session.query(FileHash).filter_by(**hash).first()
            if result:
                session.refresh(result)  # 刷新对象状态
                session.expunge(result)
            return result
        finally:
            session.close()

    def add_file(self, file: FileMeta) -> Any:
        """添加文件信息。"""
        with self.session_scope() as session:
            session.add(file)
            session.flush()  # 获取ID但不提交
            file_id = file.id
            return file_id

    def add_hash(self, hash: FileHash) -> Any:
        """添加哈希信息。"""
        with self.session_scope() as session:
            session.add(hash)
            session.flush()  # 获取ID但不提交
            hash_id = hash.id
            return hash_id

    def add(self, file: FileMeta, hash: Optional[FileHash] = None):
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

    def update_file(self, file: FileMeta, hash: Optional[FileHash] = None):
        """更新现有文件信息。"""
        with self.session_scope() as session:
            # 查找现有的文件记录
            existing_file = session.query(FileMeta).filter_by(path=file.path).first()
            if existing_file:
                # 更新现有记录的字段
                existing_file.name = file.name  # type: ignore
                existing_file.created = file.created  # type: ignore
                existing_file.modified = file.modified  # type: ignore
                existing_file.scanned = file.scanned  # type: ignore
                existing_file.operation = file.operation  # type: ignore
                existing_file.machine = file.machine  # type: ignore
                existing_file.is_archived = getattr(file, "is_archived", 0)  # type: ignore
                existing_file.archive_path = getattr(file, "archive_path", None)  # type: ignore

                if hash is not None:
                    # 如果哈希信息已经存在，则直接使用已有的哈希信息
                    hash_dict = {
                        "md5": hash.md5,
                        "sha1": hash.sha1,
                        "sha256": hash.sha256,
                    }  # type: ignore
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

    def get_files_paginated(
        self, page: int = 1, per_page: int = 20, filters: Optional[dict] = None
    ) -> dict:
        """分页查询文件列表"""
        logger = logging.getLogger(__name__)

        try:
            with self.session_scope() as session:
                query = session.query(FileMeta, FileHash).outerjoin(
                    FileHash, FileMeta.hash_id == FileHash.id
                )

                # 应用过滤器
                if filters:
                    if filters.get("name"):
                        query = query.filter(FileMeta.name.contains(filters["name"]))
                    if filters.get("path"):
                        query = query.filter(FileMeta.path.contains(filters["path"]))
                    if filters.get("machine"):
                        query = query.filter(FileMeta.machine == filters["machine"])
                    if filters.get("min_size") is not None:
                        query = query.filter(FileHash.size >= filters["min_size"])
                    if filters.get("max_size") is not None:
                        query = query.filter(FileHash.size <= filters["max_size"])
                    if filters.get("hash_value"):
                        hash_value = filters["hash_value"]
                        query = query.filter(
                            (FileHash.md5 == hash_value)
                            | (FileHash.sha1 == hash_value)
                            | (FileHash.sha256 == hash_value)
                        )
                    if filters.get("is_archived") is not None:
                        query = query.filter(
                            FileMeta.is_archived == filters["is_archived"]
                        )
                    if filters.get("archive_path"):
                        query = query.filter(
                            FileMeta.archive_path.contains(filters["archive_path"])
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
                    "files": files,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "pages": (total + per_page - 1) // per_page,
                }

        except Exception as e:
            logger.error(f"Error in get_files_paginated: {e}")
            raise

    def search_files(self, query: str, search_type: str = "name") -> list:
        """搜索文件"""
        with self.session_scope() as session:
            db_query = session.query(FileMeta, FileHash).outerjoin(
                FileHash, FileMeta.hash_id == FileHash.id
            )

            if search_type == "name":
                db_query = db_query.filter(FileMeta.name.contains(query))
            elif search_type == "path":
                db_query = db_query.filter(FileMeta.path.contains(query))
            elif search_type == "hash":
                db_query = db_query.filter(
                    (FileHash.md5 == query)
                    | (FileHash.sha1 == query)
                    | (FileHash.sha256 == query)
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
        with self.session_scope() as session:
            # 总文件数
            total_files = session.query(FileMeta).count()

            # 总大小
            total_size = session.query(func.sum(FileHash.size)).scalar() or 0

            # 按机器统计
            machine_stats = (
                session.query(FileMeta.machine, func.count(FileMeta.id))
                .group_by(FileMeta.machine)
                .all()
            )

            # 重复文件统计
            duplicate_hashes = (
                session.query(FileHash.md5, func.count(FileMeta.id).label("count"))
                .join(FileMeta, FileMeta.hash_id == FileHash.id)
                .group_by(FileHash.md5)
                .having(func.count(FileMeta.id) > 1)
                .all()
            )

            return {
                "total_files": total_files,
                "total_size": total_size,
                "machine_stats": {machine: count for machine, count in machine_stats},
                "duplicate_files": len(duplicate_hashes),
            }

    def find_duplicate_files(
        self,
        page: int = 1,
        per_page: int = 20,
        min_size: int = 1048576,  # 1MB
        min_count: int = 2,
        sort_by: str = "count_desc",
    ) -> dict:
        """查找重复文件，支持分页、过滤和排序

        Args:
            page: 页码，从1开始
            per_page: 每页数量
            min_size: 最小文件大小（字节）
            min_count: 最小重复数量
            sort_by: 排序方式 - count_desc, count_asc, size_desc, size_asc

        Returns:
            {
                'duplicates': [{'hash': str, 'files': [(FileMeta, FileHash)]}],
                'total_groups': int,  # 总重复组数
                'total_files': int,   # 总重复文件数
                'page': int,
                'per_page': int,
                'pages': int
            }
        """
        with self.session_scope() as session:
            # 先查找符合条件的重复哈希组（用于计算总数）
            duplicate_hashes_query = (
                session.query(
                    FileHash.md5,
                    FileHash.id,
                    FileHash.size,
                    func.count(FileMeta.id).label("file_count"),
                )
                .join(FileMeta, FileMeta.hash_id == FileHash.id)
                .filter(FileHash.size >= min_size)
                .group_by(FileHash.id, FileHash.md5, FileHash.size)
                .having(func.count(FileMeta.id) >= min_count)
            )

            # 根据 sort_by 参数添加排序
            if sort_by == "count_desc":
                duplicate_hashes_query = duplicate_hashes_query.order_by(
                    func.count(FileMeta.id).desc(), FileHash.size.desc()
                )
            elif sort_by == "count_asc":
                duplicate_hashes_query = duplicate_hashes_query.order_by(
                    func.count(FileMeta.id).asc(), FileHash.size.asc()
                )
            elif sort_by == "size_desc":
                duplicate_hashes_query = duplicate_hashes_query.order_by(
                    FileHash.size.desc(), func.count(FileMeta.id).desc()
                )
            elif sort_by == "size_asc":
                duplicate_hashes_query = duplicate_hashes_query.order_by(
                    FileHash.size.asc(), func.count(FileMeta.id).asc()
                )
            else:
                # 默认按重复数量降序
                duplicate_hashes_query = duplicate_hashes_query.order_by(
                    func.count(FileMeta.id).desc(), FileHash.size.desc()
                )

            # 计算总数
            total_groups = duplicate_hashes_query.count()
            total_pages = (total_groups + per_page - 1) // per_page

            # 应用分页
            offset = (page - 1) * per_page
            duplicate_hashes = duplicate_hashes_query.offset(offset).limit(per_page).all()

            duplicates = []
            total_files_count = 0

            for md5_hash, hash_id, size, file_count in duplicate_hashes:
                # 查找这个哈希对应的所有文件
                files = (
                    session.query(FileMeta, FileHash)
                    .join(FileHash, FileMeta.hash_id == FileHash.id)
                    .filter(FileHash.id == hash_id)
                    .all()
                )

                total_files_count += len(files)

                # 先收集所有文件对象
                file_group = list(files)

                # 统一从 session 中分离对象，避免重复 expunge
                # 使用 sqlalchemy.inspect 检查对象是否还在 session 中
                for file_meta, file_hash in file_group:
                    if sa_inspect(file_meta).session is not None:
                        session.expunge(file_meta)
                    if sa_inspect(file_hash).session is not None:
                        session.expunge(file_hash)

                duplicates.append({"hash": md5_hash, "files": file_group})

            return {
                "duplicates": duplicates,
                "total_groups": total_groups,
                "total_files": total_files_count,
                "page": page,
                "per_page": per_page,
                "pages": total_pages,
            }

    def get_existing_hashes_batch(self, hash_data: list[dict]) -> dict[str, int]:
        """批量查询已存在的哈希，返回哈希值到ID的映射"""
        if not hash_data:
            return {}

        with self.session_scope() as session:
            # 构建查询条件，查找所有可能存在的哈希
            hash_keys = [(h["md5"], h["sha1"], h["sha256"]) for h in hash_data]

            if not hash_keys:
                return {}

            existing_hashes = (
                session.query(FileHash)
                .filter(
                    tuple_(FileHash.md5, FileHash.sha1, FileHash.sha256).in_(hash_keys)
                )
                .all()
            )

            # 创建映射：(md5, sha1, sha256) -> hash_id
            hash_mapping: dict[tuple[str, str, str], int] = {}
            for hash_obj in existing_hashes:
                key = (hash_obj.md5, hash_obj.sha1, hash_obj.sha256)  # type: ignore
                hash_mapping[key] = hash_obj.id  # type: ignore

            return hash_mapping  # type: ignore

    def add_files_batch(self, files_data: list[dict]):
        """批量添加文件和哈希信息
        files_data: list of dict containing:
        - file_meta: FileMeta object
        - file_hash: FileHash object
        - operation: 'ADD' or 'MOD'
        """
        if not files_data:
            return

        with self.session_scope() as session:
            # 1. 分离哈希和文件数据
            hash_data = []
            new_files = []
            update_files = []

            for item in files_data:
                file_meta = item["file_meta"]
                file_hash = item["file_hash"]
                operation = item["operation"]

                hash_dict = {
                    "md5": file_hash.md5,
                    "sha1": file_hash.sha1,
                    "sha256": file_hash.sha256,
                    "size": file_hash.size,
                }
                hash_data.append(hash_dict)

                if operation == "ADD":
                    new_files.append((file_meta, file_hash, hash_dict))
                else:  # MOD
                    update_files.append((file_meta, file_hash, hash_dict))

            # 2. 批量查询已存在的哈希
            existing_hashes = self.get_existing_hashes_batch(hash_data)

            # 3. 准备需要插入的新哈希，去重批次内的重复哈希
            seen_hashes = set()
            hash_to_insert = []

            for item in hash_data:
                hash_key = (item["md5"], item["sha1"], item["sha256"])
                if hash_key not in existing_hashes and hash_key not in seen_hashes:
                    hash_to_insert.append(item)
                    seen_hashes.add(hash_key)

            # 4. 批量插入新哈希
            if hash_to_insert:
                session.bulk_insert_mappings(FileHash, hash_to_insert)  # type: ignore
                session.flush()  # 获取插入的ID

                # 重新查询获取新插入哈希的ID
                hash_keys = [(h["md5"], h["sha1"], h["sha256"]) for h in hash_to_insert]
                new_hashes = (
                    session.query(FileHash)
                    .filter(
                        tuple_(FileHash.md5, FileHash.sha1, FileHash.sha256).in_(
                            hash_keys
                        )
                    )
                    .all()
                )

                for hash_obj in new_hashes:
                    key = (hash_obj.md5, hash_obj.sha1, hash_obj.sha256)  # type: ignore
                    existing_hashes[key] = hash_obj.id  # type: ignore

            # 5. 准备文件数据并设置hash_id
            files_to_insert = []

            # 处理新文件
            for file_meta, file_hash, hash_dict in new_files:
                hash_key = (hash_dict["md5"], hash_dict["sha1"], hash_dict["sha256"])
                hash_id = existing_hashes[hash_key]

                file_dict = {
                    "name": file_meta.name,
                    "path": file_meta.path,
                    "machine": file_meta.machine,
                    "created": file_meta.created,
                    "modified": file_meta.modified,
                    "scanned": file_meta.scanned,
                    "operation": file_meta.operation,
                    "hash_id": hash_id,
                    "is_archived": getattr(file_meta, "is_archived", 0),
                    "archive_path": getattr(file_meta, "archive_path", None),
                }
                files_to_insert.append(file_dict)

            # 处理更新文件
            for file_meta, file_hash, hash_dict in update_files:
                hash_key = (hash_dict["md5"], hash_dict["sha1"], hash_dict["sha256"])
                hash_id = existing_hashes[hash_key]

                # 查找现有文件记录
                existing_file = (
                    session.query(FileMeta).filter_by(path=file_meta.path).first()
                )
                if existing_file:
                    existing_file.name = file_meta.name  # type: ignore
                    existing_file.created = file_meta.created  # type: ignore
                    existing_file.modified = file_meta.modified  # type: ignore
                    existing_file.scanned = file_meta.scanned  # type: ignore
                    existing_file.operation = file_meta.operation  # type: ignore
                    existing_file.machine = file_meta.machine  # type: ignore
                    existing_file.hash_id = hash_id  # type: ignore
                    existing_file.is_archived = getattr(file_meta, "is_archived", 0)  # type: ignore
                    existing_file.archive_path = getattr(
                        file_meta, "archive_path", None
                    )  # type: ignore
                else:
                    # 如果文件不存在，添加为新文件
                    file_dict = {
                        "name": file_meta.name,
                        "path": file_meta.path,
                        "machine": file_meta.machine,
                        "created": file_meta.created,
                        "modified": file_meta.modified,
                        "scanned": file_meta.scanned,
                        "operation": file_meta.operation,
                        "hash_id": hash_id,
                        "is_archived": getattr(file_meta, "is_archived", 0),
                        "archive_path": getattr(file_meta, "archive_path", None),
                    }
                    files_to_insert.append(file_dict)

            # 6. 批量插入新文件
            if files_to_insert:
                session.bulk_insert_mappings(FileMeta, files_to_insert)  # type: ignore


# 创建全局单例实例
db_manager = DatabaseManager()
