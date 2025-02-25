# coding: utf-8
import os
from sqlalchemy import Column, INTEGER, BIGINT, TEXT, BOOLEAN, DATETIME, TIMESTAMP, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import StaticPool

# 获取数据库URL配置，默认使用SQLite
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./config/bot.db')

# 创建数据库引擎
engine_kwargs = {
    'echo': False
}

# SQLite特定配置
if DATABASE_URL.startswith('sqlite'):
    engine_kwargs.update({
        'connect_args': {'check_same_thread': False},
        'poolclass': StaticPool
    })

engine = create_engine(DATABASE_URL, **engine_kwargs)

DBSession = sessionmaker(bind=engine)
Base = declarative_base()


class Message(Base):
    __tablename__ = 'message'

    _id = Column(INTEGER, primary_key=True)
    id = Column(BIGINT)
    link = Column(TEXT)
    type = Column(TEXT)  # 文本、图像、视频、音频、语音
    category = Column(TEXT)  # 分类
    text = Column(TEXT)
    video = Column(TEXT)
    photo = Column(TEXT)
    audio = Column(TEXT)
    voice = Column(TEXT)
    date = Column(TIMESTAMP)
    from_id = Column(BIGINT)
    from_chat = Column(BIGINT)


class User(Base):
    __tablename__ = 'user'

    id = Column(BIGINT, primary_key=True)
    fullname = Column(TEXT)
    username = Column(TEXT)


class UserAlias(Base):
    __tablename__ = 'user_alias'

    id = Column(INTEGER, primary_key=True)
    user_id = Column(BIGINT)  # The actual user ID this alias refers to
    alias = Column(TEXT)  # The alias name
    created_by = Column(BIGINT)  # The user ID who created this alias
    created_at = Column(TIMESTAMP)  # When this alias was created


class Chat(Base):
    __tablename__ = 'chat'

    id = Column(BIGINT, primary_key=True)
    title = Column(TEXT)
    enable = Column(BOOLEAN)


Base.metadata.create_all(engine)