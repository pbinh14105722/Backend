from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from jose import jwt, JWTError
import models, utils, database, schemas
from utils import SECRET_KEY, ALGORITHM

router = APIRouter()
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


class UpdateUsername(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)


# GET /account - Lấy thông tin user
@router.get("/account")
def get_me(current_user: models.User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email
    }


# PATCH /account - Đổi tên hiển thị
@router.patch("/account")
def update_username(
    data: UpdateUsername,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[UPDATE USERNAME] User {current_user.id} -> '{data.username}'")

    existing = db.query(models.User).filter(models.User.username == data.username).first()
    if existing and existing.id != current_user.id:
        raise HTTPException(status_code=400, detail="Tên hiển thị này đã được sử dụng")

    try:
        current_user.username = data.username
        db.commit()
        db.refresh(current_user)
        print(f"[UPDATE USERNAME] ✅ Thành công")
        return {"message": "Cập nhật tên thành công!", "username": current_user.username}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi cập nhật: {str(e)}")


# PATCH /account/password - Đổi mật khẩu
@router.patch("/account/password")
def update_password(
    data: schemas.UpdatePassword,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[UPDATE PASSWORD] User {current_user.id} đang đổi mật khẩu")

    if not utils.verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")

    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Mật khẩu xác nhận không khớp")

    if utils.verify_password(data.new_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Mật khẩu mới không được trùng mật khẩu cũ")

    try:
        current_user.hashed_password = utils.hash_password(data.new_password)
        db.commit()
        print(f"[UPDATE PASSWORD] ✅ Thành công")
        return {"message": "Đổi mật khẩu thành công!"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi đổi mật khẩu: {str(e)}")
