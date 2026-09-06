# backend/app/api/auth.py

from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pymongo.errors import DuplicateKeyError
from datetime import datetime, timezone
from ..core.security import hash_password
from ..schemas.auth import (
    SignupRequest,
    LoginRequest,
    AuthResponse,
    ChangePasswordRequest,
)
from ..schemas.user import UserPublic
from ..services.users import (
    get_users_collection,
    ensure_indexes,
    create_user,
    find_user_by_email,
    check_user_password,
    to_public,
)
from ..services.study_flow import ensure_user_flow
from ..core.security import create_access_token, decode_token
from ..core.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


def set_session_cookie(resp: Response, token: str):
    s = get_settings()
    resp.set_cookie(
        key=s.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=s.COOKIE_SECURE,
        samesite=s.SAMESITE,
        domain=s.COOKIE_DOMAIN,
        max_age=s.JWT_EXPIRES_MIN * 60,
        path="/",
    )


def clear_session_cookie(resp: Response):
    s = get_settings()
    resp.delete_cookie(
        key=s.COOKIE_NAME,
        domain=s.COOKIE_DOMAIN,
        path="/",
    )


# Single mapper, shared with services.users, so the two copies cannot drift.
build_user_public = to_public


def get_current_user_doc(request: Request) -> dict:
    """Authenticate the request and return the raw user document.

    Also lazily backfills step_order/completed_steps for accounts created before
    the multi-variant flow existed, so a participant mid-study picks up where
    they left off instead of restarting.
    """
    s = get_settings()
    token = request.cookies.get(s.COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token (no subject)")

    db = request.app.state.db
    doc = find_user_by_email(get_users_collection(db), email)
    if not doc:
        raise HTTPException(status_code=401, detail="User not found")

    return ensure_user_flow(db, doc)


def get_current_user(request: Request) -> UserPublic:
    return build_user_public(get_current_user_doc(request))


@router.post("/signup", response_model=AuthResponse)
def signup(data: SignupRequest, request: Request, response: Response):
    users = get_users_collection(request.app.state.db)
    ensure_indexes(users)

    if data.consent is not True:
        raise HTTPException(status_code=400, detail="Consent is required")

    try:
        user_pub = create_user(
            users,
            email=data.email,
            password=data.password,
            first_name=data.first_name,
            last_name=data.last_name,
            consent=data.consent,
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Email already registered")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    token = create_access_token(user_pub.email)
    set_session_cookie(response, token)
    return AuthResponse(user=user_pub)


@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest, request: Request, response: Response):
    db = request.app.state.db
    users = get_users_collection(db)
    doc = find_user_by_email(users, data.email)
    if not doc or not check_user_password(doc, data.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Backfill legacy accounts at the door rather than on first quiz load.
    user_pub = build_user_public(ensure_user_flow(db, doc))

    token = create_access_token(user_pub.email)
    set_session_cookie(response, token)
    return AuthResponse(user=user_pub)


@router.get("/me", response_model=AuthResponse)
def me(user: UserPublic = Depends(get_current_user)):
    return AuthResponse(user=user)


@router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"ok": True}


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    users = get_users_collection(request.app.state.db)
    doc = find_user_by_email(users, user.email)
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")

    if not check_user_password(doc, data.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    new_hash = hash_password(data.new_password)
    users.update_one(
        {"_id": doc["_id"]},
        {
            "$set": {
                "password_hash": new_hash,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    return {"ok": True}