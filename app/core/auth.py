"""Authentication utilities."""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt

from app.config import get_settings


# JWT Configuration
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate API key.

    Returns:
        Tuple of (full_key, prefix, hash)
    """
    full_key = f"vmg_{secrets.token_urlsafe(32)}"
    prefix = full_key[:12]  # "vmg_" + 8 chars
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, prefix, key_hash


def hash_api_key(api_key: str) -> str:
    """Hash API key for storage/comparison."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def create_access_token(user_id: str, username: str) -> str:
    """Create JWT access token."""
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "username": username,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate JWT token."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
