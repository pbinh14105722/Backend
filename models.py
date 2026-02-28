from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, CheckConstraint, Text, DateTime
from sqlalchemy.orm import relationship
from database import Base
import uuid
from datetime import datetime

def generate_uuid():
    """Generate a UUID v4 string"""
    return str(uuid.uuid4())

class Item(Base): #FOLDER / PROJECT
    __tablename__ = "items"

    id = Column(
        String(36), 
        primary_key=True, 
        default=generate_uuid,  # ← TỰ ĐỘNG TẠO UUID KHI INSERT
        index=True
    )
    name = Column(String(255), nullable=False)
    type = Column(
        String(50), 
        nullable=False,
        # Chỉ chấp nhận 2 giá trị: FOLDER hoặc PROJECT
    )
    ###################
    __table_args__ = (
        CheckConstraint("type IN ('FOLDER', 'PROJECT')", name="check_item_type"),
    )
    ####################
    # Hierarchy
    parent_id = Column(
        String(36), 
        ForeignKey("items.id", ondelete="CASCADE"),  # ✅ Xóa cha → xóa con
        nullable=True,
        index=True  # ✅ Index để tăng tốc query
    )
    
    # Display Properties
    position = Column(Integer, default=0, nullable=False)
    color = Column(String(7), default="#ffffff", nullable=False)  # ✅ Format #RRGGBB
    expanded = Column(Boolean, default=False, nullable=False)
    
    # ✅ Owner với CASCADE DELETE
    owner_id = Column(
        Integer, 
        ForeignKey("users.id", ondelete="CASCADE"),  # ← SỬA LỖI Ở ĐÂY
        nullable=False,
        index=True
    )
    
    # Relationships
    owner = relationship("User", back_populates="items")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")

class User(Base): # TÀI KHOẢN NGƯỜI DÙNG
    __tablename__ = "users"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # User Info
    username = Column(String(255), unique=True, nullable=False, index=True)  # ✅ Thêm unique
    email = Column(String(255), unique=True, nullable=False, index=True)  # ✅ Thêm nullable=False
    hashed_password = Column(String(255), nullable=False)  # ✅ Thêm nullable=False
    
    # Relationships
    items = relationship(
        "Item", 
        back_populates="owner", 
        cascade="all, delete-orphan"  # ✅ Tự động xóa items khi xóa user
    )
class Task(Base):  # TASK TRONG PROJECT
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)  # ← Auto-increment integer
    project_id = Column(String(36), ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, default=1, nullable=False)  # ← Bắt đầu từ 1
    name = Column(String(255), nullable=False)
    priority = Column(String(10), default='low', nullable=False)  # ← Mặc định 'low'
    
    # DateTime với timezone
    start_date = Column(DateTime, nullable=False)
    due_date = Column(DateTime, nullable=False)
    
    # Time spent (lưu tổng số giây)
    time_spent_seconds = Column(Integer, default=0)
    
    # Notes
    notes = Column(Text, default="", nullable=False)
    
    project = relationship("Item", back_populates="tasks")
    
    __table_args__ = (
        CheckConstraint("priority IN ('high', 'medium', 'low')", name="check_priority"),
        CheckConstraint("time_spent_seconds >= 0", name="check_time_positive"),
    )

class TaskHistory(Base):
    __tablename__ = "task_history"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    user_id      = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id   = Column(String, nullable=False)
    task_name    = Column(String(255), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=False)

#==============================POMODORO===========================================
class PomodoroSettings(Base):
    __tablename__ = "pomodoro_settings"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id          = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    focus_duration   = Column(Integer, nullable=False, default=1500)
    short_break      = Column(Integer, nullable=False, default=300)
    long_break       = Column(Integer, nullable=False, default=900)
    long_break_after = Column(Integer, nullable=False, default=4)
    disable_break    = Column(Boolean, nullable=False, default=False)
    auto_start_focus = Column(Boolean, nullable=False, default=False)
    auto_start_break = Column(Boolean, nullable=False, default=False)

# class PomodoroSession(Base):
#     __tablename__ = "pomodoro_sessions"

#     id           = Column(Integer, primary_key=True, autoincrement=True)
#     user_id      = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
#     mode         = Column(String(20), nullable=False)
#     duration     = Column(Integer, nullable=False)
#     task_id      = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
#     completed_at = Column(DateTime(timezone=True), nullable=False)

class PomodoroSession(Base):
    __tablename__ = "pomodoro_sessions"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    user_id      = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True) # Thêm index
    mode         = Column(String(20), nullable=False, index=True) # Thêm index (focus/break)
    duration     = Column(Integer, nullable=False)
    task_id      = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    task_name    = Column(String(255), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=False, index=True) # Thêm index để filter theo ngày
