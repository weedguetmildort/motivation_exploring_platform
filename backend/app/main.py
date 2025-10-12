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

@app.get("/")
def read_root():
    return {"message": "Hello world from FastAPI!"}

@app.get("/health")
def health():
    return {"status": "ok"}

# Mount the chat router
app.include_router(chat_router)