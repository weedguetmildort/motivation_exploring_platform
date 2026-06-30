# backend/app/api/copy_events.py
from typing import List
from fastapi import APIRouter, Request, Depends

from ..schemas.copy_event import CopyEventCreate, CopyEventPublic
from ..schemas.user import UserPublic
from ..api.auth import get_current_user
from ..services.copy_events import (
    get_copy_events_collection,
    ensure_indexes,
    create_copy_event,
    list_copy_events,
)

router = APIRouter(prefix="/copy-events", tags=["copy-events"])


@router.post("", response_model=CopyEventPublic)
def record_copy_event(
    data: CopyEventCreate,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    col = get_copy_events_collection(request.app.state.db)
    ensure_indexes(col)
    return create_copy_event(col, user, data)


@router.get("", response_model=List[CopyEventPublic])
def get_copy_events(
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    col = get_copy_events_collection(request.app.state.db)
    user_id = None if user.is_admin else user.id
    return list_copy_events(col, user_id=user_id)
