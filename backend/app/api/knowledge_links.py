from typing import List
from fastapi import APIRouter, HTTPException, Request, Depends

from ..schemas.knowledge_link import (
    KnowledgeLinkCreate,
    KnowledgeLinkUpdate,
    KnowledgeLinkPublic,
)
from ..schemas.user import UserPublic
from ..api.auth import get_current_user
from ..services.knowledge_links import (
    get_knowledge_links_collection,
    ensure_indexes,
    create_knowledge_link,
    list_knowledge_links,
    update_knowledge_link,
    delete_knowledge_link,
)

router = APIRouter(prefix="/knowledge-links", tags=["knowledge-links"])

def require_admin(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

@router.get("", response_model=List[KnowledgeLinkPublic])
def get_all_knowledge_links(
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    links = get_knowledge_links_collection(request.app.state.db)
    ensure_indexes(links)
    return list_knowledge_links(links)

@router.post("", response_model=KnowledgeLinkPublic)
def create_new_knowledge_link(
    data: KnowledgeLinkCreate,
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    links = get_knowledge_links_collection(request.app.state.db)
    ensure_indexes(links)
    created = create_knowledge_link(links, data)
    if created.active:
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

    request.app.state.knowledge_links = [
        l for l in request.app.state.knowledge_links if l["id"] != link_id
    ]
    if updated.active:
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