from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from utils import SECRET_KEY, ALGORITHM
from jose import jwt, JWTError
from sqlalchemy.orm import Session
import models, schemas, utils, database
from fastapi.middleware.cors import CORSMiddleware
from datetime import date


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
####################################### ĐĂNG NHẬP / ĐĂNG KÝ ############################################
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
##########################################################################################################
####################################### CHỈNH SỬA PROJECT / FOLDER ######################################
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
@app.get("/items", response_model=list[schemas.ItemResponse])
def get_all_items(db: Session = Depends(database.get_db), current_user: models.User = Depends(get_current_user)):
    #return db.query(models.Item).order_by(models.Item.position.asc()).all()
    return db.query(models.Item).filter(models.Item.owner_id == current_user.id).order_by(models.Item.position.asc()).all()

# 2. Thêm mới một item
@app.post("/items", response_model=schemas.ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(item: schemas.ItemCreate, db: Session = Depends(database.get_db), current_user: models.User = Depends(get_current_user)):
    db_item = models.Item(
        **item.model_dump(),
        owner_id=current_user.id
    )
    try:
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return db_item
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu vào database: {str(e)}")

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
    
    # Chỉ update các field được gửi lên
    update_data = item_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_item, key, value)
    
    try:
        db.commit()
        db.refresh(db_item)
        return db_item
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi cập nhật: {str(e)}")

