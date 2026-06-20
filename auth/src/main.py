import json
from os import getenv

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.core.api import api_router
from src.core.middlewares.exceptions_handler import error_handler_middleware
from src.config.database.setup import get_db_session
from src.config.web3.setup import get_web3_client

app = FastAPI()


@app.exception_handler(HTTPException)
async def validation_exception_handler(request, e):
    return await error_handler_middleware(request, e)


origins = json.loads(getenv("CORS_ORIGINS"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(
    api_router,
    dependencies=[
        Depends(get_db_session),
        Depends(get_web3_client)
    ],
)
