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
@app.post("/signup", response_model=schemas.AuthResponse)
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

    access_token = utils.create_access_token(data={"sub": new_user.email})

    return {
        "message": "Đăng ký tài khoản thành công!",
        "access_token": access_token,
        "token_type": "bearer"
    }

# --- API ĐĂNG NHẬP ---
@app.post("/login", response_model=schemas.AuthResponse)
def login(login_data: schemas.UserLogin, db: Session = Depends(database.get_db)):
    # Bây giờ bạn dùng login_data.email nghe sẽ thuận tai hơn nhiều!
    user = db.query(models.User).filter(models.User.email == login_data.email).first()
    
    if not user or not utils.verify_password(login_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Sai tài khoản hoặc mật khẩu")
    
    access_token = utils.create_access_token(data={"sub": user.email})
    return {
        "message": "Đăng nhập thành công!",
        "access_token": access_token,
        "token_type": "bearer"
    }

# Hàm này dùng để kiểm tra Token xem có hợp lệ không
# Sửa lại hàm này để lấy thẳng Object User từ Database
def get_current_user(db: Session = Depends(database.get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Không thể xác thực thông tin",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Giải mã token để lấy email (sub)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Truy vấn lấy user ngay tại đây
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception
        
    return user # Trả về object User (chứa id, email, username...)

# --- CÁC HÀM CRUD ĐÃ ĐƯỢC PHÂN QUYỀN ---

# Hàm tiện ích: Lấy User Object từ Email (để dùng ID của nó)
def get_user_from_token(db: Session, email: str):
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User không tồn tại")
    return user

# 1. Lấy toàn bộ danh sách (Sắp xếp theo position)
@app.get("/items")#, response_model=list[schemas.ItemResponse])
def get_all_items(db: Session = Depends(database.get_db), current_user: models.User = Depends(get_current_user)):
    #return db.query(models.Item).order_by(models.Item.position.asc()).all()
    return db.query(models.Item).filter(models.Item.owner_id == current_user.id).order_by(models.Item.position.asc()).all()

# 2. Thêm mới một item
@app.post("/items", response_model=schemas.ItemResponse)
def create_item(item: schemas.ItemCreate, db: Session = Depends(database.get_db), current_user: str = Depends(get_current_user)):
    db_item = models.Item(**item.model_dump(), owner_id=current_user.id)
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
    current_user: models.User = Depends(get_current_user)
):  
    # Tìm item, NHƯNG phải kèm điều kiện owner_id
    db_item = db.query(models.Item).filter(
        models.Item.id == item_id, 
        models.Item.owner_id == current_user.id  # <-- Khóa bảo mật
    ).first()
    
    if not db_item:
        raise HTTPException(status_code=404, detail="Không tìm thấy mục này (hoặc bạn không có quyền)")
    
    for key, value in item_data.model_dump(exclude_unset=True).items():
        setattr(db_item, key, value)
    
    db.commit()
    db.refresh(db_item)
    return db_item

# Cập nhật nhanh tối ưu hơn
@app.post("/items/save-all")
def save_all_structure(
    items: list[schemas.ItemBatchUpdate], 
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user) # Dùng thẳng object User đã login
):
    # 1. Lấy danh sách ID để kiểm tra một lượt (tăng performance)
    item_ids = [item.id for item in items]
    
    # 2. Tìm tất cả items thuộc sở hữu của user này trong danh sách gửi lên
    db_items = db.query(models.Item).filter(
        models.Item.id.in_(item_ids),
        models.Item.owner_id == current_user.id
    ).all()

    # Tạo một dictionary để tìm kiếm nhanh hơn
    db_items_dict = {item.id: item for item in db_items}

    # 3. Cập nhật dữ liệu
    for item_data in items:
        db_item = db_items_dict.get(item_data.id)
        if db_item:
            db_item.parent_id = item_data.parent_id
            db_item.position = item_data.position

    db.commit()
    return {"message": f"Đã cập nhật cấu trúc cho {len(db_items)} mục thành công"}

# 4. Xóa (CHỈ XÓA ĐƯỢC CỦA MÌNH)
@app.delete("/items/{item_id}")
def delete_item(
    item_id: str, 
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(get_current_user) # Gọn hơn
):
    db_item = db.query(models.Item).filter(
        models.Item.id == item_id, 
        models.Item.owner_id == current_user.id
    ).first()
    
    if not db_item:
        raise HTTPException(status_code=404, detail="Không tìm thấy mục này")
    
    db.delete(db_item)
    db.commit()
    return {"message": "Đã xóa thành công"}
