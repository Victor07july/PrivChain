from src.core.exceptions import UserNotFoundException
from fastapi import Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config.database.setup import get_db_session
from src.core.models import User
from src.core.repositories.users.user_base_repository import UserBaseRepository


class UserSQLAlchemyRepository(UserBaseRepository):
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def get_users(self) -> list[User]:
        result = await self.db_session.execute(select(User))
        users: list[User] = result.scalars().all()
        return users

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db_session.execute(
            select(User).where(User.email == email)
        )
        user: User = result.scalars().one_or_none()
        return user

    async def add_user(self, email: str, hashed_password: str):
        user = User(email=email, hashed_password=hashed_password)
        self.db_session.add(user)
        await self.db_session.commit()
        await self.db_session.refresh(user)
        return user
    
    async def update_user(self, email: str, first_name: str, last_name: str, is_active: bool, is_admin) -> User:

        user = await self.get_user_by_email(email)
        if user is None:
            raise UserNotFoundException()

        user.first_name = first_name if first_name is not None else user.first_name
        user.last_name = last_name if last_name is not None else user.last_name
        user.is_active = is_active if is_active is not None else user.is_active
        user.is_admin = is_admin if is_admin is not None else user.is_admin
        self.db_session.add(user)
        await self.db_session.commit()
        await self.db_session.refresh(user)
        return user

def get_user_repository(
    db_session: AsyncSession = Depends(get_db_session),
) -> UserBaseRepository:
    return UserSQLAlchemyRepository(db_session)
