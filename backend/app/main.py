import os

from pymongo import MongoClient, ASCENDING
from pymongo.errors import ServerSelectionTimeoutError
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.chat import router as chat_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://mep-frontend.herokuapp.com",
        ],
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
        # messages collection: each doc = one message (user or assistant)
        messages = db["messages"]
        # helpful indexes
        messages.create_index([("conversation_id", ASCENDING)])
        messages.create_index([("created_at", ASCENDING)])
        app.state.mongo_client = client
        app.state.db = db
        app.state.messages = messages

    except ServerSelectionTimeoutError as e:
        # Optional: log & re-raise to crash on bad config in prod
        print(f"[startup] Mongo connection failed: {e}")
        raise

@app.on_event("shutdown")
def _shutdown():
    client = getattr(app.state, "mongo_client", None)
    if client:
        client.close()

@app.get("/")
def read_root():
    return {"message": "Hello world from FastAPI!"}

@app.get("/health")
def health():
    return {"status": "ok"}

# Mount the chat router
app.include_router(chat_router)