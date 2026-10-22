from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import initialize_database
from app.routers import approvals, audit, auth, availability, chat, meetings


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


settings = get_settings()
app = FastAPI(title="AI Booking & Calendar Agent Security Lab", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)
for route_module in (auth, meetings, approvals, chat, audit, availability):
    app.include_router(route_module.router)


@app.get("/api/health")
def health():
    configured = settings.llm_configured
    return {
        "status": "ok",
        "lab_mode": settings.lab_mode,
        "chat_mode": "openai-compatible" if configured else "local",
        "external_llm": "configured" if configured else "disabled",
        "llm_configured": configured,
    }
