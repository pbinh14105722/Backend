"""
Authentication endpoints: Signup and Login
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
import utils
import database

router = APIRouter(tags=["Authentication"])


@router.post("/signup", response_model=schemas.AuthResponse)
def signup(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    """
    Register a new user account
    
    Args:
        user: User registration data (username, email, password)
        db: Database session
        
    Returns:
        Authentication response with access token
        
    Raises:
        HTTPException: If email already exists
    """
    # 1. Check if email already exists
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email đã được đăng ký!")
    
    # 2. Hash password and save user
    new_user = models.User(
        username=user.username,
        email=user.email, 
        hashed_password=utils.hash_password(user.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 3. Generate access token
    access_token = utils.create_access_token(data={"sub": new_user.email})

    return {
        "message": "Đăng ký tài khoản thành công!",
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.post("/login", response_model=schemas.AuthResponse)
def login(login_data: schemas.UserLogin, db: Session = Depends(database.get_db)):
    """
    Authenticate user and return access token
    
    Args:
        login_data: Login credentials (email, password)
        db: Database session
        
    Returns:
        Authentication response with access token
        
    Raises:
        HTTPException: If credentials are invalid
    """
    # Find user by email
    user = db.query(models.User).filter(models.User.email == login_data.email).first()
    
    # Verify password
    if not user or not utils.verify_password(login_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Sai tài khoản hoặc mật khẩu")
    
    # Generate access token
    access_token = utils.create_access_token(data={"sub": user.email})
    
    return {
        "message": "Đăng nhập thành công!",
        "access_token": access_token,
        "token_type": "bearer"
    }