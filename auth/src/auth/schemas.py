from pydantic import BaseModel


class AuthenticatedUser(BaseModel):
    id: int
    token: str
    token_type: str = "bearer"
