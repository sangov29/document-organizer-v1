from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.services.storage import storage

app = FastAPI(title="Intelligent Personal Document Organizer", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")


@app.on_event("startup")
def startup():
    storage.ensure_bucket()


@app.get("/health")
def health():
    return {"status": "ok"}
