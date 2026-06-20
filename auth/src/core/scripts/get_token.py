import asyncio
import sys

from passlib.handlers.pbkdf2 import pbkdf2_sha512
from sqlmodel import select

from src.core.middlewares.authentication_middleware import create_token
from src.core.models import User
from src.core.scripts.db import get_db


async def main():
    try:
        username = sys.argv[1]
        password = sys.argv[2]
    except IndexError:
        raise ValueError("Username or password is missing")

    db_session = next(get_db())
    result = db_session.execute(select(User).where(User.username == username))
    user: User = result.scalar_one_or_none()

    if user is None:
        raise ValueError("Invalid username or password")

    password_matches = pbkdf2_sha512.verify(password, user.hashed_password)
    if not password_matches:
        raise ValueError("Invalid username or password")

    access_token = await create_token(user.id, user.username)

    print("Token: ", access_token)


asyncio.run(main())
