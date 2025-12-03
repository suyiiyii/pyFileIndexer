# 数据库层重构计划

## 概述

本文档记录了 pyFileIndexer 项目数据库层的重构计划，旨在解决当前存在的会话管理混乱、线程安全问题以及架构设计不清晰等问题。

## 当前问题分析

### 主要问题

1. **会话管理混乱**：同时存在 `session_scope()` 和 `session_factory()` 两种会话管理方式，容易导致资源泄漏
2. **线程安全问题**：多线程环境下 ORM 对象的不当使用，导致 "Instance is not present in this Session" 错误
3. **缺少连接池配置**：没有配置连接池参数，高并发场景下性能不佳
4. **不必要的 expunge 操作**：返回 detached ORM 对象，无法懒加载关联数据
5. **业务逻辑混入数据访问层**：`add_files_batch` 等方法包含过多业务逻辑

### 当前架构问题

```
main.py → database.py (混合了数据访问和业务逻辑)
```

## 重构目标架构

```
┌─────────────────────────────────────┐
│  Presentation Layer (main.py)      │  ← 入口点、CLI 交互
├─────────────────────────────────────┤
│  Service Layer (file_service.py)   │  ← 业务逻辑
│  - scan_files()                     │
│  - handle_duplicates()              │
│  - batch_process_files()            │
├─────────────────────────────────────┤
│  Repository Layer (repositories/)   │  ← 数据访问抽象
│  - FileRepository                   │
│  - HashRepository                   │
├─────────────────────────────────────┤
│  Database Layer (database.py)       │  ← 连接管理、会话管理
│  - SessionManager                   │
│  - Engine Configuration             │
└─────────────────────────────────────┘
```

---

## P0 - 立即修复（高优先级）

这些问题影响系统稳定性和并发性能，需要立即修复。

### 1. 统一会话管理，移除 session_factory()

**当前问题：**
```python
# database.py 中同时存在两种模式
def session_scope(self):  # 上下文管理器
    session = self.Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def session_factory(self):  # 工厂方法（需要手动关闭）
    return self.Session()
```

大量方法使用 `session_factory()` + `try/finally` 模式，代码重复且容易忘记关闭。

**解决方案：**

```python
# database.py
class DatabaseManager:
    @contextmanager
    def session_scope(self):
        """统一的会话管理入口"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # 删除 session_factory() 方法

    @retry_on_db_lock(max_retries=5, retry_delay=0.5)
    def get_file_by_path(self, path: str) -> Optional[FileMeta]:
        """重构后：使用 session_scope"""
        with self.session_scope() as session:
            result = session.query(FileMeta).filter_by(path=path).first()
            if result:
                session.expunge(result)
            return result
```

**修改文件：**
- `pyFileIndexer/database.py`：修改所有使用 `session_factory()` 的方法

**预期收益：**
- 统一会话管理模式
- 自动处理事务和资源释放
- 减少代码重复

---

### 2. 使用 scoped_session 解决线程安全问题

**当前问题：**
```python
# 当前实现
self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

# 多线程环境下容易出现会话冲突
# 存在一个从未使用的 session_lock（错误的设计思路）
self.session_lock = threading.Lock()
```

SQLAlchemy 的 session 不是线程安全的，应该每个线程使用独立的 session。

**解决方案：**

```python
# database.py
from sqlalchemy.orm import scoped_session, sessionmaker

class DatabaseManager:
    def init(self, db_url: str):
        """初始化数据库连接，支持多线程安全。"""
        if db_url.startswith("sqlite"):
            self.engine = create_engine(
                db_url,
                connect_args={
                    "check_same_thread": False,
                    "timeout": 60,
                },
                echo=False,
            )
        else:
            self.engine = create_engine(db_url)

        # 使用 scoped_session 自动为每个线程创建独立会话
        session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.Session = scoped_session(session_factory)

        Base.metadata.create_all(self.engine)

        # 启用 WAL 模式...
        # ...

    @contextmanager
    def session_scope(self):
        """提供事务作用域的会话管理"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            self.Session.remove()  # 清理线程本地会话

    # 删除不必要的 session_lock
```

**修改文件：**
- `pyFileIndexer/database.py`：使用 `scoped_session`，删除 `session_lock`

**预期收益：**
- 每个线程自动获得独立的 session
- 避免线程间会话冲突
- 更简洁的代码，不需要手动管理线程锁

---

### 3. 添加连接池配置

