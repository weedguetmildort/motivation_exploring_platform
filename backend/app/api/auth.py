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
    ConsentDeclineRequest,
)
from ..schemas.user import UserPublic
from ..services.users import (
    get_users_collection,
    ensure_indexes,
    create_user,
    find_user_by_email,
    check_user_password,
    maybe_touch_last_active,
    user_to_public,
)
from ..services.study_flow import ensure_user_flow, reconcile_saved_progress
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
    """Serialize a stored user document for the client.

    Delegates to services.users.user_to_public so there is exactly one
    doc -> UserPublic mapping. This used to be a second, hand-maintained copy
    of the same field list, and it silently dropped step_order /
    completed_steps / variant_sequence when the multi-variant flow added them —
    which left every routing caller (GET /study/next, require_quiz_access)
    reading an empty flow and bouncing participants back to the dashboard.
    """
    return user_to_public(doc)


def authenticate_identity(request: Request, users) -> dict:
    """Validate the session cookie and return the user's document from ``users``.

    Identity only: no study progress is read or repaired here.
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

    doc = find_user_by_email(users, email)
    if not doc:
        raise HTTPException(status_code=401, detail="User not found")
    return doc


def get_current_user_doc(request: Request) -> dict:
    """Authenticate the request and return the raw user document.

    Also lazily backfills step_order/completed_steps for accounts created before
    the multi-variant flow existed and reconciles older snapshots with saved
    results. Once repaired, neither migration scans the result collections.
    """
    db = request.app.state.db
    users = get_users_collection(db)
    doc = authenticate_identity(request, users)

    from ..services.studies import snapshot_legacy_protocol
    doc = snapshot_legacy_protocol(db, doc)
    maybe_touch_last_active(users, doc)

    return reconcile_saved_progress(db, ensure_user_flow(db, doc))


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

    from ..services.studies import snapshot_legacy_protocol
    doc = snapshot_legacy_protocol(db, doc)
    # Backfill pre-multi-variant accounts at the door rather than on first
    # quiz load, so their first /study/next already reflects the new flow.
    user_pub = build_user_public(reconcile_saved_progress(db, ensure_user_flow(db, doc)))

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
                "consent": True,
                "consent_declined_at": None,
                "consent_agreed_at": now,
                "updated_at": now,
            }
        },
    )

    return {"ok": True}


@router.post("/decline")
def record_consent_decline(
    data: ConsentDeclineRequest,
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
                "consent": False,
                "consent_declined_at": now,
                "updated_at": now,
            }
        },
    )

    return {"ok": True}


@router.post("/consent-viewed")
def record_consent_viewed(
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    """Funnel telemetry (step 5): the participant reached the consent page.

    Records the first-view timestamp and clears any prior ``consent_abandoned_at``
    marker — being back on the page means an earlier "left without deciding"
    signal no longer reflects reality.
    """
    users = get_users_collection(request.app.state.db)
    doc = find_user_by_email(users, user.email)
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.now(timezone.utc)
    set_fields = {"updated_at": now}
    # Keep the earliest view time so it reads as the funnel-entry timestamp.
    if not doc.get("consent_viewed_at"):
        set_fields["consent_viewed_at"] = now
    users.update_one(
        {"_id": doc["_id"]},
        {"$set": set_fields, "$unset": {"consent_abandoned_at": ""}},
    )

    return {"ok": True}


@router.post("/consent-abandoned")
def record_consent_abandoned(
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    """Funnel telemetry (step 6c): the participant left the consent page without
    agreeing or declining (e.g. closed the tab).

    Sent via ``navigator.sendBeacon`` on page unload, so it is best-effort and
    may race the agree/decline write. No-op if a decision was already recorded.
    """
    users = get_users_collection(request.app.state.db)
    doc = find_user_by_email(users, user.email)
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")

    # A decision already exists → this is a stale/racing beacon; ignore it.
    if doc.get("consent_agreed_at") or doc.get("consent_declined_at"):
        return {"ok": True}

    now = datetime.now(timezone.utc)
    users.update_one(
        {"_id": doc["_id"]},
        {"$set": {"consent_abandoned_at": now, "updated_at": now}},
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
