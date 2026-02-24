from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from datetime import datetime, timezone, timedelta, date
from collections import defaultdict
import hashlib
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
    """Trả về (start, end) của tuần chứa ref (Thứ 2 → CN)"""
    start = ref - timedelta(days=ref.weekday())
    end = start + timedelta(days=6)
    return start, end

def get_month_range(ref: date):
    """Trả về (start, end) của tháng chứa ref"""
    start = ref.replace(day=1)
    if ref.month == 12:
        end = ref.replace(year=ref.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = ref.replace(month=ref.month + 1, day=1) - timedelta(days=1)
    return start, end

def get_year_range(ref: date):
    """Trả về (start, end) của năm chứa ref"""
    return ref.replace(month=1, day=1), ref.replace(month=12, day=31)

def days_in_range(start: date, end: date):
    """Sinh danh sách ngày từ start đến end"""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]

def compute_streak(active_days: set, period_start: date, period_end: date):
    """Tính streak và bestStreak trong khoảng period, cắt bỏ streak từ kỳ trước"""
    days = days_in_range(period_start, period_end)
    
    streak = 0
    best = 0
    current = 0

    for d in days:
        if d in active_days:
            current += 1
            best = max(best, current)
        else:
            current = 0

    # streak hiện tại: đếm ngược từ cuối period
    streak = 0
    for d in reversed(days):
        if d in active_days:
            streak += 1
        else:
            break

    return streak, best

def get_project_color(project_id: str, db: Session):
    """Lấy màu của project từ DB"""
    item = db.query(models.Item).filter(models.Item.id == project_id).first()
    if item and item.color:
        return item.color
    # Fallback: generate màu theo hash
    h = int(hashlib.md5(project_id.encode()).hexdigest()[:6], 16)
    return f"#{h:06x}"

def get_user_projects(user_id: int, db: Session):
    """Lấy tất cả projects của user"""
    return db.query(models.Item).filter(
        models.Item.owner_id == user_id,
        models.Item.type == 'PROJECT'
    ).all()


# ========== SUMMARY API ==========

