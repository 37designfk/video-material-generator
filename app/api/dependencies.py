"""FastAPI dependencies for authentication."""

from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, status, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.auth import decode_access_token, hash_api_key
from app.models.user import (
    User,
    APIKey,
    get_user_by_id,
    get_api_key_by_hash,
    update_api_key_last_used,
)

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(None),
) -> Optional[User]:
    """
    Get current user from JWT token (header or cookie) or API key.
    Returns None if not authenticated.
    """
    token = None

    # Try Bearer token from header first
    if credentials:
        token = credentials.credentials
    # Fall back to cookie
    elif access_token:
        token = access_token

    if not token:
        return None

    # Check if it's an API key (starts with "vmg_")
    if token.startswith("vmg_"):
        return await _authenticate_api_key(token)

    # Otherwise, treat as JWT
    return await _authenticate_jwt(token)


async def _authenticate_jwt(token: str) -> Optional[User]:
    """Authenticate using JWT token."""
    payload = decode_access_token(token)
    if not payload:
        return None

    user = get_user_by_id(payload["sub"])
    if user and user.is_active:
        return user
    return None


async def _authenticate_api_key(api_key: str) -> Optional[User]:
    """Authenticate using API key."""
    key_hash = hash_api_key(api_key)
    api_key_record = get_api_key_by_hash(key_hash)

    if not api_key_record:
        return None

    # Check expiration
    if api_key_record.expires_at and api_key_record.expires_at < datetime.utcnow():
        return None

    # Update last used
    update_api_key_last_used(api_key_record.id)

    # Get user
    user = get_user_by_id(api_key_record.user_id)
    if user and user.is_active:
        return user
    return None


async def require_auth(user: Optional[User] = Depends(get_current_user)) -> User:
    """Require authenticated user. Raises 401 if not authenticated."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin(user: User = Depends(require_auth)) -> User:
    """Require admin user."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user
