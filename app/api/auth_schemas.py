"""Pydantic schemas for authentication."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, EmailStr


class UserRegisterRequest(BaseModel):
    """Request schema for user registration."""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)


class UserLoginRequest(BaseModel):
    """Request schema for user login."""
    username: str
    password: str


class UserResponse(BaseModel):
    """Response schema for user data."""
    id: str
    username: str
    email: str
    is_active: bool
    is_admin: bool
    created_at: Optional[datetime] = None


class TokenResponse(BaseModel):
    """Response schema for login with token."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class APIKeyCreateRequest(BaseModel):
    """Request schema for creating API key."""
    name: str = Field(..., min_length=1, max_length=100)
    expires_at: Optional[datetime] = None


class APIKeyResponse(BaseModel):
    """Response schema for API key (with full key on creation)."""
    id: str
    name: str
    key: Optional[str] = None  # Only returned on creation
    key_prefix: str
    created_at: Optional[datetime] = None


class APIKeyListItem(BaseModel):
    """List item schema for API keys."""
    id: str
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class APIKeyListResponse(BaseModel):
    """Response schema for listing API keys."""
    keys: list[APIKeyListItem]
