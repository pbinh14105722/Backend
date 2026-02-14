from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from database import Base
import uuid

def generate_uuid():
    """Generate a UUID v4 string"""
    return str(uuid.uuid4())

class Item(Base):
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

class User(Base):
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