**当前问题：**
```python
# 没有配置连接池参数
self.engine = create_engine(
    db_url,
    connect_args={...},
    echo=False,
)
```

高并发场景下可能出现连接不足或连接泄漏问题。

**解决方案：**

```python
# database.py
class DatabaseManager:
    def init(self, db_url: str):
        """初始化数据库连接，支持多线程安全。"""
        if db_url.startswith("sqlite"):
            self.engine = create_engine(
                db_url,
                connect_args={
                    "check_same_thread": False,
                    "timeout": 60,
                },
                pool_size=20,              # 连接池大小
                max_overflow=40,           # 最大溢出连接数
                pool_pre_ping=True,        # 连接健康检查
                pool_recycle=3600,         # 连接回收时间（1小时）
                echo=False,
            )
        else:
            # 其他数据库的标准配置
            self.engine = create_engine(
                db_url,
                pool_size=20,
                max_overflow=40,
                pool_pre_ping=True,
                pool_recycle=3600,
            )
```

**配置说明：**
- `pool_size=20`：连接池维护 20 个活跃连接
- `max_overflow=40`：高峰时最多可创建额外 40 个连接（总共 60 个）
- `pool_pre_ping=True`：使用前检查连接是否有效，避免使用失效连接
- `pool_recycle=3600`：连接 1 小时后回收，避免长时间连接导致的问题

**修改文件：**
- `pyFileIndexer/database.py`：`init()` 方法

**预期收益：**
- 高并发场景下性能更好
- 自动检测和处理失效连接
- 避免连接泄漏

---

## P1 - 短期改进（中优先级）

这些改进可以提高代码质量和可维护性，应在 P0 完成后尽快实施。

### 4. 引入 DTO 模式，避免返回 detached ORM 对象

**当前问题：**
```python
# database.py
def get_file_by_path(self, path: str) -> Optional[FileMeta]:
    session = self.session_factory()
    try:
        result = session.query(FileMeta).filter_by(path=path).first()
        if result:
            session.refresh(result)
            session.expunge(result)  # 从会话分离
            return result  # 返回 detached ORM 对象
        return result
    finally:
        session.close()
```

返回 detached ORM 对象的问题：
- 无法懒加载关联对象
- 在多线程环境中容易出现 "Instance is not present in this Session" 错误
- 调用者需要知道对象是 detached 状态

**解决方案：**

创建 DTO（数据传输对象）层：

```python
# pyFileIndexer/models/dto.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class FileMetaDTO:
    """文件元数据传输对象，与 ORM 解耦"""
    id: Optional[int]
    name: str
    path: str
    machine: str
    created: datetime
    modified: datetime
    scanned: datetime
    operation: str
    is_archived: int
    archive_path: Optional[str]
    hash_id: Optional[int]

    @classmethod
    def from_orm(cls, orm_obj: FileMeta) -> "FileMetaDTO":
        """从 ORM 对象创建 DTO"""
        return cls(
            id=orm_obj.id,
            name=orm_obj.name,
            path=orm_obj.path,
            machine=orm_obj.machine,
            created=orm_obj.created,
            modified=orm_obj.modified,
            scanned=orm_obj.scanned,
            operation=orm_obj.operation,
            is_archived=orm_obj.is_archived,
            archive_path=orm_obj.archive_path,
            hash_id=orm_obj.hash_id,
        )

    def to_dict(self) -> dict:
        """转换为字典用于批量插入"""
        data = {
            "name": self.name,
            "path": self.path,
            "machine": self.machine,
            "created": self.created,
            "modified": self.modified,
            "scanned": self.scanned,
            "operation": self.operation,
            "is_archived": self.is_archived,
            "archive_path": self.archive_path,
        }
        if self.hash_id is not None:
            data["hash_id"] = self.hash_id
        return data

@dataclass
class FileHashDTO:
    """文件哈希传输对象"""
    id: Optional[int]
    md5: str
    sha1: str
    sha256: str
    size: int

    @classmethod
    def from_orm(cls, orm_obj: FileHash) -> "FileHashDTO":
        return cls(
            id=orm_obj.id,
            md5=orm_obj.md5,
            sha1=orm_obj.sha1,
            sha256=orm_obj.sha256,
            size=orm_obj.size,
        )

    def to_dict(self) -> dict:
        return {
            "md5": self.md5,
            "sha1": self.sha1,
            "sha256": self.sha256,
            "size": self.size,
        }

@dataclass
class FileWithHashDTO:
    """文件和哈希的组合 DTO"""
    file_meta: FileMetaDTO
    file_hash: Optional[FileHashDTO]

    @classmethod
    def from_orm(cls, file_meta: FileMeta, file_hash: Optional[FileHash]) -> "FileWithHashDTO":
        return cls(
            file_meta=FileMetaDTO.from_orm(file_meta),
            file_hash=FileHashDTO.from_orm(file_hash) if file_hash else None,
        )
```