@router.get("/statistics/summary")
def get_summary(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    try:
        today = datetime.now(timezone.utc).date()
        user_id = current_user.id

        # Lấy tất cả task history của user
        all_history = db.query(models.TaskHistory).filter(
            models.TaskHistory.user_id == user_id
        ).all()

        # Lấy tất cả pomodoro sessions của user
        all_sessions = db.query(models.PomodoroSession).filter(
            models.PomodoroSession.user_id == user_id,
            models.PomodoroSession.mode == 'focus'
        ).all()

        # Lấy tất cả tasks hiện tại (chưa done)
        projects = get_user_projects(user_id, db)
        project_ids = [p.id for p in projects]
        all_tasks = db.query(models.Task).filter(
            models.Task.project_id.in_(project_ids)
        ).all() if project_ids else []

        def build_dataset(period_start: date, period_end: date, prev_start: date, prev_end: date, group_by: str):
            # Days list trong period
            period_days = days_in_range(period_start, period_end)
            n = len(period_days)

            # Tasks done theo ngày (dùng task_history)
            tasks_by_day = defaultdict(int)
            focus_by_day = defaultdict(float)
            pomo_by_day = defaultdict(int)

            for h in all_history:
                d = h.completed_at.date() if h.completed_at.tzinfo else h.completed_at.replace(tzinfo=timezone.utc).date()
                if period_start <= d <= period_end:
                    tasks_by_day[d] += 1

            for s in all_sessions:
                d = s.completed_at.date() if s.completed_at.tzinfo else s.completed_at.replace(tzinfo=timezone.utc).date()
                if period_start <= d <= period_end:
                    focus_by_day[d] += s.duration / 3600
                    pomo_by_day[d] += 1

            # Nếu group_by year thì group theo tháng
            if group_by == 'year':
                tasks_arr = []
                focus_arr = []
                pomo_arr = []
                for month in range(1, 13):
                    t = sum(v for k, v in tasks_by_day.items() if k.month == month and k.year == period_start.year)
                    f = sum(v for k, v in focus_by_day.items() if k.month == month and k.year == period_start.year)
                    p = sum(v for k, v in pomo_by_day.items() if k.month == month and k.year == period_start.year)
                    tasks_arr.append(t)
                    focus_arr.append(round(f, 1))
                    pomo_arr.append(p)
            else:
                tasks_arr = [tasks_by_day.get(d, 0) for d in period_days]
                focus_arr = [round(focus_by_day.get(d, 0.0), 1) for d in period_days]
                pomo_arr = [pomo_by_day.get(d, 0) for d in period_days]

            # Totals
            created = sum(1 for t in all_tasks if True)  # tasks hiện có
            done = sum(1 for h in all_history if period_start <= (h.completed_at.date() if h.completed_at.tzinfo else h.completed_at.replace(tzinfo=timezone.utc).date()) <= period_end)
            created_in_period = done + len([t for t in all_tasks if True])  # approximate

            # Streak
            active_days = set(k for k, v in tasks_by_day.items() if v > 0)
            streak, best_streak = compute_streak(active_days, period_start, period_end)

            # Prev period
            prev_tasks = sum(1 for h in all_history if prev_start <= (h.completed_at.date() if h.completed_at.tzinfo else h.completed_at.replace(tzinfo=timezone.utc).date()) <= prev_end)
            prev_focus = sum(s.duration / 3600 for s in all_sessions if prev_start <= (s.completed_at.date() if s.completed_at.tzinfo else s.completed_at.replace(tzinfo=timezone.utc).date()) <= prev_end)
            prev_pomo = sum(1 for s in all_sessions if prev_start <= (s.completed_at.date() if s.completed_at.tzinfo else s.completed_at.replace(tzinfo=timezone.utc).date()) <= prev_end)

            return {
                "tasks": tasks_arr,
                "focus": focus_arr,
                "pomo": pomo_arr,
                "created": created_in_period,
                "done": done,
                "streak": streak,
                "bestStreak": best_streak,
                "prevTasks": prev_tasks,
                "prevFocus": round(prev_focus, 1),
                "prevPomo": prev_pomo,
            }

        # Week
        w_start, w_end = get_week_range(today)
        pw_start = w_start - timedelta(weeks=1)
        pw_end = w_end - timedelta(weeks=1)
        week_data = build_dataset(w_start, w_end, pw_start, pw_end, 'week')

        # Month
        m_start, m_end = get_month_range(today)
        pm_start, pm_end = get_month_range((m_start - timedelta(days=1)))
        month_data = build_dataset(m_start, m_end, pm_start, pm_end, 'month')

        # Year
        y_start, y_end = get_year_range(today)
        py_start, py_end = get_year_range(date(today.year - 1, 1, 1))
        year_data = build_dataset(y_start, y_end, py_start, py_end, 'year')

        return {
            "week": week_data,
            "month": month_data,
            "year": year_data,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate summary data")


# ========== DONUT CHART API ==========

@router.get("/statistics/donut_chart")
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

        def build_donut(period_start: date, period_end: date):
            tasks_by_project = defaultdict(int)
            focus_by_project = defaultdict(float)

            for h in all_history:
                d = h.completed_at.date() if h.completed_at.tzinfo else h.completed_at.replace(tzinfo=timezone.utc).date()
                if period_start <= d <= period_end:
                    tasks_by_project[h.project_id] += 1

            for s in all_sessions:
                if not s.task_id:
                    continue
                d = s.completed_at.date() if s.completed_at.tzinfo else s.completed_at.replace(tzinfo=timezone.utc).date()
                if period_start <= d <= period_end:
                    # Tìm project của task
                    task = db.query(models.Task).filter(models.Task.id == s.task_id).first()
                    if task:
                        focus_by_project[task.project_id] += s.duration / 3600

            def to_donut_items(data: dict, is_focus=False):
                items = []
                for pid, val in data.items():
                    if val <= 0:
                        continue
                    project = project_map.get(pid)
                    name = project.name if project else "Unknown"
                    color = (project.color if project and project.color else "#6366f1")
                    items.append({
                        "name": name,
                        "value": round(val, 1) if is_focus else int(val),
                        "color": color
                    })

                # Sort giảm dần
                items.sort(key=lambda x: x["value"], reverse=True)

                # Gộp "Other" nếu > 5
                if len(items) > 5:
                    top = items[:5]
                    others = items[5:]
                    other_val = sum(x["value"] for x in others)
                    top.append({
                        "name": "Other",
                        "value": round(other_val, 1) if is_focus else int(other_val),
                        "color": "#ffffff"
                    })
                    return top
                return items

            return {
                "tasks": to_donut_items(tasks_by_project, False),
                "focus": to_donut_items(focus_by_project, True),
            }

        # Week
        w_start, w_end = get_week_range(today)
        # Month
        m_start, m_end = get_month_range(today)
        # Year
        y_start, y_end = get_year_range(today)

        return {
            "week": build_donut(w_start, w_end),
            "month": build_donut(m_start, m_end),
            "year": build_donut(y_start, y_end),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate donut chart data")


# ========== HEATMAP API ==========

@router.get("/statistics/heatmap")
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

        # Aggregate theo ngày
        tasks_by_day = defaultdict(int)
        focus_by_day = defaultdict(float)

        for h in all_history:
            d = h.completed_at.date() if h.completed_at.tzinfo else h.completed_at.replace(tzinfo=timezone.utc).date()
            if start <= d <= today:
                tasks_by_day[d] += 1

        for s in all_sessions:
            d = s.completed_at.date() if s.completed_at.tzinfo else s.completed_at.replace(tzinfo=timezone.utc).date()
            if start <= d <= today:
                focus_by_day[d] += s.duration / 3600

        # Build response — đủ 365 ngày, không thiếu
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
        raise HTTPException(status_code=500, detail="Failed to generate heatmap data")