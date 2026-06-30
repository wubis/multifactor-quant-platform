from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from multifactor_platform.config import get_settings


def build_engine(database_url: str | None = None):
    return create_engine(database_url or get_settings().database_url, pool_pre_ping=True)


def build_session_factory(database_url: str | None = None):
    return sessionmaker(bind=build_engine(database_url), autoflush=False, autocommit=False)
