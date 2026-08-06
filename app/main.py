from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app import config, security
from app.database import Base, engine
from app.routers import actions, approvals, permits, registry

security.ensure_keypair()
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="MetricTrust Control Plane",
    description="Evidence-bound execution control for autonomous product-analytics agents.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

app.include_router(actions.router)
app.include_router(approvals.router)
app.include_router(permits.router)
app.include_router(registry.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics_endpoint():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


FRONTEND_DIR = config.BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def dashboard():
        return FileResponse(str(FRONTEND_DIR / "index.html"))
