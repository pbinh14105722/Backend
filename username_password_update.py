from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import models, utils, database
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter()

# ========== SCHEMAS (nếu bạn muốn để riêng thì chuyển sang schemas.py) ==========

class UpdateUsername(BaseModel):
    new_username: str = Field(..., min_length=1, max_length=50)

class UpdatePassword(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)
    confirm_password: str

# ========== IMPORT HÀM get_current_user TỪ main.py ==========
# Vì get_current_user đang nằm trong main.py, bạn cần import nó
# Cách 1: Chuyển get_current_user sang file auth.py riêng (recommended)
# Cách 2: Import trực tiếp từ main (dễ gây circular import)
# --> Tạm thời tôi viết lại hàm này ở đây để tránh circular import

from fastapi.security import OAuth2PasswordBearer
from utils import SECRET_KEY, ALGORITHM
from jose import jwt, JWTError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(
    db: Session = Depends(database.get_db),
    token: str = Depends(oauth2_scheme)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Không thể xác thực thông tin",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception
    return user


# ========== ROUTES ==========

# 1. ĐỔI TÊN HIỂN THỊ
@router.patch("/user/username", status_code=status.HTTP_200_OK)
def update_username(
    data: UpdateUsername,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[UPDATE USERNAME] User {current_user.id} đang đổi username thành '{data.new_username}'")

    # Kiểm tra username mới có trùng không (nếu cần)
    existing = db.query(models.User).filter(
        models.User.username == data.new_username
    ).first()
    if existing and existing.id != current_user.id:
        raise HTTPException(status_code=400, detail="Tên hiển thị này đã được sử dụng")

    try:
        current_user.username = data.new_username
        db.commit()
        db.refresh(current_user)
        print(f"[UPDATE USERNAME] ✅ Thành công")
        return {
            "message": "Cập nhật tên hiển thị thành công!",
            "username": current_user.username
        }
    except Exception as e:
        db.rollback()
        print(f"[UPDATE USERNAME] ❌ Lỗi: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi cập nhật: {str(e)}")


# 2. ĐỔI MẬT KHẨU
@router.patch("/user/password", status_code=status.HTTP_200_OK)
def update_password(
    data: UpdatePassword,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[UPDATE PASSWORD] User {current_user.id} đang đổi mật khẩu")

    # 1. Kiểm tra mật khẩu hiện tại
    if not utils.verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")

    # 2. Kiểm tra confirm password
    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Mật khẩu xác nhận không khớp")

    # 3. Không cho đổi sang mật khẩu cũ
    if utils.verify_password(data.new_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Mật khẩu mới không được trùng mật khẩu cũ")

    try:
        current_user.hashed_password = utils.hash_password(data.new_password)
        db.commit()
        print(f"[UPDATE PASSWORD] ✅ Thành công")
        return {"message": "Đổi mật khẩu thành công!"}
    except Exception as e:
        db.rollback()
        print(f"[UPDATE PASSWORD] ❌ Lỗi: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi đổi mật khẩu: {str(e)}")


# 3. LẤY THÔNG TIN USER HIỆN TẠI
@router.get("/user/me", status_code=status.HTTP_200_OK)
def get_me(current_user: models.User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email
    }