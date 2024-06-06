from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 数据库连接字符串
DB = 'sqlite:///file_hash.db'

# 创建数据库连接
Base = declarative_base()
engine = create_engine(DB)


# 创建会话
Session = sessionmaker(bind=engine)


def session_factory():
    return Session()


def create_all():
    '''创建所有表。'''
    Base.metadata.create_all(engine)
