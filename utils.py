import bcrypt
from datetime import datetime, timedelta, timezone
from jose import jwt
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY not found in environment variables. Please set it in your .env file.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60

def hash_password(password: str):
    # Chuyển password sang dạng bytes
    pwd_bytes = password.encode('utf-8')
    # Tạo salt và hash
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    # Trả về dạng string để lưu vào DB
    return hashed_password.decode('utf-8')

def verify_password(plain_password, hashed_password):
    password_byte = plain_password.encode('utf-8')
    hashed_password_byte = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_byte, hashed_password_byte)

def create_access_token(data: dict):
    to_encode = data.copy()
    # Dùng timezone-aware datetime để tránh lệch giờ hệ thống
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