修改 database.py 返回 DTO：

```python
# database.py
from .models.dto import FileMetaDTO, FileHashDTO, FileWithHashDTO

class DatabaseManager:
    @retry_on_db_lock(max_retries=5, retry_delay=0.5)
    def get_file_by_path(self, path: str) -> Optional[FileMetaDTO]:
        """返回 DTO 而不是 ORM 对象"""
        with self.session_scope() as session:
            result = session.query(FileMeta).filter_by(path=path).first()
            return FileMetaDTO.from_orm(result) if result else None

    @retry_on_db_lock(max_retries=5, retry_delay=0.5)
    def get_file_with_hash_by_path(self, path: str) -> Optional[FileWithHashDTO]:
        """返回文件和哈希的组合 DTO"""
        with self.session_scope() as session:
            result = (
                session.query(FileMeta, FileHash)
                .outerjoin(FileHash, FileMeta.hash_id == FileHash.id)
                .filter(FileMeta.path == path)
                .first()
            )
            if result:
                file_meta, file_hash = result
                return FileWithHashDTO.from_orm(file_meta, file_hash)
            return None

    @retry_on_db_lock(max_retries=5, retry_delay=0.5)
    def get_files_with_hash_by_paths_batch(
        self, paths: list[str]
    ) -> dict[str, FileWithHashDTO]:
        """批量查询，返回 DTO 字典"""
        with self.session_scope() as session:
            results = (
                session.query(FileMeta, FileHash)
                .outerjoin(FileHash, FileMeta.hash_id == FileHash.id)
                .filter(FileMeta.path.in_(paths))
                .all()
            )

            return {
                file_meta.path: FileWithHashDTO.from_orm(file_meta, file_hash)
                for file_meta, file_hash in results
            }
```

**新增文件：**
- `pyFileIndexer/models/dto.py`：DTO 定义

**修改文件：**
- `pyFileIndexer/database.py`：所有查询方法返回 DTO
- `pyFileIndexer/main.py`：调整使用 DTO 的代码

**预期收益：**
- 解决会话分离导致的所有问题
- DTO 是纯数据对象，可以安全地跨线程传递
- 代码更清晰，数据访问层和业务逻辑层解耦
- 更容易测试（DTO 是简单的数据类）

---

### 5. 改进批量操作，添加分批和错误处理

**当前问题：**
```python
# database.py
def add_files_batch(self, files_data: list[dict]):
    with self.session_scope() as session:
        # 在一个大事务中处理所有文件
        # 如果有 1000 个文件，失败一个就全部回滚
        session.bulk_insert_mappings(FileMeta, files_to_insert)
```

问题：
- 批量太大可能导致内存溢出或超时
- 一个文件失败导致整批失败
- 没有错误隔离机制

**解决方案：**

