# backend/app/schemas/auth.py
from pydantic import BaseModel, EmailStr, Field
from .user import UserPublic


# Payload sent by the client when creating a new account.
class SignupRequest(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=6)
    consent: bool  # must be True to complete registration


# Payload sent by the client when logging in.
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# Returned after successful login or signup; contains the full public user profile.
class AuthResponse(BaseModel):
    user: UserPublic


# Payload sent by the client to update their password.
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


# Payload sent by the client when the user clicks "I agree to participate" on
# the consent page. Captures the exact text shown at that moment so the
# research team can see what wording a participant agreed to even if the
# consent form is edited later.
class ConsentAgreementRequest(BaseModel):
    consent_text: str = Field(min_length=1)
