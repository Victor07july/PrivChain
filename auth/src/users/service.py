from src.core.exceptions import InvalidEmail, Unauthorized
from src.core.middlewares.authentication_middleware import validate_token
from src.core.middlewares.email_validator import validate_email
from src.core.middlewares.password_validator import validate_password
from src.core.models import User
from src.users.schemas import ListUser, PutUserRequest
from passlib.hash import pbkdf2_sha512

from src.core.repositories.users.user_base_repository import UserBaseRepository


async def get_users(user_repo: UserBaseRepository) -> list[User]:
    users: list[User] = await user_repo.get_users()
    result: list[ListUser] = []
    for user in users:
        result.append({
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_active': user.is_active
        })

    return result


async def get_user_by_email(
    email: str, user_repo: UserBaseRepository
) -> User | None:
    user: User = await user_repo.get_user_by_email(email)
    return user


async def create_user(
    email: str,
    password: str,
    user_repo: UserBaseRepository,
) -> User:
    validate_email(email)
    validate_password(password)
    user = await user_repo.get_user_by_email(email)
    if user is not None:
        raise InvalidEmail()

    hashed_password = pbkdf2_sha512.hash(password)
    return await user_repo.add_user(email=email, hashed_password=hashed_password)


async def update_user(
    new_user_data: PutUserRequest,
    user_repo: UserBaseRepository,
) -> User | None:
    validate_email(new_user_data.email)
    user = await user_repo.update_user(new_user_data.email, new_user_data.first_name, new_user_data.last_name, new_user_data.is_active, new_user_data.is_admin)
    return user