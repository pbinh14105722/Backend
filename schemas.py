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

# ============ TASK SCHEMAS ============
class TaskBase(BaseModel):
    name: str
    priority: str = 'medium'
    position: int = 0
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    time_spent_minutes: int = 0

class TaskCreate(BaseModel):
    """Tạo task - Backend tự tạo name nếu không có"""
    name: Optional[str] = None
    priority: str = 'medium'
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    time_spent_minutes: int = 0

class TaskUpdate(BaseModel):
    """PATCH - chỉ update các field được gửi"""
    name: Optional[str] = None
    priority: Optional[str] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    
    @field_validator('priority')
    @classmethod
    def validate_priority(cls, v):
        if v and v not in ['high', 'medium', 'low']:
            raise ValueError("Priority must be 'high', 'medium', or 'low'")
        return v

class TaskBatchUpdate(BaseModel):
    """PUT toàn bộ project - dùng cho kéo thả"""
    id: str
    name: str
    priority: str
    position: int
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    time_spent_minutes: int = 0

class TaskResponse(BaseModel):
    id: str
    name: str
    priority: str
    position: int
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    time_spent: str
    project_id: str
    
    class Config:
        from_attributes = True
