# backend/app/api/reports.py
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Query

from ..schemas.report import (
    ReportCreate,
    ReportPublic,
    CommentCreate,
    StatusUpdate,
)
from ..schemas.user import UserPublic
from ..api.auth import get_current_user
from ..services.reports import (
    get_reports_collection,
    ensure_indexes,
    create_report,
    list_reports,
    get_report,
    add_comment,
    update_status,
)

router = APIRouter(prefix="/reports", tags=["reports"])


def require_admin(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.post("", response_model=ReportPublic)
def submit_report(
    data: ReportCreate,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    col = get_reports_collection(request.app.state.db)
    ensure_indexes(col)
    return create_report(col, user, data)


@router.get("", response_model=List[ReportPublic])
def get_reports(
    request: Request,
    status: Optional[str] = Query(default=None),
    user: UserPublic = Depends(get_current_user),
):
    col = get_reports_collection(request.app.state.db)
    ensure_indexes(col)
    user_id = None if user.is_admin else user.id
    return list_reports(col, user_id=user_id, status=status)


@router.get("/{report_id}", response_model=ReportPublic)
def get_single_report(
    report_id: str,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    col = get_reports_collection(request.app.state.db)
    user_id = None if user.is_admin else user.id
    report = get_report(col, report_id, user_id=user_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/{report_id}/comments", response_model=ReportPublic)
def add_report_comment(
    report_id: str,
    data: CommentCreate,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    col = get_reports_collection(request.app.state.db)
    user_id = None if user.is_admin else user.id
    report = add_comment(col, report_id, user, data.body, user_id=user_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.patch("/{report_id}/status", response_model=ReportPublic)
def patch_report_status(
    report_id: str,
    data: StatusUpdate,
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    col = get_reports_collection(request.app.state.db)
    report = update_status(col, report_id, data.status)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report
