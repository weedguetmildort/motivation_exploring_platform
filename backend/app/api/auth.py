from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pymongo.errors import DuplicateKeyError
from ..schemas.auth import SignupRequest, LoginRequest, AuthResponse
from ..schemas.user import UserPublic
from ..services.users import (
    get_users_collection,
    ensure_indexes,
    create_user,
    find_user_by_email,
    check_user_password,
)
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

def get_current_user(request: Request) -> UserPublic:
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

    users = get_users_collection(request.app.state.db)
    doc = find_user_by_email(users, email)
    if not doc:
        raise HTTPException(status_code=401, detail="User not found")

    return UserPublic(id=str(doc["_id"]), email=doc["email"])

@router.post("/signup", response_model=AuthResponse)
def signup(data: SignupRequest, request: Request, response: Response):
    # DEBUG: inspect what we actually got
    try:
        pw_bytes_len = len(data.password.encode("utf-8"))
    except Exception as e:
        print(f"[auth.signup] password debug failed: {e}")

    users = get_users_collection(request.app.state.db)
    ensure_indexes(users)

    try:
        user_pub = create_user(users, data.email, data.password)
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Email already registered")
    

    token = create_access_token(user_pub.email)
    set_session_cookie(response, token)
    return AuthResponse(user=user_pub)

@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest, request: Request, response: Response):
    # DEBUG: inspect what we actually got
    try:
        pw_bytes_len = len(data.password.encode("utf-8"))
        print(f"[auth.signup] pw bytes len={pw_bytes_len} value preview={repr(data.password[:64])}")
    except Exception as e:
        print(f"[auth.signup] password debug failed: {e}")

    
    users = get_users_collection(request.app.state.db)
    doc = find_user_by_email(users, data.email)
    if not doc or not check_user_password(doc, data.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user_pub = UserPublic(id=str(doc["_id"]), email=doc["email"])
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
