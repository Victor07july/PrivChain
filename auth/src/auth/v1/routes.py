from typing import Annotated

from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Depends, APIRouter

from src.auth.services import signin_user, signup_user
from src.core.repositories.users import UserBaseRepository, get_user_repository

auth_v1_router = APIRouter(prefix="/v1/auth")


@auth_v1_router.post("/signin/")
async def signin(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    user_repo: UserBaseRepository = Depends(get_user_repository),
):
    return await signin_user(form_data.username, form_data.password, user_repo)


@auth_v1_router.post("/signup/", status_code=201)
async def signup(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    user_repo: UserBaseRepository = Depends(get_user_repository),
):
    return await signup_user(form_data.username, form_data.password, user_repo)
