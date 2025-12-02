from sqlalchemy import Column, Integer, String, DateTime
from dataclasses import dataclass

from base import Base


@dataclass
class FileHash(Base):
    __tablename__ = "file_hash"
    # id 主键，自增
    id = Column(Integer, primary_key=True, autoincrement=True)
    # 文件大小，添加索引用于大小范围查询
    size = Column(Integer, index=True)
    # 文件哈希，索引
    md5 = Column(String, index=True)
    sha1 = Column(String, index=True)
    sha256 = Column(String, index=True)


@dataclass
class FileMeta(Base):
    __tablename__ = "file_meta"
    # id 主键，自增
    id = Column(Integer, primary_key=True, autoincrement=True)
    # 哈希信息，外键到 FileHash
    hash_id = Column(Integer, index=True)
    # 文件名，索引
    name = Column(String, index=True)
    # 机器名称，添加索引用于按机器过滤
    machine = Column(String, index=True)
    # 文件路径，全文索引
    path = Column(String, index=True)
    # 创建日期，添加索引用于时间范围查询
    created = Column(DateTime, index=True)
    # 修改日期，添加索引用于时间范围查询
    modified = Column(DateTime, index=True)
    # 扫描日期，添加索引用于时间范围查询
    scanned = Column(DateTime, index=True)
    # 操作，添加索引用于按操作类型过滤
    operation = Column(String, index=True)
    # 是否来自压缩包，索引用于过滤
    is_archived = Column(Integer, index=True, default=0)
    # 压缩包路径，索引用于关联查询
    archive_path = Column(String, index=True)
