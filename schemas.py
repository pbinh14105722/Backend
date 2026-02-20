from pydantic import BaseModel, EmailStr,Field, field_validator
from typing import Optional, List
import uuid
from datetime import datetime

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

# ============ TASK SCHEMAS (MỚI) ============

class TaskCreate(BaseModel):
    """Tạo task - Tất cả fields đều optional, backend tự điền mặc định"""
    pass

class TaskUpdate(BaseModel):
    """PATCH - chỉ update các field được gửi"""
    name: Optional[str] = None
    priority: Optional[str] = None
    start_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    time_spent: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = None
    
    @field_validator('priority')
    @classmethod
    def validate_priority(cls, v):
        if v and v not in ['high', 'medium', 'low']:
            raise ValueError("Priority must be 'high', 'medium', or 'low'")
        return v

class TaskReorderItem(BaseModel):
    """Reorder - chỉ cần id và position"""
    id: int
    position: int

class TaskResponse(BaseModel):
    """Response trả về frontend"""
    id: int
    position: int
    name: str
    priority: str
    start_date: str  # ISO 8601: "2026-02-10T00:00:00.000Z"
    due_date: str    # ISO 8601: "2026-02-11T23:59:59.999Z"
    time_spent: int  
    notes: str
    
    class Config:
        from_attributes = True
