import os
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ServerSelectionTimeoutError
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.chat import router as chat_router
from .api.auth import router as auth_router
from .api.knowledge_links import router as knowledge_links_router
from .api.allowlist import router as allowlist_router
from .api import questions as questions_router
from .api import quiz as quiz_router
from .api import demographics as demographics_router
from .api import surveys as surveys_router

from .core.config import get_settings

app = FastAPI()
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB", "mep_dev")

@app.on_event("startup")
def _startup():
    try:
        client = MongoClient(
            MONGO_URL,
            serverSelectionTimeoutMS=5000,
            appname="mep-backend",
            retryWrites=True,
        )

        client.admin.command("ping")

        db = client[MONGO_DB]
        messages = db["messages"]
        messages.create_index([("conversation_id", ASCENDING)])
        messages.create_index([("created_at", ASCENDING)])

        from .services.users import get_users_collection, ensure_indexes
        ensure_indexes(get_users_collection(db))

        from .services.surveys import ensure_survey_indexes
        ensure_survey_indexes(db)

        from .services.knowledge_links import (
            get_knowledge_links_collection,
            ensure_indexes as ensure_links_indexes,
            reload_knowledge_links_cache,
        )
        links_col = get_knowledge_links_collection(db)
        ensure_links_indexes(links_col)

        # One-time idempotent migration: backfill status from active field
        missing = links_col.count_documents({"status": {"$exists": False}})
        if missing > 0:
            print(f"[startup] Migrating {missing} link(s) to status field")
            links_col.update_many(
                {"status": {"$exists": False}, "active": True},
                {"$set": {"status": "READY"}},
            )
            links_col.update_many(
                {"status": {"$exists": False}, "active": False},
                {"$set": {"status": "NOT_READY"}},
            )
            # Catch any remaining documents without an active field
            links_col.update_many(
                {"status": {"$exists": False}},
                {"$set": {"status": "READY"}},
            )

        # Load allowlist collection and cache
        from .services.allowlist import (
            get_allowlist_collection,
            ensure_indexes as ensure_allowlist_indexes,
            load_allowlist_cache,
        )
        allowlist_col = get_allowlist_collection(db)
        ensure_allowlist_indexes(allowlist_col)

        app.state.mongo_client = client
        app.state.db = db
        app.state.messages = messages
        app.state.settings = settings

        # Chat cache: only READY links are surfaced to the chatbot
        app.state.knowledge_links = reload_knowledge_links_cache(links_col)
        app.state.allowlist_cache = load_allowlist_cache(allowlist_col)

        # Start background scheduler (last, after all caches are ready)
        from .scheduler import start_scheduler
        start_scheduler(app)

    except ServerSelectionTimeoutError as e:
        print(f"[startup] Mongo connection failed: {e}")
        raise


@app.on_event("shutdown")
def _shutdown():
    from .scheduler import stop_scheduler
    stop_scheduler()

    client = getattr(app.state, "mongo_client", None)
    if client:
        client.close()


@app.get("/")
def read_root():
    return {"message": "Hello world from FastAPI!"}


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(knowledge_links_router)
app.include_router(allowlist_router)
app.include_router(questions_router.router)
app.include_router(quiz_router.router)
app.include_router(demographics_router.router)
app.include_router(surveys_router.router)