```python
# database.py
from typing import Tuple, List

class DatabaseManager:
    def add_files_batch(
        self,
        files_data: list[dict],
        chunk_size: int = 200
    ) -> Tuple[int, List[str]]:
        """
        批量添加文件，支持分批和错误隔离

        Args:
            files_data: 文件数据列表
            chunk_size: 每批处理的数量

        Returns:
            (成功数量, 失败路径列表)
        """
        if not files_data:
            return 0, []

        success_count = 0
        failed_paths = []
        logger = logging.getLogger(__name__)

        # 预处理：提取所有属性
        processed_data = []
        for item in files_data:
            file_meta = item["file_meta"]
            file_hash = item["file_hash"]
            operation = item["operation"]

            meta_dict = {
                "name": getattr(file_meta, "name", ""),
                "path": getattr(file_meta, "path", ""),
                "machine": getattr(file_meta, "machine", ""),
                "created": getattr(file_meta, "created", None),
                "modified": getattr(file_meta, "modified", None),
                "scanned": getattr(file_meta, "scanned", None),
                "operation": getattr(file_meta, "operation", "ADD"),
                "is_archived": getattr(file_meta, "is_archived", 0),
                "archive_path": getattr(file_meta, "archive_path", None),
            }

            hash_dict = {
                "md5": getattr(file_hash, "md5", None),
                "sha1": getattr(file_hash, "sha1", None),
                "sha256": getattr(file_hash, "sha256", None),
                "size": getattr(file_hash, "size", 0),
            }

            processed_data.append({
                "meta": meta_dict,
                "hash": hash_dict,
                "operation": operation,
            })

        # 分批处理
        for i in range(0, len(processed_data), chunk_size):
            chunk = processed_data[i:i + chunk_size]

            try:
                # 尝试批量处理整个 chunk
                batch_success = self._process_files_chunk(chunk)
                success_count += batch_success
                logger.info(f"Successfully processed {batch_success} files in chunk {i//chunk_size + 1}")

            except Exception as e:
                logger.warning(f"Chunk {i//chunk_size + 1} failed, trying individual files: {e}")

                # 批量失败，逐个处理以隔离错误
                for item in chunk:
                    try:
                        self._process_single_file(item)
                        success_count += 1
                    except Exception as single_error:
                        path = item["meta"]["path"]
                        failed_paths.append(path)
                        logger.error(f"Failed to process file {path}: {single_error}")

        return success_count, failed_paths

    def _process_files_chunk(self, chunk: list[dict]) -> int:
        """处理一批文件（在单个事务中）"""
        with self.session_scope() as session:
            # 提取哈希数据
            hash_data = [item["hash"] for item in chunk]

            # 批量查询已存在的哈希
            existing_hashes = self._get_existing_hashes_in_session(session, hash_data)

            # 插入新哈希
            new_hashes = self._insert_new_hashes_in_session(
                session, hash_data, existing_hashes
            )
            existing_hashes.update(new_hashes)

            # 准备文件数据
            files_to_insert = []
            files_to_update = []

            for item in chunk:
                meta = item["meta"]
                hash_dict = item["hash"]
                operation = item["operation"]

                hash_key = (hash_dict["md5"], hash_dict["sha1"], hash_dict["sha256"])
                hash_id = existing_hashes[hash_key]

                file_dict = {**meta, "hash_id": hash_id}

                if operation == "ADD":
                    files_to_insert.append(file_dict)
                else:
                    files_to_update.append(file_dict)

            # 批量插入新文件
            if files_to_insert:
                session.bulk_insert_mappings(FileMeta, files_to_insert)

            # 批量更新文件
            if files_to_update:
                session.bulk_update_mappings(FileMeta, files_to_update)

            return len(chunk)

    def _process_single_file(self, item: dict) -> None:
        """处理单个文件（独立事务）"""
        with self.session_scope() as session:
            meta = item["meta"]
            hash_dict = item["hash"]

            # 查找或创建哈希
            hash_key = (hash_dict["md5"], hash_dict["sha1"], hash_dict["sha256"])
            existing_hash = (
                session.query(FileHash)
                .filter_by(
                    md5=hash_dict["md5"],
                    sha1=hash_dict["sha1"],
                    sha256=hash_dict["sha256"]
                )
                .first()
            )

            if existing_hash:
                hash_id = existing_hash.id
            else:
                new_hash = FileHash(**hash_dict)
                session.add(new_hash)
                session.flush()
                hash_id = new_hash.id

            # 添加或更新文件
            file_dict = {**meta, "hash_id": hash_id}

            if item["operation"] == "ADD":
                session.bulk_insert_mappings(FileMeta, [file_dict])
            else:
                existing_file = session.query(FileMeta).filter_by(path=meta["path"]).first()
                if existing_file:
                    for key, value in file_dict.items():
                        setattr(existing_file, key, value)
                else:
                    session.bulk_insert_mappings(FileMeta, [file_dict])

    def _get_existing_hashes_in_session(
        self, session, hash_data: list[dict]
    ) -> dict[tuple, int]:
        """在给定会话中查询已存在的哈希"""
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

        return {
            (h.md5, h.sha1, h.sha256): h.id
            for h in existing_hashes
        }

    def _insert_new_hashes_in_session(
        self, session, hash_data: list[dict], existing_hashes: dict
    ) -> dict[tuple, int]:
        """在给定会话中插入新哈希"""
        seen_hashes = set()
        hash_to_insert = []

        for item in hash_data:
            hash_key = (item["md5"], item["sha1"], item["sha256"])
            if hash_key not in existing_hashes and hash_key not in seen_hashes:
                hash_to_insert.append(item)
                seen_hashes.add(hash_key)

        if not hash_to_insert:
            return {}

        session.bulk_insert_mappings(FileHash, hash_to_insert)
        session.flush()

        # 重新查询获取 ID
        hash_keys = [(h["md5"], h["sha1"], h["sha256"]) for h in hash_to_insert]
        new_hashes = (
            session.query(FileHash)
            .filter(
                tuple_(FileHash.md5, FileHash.sha1, FileHash.sha256).in_(hash_keys)
            )
            .all()
        )

        return {
            (h.md5, h.sha1, h.sha256): h.id
            for h in new_hashes
        }
```

