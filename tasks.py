from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import json

import models
import schemas
import database
from dependencies import get_current_user, verify_project_owner, format_task_response

# Khai báo router quản lý tất cả các endpoint liên quan đến project tasks
router = APIRouter(
    prefix="/project",
    tags=["Tasks"]
)



# 1. GET - Lấy tất cả tasks trong project
@router.get("/{projectId}/items", response_model=list[schemas.TaskResponse])
def get_project_tasks(
    projectId: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[GET TASKS] User {current_user.id} getting tasks from project {projectId}")

    # Verify ownership
    verify_project_owner(projectId, current_user.id, db)

    # Lấy tasks theo position trước
    tasks = db.query(models.Task)\
        .filter(models.Task.project_id == projectId)\
        .order_by(models.Task.position.asc())\
        .all()

    print(f"[GET TASKS] Found {len(tasks)} tasks")

    # ==================== FILTER ====================
    filter_settings = db.query(models.FilterSettings).filter(
        models.FilterSettings.project_id == projectId,
        models.FilterSettings.user_id == current_user.id
    ).first()

    if filter_settings and filter_settings.enabled:
        data = json.loads(filter_settings.filter_config or '{"logic":"and","filters":[]}')
        if isinstance(data, list):
            rules = data
            logic = "and"
        else:
            rules = data.get("filters", [])
            logic = data.get("logic", "and")

        def time_str_to_seconds(t: str) -> int:
            try:
                h, m, s = t.split(":")
                return int(h) * 3600 + int(m) * 60 + int(s)
            except:
                return 0

        def parse_dt(s: str):
            try:
                return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
            except:
                return None

        def make_dt_aware(dt):
            if dt and dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        def match_rule(task, rule: dict) -> bool:
            field    = rule.get("field")
            operator = rule.get("operator")
            value    = rule.get("value")

            if field == "name":
                task_val = (task.name or "").lower()
                val      = str(value).lower()
                if operator == "contains":     return val in task_val
                if operator == "not_contains": return val not in task_val
                if operator == "eq":           return task_val == val
                if operator == "not_eq":       return task_val != val

            elif field == "priority":
                task_val = task.priority or ""
                if operator == "in":     return task_val in value
                if operator == "not_in": return task_val not in value

            elif field in ("start_date", "due_date"):
                task_dt = make_dt_aware(task.start_date if field == "start_date" else task.due_date)
                if task_dt is None: return False

                if operator == "between":
                    dt_from = parse_dt(value.get("from"))
                    dt_to   = parse_dt(value.get("to"))
                    if dt_from and dt_to:
                        return dt_from <= task_dt <= dt_to
                else:
                    cmp_dt = parse_dt(value)
                    if cmp_dt is None: return False
                    if operator == "eq":  return task_dt == cmp_dt
                    if operator == "gt":  return task_dt > cmp_dt
                    if operator == "gte": return task_dt >= cmp_dt
                    if operator == "lt":  return task_dt < cmp_dt
                    if operator == "lte": return task_dt <= cmp_dt

            elif field == "time_spent":
                task_val = task.time_spent_seconds or 0
                if operator == "between":
                    v_from = time_str_to_seconds(value.get("from", "00:00:00"))
                    v_to   = time_str_to_seconds(value.get("to", "00:00:00"))
                    return v_from <= task_val <= v_to
                else:
                    cmp_val = time_str_to_seconds(str(value))
                    if operator == "eq":     return task_val == cmp_val
                    if operator == "gt":     return task_val > cmp_val
                    if operator == "gte":    return task_val >= cmp_val
                    if operator == "lt":     return task_val < cmp_val
                    if operator == "lte":    return task_val <= cmp_val

            return True

        def task_matches(task) -> bool:
            if not rules:
                return True
            results = [match_rule(task, rule) for rule in rules]
            if logic == "or":
                return any(results)
            return all(results)

        before = len(tasks)
        tasks = [t for t in tasks if task_matches(t)]
        print(f"[GET TASKS] Filter applied: {before} → {len(tasks)} tasks, logic={logic}")

    # ==================== SORT ====================
    sort_settings = db.query(models.SortSettings).filter(
        models.SortSettings.project_id == projectId,
        models.SortSettings.user_id == current_user.id
    ).first()

    if sort_settings and sort_settings.enabled:
        rules = json.loads(sort_settings.sort_config or "[]")
        rules.sort(key=lambda r: r.get("order", 0))  # order=1 lên đầu

        FIELD_MAP = {
            "name":       lambda t: (t.name or "").lower(),
    
            # ✅ Fix: low=0 → medium=1 → high=2
            # ascending=True  → low → medium → high (tăng dần mức quan trọng)
            # ascending=False → high → medium → low (giảm dần mức quan trọng)
            "priority":   lambda t: {"low": 0, "medium": 1, "high": 2}.get(t.priority, -1),
    
            "start_date": lambda t: t.start_date or datetime.min,
            "due_date":   lambda t: t.due_date or datetime.min,
            "time_spent": lambda t: t.time_spent_seconds or 0,
        }

        # Stable sort: lặp từ rule ưu tiên THẤP nhất → CAO nhất
        # Python giữ nguyên thứ tự các phần tử bằng nhau (stable)
        # → Rule order=1 sort cuối cùng sẽ là tiêu chí quyết định
        for rule in reversed(rules):
            field     = rule.get("field")
            ascending = rule.get("ascending", True)
            key_fn    = FIELD_MAP.get(field)
            if key_fn is None:
                continue
            try:
                tasks = sorted(tasks, key=key_fn, reverse=not ascending)
                print(f"[SORT] field='{field}' ascending={ascending}")
            except TypeError:
                print(f"[SORT] ⚠️ Không thể sort field '{field}', bỏ qua")

        print(f"[SORT] ✅ {len(rules)} rules applied")

    return [format_task_response(task) for task in tasks]

# 2. POST - Tạo task mới với giá trị mặc định
@router.post("/{projectId}/items", response_model=schemas.TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    projectId: str,
    task: schemas.TaskCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[CREATE TASK] User {current_user.id} creating task in project {projectId}")
    
    verify_project_owner(projectId, current_user.id, db)
    
    task_count = db.query(models.Task).filter(models.Task.project_id == projectId).count()
    now = datetime.now(timezone.utc)

    db_task = models.Task(
        project_id=projectId,
        position=task_count + 1,
        name=task.name or f"Task {task_count + 1}",
        priority=task.priority or 'low',
        start_date=task.start_date or now,
        due_date=task.due_date or now + timedelta(hours=1),
        time_spent_seconds=0,
        notes=task.notes or "",
        progress=0
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
@router.delete("/{projectId}/items/{id}")
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
        # Chỉ ghi lịch sử nếu task chưa được đánh dấu hoàn thành trước đó
        if not db_task.is_completed:
            history = models.TaskHistory(
                user_id=current_user.id,
                project_id=projectId,
                task_name=db_task.name,
                completed_at=datetime.now(timezone.utc),
                due_date=db_task.due_date
            )
            db.add(history)
        
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


# Đã loại bỏ API DELETE /{projectId}/items/{id}/done
# Thay thế bằng logic PATCH { is_completed: true } trên route update_task

# 4. PATCH - Cập nhật vị trí task (Reorder)
@router.patch("/{projectId}/items/reorder", response_model=list[schemas.TaskResponse])
def reorder_tasks(
    projectId: str,
    reorder_data: list[schemas.TaskReorderItem],
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[REORDER TASKS] User {current_user.id} reordering {len(reorder_data)} tasks in project {projectId}")
    
    verify_project_owner(projectId, current_user.id, db)
    
    task_ids = [item.id for item in reorder_data]
    db_tasks = db.query(models.Task).filter(
        models.Task.id.in_(task_ids),
        models.Task.project_id == projectId
    ).all()
    
    db_tasks_dict = {task.id: task for task in db_tasks}
    
    updated_count = 0
    for item in reorder_data:
        db_task = db_tasks_dict.get(item.id)
        if db_task:
            db_task.position = item.position
            updated_count += 1
    
    try:
        db.commit()
        
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
@router.patch("/{projectId}/items/{id}", response_model=schemas.TaskResponse)
def update_task(
    projectId: str,
    id: int,
    task_data: schemas.TaskUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[UPDATE TASK] User {current_user.id} updating task {id} in project {projectId}")
    
    verify_project_owner(projectId, current_user.id, db)
    
    db_task = db.query(models.Task).filter(
        models.Task.id == id,
        models.Task.project_id == projectId
    ).first()
    
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Lưu lại trạng thái is_completed trước khi cập nhật
    was_completed = db_task.is_completed
    
    update_data = task_data.model_dump(exclude_unset=True)
    
    if 'time_spent' in update_data:
        update_data['time_spent_seconds'] = update_data.pop('time_spent')

    if 'process' in update_data:
        update_data['progress'] = update_data.pop('process')

    if 'progress' in update_data:
        update_data['progress'] = max(0, min(100, update_data['progress']))

    for key, value in update_data.items():
        setattr(db_task, key, value)
    
    try:
        # Nếu task được đánh dấu hoàn thành (False -> True)
        is_newly_completed = (not was_completed) and db_task.is_completed
        if is_newly_completed:
            history = models.TaskHistory(
                user_id=current_user.id,
                project_id=projectId,
                task_name=db_task.name,
                completed_at=datetime.now(timezone.utc),
                due_date=db_task.due_date
            )
            db.add(history)

        db.commit()
        db.refresh(db_task)
        
        print(f"[UPDATE TASK] ✅ Updated task {id}")
        return format_task_response(db_task)
    except Exception as e:
        db.rollback()
        print(f"[UPDATE TASK] ❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi cập nhật task: {str(e)}")

# 6. POST - Dự đoán độ khó của task bằng AI
# Rate limit: mỗi task chỉ được estimate lại sau ít nhất ESTIMATE_COOLDOWN_SECONDS giây
ESTIMATE_COOLDOWN_SECONDS = 30

@router.post("/{projectId}/items/{id}/estimate-difficulty", response_model=schemas.TaskResponse)
def estimate_difficulty(
    projectId: str,
    id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    print(f"[ESTIMATE DIFFICULTY] User {current_user.id} estimating task {id} in project {projectId}")

    verify_project_owner(projectId, current_user.id, db)

    db_task = db.query(models.Task).filter(
        models.Task.id == id,
        models.Task.project_id == projectId
    ).first()

    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")

    # ── Rate limit ────────────────────────────────────────────────────────────
    # Nếu task đã được estimate gần đây, trả về giá trị cũ luôn (không gọi AI)
    last_estimated = getattr(db_task, "last_estimated_at", None)
    if last_estimated:
        if last_estimated.tzinfo is None:
            last_estimated = last_estimated.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last_estimated).total_seconds()
        if elapsed < ESTIMATE_COOLDOWN_SECONDS:
            wait = int(ESTIMATE_COOLDOWN_SECONDS - elapsed)
            print(f"[ESTIMATE DIFFICULTY] ⏳ Rate limited — task {id} estimated {int(elapsed)}s ago, cooldown {wait}s left")
            raise HTTPException(
                status_code=429,
                detail=f"Task vừa được estimate {int(elapsed)}s trước. Vui lòng chờ thêm {wait}s."
            )

    # ── Build context ─────────────────────────────────────────────────────────
    # Lấy TẤT CẢ task khác trong project (cả completed lẫn active) để AI có
    # bức tranh đầy đủ hơn về độ phức tạp chung của project.
    context_tasks = db.query(models.Task).filter(
        models.Task.project_id == projectId,
        models.Task.id != id,
    ).order_by(models.Task.position.asc()).all()

    context_lines = []
    for t in context_tasks:
        status_label = "completed" if t.is_completed else "active"
        priority_label = t.priority or "low"
        time_str = f"{t.time_spent_seconds}s" if t.time_spent_seconds else "not started"
        context_lines.append(
            f"- [{status_label}] {t.name} | priority: {priority_label} | time_spent: {time_str}"
        )

    context_str = "\n".join(context_lines)

    # Lấy tên project để truyền vào AI làm domain context
    project_item = db.query(models.Item).filter(models.Item.id == projectId).first()
    project_name = project_item.name if project_item else ""

    print(f"[ESTIMATE DIFFICULTY] Task: '{db_task.name}' | Project: '{project_name}' | Context tasks: {len(context_lines)}")

    # ── Gọi AI ────────────────────────────────────────────────────────────────
    from chatbot import estimate_task_difficulty
    new_difficulty = estimate_task_difficulty(db_task.name, context_str, project_name)

    # ── Lưu DB ───────────────────────────────────────────────────────────────
    db_task.difficulty_rating = new_difficulty
    if hasattr(db_task, "last_estimated_at"):
        db_task.last_estimated_at = datetime.now(timezone.utc)

    try:
        db.commit()
        db.refresh(db_task)
        print(f"[ESTIMATE DIFFICULTY] ✅ Task {id} ('{db_task.name}') → difficulty {new_difficulty}/5")
        return format_task_response(db_task)
    except Exception as e:
        db.rollback()
        print(f"[ESTIMATE DIFFICULTY] ❌ DB error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu độ khó: {str(e)}")