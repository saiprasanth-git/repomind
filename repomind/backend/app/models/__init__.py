"""
Import all models here so SQLAlchemy discovers them when creating tables.
Alembic also imports from this module for autogenerate migrations.
"""
from app.models.repo import Repository, RepoStatus
from app.models.chunk import CodeChunk
from app.models.query_log import QueryLog

__all__ = ["Repository", "RepoStatus", "CodeChunk", "QueryLog"]