**修改文件：**
- `pyFileIndexer/database.py`：重写 `add_files_batch()` 方法
- `pyFileIndexer/main.py`：处理返回的失败列表

**预期收益：**
- 分批处理避免内存溢出和超时
- 错误隔离，一个文件失败不影响其他文件
- 返回详细的成功/失败信息，便于监控和调试
- 更好的容错性

---

### 6. 添加数据库连接健康检查和监控

**当前问题：**
- 没有连接健康检查机制
- 没有性能监控
- 出现问题难以排查

**解决方案：**

```python
# database.py
import time
from contextlib import contextmanager

class DatabaseManager:
    def __init__(self):
        # ... 现有初始化代码
        self._connection_pool_stats = {
            "total_connections": 0,
            "active_connections": 0,
            "idle_connections": 0,
        }

    @contextmanager
    def session_scope_with_metrics(self, operation_name: str = "unknown"):
        """带性能监控的会话管理"""
        session = self.Session()
        start_time = time.time()

        try:
            yield session
            session.commit()

            duration = time.time() - start_time
            self._record_transaction_success(operation_name, duration)

        except Exception as e:
            session.rollback()

            duration = time.time() - start_time
            self._record_transaction_failure(operation_name, duration, e)

            raise
        finally:
            session.close()

    def _record_transaction_success(self, operation: str, duration: float):
        """记录成功的事务"""
        logger = logging.getLogger(__name__)
        logger.debug(f"Transaction '{operation}' completed in {duration:.3f}s")

        try:
            from .metrics import metrics
            metrics.observe_db_transaction(duration, "success", operation)
        except Exception:
            pass

    def _record_transaction_failure(
        self, operation: str, duration: float, error: Exception
    ):
        """记录失败的事务"""
        logger = logging.getLogger(__name__)
        logger.error(
            f"Transaction '{operation}' failed after {duration:.3f}s: {error}"
        )

        try:
            from .metrics import metrics
            metrics.observe_db_transaction(duration, "failed", operation)
            metrics.inc_db_errors(type(error).__name__, operation)
        except Exception:
            pass

    def get_connection_pool_stats(self) -> dict:
        """获取连接池统计信息"""
        if self.engine is None:
            return {}

        pool = self.engine.pool
        return {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "total": pool.size() + pool.overflow(),
        }

    def health_check(self) -> dict:
        """数据库健康检查"""
        result = {
            "status": "unknown",
            "latency_ms": None,
            "pool_stats": {},
            "error": None,
        }

        try:
            start_time = time.time()

            # 执行简单查询测试连接
            with self.session_scope() as session:
                session.execute(text("SELECT 1"))

            latency = (time.time() - start_time) * 1000

            result.update({
                "status": "healthy",
                "latency_ms": round(latency, 2),
                "pool_stats": self.get_connection_pool_stats(),
            })

        except Exception as e:
            result.update({
                "status": "unhealthy",
                "error": str(e),
            })

        return result
```

在 main.py 中添加健康检查：

```python
# main.py
def main():
    # ... 现有代码

    if args.command == "scan":
        # 扫描前进行健康检查
        health = db_manager.health_check()
        logger.info(f"Database health check: {health['status']}")

        if health["status"] == "unhealthy":
            logger.error(f"Database unhealthy: {health['error']}")
            sys.exit(1)

        logger.info(f"Database latency: {health['latency_ms']}ms")
        logger.info(f"Connection pool: {health['pool_stats']}")

        # 开始扫描
        scan(args.path)
```

**新增方法：**
- `session_scope_with_metrics()`：带监控的会话管理
- `get_connection_pool_stats()`：连接池统计
- `health_check()`：健康检查

