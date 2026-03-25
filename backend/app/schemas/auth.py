# backend/app/schemas/auth.py
from pydantic import BaseModel, EmailStr, Field
from .user import UserPublic

class SignupRequest(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=6)
    consent: bool

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    user: UserPublic

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)