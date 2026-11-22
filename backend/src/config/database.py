from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from src.config.settings import DB_URL

class Base(DeclarativeBase):
    pass

engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=240)
Session = sessionmaker(engine, expire_on_commit=False)


def migrate():
    """为既有数据库补充后加列，保持幂等；新建库由 create_all 一并建出。"""
    with engine.begin() as connection:
        connection.execute(text('ALTER TABLE runs ADD COLUMN IF NOT EXISTS checkpoint JSON'))


def connection():
    with Session() as db:
        yield db
