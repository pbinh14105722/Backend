from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from utils import SECRET_KEY, ALGORITHM
from jose import jwt, JWTError
from sqlalchemy.orm import Session
import models, schemas, utils, database
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()
# Tạo bảng trong DB (chỉ dùng cho demo, thực tế nên dùng Alembic)
#models.Base.metadata.create_all(bind=database.engine)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Cho phép tất cả các nguồn (trong thực tế nên chỉ định rõ domain)
    allow_credentials=True,
    allow_methods=["*"], # Cho phép tất cả các phương thức (GET, POST,...)
    allow_headers=["*"], # Cho phép tất cả các headers
)

# Tạo bảng trong DB (chỉ dùng cho demo, thực tế nên dùng Alembic)

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
def get_current_user(token: str = Depends(oauth2_scheme)):
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

# --- BỔ SUNG LOGIC QUẢN LÝ FOLDER/PROJECT ---

# 1. Lấy toàn bộ danh sách (Sắp xếp theo position)
@app.get("/data", response_model=list[schemas.ItemResponse])
def get_all_items(db: Session = Depends(database.get_db), current_user: str = Depends(get_current_user)):
    return db.query(models.Item).order_by(models.Item.position.asc()).all()

# 2. Thêm mới một item
@app.post("/items", response_model=schemas.ItemResponse)
def create_item(item: schemas.ItemCreate, db: Session = Depends(database.get_db), current_user: str = Depends(get_current_user)):
    db_item = models.Item(**item.model_dump())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

# 3. Cập nhật một item (Sửa tên, màu, trạng thái mở rộng hoặc kéo thả)
@app.put("/items/{item_id}", response_model=schemas.ItemResponse)
def update_item(item_id: str, item_data: schemas.ItemUpdate, db: Session = Depends(database.get_db), current_user: str = Depends(get_current_user)):
    db_item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Không tìm thấy mục này")
    
    for key, value in item_data.model_dump(exclude_unset=True).items():
        setattr(db_item, key, value)
    
    db.commit()
    db.refresh(db_item)
    return db_item

# 4. Xóa một item (Cascade delete sẽ tự xóa con nếu bạn config DB đúng)
@app.delete("/items/{item_id}")
def delete_item(item_id: str, db: Session = Depends(database.get_db), current_user: str = Depends(get_current_user)):
    db_item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Không tìm thấy mục này")
    
    db.delete(db_item)
    db.commit()
    return {"message": "Đã xóa thành công"}

# 5. Lưu toàn bộ cấu trúc (Dùng khi kéo thả số lượng lớn)
@app.post("/save-all")
def save_all_items(items: list[schemas.ItemCreate], db: Session = Depends(database.get_db), current_user: str = Depends(get_current_user)):
    # Xóa sạch bảng và ghi đè lại (Đơn giản nhất cho kéo thả)
    db.query(models.Item).delete()
    for item in items:
        db.add(models.Item(**item.model_dump()))
    db.commit()
    return {"message": "Đã lưu toàn bộ cấu trúc"}

# Đây là API bí mật
@app.get("/users/me")
def read_users_me(current_user_email: str = Depends(get_current_user)):
    return {"message": "Chào mừng bạn!", "user_email": current_user_email}

