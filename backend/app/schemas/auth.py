from pydantic import BaseModel

from app.schemas.common import UserOut


class LoginRequest(BaseModel):
    username: str
    password: str


class SessionOut(BaseModel):
    success: bool = True
    user: UserOut
