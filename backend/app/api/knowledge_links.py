# backend/app/api/knowledge_links.py
import os
import threading
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from openai import OpenAI

from ..schemas.knowledge_link import (
    KnowledgeLinkCreate,
    KnowledgeLinkUpdate,
    KnowledgeLinkPublic,
    ExplorePreview,
    ExploreApply,
)
from ..schemas.user import UserPublic
from ..api.auth import get_current_user
from ..services.knowledge_links import (
    get_knowledge_links_collection,
    ensure_indexes,
    create_knowledge_link,
    list_knowledge_links_by_status,
    update_knowledge_link,
    delete_knowledge_link,
    approve_link,
    reject_link,
    explore_link,
    apply_explore,
)

router = APIRouter(prefix="/knowledge-links", tags=["knowledge-links"])


def require_admin(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── Literal-path routes MUST come before /{link_id} ─────────────────────────

@router.post("/trigger-health-check")
def trigger_health_check(
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    """Fire-and-forget: runs health check then discovery in a background thread."""
    from ..scheduler import run_jobs_now

    t = threading.Thread(target=run_jobs_now, args=[request.app], daemon=True)
    t.start()
    return {"ok": True, "message": "Health check triggered. Refresh in a moment to see results."}


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[KnowledgeLinkPublic])
def get_all_knowledge_links(
    request: Request,
    status: Optional[str] = Query(default=None),
    user: UserPublic = Depends(require_admin),
):
    links = get_knowledge_links_collection(request.app.state.db)
    ensure_indexes(links)
    return list_knowledge_links_by_status(links, status)


@router.post("", response_model=KnowledgeLinkPublic)
def create_new_knowledge_link(
    data: KnowledgeLinkCreate,
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    links = get_knowledge_links_collection(request.app.state.db)
    ensure_indexes(links)
    created = create_knowledge_link(links, data)
    # Admin-created links are READY — add to chatbot cache immediately
    if created.status.value == "READY":
        request.app.state.knowledge_links.append({
            "id": created.id,
            "title": created.title,
            "url": str(created.url),
            "description": created.description,
        })
    return created


@router.put("/{link_id}", response_model=KnowledgeLinkPublic)
def update_existing_knowledge_link(
    link_id: str,
    data: KnowledgeLinkUpdate,
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    links = get_knowledge_links_collection(request.app.state.db)
    ensure_indexes(links)
    updated = update_knowledge_link(links, link_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Knowledge link not found")

    # Refresh cache entry
    request.app.state.knowledge_links = [
        l for l in request.app.state.knowledge_links if l["id"] != link_id
    ]
    if updated.status.value == "READY":
        request.app.state.knowledge_links.append({
            "id": updated.id,
            "title": updated.title,
            "url": str(updated.url),
            "description": updated.description,
        })
    return updated


@router.delete("/{link_id}", response_model=KnowledgeLinkPublic)
def delete_existing_knowledge_link(
    link_id: str,
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    links = get_knowledge_links_collection(request.app.state.db)
    ensure_indexes(links)
    deleted = delete_knowledge_link(links, link_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge link not found")
    request.app.state.knowledge_links = [
        l for l in request.app.state.knowledge_links if l["id"] != link_id
    ]
    return deleted


# ── Approve / Reject ─────────────────────────────────────────────────────────

@router.post("/{link_id}/approve", response_model=KnowledgeLinkPublic)
def approve_knowledge_link(
    link_id: str,
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    links = get_knowledge_links_collection(request.app.state.db)
    result = approve_link(links, link_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Link not found or not in NEEDS_REVIEW state",
        )
    request.app.state.knowledge_links.append({
        "id": result.id,
        "title": result.title,
        "url": str(result.url),
        "description": result.description,
    })
    return result


@router.post("/{link_id}/explore", response_model=ExplorePreview)
def explore_knowledge_link(
    link_id: str,
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    """Fetch the live page and return a preview (proposed title, description, article
    excerpt, and relevance verdict) WITHOUT saving anything. The admin reviews and
    calls /explore/apply to commit."""
    links = get_knowledge_links_collection(request.app.state.db)
    openai_client = OpenAI(
        api_key=os.getenv("UF_OPENAI_API_KEY"),
        base_url=os.getenv("UF_OPENAI_BASE_URL", "https://api.ai.it.ufl.edu"),
    )
    result = explore_link(
        links,
        link_id,
        openai_client,
        request.app.state.allowlist_cache,
        timeout=request.app.state.settings.LINK_REQUEST_TIMEOUT,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Link not found or is tombstoned")
    return result


@router.post("/{link_id}/explore/apply", response_model=KnowledgeLinkPublic)
def apply_explore_knowledge_link(
    link_id: str,
    data: ExploreApply,
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    """Save the admin-confirmed title/description, re-run the relevance judge, and
    return the updated link state."""
    links = get_knowledge_links_collection(request.app.state.db)
    openai_client = OpenAI(
        api_key=os.getenv("UF_OPENAI_API_KEY"),
        base_url=os.getenv("UF_OPENAI_BASE_URL", "https://api.ai.it.ufl.edu"),
    )
    result = apply_explore(
        links,
        link_id,
        data.title,
        data.description,
        openai_client,
        request.app.state.allowlist_cache,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Link not found or is tombstoned")

    request.app.state.knowledge_links = [
        l for l in request.app.state.knowledge_links if l["id"] != link_id
    ]
    if result.status.value == "READY":
        request.app.state.knowledge_links.append({
            "id": result.id,
            "title": result.title,
            "url": str(result.url),
            "description": result.description,
        })
    return result


@router.post("/{link_id}/reject", response_model=KnowledgeLinkPublic)
def reject_knowledge_link(
    link_id: str,
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    links = get_knowledge_links_collection(request.app.state.db)
    result = reject_link(links, link_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Link not found or not in a rejectable state (NEEDS_REVIEW or NOT_READY)",
        )
    request.app.state.knowledge_links = [
        l for l in request.app.state.knowledge_links if l["id"] != link_id
    ]
    return result
