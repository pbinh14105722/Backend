from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from typing import Optional, List, Literal, Union, Any
from datetime import datetime
import re

# ============ ITEM SCHEMAS (FOLDER/PROJECT) ============
class ItemBase(BaseModel):
    name: str
    type: str
    parent_id: Optional[str] = None
    position: int = 0
    color: str =  "#ffffff"
    expanded: bool = False

class ItemCreate(ItemBase):
    pass

class ItemBatchUpdate(ItemBase):
    id: str
    name: str
    type: str
    parent_id: Optional[str] = None
    position: int
    color: str = "#ffffff"
    expanded: bool = False

class ItemUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    expanded: Optional[bool] = None
    parent_id: Optional[str] = None
    position: Optional[int] = None

class ItemResponse(ItemBase):
    id: str
    name: str
    type: str
    parent_id: Optional[str] = None
    position: int
    color: str
    expanded: bool
    owner_id: int

    class Config:
        from_attributes = True

# ============ USER SCHEMAS ============
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    class Config:
        from_attributes = True

class UserIdResponse(BaseModel):
    user_id: int

class AuthResponse(BaseModel):
    message: str
    access_token: str
    token_type: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UpdatePassword(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)
    confirm_password: str

# ============ TASK SCHEMAS =====================================
class TaskCreate(BaseModel):
    """Tạo task - Frontend có thể gửi hoặc không, backend tự điền mặc định nếu thiếu"""
    name: Optional[str] = None
    priority: Optional[str] = None
    start_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    notes: Optional[str] = None

    @field_validator('priority')
    @classmethod
    def validate_priority(cls, v):
        if v and v not in ['high', 'medium', 'low']:
            raise ValueError("Priority must be 'high', 'medium', or 'low'")
        return v

class TaskUpdate(BaseModel):
    name: Optional[str] = None
    priority: Optional[str] = None
    start_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    time_spent: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    process: Optional[int] = Field(default=None, ge=0, le=100)

    @field_validator('priority')
    @classmethod
    def validate_priority(cls, v):
        if v and v not in ['high', 'medium', 'low']:
            raise ValueError("Priority must be 'high', 'medium', or 'low'")
        return v

class TaskReorderItem(BaseModel):
    id: int
    position: int

class TaskResponse(BaseModel):
    id: int
    position: int
    name: str
    priority: str
    start_date: str
    due_date: str
    time_spent: int
    notes: str
    progress: int = 0

    class Config:
        from_attributes = True


# ============================================================
# ============ SORT SCHEMAS ==================================
# ============================================================

SortField = Literal["name", "priority", "start_date", "due_date", "time_spent", "create_date"]


class SortRule(BaseModel):
    """
    Một tiêu chí sort.
    { "field": "priority", "order": 1, "ascending": false }
    """
    field: SortField
    order: int = Field(..., ge=1, description="Thứ tự ưu tiên (1 = cao nhất)")
    ascending: bool = Field(..., description="true = tăng dần, false = giảm dần")


def validate_sort_rules(rules: List[SortRule]) -> List[SortRule]:
    """Validate toàn bộ danh sách rules: không trùng field, không trùng order, tối đa 5"""
    if len(rules) > 5:
        raise ValueError("Tối đa 5 tiêu chí sort")

    fields = [r.field for r in rules]
    if len(fields) != len(set(fields)):
        raise ValueError("Không được sort trùng field")

    orders = [r.order for r in rules]
    if len(orders) != len(set(orders)):
        raise ValueError("Thứ tự ưu tiên (order) không được trùng nhau")

    return rules


# ============================================================
# ============ FILTER SCHEMAS ================================
# ============================================================

FilterField = Literal["name", "priority", "start_date", "due_date", "time_spent", "create_date"]
FilterLogic = Literal["and", "or"]

VALID_OPERATORS: dict[str, list[str]] = {
    "name":        ["eq", "not_eq", "contains", "not_contains"],
    "priority":    ["in", "not_in"],
    "start_date":  ["eq", "gt", "gte", "lt", "lte", "between"],
    "due_date":    ["eq", "gt", "gte", "lt", "lte", "between"],
    "create_date": ["eq", "gt", "gte", "lt", "lte", "between"],
    "time_spent":  ["eq", "gt", "gte", "lt", "lte", "between"],
}

