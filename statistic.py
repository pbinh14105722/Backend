from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from datetime import datetime, timezone, timedelta, date
from collections import defaultdict
import hashlib
import models, database
from utils import SECRET_KEY, ALGORITHM

router = APIRouter(prefix="/statistic")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


# ========== AUTH ==========
def get_current_user(
    db: Session = Depends(database.get_db),
    token: str = Depends(oauth2_scheme)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
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


# ========== HELPERS ==========

def get_week_range(ref: date):
    start = ref - timedelta(days=ref.weekday())
    end = start + timedelta(days=6)
    return start, end

def get_month_range(ref: date):
    start = ref.replace(day=1)
    if ref.month == 12:
        end = ref.replace(year=ref.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = ref.replace(month=ref.month + 1, day=1) - timedelta(days=1)
    return start, end

def get_year_range(ref: date):
    return ref.replace(month=1, day=1), ref.replace(month=12, day=31)

def days_in_range(start: date, end: date):
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]

def to_date(dt):
    """Convert datetime sang date, handle cả naive và aware"""
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt
    if dt.tzinfo:
        return dt.date()
    return dt.replace(tzinfo=timezone.utc).date()

def compute_streak(active_days: set, period_start: date, period_end: date):
    days = days_in_range(period_start, period_end)
    best = 0
    current = 0
    for d in days:
        if d in active_days:
            current += 1
            best = max(best, current)
        else:
            current = 0
    streak = 0
    for d in reversed(days):
        if d in active_days:
            streak += 1
        else:
            break
    return streak, best

def get_user_projects(user_id: int, db: Session):
    return db.query(models.Item).filter(
        models.Item.owner_id == user_id,
        models.Item.type == 'PROJECT'
    ).all()


# ========== SUMMARY ==========

# @router.get("/summary")
# def get_summary(
#     db: Session = Depends(database.get_db),
#     current_user: models.User = Depends(get_current_user)
# ):
#     try:
#         today = datetime.now(timezone.utc).date()
#         user_id = current_user.id

#         all_history = db.query(models.TaskHistory).filter(
#             models.TaskHistory.user_id == user_id
#         ).all()

#         all_sessions = db.query(models.PomodoroSession).filter(
#             models.PomodoroSession.user_id == user_id,
#             models.PomodoroSession.mode == 'focus'
#         ).all()

#         projects = get_user_projects(user_id, db)
#         project_ids = [p.id for p in projects]
#         all_tasks = db.query(models.Task).filter(
#             models.Task.project_id.in_(project_ids)
#         ).all() if project_ids else []

#         def build_dataset(period_start, period_end, prev_start, prev_end, group_by):
#             period_days = days_in_range(period_start, period_end)

#             tasks_by_day = defaultdict(int)
#             focus_by_day = defaultdict(float)
#             pomo_by_day = defaultdict(int)

#             for h in all_history:
#                 d = to_date(h.completed_at)
#                 if period_start <= d <= period_end:
#                     tasks_by_day[d] += 1

#             for s in all_sessions:
#                 d = to_date(s.completed_at)
#                 if period_start <= d <= period_end:
#                     focus_by_day[d] += s.duration / 3600
#                     pomo_by_day[d] += 1

#             if group_by == 'year':
#                 tasks_arr, focus_arr, pomo_arr = [], [], []
#                 for month in range(1, 13):
#                     t = sum(v for k, v in tasks_by_day.items() if k.month == month and k.year == period_start.year)
#                     f = sum(v for k, v in focus_by_day.items() if k.month == month and k.year == period_start.year)
#                     p = sum(v for k, v in pomo_by_day.items() if k.month == month and k.year == period_start.year)
#                     tasks_arr.append(t)
#                     focus_arr.append(round(f, 1))
#                     pomo_arr.append(p)
#             else:
#                 tasks_arr = [tasks_by_day.get(d, 0) for d in period_days]
#                 focus_arr = [round(focus_by_day.get(d, 0.0), 1) for d in period_days]
#                 pomo_arr = [pomo_by_day.get(d, 0) for d in period_days]

#             done = sum(1 for h in all_history if period_start <= to_date(h.completed_at) <= period_end)
#             created = done + len(all_tasks)

#             active_days = set(k for k, v in tasks_by_day.items() if v > 0)
#             streak, best_streak = compute_streak(active_days, period_start, period_end)

#             prev_tasks = sum(1 for h in all_history if prev_start <= to_date(h.completed_at) <= prev_end)
#             prev_focus = sum(s.duration / 3600 for s in all_sessions if prev_start <= to_date(s.completed_at) <= prev_end)
#             prev_pomo = sum(1 for s in all_sessions if prev_start <= to_date(s.completed_at) <= prev_end)

#             return {
#                 "tasks": tasks_arr,
#                 "focus": focus_arr,
#                 "pomo": pomo_arr,
#                 "created": created,
#                 "done": done,
#                 "streak": streak,
#                 "bestStreak": best_streak,
#                 "prevTasks": prev_tasks,
#                 "prevFocus": round(prev_focus, 1),
#                 "prevPomo": prev_pomo,
#             }

#         w_start, w_end = get_week_range(today)
#         pw_start = w_start - timedelta(weeks=1)
#         pw_end = w_end - timedelta(weeks=1)

#         m_start, m_end = get_month_range(today)
#         pm_start, pm_end = get_month_range(m_start - timedelta(days=1))

#         y_start, y_end = get_year_range(today)
#         py_start, py_end = get_year_range(date(today.year - 1, 1, 1))

#         return {
#             "week": build_dataset(w_start, w_end, pw_start, pw_end, 'week'),
#             "month": build_dataset(m_start, m_end, pm_start, pm_end, 'month'),
#             "year": build_dataset(y_start, y_end, py_start, py_end, 'year'),
#         }

#     except Exception as e:
#         print(f"[SUMMARY] ❌ {str(e)}")
#         raise HTTPException(status_code=500, detail="Failed to generate summary data")

@router.get("/summary")
def get_summary(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    try:
        today = datetime.now(timezone.utc).date()
        user_id = current_user.id

        all_history = db.query(models.TaskHistory).filter(
            models.TaskHistory.user_id == user_id
        ).all()

        all_sessions = db.query(models.PomodoroSession).filter(
            models.PomodoroSession.user_id == user_id,
            models.PomodoroSession.mode == 'focus'
        ).all()

        projects = get_user_projects(user_id, db)
        project_ids = [p.id for p in projects]
        all_tasks = db.query(models.Task).filter(
            models.Task.project_id.in_(project_ids)
        ).all() if project_ids else []

        def build_dataset(period_start, period_end, prev_start, prev_end, group_by):
            period_days = days_in_range(period_start, period_end)

            tasks_by_day = defaultdict(int)
            focus_by_day = defaultdict(float)
            pomo_by_day = defaultdict(int)

            for h in all_history:
                d = to_date(h.completed_at)
                if period_start <= d <= period_end:
                    tasks_by_day[d] += 1

            for s in all_sessions:
                d = to_date(s.completed_at)
                if period_start <= d <= period_end:
                    focus_by_day[d] += s.duration / 3600
                    pomo_by_day[d] += 1

            if group_by == 'year':
                tasks_arr, focus_arr, pomo_arr = [], [], []
                for month in range(1, 13):
                    t = sum(v for k, v in tasks_by_day.items() if k.month == month and k.year == period_start.year)
                    f = sum(v for k, v in focus_by_day.items() if k.month == month and k.year == period_start.year)
                    p = sum(v for k, v in pomo_by_day.items() if k.month == month and k.year == period_start.year)
                    tasks_arr.append(t)
                    focus_arr.append(round(f, 2))  # ← sửa 1→2
                    pomo_arr.append(p)
            else:
                tasks_arr = [tasks_by_day.get(d, 0) for d in period_days]
                focus_arr = [round(focus_by_day.get(d, 0.0), 2) for d in period_days]  # ← sửa 1→2
                pomo_arr = [pomo_by_day.get(d, 0) for d in period_days]

            done = sum(1 for h in all_history if period_start <= to_date(h.completed_at) <= period_end)
            created = done + len(all_tasks)

            active_days = set(k for k, v in tasks_by_day.items() if v > 0)
            streak, best_streak = compute_streak(active_days, period_start, period_end)

            prev_tasks = sum(1 for h in all_history if prev_start <= to_date(h.completed_at) <= prev_end)
            prev_focus = sum(s.duration / 3600 for s in all_sessions if prev_start <= to_date(s.completed_at) <= prev_end)
            prev_pomo = sum(1 for s in all_sessions if prev_start <= to_date(s.completed_at) <= prev_end)

            return {
                "tasks": tasks_arr,
                "focus": focus_arr,
                "pomo": pomo_arr,
                "created": created,
                "done": done,
                "streak": streak,
                "bestStreak": best_streak,
                "prevTasks": prev_tasks,
                "prevFocus": round(prev_focus, 2),  # ← sửa 1→2
                "prevPomo": prev_pomo,
            }

        w_start, w_end = get_week_range(today)
        pw_start = w_start - timedelta(weeks=1)
        pw_end = w_end - timedelta(weeks=1)

        m_start, m_end = get_month_range(today)
        pm_start, pm_end = get_month_range(m_start - timedelta(days=1))

        y_start, y_end = get_year_range(today)
        py_start, py_end = get_year_range(date(today.year - 1, 1, 1))

        return {
            "week": build_dataset(w_start, w_end, pw_start, pw_end, 'week'),
            "month": build_dataset(m_start, m_end, pm_start, pm_end, 'month'),
            "year": build_dataset(y_start, y_end, py_start, py_end, 'year'),
        }

    except Exception as e:
        print(f"[SUMMARY] ❌ {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate summary data")

# ========== DONUT CHART ==========

@router.get("/donut_chart")
def get_donut_chart(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    try:
        today = datetime.now(timezone.utc).date()
        user_id = current_user.id

        projects = get_user_projects(user_id, db)
        project_map = {p.id: p for p in projects}
        project_ids = list(project_map.keys())

        all_history = db.query(models.TaskHistory).filter(
            models.TaskHistory.user_id == user_id,
            models.TaskHistory.project_id.in_(project_ids)
        ).all() if project_ids else []

        all_sessions = db.query(models.PomodoroSession).filter(
            models.PomodoroSession.user_id == user_id,
            models.PomodoroSession.mode == 'focus'
        ).all()

        # Cache task->project mapping
        task_project_cache = {}
        def get_task_project(task_id):
            if task_id not in task_project_cache:
                task = db.query(models.Task).filter(models.Task.id == task_id).first()
                task_project_cache[task_id] = task.project_id if task else None
            return task_project_cache[task_id]

        def build_donut(period_start, period_end):
            tasks_by_project = defaultdict(int)
            focus_by_project = defaultdict(float)

            for h in all_history:
                d = to_date(h.completed_at)
                if period_start <= d <= period_end:
                    tasks_by_project[h.project_id] += 1

            for s in all_sessions:
                if not s.task_id:
                    continue
                d = to_date(s.completed_at)
                if period_start <= d <= period_end:
                    pid = get_task_project(s.task_id)
                    if pid:
                        focus_by_project[pid] += s.duration / 3600

            def to_items(data, is_focus=False):
                items = []
                for pid, val in data.items():
                    if val <= 0:
                        continue
                    project = project_map.get(pid)
                    items.append({
                        "name": project.name if project else "Unknown",
                        "value": round(val, 1) if is_focus else int(val),
                        "color": (project.color if project and project.color else "#6366f1"),
                    })
                items.sort(key=lambda x: x["value"], reverse=True)
                if len(items) > 5:
                    top = items[:5]
                    other_val = sum(x["value"] for x in items[5:])
                    top.append({
                        "name": "Other",
                        "value": round(other_val, 1) if is_focus else int(other_val),
                        "color": "#ffffff"
                    })
                    return top
                return items

            return {
                "tasks": to_items(tasks_by_project, False),
                "focus": to_items(focus_by_project, True),
            }

        w_start, w_end = get_week_range(today)
        m_start, m_end = get_month_range(today)
        y_start, y_end = get_year_range(today)

        return {
            "week": build_donut(w_start, w_end),
            "month": build_donut(m_start, m_end),
            "year": build_donut(y_start, y_end),
        }

    except Exception as e:
        print(f"[DONUT] ❌ {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate donut chart data")


# ========== HEATMAP ==========

@router.get("/heatmap")
def get_heatmap(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    try:
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=364)
        user_id = current_user.id

        all_history = db.query(models.TaskHistory).filter(
            models.TaskHistory.user_id == user_id
        ).all()

        all_sessions = db.query(models.PomodoroSession).filter(
            models.PomodoroSession.user_id == user_id,
            models.PomodoroSession.mode == 'focus'
        ).all()

        tasks_by_day = defaultdict(int)
        focus_by_day = defaultdict(float)

        for h in all_history:
            d = to_date(h.completed_at)
            if start <= d <= today:
                tasks_by_day[d] += 1

        for s in all_sessions:
            d = to_date(s.completed_at)
            if start <= d <= today:
                focus_by_day[d] += s.duration / 3600

        all_days = days_in_range(start, today)
        tasks_result = {}
        focus_result = {}

        for d in all_days:
            key = d.strftime("%Y-%m-%d")
            tasks_result[key] = tasks_by_day.get(d, 0)
            focus_result[key] = round(focus_by_day.get(d, 0.0), 1)

        return {
            "tasks": tasks_result,
            "focus": focus_result,
        }

    except Exception as e:
        print(f"[HEATMAP] ❌ {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate heatmap data")


# ========== LINE CHART (placeholder) ==========

@router.get("/line_chart")
def get_line_chart(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Trả về data giống summary nhưng chỉ focus array
    # Cần tài liệu API cụ thể để implement đúng
    try:
        today = datetime.now(timezone.utc).date()
        user_id = current_user.id

        all_sessions = db.query(models.PomodoroSession).filter(
            models.PomodoroSession.user_id == user_id,
            models.PomodoroSession.mode == 'focus'
        ).all()

        def build_focus_line(period_start, period_end, group_by):
            focus_by_day = defaultdict(float)
            for s in all_sessions:
                d = to_date(s.completed_at)
                if period_start <= d <= period_end:
                    focus_by_day[d] += s.duration / 3600

            if group_by == 'year':
                return [round(sum(v for k, v in focus_by_day.items() if k.month == m and k.year == period_start.year), 1) for m in range(1, 13)]
            else:
                return [round(focus_by_day.get(d, 0.0), 1) for d in days_in_range(period_start, period_end)]

        w_start, w_end = get_week_range(today)
        m_start, m_end = get_month_range(today)
        y_start, y_end = get_year_range(today)

        return {
            "week": build_focus_line(w_start, w_end, 'week'),
            "month": build_focus_line(m_start, m_end, 'month'),
            "year": build_focus_line(y_start, y_end, 'year'),
        }

    except Exception as e:
        print(f"[LINE CHART] ❌ {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate line chart data")
