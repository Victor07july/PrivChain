from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    id: int | None = Field(nullable=False, default=None, primary_key=True, index=True)
    email: str = Field(unique=True, nullable=False)
    hashed_password: str | None = Field(nullable=False)
    first_name: str = Field(nullable=True, default=None)
    last_name: str = Field(nullable=True, default=None)
    is_active: bool = Field(nullable=False, default=True)
    is_admin: bool = Field(nullable=False, default=False)
