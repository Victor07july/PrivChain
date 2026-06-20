from fastapi import APIRouter

healthcheck_router = APIRouter()


@healthcheck_router.get("/healthcheck/")
async def healthcheck():
    return {"data": "it's alive!"}
