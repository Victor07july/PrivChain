from http import HTTPStatus
from typing import Annotated

from fastapi import Depends, APIRouter, Header
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext

from src.core.middlewares.authentication_middleware import check_is_admin
from src.core.repositories.users import UserBaseRepository, get_user_repository
from src.users.schemas import PostUser, ListUser, PutUserRequest
from src.users.service import (
    get_users,
    create_user,
    update_user,
)

users_v1_router = APIRouter(prefix="/v1/users")
context = CryptContext(
    schemes=["sha512_crypt"], deprecated="auto", default="sha512_crypt"
)


@users_v1_router.get("/", response_model=list[ListUser])
async def list_users(
    authorization: Annotated[str | None, Header()] = None,
    user_repo: UserBaseRepository = Depends(get_user_repository),
):
    is_admin = await check_is_admin(authorization, user_repo)

    if is_admin:
        return await get_users(user_repo)
    return None


@users_v1_router.post(
    "/",
    response_model=PostUser,
    status_code=HTTPStatus.CREATED,
)
async def post_user(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    authorization: Annotated[str | None, Header()] = None,
    user_repo: UserBaseRepository = Depends(get_user_repository),
):
    is_admin = await check_is_admin(authorization, user_repo)

    if is_admin:
        user = await create_user(
            email=form_data.username,
            password=form_data.password,
            user_repo=user_repo,
        )
        return user
    return None


@users_v1_router.put(
    "/",
    status_code=HTTPStatus.OK,
)
async def put_user(
    user: PutUserRequest,
    authorization: Annotated[str | None, Header()] = None,
    user_repo: UserBaseRepository = Depends(get_user_repository),
):
    is_admin = await check_is_admin(authorization, user_repo)

    if is_admin:
        await update_user(
            new_user_data=user,
            user_repo=user_repo,
        )
    return {"details": "User updated successfully"}
    
