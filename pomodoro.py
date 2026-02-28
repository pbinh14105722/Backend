from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from jose import jwt, JWTError
from datetime import datetime
import models, database
from utils import SECRET_KEY, ALGORITHM

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


# ========== AUTH ==========
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


# ========== SCHEMAS ==========
class PomodoroSettingsSchema(BaseModel):
    focus_duration:   int = Field(default=1500, ge=60)
    short_break:      int = Field(default=300,  ge=60)
    long_break:       int = Field(default=900,  ge=60)
    long_break_after: int = Field(default=4,    ge=1)
    disable_break:    bool = False
    auto_start_focus: bool = False
    auto_start_break: bool = False

# class PomodoroSessionSchema(BaseModel):
#     mode:         str
#     duration:     int
#     task_id:      Optional[int] = None
#     completed_at: Optional[datetime] = None

class PomodoroSessionSchema(BaseModel):
    mode:         str
    duration:     int
    task_id:      Optional[int] = None
    task_name:    Optional[str] = "Unknown"  # <--- THÊM DÒNG NÀY
    completed_at: Optional[datetime] = None


# ========== ROUTES ==========

# GET /pomodoro/settings — Lấy settings, tự tạo nếu chưa có
@router.get("/pomodoro/settings")
def get_settings(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[POMODORO] GET settings - User {current_user.id}")

    settings = db.query(models.PomodoroSettings).filter(
        models.PomodoroSettings.user_id == current_user.id
    ).first()

    # Nếu chưa có thì tạo mặc định
    if not settings:
        settings = models.PomodoroSettings(user_id=current_user.id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
        print(f"[POMODORO] ✅ Created default settings for User {current_user.id}")

    return {
        "focus_duration":   settings.focus_duration,
        "short_break":      settings.short_break,
        "long_break":       settings.long_break,
        "long_break_after": settings.long_break_after,
        "disable_break":    settings.disable_break,
        "auto_start_focus": settings.auto_start_focus,
        "auto_start_break": settings.auto_start_break,
    }


# PATCH /pomodoro/settings — Cập nhật settings
@router.patch("/pomodoro/settings")
def update_settings(
    data: PomodoroSettingsSchema,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[POMODORO] PATCH settings - User {current_user.id}")

    settings = db.query(models.PomodoroSettings).filter(
        models.PomodoroSettings.user_id == current_user.id
    ).first()

    # Nếu chưa có thì tạo mới
    if not settings:
        settings = models.PomodoroSettings(user_id=current_user.id)
        db.add(settings)

    settings.focus_duration   = data.focus_duration
    settings.short_break      = data.short_break
    settings.long_break       = data.long_break
    settings.long_break_after = data.long_break_after
    settings.disable_break    = data.disable_break
    settings.auto_start_focus = data.auto_start_focus
    settings.auto_start_break = data.auto_start_break

    try:
        db.commit()
        db.refresh(settings)
        print(f"[POMODORO] ✅ Updated settings for User {current_user.id}")
        return {"message": "Cập nhật settings thành công!"}
    except Exception as e:
        db.rollback()
        print(f"[POMODORO] ❌ Lỗi: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu settings: {str(e)}")


# GET /pomodoro/tasks — Lấy tất cả tasks của user (cho dropdown)
@router.get("/pomodoro/tasks")
def get_tasks(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[POMODORO] GET tasks - User {current_user.id}")

    # Lấy tất cả projects của user
    projects = db.query(models.Item).filter(
        models.Item.owner_id == current_user.id,
        models.Item.type == 'PROJECT'
    ).all()

    project_ids = [p.id for p in projects]

    # Lấy tất cả tasks thuộc các project đó
    tasks = db.query(models.Task).filter(
        models.Task.project_id.in_(project_ids)
    ).order_by(models.Task.position.asc()).all()

    return [{"id": t.id, "name": t.name} for t in tasks]


# POST /pomodoro/sessions — Lưu session hoàn thành
@router.post("/pomodoro/sessions", status_code=status.HTTP_201_CREATED)
def create_session(
    data: PomodoroSessionSchema,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[POMODORO] POST session - User {current_user.id}, mode={data.mode}")

    session = models.PomodoroSession(
        user_id=current_user.id,
        mode=data.mode,
        duration=data.duration,
        task_id=data.task_id,
        completed_at=data.completed_at or datetime.utcnow()
    )

    try:
        db.add(session)

        # Nếu là focus session và có task_id -> cộng thêm duration vào time_spent_seconds của task
        if data.mode == "focus" and data.task_id is not None:
            task = db.query(models.Task).filter(models.Task.id == data.task_id).first()
            if task:
                task.time_spent_seconds = (task.time_spent_seconds or 0) + data.duration
                print(f"[POMODORO] ⏱ Updated task {task.id} time_spent_seconds += {data.duration} -> {task.time_spent_seconds}")

        db.commit()
        db.refresh(session)
        print(f"[POMODORO] ✅ Session saved ID {session.id}")
        return {"message": "Session saved!", "id": session.id}
    except Exception as e:
        db.rollback()
        print(f"[POMODORO] ❌ Lỗi: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu session: {str(e)}")
