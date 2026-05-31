from fastapi import FastAPI
from backend.api.health import router as health_router
from backend.api.routes import router as api_router
from backend.api.auth import router as auth_router
from backend.api.user_profile import router as user_profile_router
from backend.api.users import router as users_router
from backend.api.instances import router as instances_router

app = FastAPI(
    title="AIOps AWS Backend",
    version="0.1.0",
    description="Backend API for AWS monitoring, anomaly detection, and recommendations.",
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(user_profile_router)
app.include_router(users_router)
app.include_router(instances_router)
app.include_router(api_router)