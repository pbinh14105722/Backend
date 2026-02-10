from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from utils import SECRET_KEY, ALGORITHM
from jose import jwt, JWTError
from sqlalchemy.orm import Session
import models, schemas, utils, database
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Cho phép tất cả các nguồn (trong thực tế nên chỉ định rõ domain)
    allow_credentials=True,
    allow_methods=["*"], # Cho phép tất cả các phương thức (GET, POST,...)
    allow_headers=["*"], # Cho phép tất cả các headers
)

# Tạo bảng trong DB (chỉ dùng cho demo, thực tế nên dùng Alembic)
#models.Base.metadata.create_all(bind=database.engine)

# --- API ĐĂNG KÝ ---
@app.post("/signup", response_model=schemas.UserResponse)
def signup(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    # 1. Kiểm tra email tồn tại chưa
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email đã được đăng ký!")
    
    # 2. Hash mật khẩu và lưu
    new_user = models.User(email=user.email, hashed_password=utils.hash_password(user.password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

# --- API ĐĂNG NHẬP ---
@app.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    # 1. Tìm user theo email (form_data.username ở đây chính là email)
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    
    # 2. Kiểm tra user và verify mật khẩu
    if not user or not utils.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Sai tài khoản hoặc mật khẩu")
    
    # 3. Tạo JWT Token
    access_token = utils.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

# Hàm này dùng để kiểm tra Token xem có hợp lệ không
def get_current_user(token: str = Depends(database.oauth2_scheme)):
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
        return email
    except JWTError:
        raise credentials_exception

# Đây là API bí mật
@app.get("/users/me")
def read_users_me(current_user_email: str = Depends(get_current_user)):

    return {"message": "Chào mừng bạn!", "user_email": current_user_email}
