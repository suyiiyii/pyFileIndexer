from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dataclasses import dataclass
# 创建对象的基类
Base = declarative_base()

# 数据库连接字符串
DB = 'sqlite:///file_hash.db'


@dataclass
class FileHash(Base):
    __tablename__ = 'file_hash'
    # id 主键，自增
    id = Column(Integer, primary_key=True, autoincrement=True)
    # 文件大小
    size = Column(Integer)
    # 文件哈希，索引
    md5 = Column(String, index=True)
    sha1 = Column(String, index=True)
    sha256 = Column(String, index=True)

@dataclass
class FileMeta(Base):
    __tablename__ = 'file_meta'
    # id 主键，自增
    id = Column(Integer, primary_key=True, autoincrement=True)
    # 哈希信息，外键到 FileHash
    hash_id = Column(Integer, index=True)
    # 文件名
    name = Column(String)
    # 文件路径
    path = Column(String)
    # 创建日期
    created = Column(DateTime)
    # 修改日期
    modified = Column(DateTime)
    # 扫描日期
    scanned = Column(DateTime)


# 创建数据库连接
engine = create_engine(DB)

# 创建数据库表
Base.metadata.create_all(engine)

# 创建会话
Session = sessionmaker(bind=engine)


def session_factory():
    return Session()
