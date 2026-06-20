from pydantic import BaseModel


class PostUser(BaseModel):
    id: int
    email: str


class ListUser(BaseModel):
    id: int
    email: str
    first_name: str | None
    last_name: str | None
    is_active: bool

class PutUserRequest(BaseModel):
    email: str
    first_name: str | None = None
    last_name: str | None = None
    is_active: bool | None = None
    is_admin: bool | None = None

class PutUserResponse(BaseModel):
    details: str