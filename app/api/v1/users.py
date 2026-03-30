"""User endpoints — register, login, and profile."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user_id, get_db
from app.core.security import create_access_token, verify_password
from app.schemas.user import TokenResponse, UserCreate, UserLogin, UserResponse
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/register", response_model=UserResponse, status_code=201)
async def register_user(payload: UserCreate, db: Session = Depends(get_db)):
    """Register a new user. Returns user profile (no password)."""
    if user_service.get_user_by_email(db, payload.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    return user_service.create_user(db, payload)


@router.post("/login", response_model=TokenResponse)
async def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    """Authenticate with email + password and receive a JWT access token."""
    user = user_service.get_user_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    token = create_access_token(user.user_id)
    return TokenResponse(access_token=token, user_id=user.user_id)


@router.get("/me", response_model=UserResponse)
async def get_me(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Return the profile of the currently authenticated user."""
    user = user_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    _: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Fetch a user by ID (requires authentication)."""
    user = user_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
