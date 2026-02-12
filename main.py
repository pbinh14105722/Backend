from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from utils import SECRET_KEY, ALGORITHM
from jose import jwt, JWTError
from sqlalchemy.orm import Session
import models, schemas, utils, database
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()
# Tạo bảng trong DB (chỉ dùng cho demo, thực tế nên dùng Alembic)
models.Base.metadata.create_all(bind=database.engine)

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
    new_user = models.User(username=user.username,email=user.email, hashed_password=utils.hash_password(user.password))
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

# --- CÁC HÀM CRUD ĐÃ ĐƯỢC PHÂN QUYỀN ---

# Hàm tiện ích: Lấy User Object từ Email (để dùng ID của nó)
def get_user_from_token(db: Session, email: str):
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User không tồn tại")
    return user

# 1. Lấy danh sách (CHỈ LẤY CỦA MÌNH)
@app.get("/items", response_model=list[schemas.ItemResponse]) # Đổi /data thành /items cho chuẩn RESTful
def get_my_items(
    db: Session = Depends(database.get_db), 
    current_user_email: str = Depends(get_current_user)
):
    # Tìm user hiện tại
    user = get_user_from_token(db, current_user_email)
    
    # LỌC DỮ LIỆU: Chỉ lấy item có owner_id trùng với id của user
    return db.query(models.Item).filter(models.Item.owner_id == user.id).order_by(models.Item.position.asc()).all()

# 2. Thêm mới (TỰ ĐỘNG GÁN CHO MÌNH)
@app.post("/items", response_model=schemas.ItemResponse)
def create_item(
    item: schemas.ItemCreate, 
    db: Session = Depends(database.get_db), 
    current_user_email: str = Depends(get_current_user)
):
    user = get_user_from_token(db, current_user_email)
    
    # Khi tạo, gán luôn owner_id = user.id
    db_item = models.Item(**item.model_dump(), owner_id=user.id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

# 3. Cập nhật (CHỈ SỬA ĐƯỢC CỦA MÌNH)
@app.put("/items/{item_id}", response_model=schemas.ItemResponse)
def update_item(
    item_id: str, 
    item_data: schemas.ItemUpdate, 
    db: Session = Depends(database.get_db), 
    current_user_email: str = Depends(get_current_user)
):
    user = get_user_from_token(db, current_user_email)
    
    # Tìm item, NHƯNG phải kèm điều kiện owner_id
    db_item = db.query(models.Item).filter(
        models.Item.id == item_id, 
        models.Item.owner_id == user.id  # <-- Khóa bảo mật
    ).first()
    
    if not db_item:
        raise HTTPException(status_code=404, detail="Không tìm thấy mục này (hoặc bạn không có quyền)")
    
    for key, value in item_data.model_dump(exclude_unset=True).items():
        setattr(db_item, key, value)
    
    db.commit()
    db.refresh(db_item)
    return db_item

# 4. Xóa (CHỈ XÓA ĐƯỢC CỦA MÌNH)
@app.delete("/items/{item_id}")
def delete_item(
    item_id: str, 
    db: Session = Depends(database.get_db), 
    current_user_email: str = Depends(get_current_user)
):
    user = get_user_from_token(db, current_user_email)
    
    db_item = db.query(models.Item).filter(
        models.Item.id == item_id, 
        models.Item.owner_id == user.id # <-- Khóa bảo mật
    ).first()
    
    if not db_item:
        raise HTTPException(status_code=404, detail="Không tìm thấy mục này")
    
    db.delete(db_item)
    db.commit()
    return {"message": "Đã xóa thành công"}