VALID_PRIORITIES = {"high", "medium", "low"}
TIME_PATTERN = re.compile(r"^\d{2}:\d{2}:\d{2}$")


def _validate_iso8601(value: str, label: str):
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{label} phải đúng định dạng ISO 8601 (ví dụ: 2026-01-15T00:00:00.000Z)")


def _validate_time_spent(value: str, label: str = "time_spent"):
    if not TIME_PATTERN.match(str(value)):
        raise ValueError(f"{label} phải đúng định dạng HH:mm:ss (ví dụ: 02:30:00)")


def _time_to_seconds(t: str) -> int:
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


class FilterRule(BaseModel):
    """
    Một tiêu chí filter.
    - Thường:  { "field": "name", "operator": "contains", "value": "sprint" }
    - between: { "field": "due_date", "operator": "between", "value": {"from": "...", "to": "..."} }
    """
    field: FilterField
    operator: str
    value: Optional[Any] = None

    @model_validator(mode="after")
    def validate_rule(self):
        field    = self.field
        operator = self.operator
        value    = self.value

        # 1. Operator có hợp lệ với field không
        if operator not in VALID_OPERATORS[field]:
            valid = ", ".join(VALID_OPERATORS[field])
            raise ValueError(
                f"Operator '{operator}' không hợp lệ cho field '{field}'. Hợp lệ: {valid}"
            )

        # 2. between → value phải là {"from": ..., "to": ...}
        if operator == "between":
            if not isinstance(value, dict) or "from" not in value or "to" not in value:
                raise ValueError(
                    "Operator 'between' cần value là object: {\"from\": \"...\", \"to\": \"...\"}"
                )
            v_from, v_to = value["from"], value["to"]

            if field in ("start_date", "due_date", "create_date"):
                _validate_iso8601(str(v_from), "from")
                _validate_iso8601(str(v_to), "to")
                dt_from = datetime.fromisoformat(str(v_from).replace("Z", "+00:00"))
                dt_to   = datetime.fromisoformat(str(v_to).replace("Z", "+00:00"))
                if dt_from > dt_to:
                    raise ValueError("'from' phải nhỏ hơn hoặc bằng 'to'")

            if field == "time_spent":
                _validate_time_spent(str(v_from), "from")
                _validate_time_spent(str(v_to), "to")
                if _time_to_seconds(str(v_from)) > _time_to_seconds(str(v_to)):
                    raise ValueError("'from' phải nhỏ hơn hoặc bằng 'to'")

            return self

        # 3. Các operator khác → bắt buộc có value
        if value is None:
            raise ValueError(f"Operator '{operator}' cần có 'value'")

        # 4. Validate value theo field
        if field == "priority":
            if not isinstance(value, list):
                raise ValueError("priority cần value là danh sách, ví dụ: [\"high\", \"low\"]")
            invalid = set(value) - VALID_PRIORITIES
            if invalid:
                raise ValueError(
                    f"Giá trị priority không hợp lệ: {invalid}. Chỉ chấp nhận: high, medium, low"
                )

        if field in ("start_date", "due_date", "create_date"):
            _validate_iso8601(str(value), field)

        if field == "time_spent":
            _validate_time_spent(str(value))

        return self


class FilterSettingsUpdate(BaseModel):
    """
    PUT /project/{projectId}/filter
    - filters=[]  → tắt filter
    - logic mặc định "and" nếu không truyền
    """
    logic: FilterLogic = Field(default="and")
    filters: List[FilterRule] = Field(...)

    @model_validator(mode="after")
    def validate_filters(self):
        if len(self.filters) > 10:
            raise ValueError("Tối đa 10 tiêu chí filter")
        return self


class FilterSettingsResponse(BaseModel):
    logic: str
    filters: List[FilterRule]

# ============================================================
# ============ ROADMAP SCHEMAS ===============================
# ============================================================

class RoadmapCreate(BaseModel):
    """POST /roadmap — Tạo roadmap mới"""
    name: str = Field(default="Roadmap 1")
    nodes: dict = Field(default={})
    edges: list = Field(default=[])
    nCnt: int = Field(default=0, ge=0)
    panX: float = Field(default=0.0)
    panY: float = Field(default=0.0)
    zoom: float = Field(default=1.0, ge=0.15, le=4.0)


