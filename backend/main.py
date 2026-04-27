from fastapi import FastAPI
from backend.api.health import router as health_router
from backend.api.routes import router as api_router
from backend.api.auth import router as auth_router

app = FastAPI(
    title="AIOps AWS Backend",
    version="1.0.0",
    description="Autonomous AIOps backend for AWS monitoring and anomaly detection",
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(api_router)