**修改文件：**
- `pyFileIndexer/database.py`：添加监控方法
- `pyFileIndexer/main.py`：添加启动时健康检查

**预期收益：**
- 实时监控数据库性能
- 及时发现连接池问题
- 启动时检查数据库可用性
- 更容易排查问题

---

## P2 - 中期重构（低优先级）

这些改进涉及更大范围的架构调整，建议在 P0 和 P1 完成后，根据实际需求逐步实施。

### 7. 引入 Repository 模式

将数据访问逻辑从 `DatabaseManager` 中分离到专门的 Repository 类中：

```python
# repositories/file_repository.py
class FileRepository:
    def __init__(self, session):
        self.session = session

    def get_by_path(self, path: str) -> Optional[FileMetaDTO]:
        result = self.session.query(FileMeta).filter_by(path=path).first()
        return FileMetaDTO.from_orm(result) if result else None

    def batch_get_by_paths(self, paths: list[str]) -> dict[str, FileMetaDTO]:
        results = self.session.query(FileMeta).filter(FileMeta.path.in_(paths)).all()
        return {r.path: FileMetaDTO.from_orm(r) for r in results}

    def batch_insert(self, files: list[FileMetaDTO]) -> None:
        mappings = [f.to_dict() for f in files]
        self.session.bulk_insert_mappings(FileMeta, mappings)

# repositories/hash_repository.py
class HashRepository:
    def __init__(self, session):
        self.session = session

    def get_by_hash(self, md5: str, sha1: str, sha256: str) -> Optional[FileHashDTO]:
        result = self.session.query(FileHash).filter_by(
            md5=md5, sha1=sha1, sha256=sha256
        ).first()
        return FileHashDTO.from_orm(result) if result else None
```

### 8. 引入 Unit of Work 模式

统一管理多个 Repository 的事务：

```python
# uow.py
class UnitOfWork:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def __enter__(self):
        self.session = self.session_factory()
        self.files = FileRepository(self.session)
        self.hashes = HashRepository(self.session)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        self.session.close()

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()
```

### 9. 配置化重试策略

从配置文件读取重试参数，支持不同操作使用不同策略。

---

## P3 - 长期优化（可选）

这些优化针对大规模部署和极高性能要求的场景，根据实际需求评估是否实施。

### 10. 添加查询缓存

使用 Redis 缓存常用查询结果，减少数据库压力。

### 11. 考虑读写分离

如果数据量非常大，可以考虑主从复制，读写分离。

### 12. 添加数据库性能监控

集成 Prometheus、Grafana 等工具，实时监控数据库性能指标。

---

## 实施时间表

| 阶段 | 预计时间 | 主要任务 |
|------|---------|---------|
| P0 - 立即修复 | 1-2 天 | 统一会话管理、scoped_session、连接池配置 |
| P1 - 短期改进 | 3-5 天 | DTO 模式、改进批量操作、健康检查 |
| P2 - 中期重构 | 1-2 周 | Repository 模式、UnitOfWork 模式 |
| P3 - 长期优化 | 按需实施 | 缓存、读写分离、性能监控 |

---

## 测试策略

每个阶段完成后需要进行充分测试：

1. **单元测试**：测试各个方法的正确性
2. **集成测试**：测试数据库操作的正确性
3. **并发测试**：使用 pytest-xdist 进行多线程测试
4. **性能测试**：对比重构前后的性能指标

---

## 风险评估

| 风险 | 影响程度 | 缓解措施 |
|------|---------|---------|
| 重构引入新 bug | 高 | 充分测试，渐进式重构，每个阶段都保持测试通过 |
| 性能下降 | 中 | 性能基准测试，对比重构前后的性能 |
| 兼容性问题 | 低 | DTO 保持向后兼容，逐步迁移调用代码 |

---

## 总结

本重构计划旨在解决当前数据库层存在的主要问题，提高代码质量、可维护性和性能。通过分阶段实施，可以在保证系统稳定性的前提下逐步改进架构。

**核心原则：**
1. 分离关注点：数据访问、业务逻辑、表示层清晰分离
2. 线程安全：使用 scoped_session，避免会话冲突
3. 容错性：分批处理，错误隔离
4. 可测试性：DTO 模式，依赖注入
5. 可监控性：添加健康检查和性能指标

通过这些改进，pyFileIndexer 的数据库层将更加健壮、高效和易于维护。
