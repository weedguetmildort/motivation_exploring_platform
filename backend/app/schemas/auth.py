from pydantic import BaseModel, EmailStr, Field
from .user import UserPublic

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    user: UserPublic
