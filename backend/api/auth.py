"""
Authentication module - local JWT login/register flow.
"""
import base64
import binascii
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import AuthRequest, AuthTokenResponse, UserResponse
from config import settings
from db import User, get_user_db


logger = structlog.get_logger()
security = HTTPBearer(auto_error=False)
router = APIRouter()

PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 260_000


def _auth_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
    )


def _invalid_credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
    )


def _require_jwt_secret() -> None:
    if not settings.JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT_SECRET is not configured",
        )


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"{PASSWORD_HASH_ALGORITHM}${PASSWORD_HASH_ITERATIONS}${salt_b64}${digest_b64}"


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_b64, expected_b64 = password_hash.split("$", 3)
        if algorithm != PASSWORD_HASH_ALGORITHM:
            return False

        iterations = int(iterations_raw)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(expected_b64.encode("ascii"))
    except (ValueError, TypeError, binascii.Error):
        return False

    calculated = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(calculated, expected)


def _create_access_token(user: User) -> str:
    _require_jwt_secret()

    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS)
    payload = {
        "sub": str(user.user_id),
        "email": user.email,
        "type": "access",
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _decode_access_token(token: str) -> dict:
    _require_jwt_secret()

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        raise _auth_error()

    if payload.get("type") != "access":
        raise _auth_error()

    return payload


def _normalize_email(email: str) -> str:
    return email.strip().lower()


@router.post("/auth/register", response_model=AuthTokenResponse)
async def register(payload: AuthRequest, db: AsyncSession = Depends(get_user_db)):
    """Create a user account and return an access token."""
    email = _normalize_email(str(payload.email))

    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=email,
        password_hash=_hash_password(payload.password),
    )
    db.add(user)

    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    return AuthTokenResponse(access_token=_create_access_token(user))


@router.post("/auth/login", response_model=AuthTokenResponse)
async def login(payload: AuthRequest, db: AsyncSession = Depends(get_user_db)):
    """Authenticate with email/password and return an access token."""
    email = _normalize_email(str(payload.email))
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not _verify_password(payload.password, user.password_hash):
        raise _invalid_credentials_error()

    return AuthTokenResponse(access_token=_create_access_token(user))


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_user_db),
) -> User:
    """
    Dependency to get current authenticated user from a local JWT access token.
    """
    if credentials is None or not credentials.credentials:
        raise _auth_error()

    payload = _decode_access_token(credentials.credentials)

    subject = payload.get("sub")
    if not subject:
        raise _auth_error()

    try:
        user_id = uuid.UUID(str(subject))
    except (TypeError, ValueError):
        raise _auth_error()

    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise _auth_error()

    return user


@router.get("/auth/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile from the local JWT identity."""
    return UserResponse(
        user_id=str(current_user.user_id),
        email=current_user.email,
        created_at=current_user.created_at,
    )
