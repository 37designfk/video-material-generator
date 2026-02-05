"""SQLAlchemy models for user and authentication management."""

from datetime import datetime
from typing import Optional
import hashlib
import secrets
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    String,
    Boolean,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from app.models.job import Base, get_session


class User(Base):
    """User model for authentication."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class APIKey(Base):
    """API Key model for programmatic access."""

    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    key_prefix = Column(String(12), nullable=False)  # "vmg_" + 8 chars
    key_hash = Column(String(64), nullable=False)  # SHA256 hash
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="api_keys")

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "key_prefix": f"{self.key_prefix}...",
            "is_active": self.is_active,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# CRUD functions for User
def get_user_by_id(user_id: str) -> Optional[User]:
    """Get user by ID."""
    session = get_session()
    try:
        return session.query(User).filter(User.id == user_id).first()
    finally:
        session.close()


def get_user_by_username(username: str) -> Optional[User]:
    """Get user by username."""
    session = get_session()
    try:
        return session.query(User).filter(User.username == username).first()
    finally:
        session.close()


def get_user_by_email(email: str) -> Optional[User]:
    """Get user by email."""
    session = get_session()
    try:
        return session.query(User).filter(User.email == email).first()
    finally:
        session.close()


def create_user(username: str, email: str, password_hash: str) -> User:
    """Create a new user."""
    session = get_session()
    try:
        user = User(
            id=str(uuid.uuid4()),
            username=username,
            email=email,
            password_hash=password_hash,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


# CRUD functions for APIKey
def get_api_key_by_hash(key_hash: str) -> Optional[APIKey]:
    """Get API key by hash."""
    session = get_session()
    try:
        return session.query(APIKey).filter(
            APIKey.key_hash == key_hash,
            APIKey.is_active == True
        ).first()
    finally:
        session.close()


def create_api_key(user_id: str, name: str, key_prefix: str, key_hash: str, expires_at: Optional[datetime] = None) -> APIKey:
    """Create a new API key."""
    session = get_session()
    try:
        api_key = APIKey(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            expires_at=expires_at,
        )
        session.add(api_key)
        session.commit()
        session.refresh(api_key)
        return api_key
    finally:
        session.close()


def list_api_keys_by_user(user_id: str) -> list[APIKey]:
    """List all active API keys for a user."""
    session = get_session()
    try:
        return session.query(APIKey).filter(
            APIKey.user_id == user_id,
            APIKey.is_active == True
        ).all()
    finally:
        session.close()


def revoke_api_key(key_id: str, user_id: str) -> bool:
    """Revoke an API key."""
    session = get_session()
    try:
        api_key = session.query(APIKey).filter(
            APIKey.id == key_id,
            APIKey.user_id == user_id
        ).first()
        if api_key:
            api_key.is_active = False
            session.commit()
            return True
        return False
    finally:
        session.close()


def update_api_key_last_used(key_id: str) -> None:
    """Update API key last used timestamp."""
    session = get_session()
    try:
        api_key = session.query(APIKey).filter(APIKey.id == key_id).first()
        if api_key:
            api_key.last_used_at = datetime.utcnow()
            session.commit()
    finally:
        session.close()
