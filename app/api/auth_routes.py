"""Authentication API routes."""

from fastapi import APIRouter, HTTPException, Depends, status, Response

from app.api.auth_schemas import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    TokenResponse,
    APIKeyCreateRequest,
    APIKeyResponse,
    APIKeyListItem,
    APIKeyListResponse,
)
from app.api.dependencies import require_auth
from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    generate_api_key,
)
from app.models.user import (
    User,
    get_user_by_username,
    get_user_by_email,
    create_user,
    create_api_key,
    list_api_keys_by_user,
    revoke_api_key,
)
from app.utils.logger import get_logger

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = get_logger(__name__)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(request: UserRegisterRequest) -> UserResponse:
    """Register a new user."""
    # Check if username exists
    if get_user_by_username(request.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )

    # Check if email exists
    if get_user_by_email(request.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create user
    user = create_user(
        username=request.username,
        email=request.email,
        password_hash=hash_password(request.password),
    )

    logger.info("user_registered", username=user.username, user_id=user.id)

    return UserResponse(**user.to_dict())


@router.post("/login", response_model=TokenResponse)
async def login(request: UserLoginRequest, response: Response) -> TokenResponse:
    """Login and get access token."""
    user = get_user_by_username(request.username)

    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled"
        )

    token = create_access_token(user.id, user.username)

    # Set HTTP-only cookie for web UI
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,  # Set True in production with HTTPS
        samesite="lax",
        max_age=60 * 60 * 24,  # 24 hours
    )

    logger.info("user_login", username=user.username, user_id=user.id)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(**user.to_dict())
    )


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Logout and clear session cookie."""
    response.delete_cookie("access_token")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(require_auth)) -> UserResponse:
    """Get current authenticated user."""
    return UserResponse(**user.to_dict())


@router.post("/api-keys", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_new_api_key(
    request: APIKeyCreateRequest,
    user: User = Depends(require_auth)
) -> APIKeyResponse:
    """Create a new API key."""
    full_key, prefix, key_hash = generate_api_key()

    api_key = create_api_key(
        user_id=user.id,
        name=request.name,
        key_prefix=prefix,
        key_hash=key_hash,
        expires_at=request.expires_at,
    )

    logger.info("api_key_created", user_id=user.id, key_id=api_key.id)

    # Return the full key ONLY on creation
    return APIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key=full_key,  # Only returned on creation!
        key_prefix=f"{prefix}...",
        created_at=api_key.created_at,
    )


@router.get("/api-keys", response_model=APIKeyListResponse)
async def list_my_api_keys(user: User = Depends(require_auth)) -> APIKeyListResponse:
    """List user's API keys."""
    keys = list_api_keys_by_user(user.id)

    return APIKeyListResponse(
        keys=[
            APIKeyListItem(
                id=k.id,
                name=k.name,
                key_prefix=f"{k.key_prefix}...",
                is_active=k.is_active,
                last_used_at=k.last_used_at,
                expires_at=k.expires_at,
                created_at=k.created_at,
            )
            for k in keys
        ]
    )


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(key_id: str, user: User = Depends(require_auth)) -> None:
    """Revoke an API key."""
    if not revoke_api_key(key_id, user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    logger.info("api_key_revoked", user_id=user.id, key_id=key_id)
