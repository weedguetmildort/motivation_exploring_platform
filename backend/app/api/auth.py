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
    ConsentAgreementRequest,
)
from ..schemas.user import UserPublic, SurveyStage, AssignedVar
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


def build_user_public(doc: dict) -> UserPublic:
    raw_stage = doc.get("survey_stage", SurveyStage.pre_base)

    try:
        survey_stage = raw_stage if isinstance(raw_stage, SurveyStage) else SurveyStage(raw_stage)
    except Exception:
        survey_stage = SurveyStage.pre_base

    return UserPublic(
        id=str(doc["_id"]),
        email=doc["email"],
        first_name=doc.get("first_name"),
        last_name=doc.get("last_name"),
        consent=doc.get("consent"),
        consent_given_at=doc.get("consent_given_at"),
        consent_text=doc.get("consent_text"),
        consent_agreed_at=doc.get("consent_agreed_at"),
        assigned_var=doc.get("assigned_var", AssignedVar.followup.value),
        is_admin=bool(doc.get("is_admin", False)),
        demographics_completed=doc.get("demographics_completed", False),
        survey_pre_base_completed=doc.get("survey_pre_base_completed", False),
        quiz_base_completed=doc.get("quiz_base_completed", False),
        survey_post_base_completed=doc.get("survey_post_base_completed", False),
        quiz_variant_completed=doc.get("quiz_variant_completed", False),
        survey_post_variant_completed=doc.get("survey_post_variant_completed", False),
        survey_stage=survey_stage,
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

    return build_user_public(doc)


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
    users = get_users_collection(request.app.state.db)
    doc = find_user_by_email(users, data.email)
    if not doc or not check_user_password(doc, data.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_pub = build_user_public(doc)

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


@router.post("/consent")
def record_consent_agreement(
    data: ConsentAgreementRequest,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    users = get_users_collection(request.app.state.db)
    doc = find_user_by_email(users, user.email)
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.now(timezone.utc)
    users.update_one(
        {"_id": doc["_id"]},
        {
            "$set": {
                "consent_text": data.consent_text,
                "consent_agreed_at": now,
                "updated_at": now,
            }
        },
    )

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