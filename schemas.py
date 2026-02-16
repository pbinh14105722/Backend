from pydantic import BaseModel, EmailStr,Field, field_validator
from typing import Optional, List
import uuid
from datetime import date

# ============ ITEM SCHEMAS (FOLDER/PROJECT) ============
class ItemBase(BaseModel):
    name: str
    type: str
    parent_id: Optional[str] = None
    position: int = 0
    color: str =  "#ffffff"
    expanded: bool = False

class ItemCreate(ItemBase):
    pass

class ItemBatchUpdate(ItemBase):
    id: str
    name: str
    type: str
    parent_id: Optional[str] = None
    position: int
    color: str = "#ffffff"
    expanded: bool = False

class ItemUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    expanded: Optional[bool] = None
    parent_id: Optional[str] = None
    position: Optional[int] = None

class ItemResponse(ItemBase):
    id: str
    name: str
    type: str
    parent_id: Optional[str] = None
    position: int
    color: str
    expanded: bool
    owner_id: int  # Frontend cần biết owner

    class Config:
        from_attributes = True

# ============ USER SCHEMAS ============
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    class Config:
        from_attributes = True

class AuthResponse(BaseModel):
    message: str
    access_token: str
    token_type: str
    # Bạn có thể thêm trường user nếu muốn frontend hiển thị tên người dùng
    # username: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str
