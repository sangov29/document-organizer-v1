from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.shares import router as shares_router
from app.services.storage import storage
from app.services.readiness import dependency_readiness

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
app.include_router(shares_router, prefix="/api/v1")


@app.on_event("startup")
def startup():
    storage.ensure_bucket()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/live")
def liveness():
    """Process-only probe; dependency failures must not trigger a restart loop."""
    return {"status": "alive"}


@app.get("/health/ready")
def readiness(response: Response):
    """Traffic-readiness probe with sanitized dependency state."""
    dependencies = dependency_readiness()
    ready = all(value == "ok" for value in dependencies.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready else "not_ready",
        "dependencies": dependencies,
    }
