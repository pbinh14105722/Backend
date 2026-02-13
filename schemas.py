from pydantic import BaseModel, EmailStr
from typing import Optional, List

class ItemBase(BaseModel):
    id: str
    name: str
    type: str
    parent_id: Optional[str] = None
    position: int = 0
    color: str = "#ffffff"
    expanded: bool = False

class ItemCreate(ItemBase):
    pass

class ItemBatchUpdate(BaseModel):
    id: str
    parent_id: Optional[str] = None
    position: int

class ItemUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    expanded: Optional[bool] = None
    parent_id: Optional[str] = None
    position: Optional[int] = None

class ItemResponse(ItemBase):
    class Config:
        from_attributes = True

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