# Cập nhật nhanh tối ưu hơn
@app.post("/items/save-all")
def save_all_structure(
    items: list[schemas.ItemBatchUpdate], 
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if not items:
        return {"message": "Không có dữ liệu để cập nhật"}
    
    item_ids = [item.id for item in items]
    
    # Tìm các item hiện có trong DB thuộc về User này
    db_items = db.query(models.Item).filter(
        models.Item.id.in_(item_ids),
        models.Item.owner_id == current_user.id
    ).all()

    db_items_dict = {item.id: item for item in db_items}

    updated_count = 0
    for item_data in items:
        db_item = db_items_dict.get(item_data.id)
        if db_item:
            # ✅ CHỈ UPDATE CÁC FIELD AN TOÀN (không cho phép đổi owner_id)
            safe_fields = ['name', 'type', 'parent_id', 'position', 'color', 'expanded']
            update_data = item_data.model_dump(include=safe_fields)
            for key, value in update_data.items():
                setattr(db_item, key, value)
            
            #db.add(db_item)
            updated_count += 1

    try:
        db.commit()
        return {"message": f"Đã cập nhật {updated_count}/{len(items)} mục thành công"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu: {str(e)}")

# 4. Xóa (CHỈ XÓA ĐƯỢC CỦA MÌNH)
@app.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
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
    
    try:
        db.delete(db_item)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa: {str(e)}")
##########################################################################################################
########################################## CHỈNH SỬA TASK ###############################################

# Helper functions
def format_time_spent(minutes: int) -> str:
    """Convert phút sang format 'Xh Ym'"""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"

def format_date(d: date) -> str:
    """Convert date sang DD/MM/YYYY"""
    return d.strftime("%d/%m/%Y") if d else None

def verify_project_owner(project_id: str, user_id: int, db: Session):
    """Kiểm tra user có phải owner của project không"""
    project = db.query(models.Item).filter(
        models.Item.id == project_id,
        models.Item.type == 'PROJECT',
        models.Item.owner_id == user_id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or access denied")
    
    return project

# 1. GET - Lấy tất cả tasks trong project
@app.get("/project/{id_project}/items", response_model=list[schemas.TaskResponse])
def get_project_tasks(
    id_project: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Verify ownership
    verify_project_owner(id_project, current_user.id, db)
    
    # Lấy tasks
    tasks = db.query(models.Task)\
        .filter(models.Task.project_id == id_project)\
        .order_by(models.Task.position.asc())\
        .all()
    
    # Format response
    response = []
    for task in tasks:
        response.append({
            "id": task.id,
            "name": task.name,
            "priority": task.priority,
            "position": task.position,
            "start_date": format_date(task.start_date),
            "due_date": format_date(task.due_date),
            "time_spent": format_time_spent(task.time_spent_minutes),
            "project_id": task.project_id
        })
    
    return response

# 2. POST - Tạo task mới
@app.post("/project/{id_project}/items", response_model=schemas.TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    id_project: str,
    task: schemas.TaskCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Verify ownership
    verify_project_owner(id_project, current_user.id, db)
    
    # Đếm số task hiện tại
    task_count = db.query(models.Task).filter(models.Task.project_id == id_project).count()
    
    # Tạo name mặc định nếu không có
    if not task.name:
        task.name = f"Task {task_count + 1}"
    
    # Ngày bắt đầu và kết thúc mặc định là hôm nay
    today = date.today()
    if not task.start_date:
        task.start_date = today
    if not task.due_date:
        task.due_date = today
    
    # Tạo task
    db_task = models.Task(
        project_id=id_project,
        name=task.name,
        priority=task.priority,
        position=task_count,
        start_date=task.start_date,
        due_date=task.due_date,
        time_spent_minutes=task.time_spent_minutes
    )
    
    try:
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        
        return {
            "id": db_task.id,
            "name": db_task.name,
            "priority": db_task.priority,
            "position": db_task.position,
            "start_date": format_date(db_task.start_date),
            "due_date": format_date(db_task.due_date),
            "time_spent": format_time_spent(db_task.time_spent_minutes),
            "project_id": db_task.project_id
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi tạo task: {str(e)}")

# 3. PATCH - Chỉnh sửa task
@app.patch("/project/{id_project}/items/{id}", response_model=schemas.TaskResponse)
def update_task(
    id_project: str,
    id: str,
    task_data: schemas.TaskUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Verify ownership
    verify_project_owner(id_project, current_user.id, db)
    
    # Tìm task
    db_task = db.query(models.Task).filter(
        models.Task.id == id,
        models.Task.project_id == id_project
    ).first()
    
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Update chỉ các field được gửi
    update_data = task_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_task, key, value)
    
    try:
        db.commit()
        db.refresh(db_task)
        
        return {
            "id": db_task.id,
            "name": db_task.name,
            "priority": db_task.priority,
            "position": db_task.position,
            "start_date": format_date(db_task.start_date),
            "due_date": format_date(db_task.due_date),
            "time_spent": format_time_spent(db_task.time_spent_minutes),
            "project_id": db_task.project_id
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi cập nhật task: {str(e)}")

# 4. DELETE - Xóa task
@app.delete("/project/{id_project}/items/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    id_project: str,
    id: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Verify ownership
    verify_project_owner(id_project, current_user.id, db)
    
    # Tìm và xóa task
    db_task = db.query(models.Task).filter(
        models.Task.id == id,
        models.Task.project_id == id_project
    ).first()
    
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    try:
        db.delete(db_task)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa task: {str(e)}")

# 5. PUT - Cập nhật toàn bộ (kéo thả)
@app.put("/project/{id_project}")
def update_all_tasks(
    id_project: str,
    tasks: list[schemas.TaskBatchUpdate],
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Verify ownership
    verify_project_owner(id_project, current_user.id, db)
    
    if not tasks:
        return {"message": "Không có dữ liệu để cập nhật"}
    
    # Lấy tất cả tasks của project
    task_ids = [task.id for task in tasks]
    db_tasks = db.query(models.Task).filter(
        models.Task.id.in_(task_ids),
        models.Task.project_id == id_project
    ).all()
    
    db_tasks_dict = {task.id: task for task in db_tasks}
    
    # Update từng task
    updated_count = 0
    for task_data in tasks:
        db_task = db_tasks_dict.get(task_data.id)
        if db_task:
            db_task.name = task_data.name
            db_task.priority = task_data.priority
            db_task.position = task_data.position
            db_task.start_date = task_data.start_date
            db_task.due_date = task_data.due_date
            db_task.time_spent_minutes = task_data.time_spent_minutes
            updated_count += 1
    
    try:
        db.commit()
        return {"message": f"Đã cập nhật {updated_count}/{len(tasks)} tasks thành công"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu: {str(e)}")

##########################################################################################################
