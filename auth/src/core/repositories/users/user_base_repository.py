from abc import ABC, abstractmethod
from typing import Optional, List
from src.core.models import User


class UserBaseRepository(ABC):
    @abstractmethod
    async def get_users(self) -> List[User]:
        pass

    @abstractmethod
    async def get_user_by_email(self, email: str) -> Optional[User]:
        pass

    @abstractmethod
    async def add_user(self, email: str, hashed_password: str) -> User:
        pass

    @abstractmethod
    async def update_user(self, email: str, first_name: str, last_name: str, is_active: bool, is_admin) -> User:
        pass