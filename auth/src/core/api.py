from fastapi import APIRouter

from src.besu.v1.routes import besu_v1_router
from src.auth.v1.routes import auth_v1_router
from src.core.healthcheck import healthcheck_router
from src.users.v1.routes import users_v1_router

api_router = APIRouter(prefix="/api")

api_router.include_router(healthcheck_router)
api_router.include_router(auth_v1_router)
api_router.include_router(users_v1_router)
api_router.include_router(besu_v1_router)
