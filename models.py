from sqlalchemy import Column, String, Integer, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class Item(Base):
    __tablename__ = "items"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String)  # "FOLDER" hoặc "PROJECT"
    parent_id = Column(String, ForeignKey("items.id", ondelete="CASCADE"), nullable=True)
    position = Column(Integer, default=0)
    color = Column(String, default="#ffffff")
    expanded = Column(Boolean, default=False)
    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="items")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    items = relationship("Item", back_populates="owner")
