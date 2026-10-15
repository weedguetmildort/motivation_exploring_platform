"""Resolve explicit /studies/{id}/... API routes without shared mutable state."""
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from ..services.studies import StudyDatabase, STUDY_IDS, check_access


class StudyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        parts = path.split("/", 3)
        if len(parts) < 3 or parts[1] != "studies" or parts[2] in ("catalog", "participants"):
            return await self.app(scope, receive, send)
        sid = parts[2]
        if sid not in STUDY_IDS:
            return await JSONResponse({"detail": "Unknown study"}, status_code=404)(scope, receive, send)
        app = scope["app"]
        raw = getattr(app.state, "raw_db", None)
        if raw is None:
            return await JSONResponse({"detail": "Study storage unavailable"}, status_code=503)(scope, receive, send)
        from ..api.auth import get_current_user_doc
        from starlette.requests import Request
        from fastapi import HTTPException
        # Authenticate against the global identity/Study 1 before selecting progress.
        try:
            user = await run_in_threadpool(get_current_user_doc, Request(scope, receive))
            await run_in_threadpool(check_access, raw, user, sid)
            if sid == "study-2" and user.get("is_admin"):
                from ..services.studies import ensure_admin_preview
                await run_in_threadpool(ensure_admin_preview, raw, user)
            inner_path = "/" + (parts[3] if len(parts) > 3 else "")
            if sid == "study-2" and not user.get("is_admin") and inner_path.startswith(("/quiz/", "/surveys/", "/chat/", "/research/events")):
                enrollment = await run_in_threadpool(raw["study_enrollments"].find_one, {"_id": user["_id"]})
                if not (enrollment or {}).get("consent_agreed_at") or (enrollment or {}).get("consent_declined_at"):
                    raise HTTPException(403, "Study 2 consent is required")
        except HTTPException as exc:
            return await JSONResponse({"detail": exc.detail}, status_code=exc.status_code)(scope, receive, send)
        class RequestApp:
            def __getattr__(self, name):
                return getattr(app, name)
        class RequestState:
            def __init__(self):
                object.__setattr__(self, "db", StudyDatabase(raw, sid))
                object.__setattr__(self, "messages", self.db["messages"])
                object.__setattr__(self, "study_id", sid)

            def __getattr__(self, name):
                return getattr(app.state, name)

            def __setattr__(self, name, value):
                if name in ("db", "messages", "study_id"):
                    object.__setattr__(self, name, value)
                else:
                    setattr(app.state, name, value)
        scoped_app = RequestApp()
        scoped_app.state = RequestState()
        scoped = {**scope, "app": scoped_app, "path": inner_path,
                  "raw_path": inner_path.encode(), "study_id": sid}
        return await self.app(scoped, receive, send)
