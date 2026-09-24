import secrets

from fastapi import FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.shares import router as shares_router
from app.services.storage import storage
from app.services.readiness import dependency_readiness
from app.services.http_metrics import http_metrics, record_http_metrics
from app.core.config import settings

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
app.middleware("http")(record_http_metrics)


@app.middleware("http")
async def security_headers(request, call_next):
    """Apply browser-safe baseline headers without recording request data."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    return response


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


@app.get("/internal/metrics", include_in_schema=False)
def metrics(x_metrics_token: str | None = Header(default=None)):
    """Token-protected, low-cardinality telemetry for internal scraping."""
    token = settings.metrics_token
    if not token or not x_metrics_token or not secrets.compare_digest(x_metrics_token, token):
        raise HTTPException(status_code=404, detail="Not Found")
    return PlainTextResponse(http_metrics.render(), media_type="text/plain; version=0.0.4")
