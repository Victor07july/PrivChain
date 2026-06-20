from datetime import datetime, timedelta, timezone

from src.core.repositories.users.user_base_repository import UserBaseRepository
from src.core.exceptions import Forbidden, Unauthorized, UnauthorizedByExpiredSignature
from dotenv import load_dotenv
from jose import JWTError, jwt, ExpiredSignatureError
from os import getenv
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext

from src.core.models import User

load_dotenv("src/config/.env")

JWT_SECRET = getenv("JWT_SECRET")
JWT_ALGORITHM = getenv("JWT_ALGORITHM")
JWT_EXPIRATION_DAYS = getenv("JWT_EXPIRATION_DAYS")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

context = CryptContext(
    schemes=["sha512_crypt"], deprecated="auto", default="sha512_crypt"
)



async def validate_token(access_token: str = Depends(oauth2_scheme)) -> User:
    try:
        payload = jwt.decode(access_token, key=JWT_SECRET, algorithms=[JWT_ALGORITHM])

        return User(
            id=payload["user_id"],
            email=payload["email"],
        )
    except ExpiredSignatureError:
        raise UnauthorizedByExpiredSignature()
    except JWTError:
        raise Unauthorized()
    

async def create_token(user_id: int, username: str):
    expire = datetime.now(timezone.utc) + timedelta(days=int(JWT_EXPIRATION_DAYS))
    access_token = jwt.encode(
        {
            "user_id": user_id,
            "email": username,
            "exp": expire,
            "iat": datetime.now(timezone.utc).timestamp(),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    return access_token


async def check_authorization(authorization: str) -> bool:
    if authorization is None:
        raise Unauthorized()

    token = authorization.split()[1]
    await validate_token(token)

    return True


async def check_is_admin(authorization: str, user_repo: UserBaseRepository) -> bool:
    if authorization is None:
        raise Unauthorized()

    token = authorization.split()[1]
    token_user = await validate_token(token)
    user = await user_repo.get_user_by_email(token_user.email)
    print("USUARIO DE TESTE: ", user)
    if user.is_admin is False or user.is_active is False:
        raise Forbidden()

    return user.is_admin