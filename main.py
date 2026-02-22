from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from utils import SECRET_KEY, ALGORITHM
from jose import jwt, JWTError
from sqlalchemy.orm import Session
import models, schemas, utils, database
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone, timedelta


app = FastAPI()
# Tạo bảng trong DB (chỉ dùng cho demo, thực tế nên dùng Alembic)
#models.Base.metadata.create_all(bind=database.engine)

import username_password_update
app.include_router(username_password_update.router)

import pomodoro                        
app.include_router(pomodoro.router)

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
        return {"message": "Đã xóa thành công", "id": item_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa: {str(e)}")
##########################################################################################################
########################################## CHỈNH SỬA TASK ###############################################

def format_datetime_iso(dt: datetime) -> str:
    """Convert datetime sang ISO 8601 với timezone"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    iso_str = dt.isoformat()
    if iso_str.endswith('+00:00'):
        return iso_str.replace('+00:00', 'Z')
    return iso_str ##############=========== hàm mới thêm nha code chạy lỗi thì là ở ===============

def verify_project_owner(project_id: str, user_id: int, db: Session):
    """Kiểm tra user có phải owner của project không"""
    project = db.query(models.Item).filter(
        models.Item.id == project_id,
        models.Item.type == 'PROJECT',
        models.Item.owner_id == user_id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return project

def format_task_response(task: models.Task) -> dict:
    """Format task object sang response format"""
    return {
        "id": task.id,
        "position": task.position,
        "name": task.name,
        "priority": task.priority,
        "start_date": format_datetime_iso(task.start_date),
        "due_date": format_datetime_iso(task.due_date),
        "time_spent": task.time_spent_seconds,
        "notes": task.notes
    }

# 1. GET - Lấy tất cả tasks trong project
@app.get("/project/{projectId}/items", response_model=list[schemas.TaskResponse])
def get_project_tasks(
    projectId: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[GET TASKS] User {current_user.id} getting tasks from project {projectId}")
    
    # Verify ownership
    verify_project_owner(projectId, current_user.id, db)
    
    # Lấy tasks, sắp xếp theo position
    tasks = db.query(models.Task)\
        .filter(models.Task.project_id == projectId)\
        .order_by(models.Task.position.asc())\
        .all()
    
    print(f"[GET TASKS] Found {len(tasks)} tasks")
    
    # Format response
    return [format_task_response(task) for task in tasks]

# 2. POST - Tạo task mới với giá trị mặc định
@app.post("/project/{projectId}/items", response_model=schemas.TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    projectId: str,
    task: schemas.TaskCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[CREATE TASK] User {current_user.id} creating task in project {projectId}")
    
    # Verify ownership
    verify_project_owner(projectId, current_user.id, db)
    
    # Đếm số task hiện tại để tạo position và name
    task_count = db.query(models.Task).filter(models.Task.project_id == projectId).count()
    
    # Giá trị mặc định
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999000)
    
    # Tạo task
    db_task = models.Task(
        project_id=projectId,
        position=task_count + 1,  # Vị trí cuối cùng
        name=f"Task {task_count + 1}",
        priority='low',  # Mặc định low
        start_date=now,                              # ✅ Thời gian hiện tại chính xác
        due_date=now + timedelta(hours=1),
        time_spent_seconds=0,
        notes=""
    )
    
    try:
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        
        print(f"[CREATE TASK] ✅ Created task ID {db_task.id}")
        return format_task_response(db_task)
    except Exception as e:
        db.rollback()
        print(f"[CREATE TASK] ❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi tạo task: {str(e)}")

# 3. DELETE - Xóa task và reorder
@app.delete("/project/{projectId}/items/{id}")
def delete_task(
    projectId: str,
    id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[DELETE TASK] User {current_user.id} deleting task {id} from project {projectId}")
    
    # Verify ownership
    verify_project_owner(projectId, current_user.id, db)
    
    # Tìm task
    db_task = db.query(models.Task).filter(
        models.Task.id == id,
        models.Task.project_id == projectId
    ).first()
    
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    deleted_position = db_task.position
    
    try:
        # Xóa task
        db.delete(db_task)
        
        # Cập nhật position của các task còn lại
        remaining_tasks = db.query(models.Task)\
            .filter(
                models.Task.project_id == projectId,
                models.Task.position > deleted_position
            )\
            .all()
        
        for task in remaining_tasks:
            task.position -= 1
        
        db.commit()
        
        print(f"[DELETE TASK] ✅ Deleted task {id} and reordered {len(remaining_tasks)} tasks")
        return {"message": "Task deleted successfully", "id": id}
    except Exception as e:
        db.rollback()
        print(f"[DELETE TASK] ❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa task: {str(e)}")

# 4. PATCH - Cập nhật vị trí task (Reorder)
@app.patch("/project/{projectId}/items/reorder", response_model=list[schemas.TaskResponse])
def reorder_tasks(
    projectId: str,
    reorder_data: list[schemas.TaskReorderItem],
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[REORDER TASKS] User {current_user.id} reordering {len(reorder_data)} tasks in project {projectId}")
    
    # Verify ownership
    verify_project_owner(projectId, current_user.id, db)
    
    # Lấy các task cần update
    task_ids = [item.id for item in reorder_data]
    db_tasks = db.query(models.Task).filter(
        models.Task.id.in_(task_ids),
        models.Task.project_id == projectId
    ).all()
    
    db_tasks_dict = {task.id: task for task in db_tasks}
    
    # Update position
    updated_count = 0
    for item in reorder_data:
        db_task = db_tasks_dict.get(item.id)
        if db_task:
            db_task.position = item.position
            updated_count += 1
    
    try:
        db.commit()
        
        # Lấy lại tất cả tasks đã sắp xếp
        all_tasks = db.query(models.Task)\
            .filter(models.Task.project_id == projectId)\
            .order_by(models.Task.position.asc())\
            .all()
        
        print(f"[REORDER TASKS] ✅ Updated {updated_count} tasks")
        return [format_task_response(task) for task in all_tasks]
    except Exception as e:
        db.rollback()
        print(f"[REORDER TASKS] ❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi reorder: {str(e)}")

# 5. PATCH - Chỉnh sửa task
@app.patch("/project/{projectId}/items/{id}", response_model=schemas.TaskResponse)
def update_task(
    projectId: str,
    id: int,
    task_data: schemas.TaskUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[UPDATE TASK] User {current_user.id} updating task {id} in project {projectId}")
    
    # Verify ownership
    verify_project_owner(projectId, current_user.id, db)
    
    # Tìm task
    db_task = db.query(models.Task).filter(
        models.Task.id == id,
        models.Task.project_id == projectId
    ).first()
    
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Update chỉ các field được gửi
    update_data = task_data.model_dump(exclude_unset=True)
    
    # Xử lý time_spent nếu có
    if 'time_spent' in update_data:
        update_data['time_spent_seconds'] = update_data.pop('time_spent')
    
    # Update các field còn lại
    for key, value in update_data.items():
        setattr(db_task, key, value)
    
    try:
        db.commit()
        db.refresh(db_task)
        
        print(f"[UPDATE TASK] ✅ Updated task {id}")
        return format_task_response(db_task)
    except Exception as e:
        db.rollback()
        print(f"[UPDATE TASK] ❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi cập nhật task: {str(e)}")
##########################################################################################################




@app.api_route('/health', methods=['GET', 'HEAD'])
def health():
    return {"status": "ok"}
