# backend/app/api/link_clicks.py
from typing import List, Optional
from fastapi import APIRouter, Request, Depends

from ..schemas.link_click import LinkClickCreate, LinkClickPublic
from ..schemas.user import UserPublic
from ..api.auth import get_current_user
from ..services.link_clicks import (
    get_link_clicks_collection,
    ensure_indexes,
    create_link_click,
    list_link_clicks,
)

router = APIRouter(prefix="/links", tags=["links"])


@router.post("/clicks", response_model=LinkClickPublic)
def record_link_click(
    data: LinkClickCreate,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    col = get_link_clicks_collection(request.app.state.db)
    ensure_indexes(col)
    return create_link_click(col, user, data)


@router.get("/clicks", response_model=List[LinkClickPublic])
def get_link_clicks(
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    col = get_link_clicks_collection(request.app.state.db)
    user_id = None if user.is_admin else user.id
    return list_link_clicks(col, user_id=user_id)
