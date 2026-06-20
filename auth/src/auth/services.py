from src.auth.exceptions import IncorrectEmailOrPassword
from src.auth.schemas import AuthenticatedUser
from src.core.exceptions import InvalidEmail
from src.core.middlewares.authentication_middleware import create_token
from src.core.middlewares.email_validator import validate_email
from src.core.middlewares.password_validator import validate_password
from src.core.models import User
from src.core.repositories.users import UserBaseRepository
from src.users.service import get_user_by_email, create_user
from passlib.hash import pbkdf2_sha512


async def signin_user(
    email: str, password: str, user_repo: UserBaseRepository
) -> AuthenticatedUser:
    registered_user: User = await get_user_by_email(email, user_repo)

    if registered_user is None:
        raise IncorrectEmailOrPassword()

    password_matches = pbkdf2_sha512.verify(password, registered_user.hashed_password)
    if not password_matches:
        raise IncorrectEmailOrPassword()

    access_token = await create_token(registered_user.id, registered_user.email)

    auth_user = AuthenticatedUser(
        id=registered_user.id,
        token=access_token,
    )
    return auth_user


async def signup_user(
    email: str, password: str, user_repo: UserBaseRepository
) -> AuthenticatedUser:
    validate_email(email)
    validate_password(password)

    registered_user: User = await get_user_by_email(email, user_repo)

    if registered_user is not None:
        raise InvalidEmail()

    new_user = await create_user(email, password, user_repo)
    access_token = await create_token(new_user.id, new_user.email)
    auth_user = AuthenticatedUser(
        id=new_user.id,
        token=access_token,
    )
    return auth_user
