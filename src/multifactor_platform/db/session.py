from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from multifactor_platform.config import get_settings


def build_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


def build_session_factory(database_url: str | None = None):
    return sessionmaker(bind=build_engine(database_url), autoflush=False, autocommit=False)
