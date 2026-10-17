# backend/app/api/allowlist.py
from typing import List
from fastapi import APIRouter, HTTPException, Request, Depends
from pymongo.errors import DuplicateKeyError

from ..schemas.allowlist import AllowlistCreate, AllowlistPublic
from ..schemas.user import UserPublic
from ..api.auth import get_current_user
from ..services.allowlist import (
    get_allowlist_collection,
    ensure_indexes,
    list_domains,
    add_domain,
    remove_domain,
)

router = APIRouter(prefix="/allowlist", tags=["allowlist"])


def require_admin(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("", response_model=List[AllowlistPublic])
def get_allowlist(
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    col = get_allowlist_collection(request.app.state.db)
    ensure_indexes(col)
    return list_domains(col)


@router.post("", response_model=AllowlistPublic, status_code=201)
def add_to_allowlist(
    data: AllowlistCreate,
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    col = get_allowlist_collection(request.app.state.db)
    ensure_indexes(col)
    try:
        entry = add_domain(col, data.domain, added_by=user.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Domain is already in the allowlist")

    # Update in-memory cache
    if hasattr(request.app.state, "allowlist_cache"):
        request.app.state.allowlist_cache.add(entry.domain)

    return entry


@router.delete("/{domain_id}", response_model=AllowlistPublic)
def remove_from_allowlist(
    domain_id: str,
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    col = get_allowlist_collection(request.app.state.db)
    removed = remove_domain(col, domain_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Domain not found")

    # Update in-memory cache
    if hasattr(request.app.state, "allowlist_cache"):
        request.app.state.allowlist_cache.discard(removed.domain)

    return removed
