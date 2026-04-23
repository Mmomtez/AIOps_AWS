from fastapi import FastAPI
from backend.api.health import router as health_router
from backend.api.routes import router as api_router

app = FastAPI(
    title="AIOps AWS Backend",
    version="0.1.0",
    description="Backend API for AWS monitoring, anomaly detection, and recommendations.",
)

app.include_router(health_router)
app.include_router(api_router)