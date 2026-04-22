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

    # 3. Create default data
    from datetime import datetime
    now = datetime.utcnow()
    
    # 3.1 Folder
    folder = models.Item(
        name="Khám phá Manask",
        type="FOLDER",
        color="#8b5cf6",
        owner_id=new_user.id,
        position=0,
        expanded=True
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)

    # 3.2 Projects
    projects_data = [
        {"name": "Quản lý Task", "color": "#3b82f6"},
        {"name": "Pomodoro", "color": "#f6ad55"},
        {"name": "Thống kê", "color": "#6ee7b7"},
        {"name": "AI Chatbot", "color": "#ec4899"}
    ]
    
    projects = {}
    for i, p_data in enumerate(projects_data):
        project = models.Item(
            name=p_data["name"],
            type="PROJECT",
            parent_id=folder.id,
            color=p_data["color"],
            owner_id=new_user.id,
            position=i
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        projects[p_data["name"]] = project.id

    # 3.3 Tasks
    tasks_data = {
        "Quản lý Task": [
            {"name":"Tạo task mới", "importance":"medium", "note":"Nhập tên task, chọn độ ưu tiên."},
            {"name":"Kéo thả để sắp xếp task", "importance":"medium", "note":"Thử drag-drop thay đổi thứ tự."},
            {"name":"Thêm ghi chú vào task", "importance":"low", "note":"Mở task card và chỉnh sửa note."},
            {"name":"Thử filter / sort", "importance":"medium", "note":"Lọc task High / Medium / Low."}
        ],
        "Pomodoro": [
            {"name":"Chọn một task để tập trung", "importance":"low", "note":"Pomodoro luôn gắn với task."},
            {"name":"Bắt đầu Focus 25 phút", "importance":"high", "note":"Thử chạy bộ đếm giờ."},
            {"name":"Thử Short Break", "importance":"medium", "note":"Quan sát chuyển phiên nghỉ."},
            {"name":"Bật Auto-play trong settings", "importance":"medium", "note":"Khám phá cài đặt Pomodoro."},
            {"name":"Kiểm tra thời gian đã cộng vào task", "importance":"high", "note":"Xem time_spent được cập nhật."}
        ],
        "Thống kê": [
            {"name":"Mở trang Statistics", "importance":"low", "note":"Xem dashboard thống kê."},
            {"name":"Xem Summary tổng quan", "importance":"medium", "note":"Quan sát task hoàn thành và giờ làm."},
            {"name":"Xem biểu đồ Line Chart", "importance":"medium", "note":"Theo dõi xu hướng tiến độ."},
            {"name":"Xem Donut Chart theo project", "importance":"medium", "note":"Xem phân bố task."},
            {"name":"Xem Heatmap hoạt động", "importance":"high", "note":"Khám phá activity calendar."}
        ],
        "AI Chatbot": [
            {"name":"Chat hỏi AI về tổ chức công việc", "importance":"low", "note":"Thử chat thường với AI."},
            {"name":"Dùng AI tạo folder-tree", "importance":"high", "note":"Prompt thử tạo workspace tự động."},
            {"name":"Lưu folder-tree AI tạo ra", "importance":"high", "note":"Bấm Lưu để import vào hệ thống."},
            {"name":"Dùng AI tạo roadmap", "importance":"high", "note":"Prompt thử sinh roadmap tự động."},
            {"name":"Lưu roadmap vào Roadmap Editor", "importance":"high", "note":"Import roadmap vừa tạo."}
        ]
    }

    for proj_name, t_list in tasks_data.items():
        proj_id = projects.get(proj_name)
        if not proj_id:
            continue
        for i, t_data in enumerate(t_list):
            task = models.Task(
                project_id=proj_id,
                name=t_data["name"],
                priority=t_data["importance"],
                position=i+1,
                start_date=now,
                due_date=now,
                notes=t_data["note"]
            )
            db.add(task)
            
    db.commit()

    # 3.4 Roadmap
    import json
    roadmap_nodes = {
        "n1": {
            "x": 100, 
            "y": 200, 
            "item": {
                "id": projects.get("Quản lý Task", ""), 
                "name": "Quản lý Task", 
                "type": "PROJECT", 
                "color": "#3b82f6",
                "parent_name": "Khám phá Manask"
            }
        },
        "n2": {
            "x": 450, 
            "y": 200, 
            "item": {
                "id": projects.get("Pomodoro", ""), 
                "name": "Pomodoro", 
                "type": "PROJECT", 
                "color": "#f6ad55",
                "parent_name": "Khám phá Manask"
            }
        },
        "n3": {
            "x": 800, 
            "y": 200, 
            "item": {
                "id": projects.get("Thống kê", ""), 
                "name": "Thống kê", 
                "type": "PROJECT", 
                "color": "#6ee7b7",
                "parent_name": "Khám phá Manask"
            }
        },
        "n4": {
            "x": 1150, 
            "y": 200, 
            "item": {
                "id": projects.get("AI Chatbot", ""), 
                "name": "AI Chatbot", 
                "type": "PROJECT", 
                "color": "#ec4899",
                "parent_name": "Khám phá Manask"
            }
        }
    }

    roadmap_edges = [
        {"from": "n1", "to": "n2", "fromPort": "right", "toPort": "left", "etype": "one", "style": "solid", "label": "Tiếp theo"},
        {"from": "n2", "to": "n3", "fromPort": "right", "toPort": "left", "etype": "one", "style": "solid", "label": "Tiến độ"},
        {"from": "n3", "to": "n4", "fromPort": "right", "toPort": "left", "etype": "one", "style": "solid", "label": "Nâng cao"}
    ]

    roadmap = models.Roadmap(
        user_id=new_user.id,
        name="Lộ trình Khám phá Manask",
        nodes=json.dumps(roadmap_nodes),
        edges=json.dumps(roadmap_edges),
        n_cnt=4,
        pan_x=0.0,
        pan_y=0.0,
        zoom=1.0
    )
    db.add(roadmap)
    db.commit()

    # 4. Generate access token
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