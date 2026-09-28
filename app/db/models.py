import uuid
import json
from datetime import datetime, timezone
from typing import List, Optional, Any
from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    Text,
    Boolean,
    Integer,
    Float,
    BigInteger,
    Index,
    JSON,
    TypeDecorator
)
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.db.database import Base
from app.config import settings


class FlexibleVector(TypeDecorator):
    """
    SQLAlchemy type that uses native pgvector Vector on PostgreSQL,
    and falls back to JSON-serialized floats on SQLite or non-pgvector engines.
    """
    impl = Text
    cache_ok = True
    comparator_factory = Vector.comparator_factory

    def __init__(self, dim: int = 768):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dim))
        else:
            return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        if isinstance(value, (list, tuple)):
            return json.dumps(list(value))
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            # pgvector Vector already returns numpy array or list
            if hasattr(value, "tolist"):
                return value.tolist()
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return []
        return value


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="organization", cascade="all, delete-orphan")
    document_chunks = relationship("DocumentChunk", back_populates="organization", cascade="all, delete-orphan")
    query_logs = relationship("QueryLog", back_populates="organization", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    role = Column(String(32), default="employee", nullable=False)  # "admin" or "employee"
    status = Column(String(32), default="active", nullable=False)  # "active", "suspended"
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    organization = relationship("Organization", back_populates="users")
    query_logs = relationship("QueryLog", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_org_employee", "organization_id", "employee_id", unique=True),
    )


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    storage_path = Column(String(512), nullable=False)
    file_size = Column(Integer, default=0, nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    organization = relationship("Organization", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(FlexibleVector(dim=settings.EMBEDDING_DIMENSION), nullable=True)
    chunk_metadata = Column(JSON, nullable=True)

    document = relationship("Document", back_populates="chunks")
    organization = relationship("Organization", back_populates="document_chunks")

    __table_args__ = (
        Index("ix_chunk_org", "organization_id"),
    )


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    model_used = Column(String(64), nullable=False)
    cache_hit = Column(Boolean, default=False, nullable=False)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    estimated_cost = Column(Float, default=0.0, nullable=False)
    latency_ms = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="query_logs")
    organization = relationship("Organization", back_populates="query_logs")


class TelegramSession(Base):
    __tablename__ = "telegram_sessions"

    telegram_user_id = Column(BigInteger, primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    role = Column(String(32), nullable=True)  # "admin" | "employee"
    auth_state = Column(String(32), default="UNAUTHENTICATED", nullable=False)
    auth_context = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User")
    organization = relationship("Organization")