class RoadmapUpdate(BaseModel):
    """
    PATCH /roadmap/{id} — Partial update, 2 trường hợp:
    - Đổi tên: chỉ gửi name
    - Lưu canvas: gửi nodes, edges, nCnt, panX, panY, zoom
    Tất cả đều Optional vì chỉ update field nào được gửi
    """
    name: Optional[str] = None
    nodes: Optional[dict] = None
    edges: Optional[list] = None
    nCnt: Optional[int] = Field(default=None, ge=0)
    panX: Optional[float] = None
    panY: Optional[float] = None
    zoom: Optional[float] = Field(default=None, ge=0.15, le=4.0)


class RoadmapResponse(BaseModel):
    """Response trả về frontend — đúng field name frontend đọc"""
    id: str
    name: str
    nodes: dict
    edges: list
    nCnt: int
    panX: float
    panY: float
    zoom: float

    class Config:
        from_attributes = True

# ============================================================
# ============ CHATBOT SCHEMAS ===============================
# ============================================================

from typing import Any

# ---- Request schemas ----

class ChatMessageSend(BaseModel):
    """POST /chatbot — Gửi tin nhắn"""
    message: str = Field(..., min_length=1, description="Nội dung tin nhắn, không được rỗng")
    project_id: Optional[str] = Field(None, description="ID của project đang mở (dùng cho auto-apply filter)")

class TaskBreakdownRequest(BaseModel):
    """POST /chatbot/breakdown — Yêu cầu chia nhỏ task"""
    task_id: int = Field(..., description="ID của task cần chia nhỏ")

class TaskBreakdownResponse(BaseModel):
    """Phản hồi sau khi chia nhỏ task"""
    new_tasks_count: int
    project_id: str
    message: str


# ---- Response schemas ----

class ChatMessageResponse(BaseModel):
    """Một tin nhắn trong lịch sử"""
    id: str
    role: str                        # "user" | "assistant"
    message: str
    type: Optional[str] = None       # "roadmap" | "folder_tree" | "statistic" | "filter" | None
    data: Optional[Any] = None       # object | None
    created_at: str                  # ISO 8601

    class Config:
        from_attributes = True


class ChatHistoryResponse(BaseModel):
    """GET /chatbot/history"""
    history: List[ChatMessageResponse]
    total: int
    limit: int = 50


class ChatbotResponse(BaseModel):
    """GET /chatbot — Phản hồi mới nhất của AI"""
    message: str
    type: Optional[str] = None
    data: Optional[Any] = None


# ---- Save schemas ----

class TreeItem(BaseModel):
    """Một item trong folder tree do AI tạo"""
    id: str                          # AI-generated, backend bỏ qua khi lưu
    name: str
    type: str                        # "FOLDER" | "PROJECT" | "TASK"
    position: int = Field(..., ge=0)
    color: Optional[str] = None
    parent_id: Optional[str] = None  # Dùng cho FOLDER/PROJECT
    project_id: Optional[str] = None # Dùng cho TASK
    priority: Optional[str] = None   # Dùng cho TASK
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    time_spent: Optional[int] = 0
    process: Optional[int] = 0
    notes: Optional[str] = None


class SaveFolderTreeRequest(BaseModel):
    """POST /chatbot/save/folder-tree"""
    title: str
    tree: List[TreeItem] = Field(..., min_length=1)


class SaveRoadmapRequest(BaseModel):
    """POST /chatbot/save/roadmap"""
    title: str
    id: str                          # AI-generated, backend bỏ qua
    name: str
    nodes: dict = Field(default={})
    edges: list = Field(default=[])
    nCnt: int = Field(default=0, ge=0)
    panX: float = Field(default=0.0)
    panY: float = Field(default=0.0)
    zoom: float = Field(default=1.0, ge=0.15, le=4.0)

class CreatedItemResponse(ItemResponse):
    ai_id: Optional[str] = None

class SaveRoadmapResponse(BaseModel):
    """POST /chatbot/save/roadmap response"""
    id: str
    name: str
    nodes: dict
    edges: list
    nCnt: int
    panX: float
    panY: float
    zoom: float
    created_items: List[CreatedItemResponse]

