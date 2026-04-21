"""
Shared dependencies and helper functions used across multiple routers
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from datetime import datetime, timezone

import models
import database
from utils import SECRET_KEY, ALGORITHM


def format_datetime_iso(dt: datetime) -> str:
    """Convert datetime sang ISO 8601 chuẩn với timezone suffix 'Z'"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    iso_str = dt.isoformat()
    if iso_str.endswith('+00:00'):
        return iso_str.replace('+00:00', 'Z')
    return iso_str

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def get_current_user(db: Session = Depends(database.get_db), token: str = Depends(oauth2_scheme)):
    """
    Validate JWT token and return current user object from database
    
    Args:
        db: Database session
        token: JWT token from Authorization header
        
    Returns:
        User object from database
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Không thể xác thực thông tin",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Decode token to get email (sub)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Query user from database
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception
        
    return user


def get_user_from_token(db: Session, email: str):
    """
    Helper function to get User object from email (legacy, consider removing)
    
    Args:
        db: Database session
        email: User email address
        
    Returns:
        User object
        
    Raises:
        HTTPException: If user not found
    """
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User không tồn tại")
    return user


def verify_project_owner(project_id: str, user_id: int, db: Session):
    """
    Verify that a project belongs to the specified user
    
    Args:
        project_id: ID of the project to verify
        user_id: ID of the user to check ownership
        db: Database session
        
    Returns:
        The project Item object
        
    Raises:
        HTTPException: If project not found or user is not the owner
    """
    project = db.query(models.Item).filter(
        models.Item.id == project_id,
        models.Item.type == 'PROJECT',
        models.Item.owner_id == user_id
    ).first()
    
    if not project:
        raise HTTPException(
            status_code=404, 
            detail="Project không tồn tại hoặc bạn không có quyền truy cập"
        )
    
    return project


def format_task_response(task: models.Task) -> dict:
    """
    Format Task model to response dictionary with proper field names.
    Datetime fields are serialized to ISO 8601 with 'Z' suffix.
    
    Args:
        task: Task model object from database
        
    Returns:
        Dictionary with formatted task data
    """
    return {
        "id": task.id,
        "position": task.position,
        "name": task.name,
        "priority": task.priority,
        "start_date": format_datetime_iso(task.start_date),
        "due_date": format_datetime_iso(task.due_date),
        "time_spent": task.time_spent_seconds,
        "notes": task.notes,
        "progress": task.progress or 0
    }
