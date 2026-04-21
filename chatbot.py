import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from typing import Optional
import anthropic
import re
  
import models, database, schemas
from utils import SECRET_KEY, ALGORITHM
from fastapi.responses import JSONResponse

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Giới hạn lịch sử hội thoại
HISTORY_LIMIT = 50

# 20 màu hợp lệ
VALID_COLORS = {
    "#a0aec0", "#818cf8", "#4fd1ed", "#f6ad55", "#b83280",
    "#f687b3", "#faf089", "#9ae6b4", "#fc8181", "#a78bfa",
    "#22d3ee", "#6ee7b7", "#8b5cf6", "#3b82f6", "#ec4899",
    "#f87171", "#94a3b8", "#b7948c", "#5eead4", "#4a5568"
}
DEFAULT_COLOR = "#a0aec0"


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


# ========== HELPERS ==========

def validate_color(color: Optional[str]) -> str:
    """Validate color, fallback về #a0aec0 nếu sai"""
    if color and color in VALID_COLORS:
        return color
    return DEFAULT_COLOR

def extract_roadmap_context(message: str):
    """
    Tách [ROADMAP_CONTEXT]...[/ROADMAP_CONTEXT] ra khỏi message.
    Trả về (context_dict | None, clean_message).
    """
    match = re.search(
        r'\[ROADMAP_CONTEXT\](.*?)\[/ROADMAP_CONTEXT\]',
        message,
        re.DOTALL
    )
    if match:
        try:
            context = json.loads(match.group(1))
        except json.JSONDecodeError:
            context = None
        clean = re.sub(
            r'\[ROADMAP_CONTEXT\].*?\[/ROADMAP_CONTEXT\]',
            '',
            message,
            flags=re.DOTALL
        ).strip()
        return context, clean
    return None, message


def enforce_history_limit(user_id: int, db: Session):
    """
    ✅ FIX: Xóa tin nhắn cũ nhất nếu đã đạt giới hạn 50 tin.
    Gọi hàm này TRƯỚC KHI lưu message mới.
    """
    msg_count = db.query(models.ChatMessage).filter(
        models.ChatMessage.user_id == user_id
    ).count()

    if msg_count >= HISTORY_LIMIT:
        # Xóa tin nhắn cũ nhất
        oldest = db.query(models.ChatMessage).filter(
            models.ChatMessage.user_id == user_id
        ).order_by(models.ChatMessage.created_at.asc()).first()
        
        if oldest:
            db.delete(oldest)
            db.flush()
            print(f"[CHATBOT] 🗑️ Auto-deleted oldest message (id: {oldest.id}) - Limit reached")


def get_user_context(user_id: int, db: Session) -> str:
    """Lấy dữ liệu thực của user để AI có context"""
    # Lấy items (folder/project)
    items = db.query(models.Item).filter(
        models.Item.owner_id == user_id
    ).order_by(models.Item.position.asc()).all()

    # Lấy tasks
    project_ids = [i.id for i in items if i.type == 'PROJECT']
    tasks = []
    if project_ids:
        tasks = db.query(models.Task).filter(
            models.Task.project_id.in_(project_ids)
        ).all()

    # Format context
    context_parts = []

    if items:
        context_parts.append("=== CẤU TRÚC WORKSPACE ===")
        for item in items:
            indent = "  " if item.parent_id else ""
            context_parts.append(f"{indent}[{item.type}] {item.name} (id: {item.id}, color: {item.color})")

    if tasks:
        context_parts.append("\n=== DANH SÁCH TASK ===")
        for task in tasks:
            context_parts.append(
                f"- {task.name} | project: {task.project_id} | "
                f"priority: {task.priority} | progress: {getattr(task, 'progress', 0)}% | "
                f"due: {task.due_date} | time_spent: {task.time_spent_seconds}s"
            )

    return "\n".join(context_parts) if context_parts else "Người dùng chưa có dữ liệu nào."


def call_claude_api(user_message: str, history: list, user_context: str) -> dict:
    """
    Gọi Claude API và trả về response có cấu trúc:
    { "message": str, "type": str|None, "data": dict|None }
    
    ✅ IMPROVED: Claude detects user language - handles non-diacritical Vietnamese
    ✅ IMPROVED: System prompt rõ ràng hơn về folder_tree vs roadmap
    ✅ IMPROVED: Validation AI output structure
    ✅ IMPROVED: Debug logging
    """
    client = anthropic.Anthropic(api_key=database.ANTHROPIC_API_KEY)

    # Language-specific templates (will be chosen by Claude based on detected language)
    templates = {
        'vi': {
            'lang_instruction': "Detect the language of the user's message. If it's Vietnamese (including non-diacritical Vietnamese like 'toi', 'va', etc.), respond ENTIRELY in Vietnamese.",
            'folder_tree_msg': "✅ Tôi đã tạo xong cấu trúc **[title]** gồm [X] folder, [Y] project và [Z] task. Xem preview và nhấn **Save** để lưu vào workspace của bạn!",
            'roadmap_msg': "✅ Tôi đã tạo xong roadmap **[title]** gồm [N_FOLDER] giai đoạn chính và [N_PROJECT] module chi tiết ([TOTAL] nodes). Xem preview và nhấn **Save** để lưu vào workspace của bạn!",
            'ambiguous_msg': "Bạn muốn (1) một cấu trúc folder & task được tổ chức để nhập vào workspace, hay (2) một timeline trực quan hiển thị các giai đoạn và milestone?"
        },
        'en': {
            'lang_instruction': "If the user's message is in English, respond ENTIRELY in English.",
            'folder_tree_msg': "✅ I've created the **[title]** structure with [X] folders, [Y] projects, and [Z] tasks. Check the preview and click **Save** to add it to your workspace!",
            'roadmap_msg': "✅ I've created the **[title]** roadmap with [N_FOLDER] main phases and [N_PROJECT] detailed modules ([TOTAL] nodes). Check the preview and click **Save** to add it to your workspace!",
            'ambiguous_msg': "Would you like (1) an organized folder & task structure to import into your workspace, or (2) a visual timeline showing the phases and milestones?"
        }
    }

    # Combine templates for use in prompt
    vi_templates = templates['vi']
    en_templates = templates['en']

    system_prompt = f"""You are Manask AI — a smart, proactive assistant built into the Manask task management application.
    Help users organize work, visualize projects, analyze progress, and find tasks efficiently.
    You have access to the user's workspace data below. Use it for precise, personalized answers.

    LANGUAGE: Detect the user's language (English or Vietnamese — including non-diacritical like 'toi', 'va', 'khong').
    Respond ENTIRELY in that language. Do NOT mix languages.

    {user_context}

    Today's date: {datetime.now(timezone.utc).strftime("%Y-%m-%d")}

    # SECTION 1 — RESPONSE FORMAT (MANDATORY)

    Always return a single valid JSON object. No exceptions.

    {{"message": "...", "type": null | "folder_tree" | "roadmap" | "roadmap_update" | "statistic" | "filter", "data": null | {{...}}}}

    - Return ONLY raw JSON — no ```json fences, no preamble.
    - Double quotes everywhere. No trailing commas.
    - "message" is always required and never empty.
    - If unsure about type → default to null.

    # SECTION 2 — TYPE SELECTION

    | type | Use when user wants... |
    |---|---|
    | folder_tree | Work breakdown: folders, projects, tasks |
    | roadmap | NEW timeline/phases from scratch |
    | roadmap_update | EDIT an existing roadmap (context provided) |
    | statistic | Progress insights, reports, bottlenecks |
    | filter | Find/filter tasks by criteria |
    | null | General chat, advice, clarification |

    FOLDER_TREE vs ROADMAP — ask yourself: STRUCTURE or TIME?
    - STRUCTURE (who does what) → folder_tree. Signals: "organize", "breakdown", "setup", "team structure"
    - TIME (when, in what order) → roadmap. Signals: "roadmap", "timeline", "phases", "milestones", "stages"
    - AMBIGUOUS → type=null. Vietnamese: "{vi_templates['ambiguous_msg']}" / English: "{en_templates['ambiguous_msg']}"

    ROADMAP vs ROADMAP_UPDATE:
    - Message contains [ROADMAP_CONTEXT]...[/ROADMAP_CONTEXT] → always roadmap_update.

    # SECTION 3 — FOLDER TREE

    type = "folder_tree"
    PURPOSE: Generate an importable project hierarchy with folders, projects, and actionable tasks.

    DATA FORMAT: {{"title": "...", "tree": [FOLDER..., PROJECT..., TASK...]}}
    - FOLDER:  {{"id":"f1","parent_id":null,"name":"Frontend","type":"FOLDER","position":0,"color":"#818cf8"}}
    - PROJECT: {{"id":"p1","parent_id":"f1","name":"Landing Page","type":"PROJECT","position":0,"color":"#a78bfa"}}
    - TASK:    {{"id":"t1","project_id":"p1","name":"Design hero section","type":"TASK","position":0,"priority":"high","start_date":"2025-05-01T00:00:00.000Z","due_date":"2025-05-10T23:59:59.999Z","time_spent":0,"process":0,"notes":"Mobile-first. Follow brand guidelines."}}

    SCALE: Small → 2-3F/3-5P/6-12T. Medium → 3-5F/5-10P/15-25T. Large → ask first.

    RULES:
    - EVERY PROJECT ≥ 2 tasks — reduce projects before leaving any empty. 3 complete projects > 8 with gaps.
    - Task names: verb phrases. ✅ "Write unit tests for auth module" ❌ "Unit tests"
    - Notes: 1 specific actionable sentence. Never null for high/medium priority tasks.
    - Priority: "high"=blocking/deadline-critical, "medium"=important, "low"=nice-to-have.
    - IDs: f1,f2.../p1,p2.../t1,t2... — must be unique.
    - Dates: "YYYY-MM-DDTHH:mm:ss.000Z" — space tasks realistically, don't cluster.
    - process: always 0 unless user states otherwise. time_spent: seconds (3600=1hr).

    MESSAGE — Vietnamese: "{vi_templates['folder_tree_msg']}" / English: "{en_templates['folder_tree_msg']}"

    # SECTION 4 — ROADMAP (NEW)

    type = "roadmap"
    PURPOSE: Generate a detailed node-graph showing ALL phases, sub-phases, and dependencies.
    Prioritize COMPLETENESS — if user provides explicit names, generate every named node.

    DATA FORMAT:
    {{"title":"...","id":"rm_slug","name":"...",
      "nodes":{{
        "n1":{{"x":80,"y":400,"item":{{"id":"f1","name":"Phase1","type":"FOLDER","color":"#818cf8","parent_name":null,"parent_id":null}}}},
        "n2":{{"x":480,"y":250,"item":{{"id":"p1","name":"SubPhase","type":"PROJECT","color":"#4fd1ed","parent_name":"Phase1","parent_id":"f1"}}}}
      }},
      "edges":[{{"from":"n1","to":"n2","fromPort":"right","toPort":"left","etype":"one","style":"solid","label":""}}],
      "nCnt":2,"panX":0,"panY":0,"zoom":1.0
    }}

    LAYOUT ENGINE — READ CAREFULLY, execute in order:

    STEP 1 — COUNT nodes per column before placing anything:
      For each FOLDER column, count how many PROJECT children it has.
      col_height = child_count × 150
      col_center_y = total_canvas_height / 2  (use 400 as default center)

    STEP 2 — Place FOLDER nodes on the main horizontal spine:
      FOLDER x positions: 80, 80 + col_gap, 80 + 2×col_gap, ...
      col_gap = max(400, 120 + longest_project_name_chars × 8)
      FOLDER y = center_y (same y for all FOLDERs to form a horizontal spine)

    STEP 3 — Fan out PROJECT children vertically around their parent FOLDER:
      For a FOLDER at (fx, fy) with N children:
        total_spread = (N - 1) × 150
        first_child_y = fy - total_spread / 2
        child_x = fx + 380
        child_y[i] = first_child_y + i × 150

    STEP 4 — Set zoom based on total node count:
      ≤ 10 nodes  → zoom: 1.0
      11-20 nodes → zoom: 0.75
      21-35 nodes → zoom: 0.55
      > 35 nodes  → zoom: 0.40

    ABSOLUTE RULES:
    - NEVER place 2 nodes at identical (x, y) — check before writing each node.
    - Minimum y gap between any two nodes: 130px.
    - Canvas grows downward as needed — do not compress nodes to fit a fixed height.
    - PRE-COMPUTE all positions before writing JSON (do not place as you go).

    NODE RULES:
    - FOLDER = major phase, parent_id: null. PROJECT = sub-phase, parent_id → FOLDER id.
    - NO TASK nodes. parent_name must exactly match parent FOLDER's name field.
    - All PROJECTs in same FOLDER share the same color as their parent FOLDER.
    - COMPLETENESS MANDATORY: each named item = one node. Do NOT collapse or summarize.

    EDGE RULES:
    - FOLDER → children: fromPort="right", toPort="left", style="solid", etype="one"
    - FOLDER → next FOLDER: same as above
    - Cross-phase dependency: style="dashed", label="depends on"
    - Parallel tracks: label="parallel"
    - etype: "none" | "one"(→) | "two"(↔)

    SCALE: ≤8 nodes → zoom 1.0. 9-20 → 0.75. 21-40 → 0.55, generate ALL nodes.

    MESSAGE — Vietnamese: "{vi_templates['roadmap_msg']}" / English: "{en_templates['roadmap_msg']}"

    # SECTION 5 — ROADMAP UPDATE (EDIT EXISTING)

    type = "roadmap_update"
    PURPOSE: Edit an existing roadmap by returning ONLY the diff — never the full roadmap.
    TRIGGER: Message contains [ROADMAP_CONTEXT]...[/ROADMAP_CONTEXT].

    DATA FORMAT:
    {{"target_roadmap_id": "uuid",
      "diff": {{
        "add_nodes":    {{"n6": {{"x":1500,"y":250,"item":{{"id":"f3","name":"Deployment","type":"FOLDER","color":"#22d3ee","parent_name":null,"parent_id":null}}}}}},
        "update_nodes": {{"n2": {{"item": {{"name":"Design & UX Research"}}}}}},
        "delete_nodes": ["n4"],
        "add_edges":    [{{"from":"n5","to":"n6","fromPort":"right","toPort":"left","etype":"one","style":"solid","label":""}}],
        "delete_edges": [{{"from":"n2","to":"n4"}}]
      }}
    }}

    DIFF RULES:
    1. All 5 keys MUST exist — use {{}} or [] if no change.
    2. add_nodes: keys start from n{{nCnt+1}} (nCnt is in the context).
    3. update_nodes: PARTIAL only — include only changed fields.
    4. delete_nodes: MUST add all related edges to delete_edges (any edge where from or to = deleted node key).
    5. delete_edges: identify by {{from, to}} only. No TASK nodes. Colors from Section 9 only.

    MESSAGE: Vietnamese → "✅ Đã cập nhật roadmap **[name]**: [mô tả ngắn]."
             English   → "✅ Updated roadmap **[name]**: [short description]."

    # SECTION 6 — SMART ANALYSIS

    type = "statistic", data = null
    TRIGGERS: "summarize", "analyze", "how am I doing", "report", "overdue", "progress", "time spent"

    Calculate from actual workspace data:
    - Total tasks vs completed (process=100), avg progress, overdue (due_date < today AND process < 100)
    - High-priority not started (priority="high" AND process=0), time invested (sum time_spent → hours)

    Message structure:
    **📋 Executive Summary** — 1 sentence with real numbers on overall health.
    **📊 Key Metrics** — table: Total Tasks | Completed | Overdue | Time Invested | High Priority Pending.
    **⚠️ Issues & Bottlenecks** — specific problems naming projects/tasks and numbers.
    **✅ Recommendations** — 2-4 next steps naming specific tasks.

    If workspace empty: respond warmly, guide to add first project.

    # SECTION 7 — FILTER

    type = "filter"
    TRIGGERS: "find", "show me", "filter", "which tasks", "list tasks that", "display"

    DATA FORMAT:
    {{"logic":"and","filters":[
      {{"field":"priority","operator":"in","value":["high"]}},
      {{"field":"due_date","operator":"lte","value":"2026-04-30T23:59:59.999Z"}}
    ]}}

    Fields: "name"(contains), "priority"(in: high/medium/low), "start_date", "due_date", "time_spent", "create_date"
    Operators: "eq"|"contains"|"in"|"gt"|"gte"|"lt"|"lte"|"between"(value:{{"from":"...","to":"..."}})
    Logic: "and"(default) | "or"

    In message: explain the filter in plain language so user knows what they'll see.

    # SECTION 8 — GENERAL CONVERSATION

    type = null, data = null
    Use for: greetings, feature questions, productivity advice, clarification.

    - Concise and direct. No filler ("Great question!", "Of course!").
    - Markdown for clarity. Reference user's actual data when relevant.
    - Ask ONE clarifying question at most. Proactively suggest features when useful.

    # SECTION 9 — VALID COLORS

    Only use colors from this exact list:
    #a0aec0 #818cf8 #4fd1ed #f6ad55 #b83280
    #f687b3 #faf089 #9ae6b4 #fc8181 #a78bfa
    #22d3ee #6ee7b7 #8b5cf6 #3b82f6 #ec4899
    #f87171 #94a3b8 #b7948c #5eead4 #4a5568"""



    # Build messages từ history
    messages = []
    for h in history:
        messages.append({
            "role": h["role"],
            "content": h["message"]
        })
    # Thêm tin nhắn mới nhất
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16000,  # ✅ Tăng từ 2048 → 4096 để đủ cho folder tree lớn
            system=system_prompt,
            messages=messages
        )

        raw_text = response.content[0].text.strip()
        
        # ✅ Debug: Log raw response length
        print(f"[CHATBOT] 📝 AI raw response: {len(raw_text)} chars")
        print(f"[CHATBOT] 📝 Raw response tail: ...{raw_text[-200:]}")

        # Parse JSON response
        try:
            result = json.loads(raw_text)
        except json.JSONDecodeError as e:
            print(f"[CHATBOT] ❌ JSON parse error: {str(e)}")
            print(f"[CHATBOT] Raw text preview: {raw_text[:200]}...")
    
            # Thử tìm JSON object trong text
            import re
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    print(f"[CHATBOT] ✅ Extracted JSON from raw text")
                except:
                    result = {"message": raw_text, "type": None, "data": None}
            else:
                result = {"message": raw_text, "type": None, "data": None}

        # Validate và sanitize
        msg_text = result.get("message", "Xin lỗi, tôi không thể xử lý yêu cầu này.")
        msg_type = result.get("type")
        msg_data = result.get("data")
        
        # ✅ Debug: Log parsed response
        print(f"[CHATBOT] 🤖 AI Response parsed:")
        print(f"  - Type: {msg_type}")
        print(f"  - Has data: {msg_data is not None}")

        # Validate type
        if msg_type not in (None, "folder_tree", "roadmap", "roadmap_update", "statistic", "filter", "filter_applied"):
            print(f"[CHATBOT] ⚠️ Invalid type '{msg_type}', fallback to None")
            msg_type = None

        # Validate data
        if msg_type in (None, "statistic"):
            msg_data = None
        
        # ✅ Validate folder_tree structure
        if msg_type == "folder_tree" and msg_data:
            tree = msg_data.get("tree", [])
            print(f"[CHATBOT]   - Tree items: {len(tree)}")
            
            folders = [i for i in tree if i.get("type") == "FOLDER"]
            projects = [i for i in tree if i.get("type") == "PROJECT"]
            tasks = [i for i in tree if i.get("type") == "TASK"]
            
            print(f"[CHATBOT]   - Folders: {len(folders)}, Projects: {len(projects)}, Tasks: {len(tasks)}")
            
            # Must have at least 1 folder and 1 project
            if len(folders) < 1 or len(projects) < 1:
                print(f"[CHATBOT] ⚠️ folder_tree invalid: need 1+ folder and 1+ project, fallback to None")
                msg_type = None
                msg_data = None
            else:
                # Validate colors
                for item in tree:
                    if "color" in item:
                        item["color"] = validate_color(item.get("color"))
        
        # ✅ Validate roadmap structure
        if msg_type == "roadmap" and msg_data:
            nodes = msg_data.get("nodes", {})
            edges = msg_data.get("edges", [])
            
            print(f"[CHATBOT]   - Nodes: {len(nodes)}, Edges: {len(edges)}")
            
            # Must have at least 2 nodes
            if len(nodes) < 2:
                print(f"[CHATBOT] ⚠️ Roadmap invalid: need 2+ nodes, fallback to None")
                msg_type = None
                msg_data = None
            else:
                # Validate colors trong nodes
                for node_key, node in nodes.items():
                    if "item" in node and "color" in node["item"]:
                        node["item"]["color"] = validate_color(node["item"].get("color"))
        
        # ✅ Validate roadmap_update structure
        if msg_type == "roadmap_update" and msg_data:
            target_id = msg_data.get("target_roadmap_id")
            diff = msg_data.get("diff")
 
            if not target_id or not isinstance(diff, dict):
                print(f"[CHATBOT] ⚠️ roadmap_update invalid: missing target_roadmap_id or diff")
                msg_type = None
                msg_data = None
            else:
                # Fill missing diff keys với default rỗng
                diff.setdefault("add_nodes", {})
                diff.setdefault("update_nodes", {})
                diff.setdefault("delete_nodes", [])
                diff.setdefault("add_edges", [])
                diff.setdefault("delete_edges", [])
 
                # Validate colors trong add_nodes
                for node_key, node in diff.get("add_nodes", {}).items():
                    if "item" in node and "color" in node["item"]:
                        node["item"]["color"] = validate_color(node["item"].get("color"))
 
                # Validate colors trong update_nodes (nếu có field color)
                for node_key, partial in diff.get("update_nodes", {}).items():
                    if "item" in partial and "color" in partial["item"]:
                        partial["item"]["color"] = validate_color(partial["item"].get("color"))
 
                # Auto-cleanup: đảm bảo delete_nodes đi kèm delete_edges
                deleted_keys = set(diff.get("delete_nodes", []))
                if deleted_keys:
                    existing_del_edges = {
                        (e.get("from"), e.get("to"))
                        for e in diff.get("delete_edges", [])
                    }
                    # Không thể tự biết edge nào tồn tại ở đây (không có roadmap state),
                    # nhưng log cảnh báo nếu AI quên delete_edges khi delete_nodes không rỗng
                    if not diff.get("delete_edges"):
                        print(f"[CHATBOT] ⚠️ delete_nodes={list(deleted_keys)} nhưng delete_edges rỗng — AI có thể đã quên. Frontend sẽ auto-cleanup ghost edges.")
 
                print(f"[CHATBOT]   - roadmap_update: target={target_id}")
                print(f"[CHATBOT]   - add_nodes={len(diff['add_nodes'])}, update_nodes={len(diff['update_nodes'])}, delete_nodes={len(diff['delete_nodes'])}")
                print(f"[CHATBOT]   - add_edges={len(diff['add_edges'])}, delete_edges={len(diff['delete_edges'])}")

    
        # ✅ Validate filter structure
        if msg_type == "filter" and msg_data:
            if "logic" not in msg_data or "filters" not in msg_data:
                print(f"[CHATBOT] ⚠️ filter invalid: missing logic or filters, fallback to None")
                msg_type = None
                msg_data = None

        return {
            "message": msg_text,
            "type": msg_type,
            "data": msg_data
        }

    except Exception as e:
        print(f"[CHATBOT] Claude API error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi gọi AI: {str(e)}"
        )


# ========== ROUTES ==========

@router.post("/chatbot", summary="Gửi tin nhắn tới AI")
def send_message(
    data: schemas.ChatMessageSend,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    POST /chatbot
    Gửi tin nhắn của user, lưu vào DB, gọi AI, lưu response AI.
    
    ✅ FIX: 
    - Validate message không rỗng
    - Enforce 50 message limit TRƯỚC KHI lưu message mới
    - Validate AI output structure
    """
    # ✅ Validate message không rỗng (theo spec)
    if not data.message or not data.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message không được rỗng"
        )
    
    print(f"[CHATBOT] POST - User {current_user.id}: {data.message[:50]}...")

    # ✅ FIX: Enforce history limit TRƯỚC KHI lưu message mới
    enforce_history_limit(current_user.id, db)

    # Lưu message của user
    user_msg = models.ChatMessage(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        role="user",
        message=data.message,
        type=None,
        data=None,
        created_at=datetime.now(timezone.utc)
    )
    db.add(user_msg)

    try:
        db.commit()
        print(f"[CHATBOT] ✅ User message saved: {user_msg.id}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu tin nhắn: {str(e)}")

    # Lấy history để gửi cho AI
    history_msgs = db.query(models.ChatMessage).filter(
        models.ChatMessage.user_id == current_user.id
    ).order_by(models.ChatMessage.created_at.asc()).all()

    history = []
    for msg in history_msgs[:-1]:  # Bỏ tin nhắn mới nhất (vì đã thêm trong call_claude_api)
        history.append({
            "role": msg.role,
            "message": msg.message
        })

    # Lấy user context
    user_context = get_user_context(current_user.id, db)
    

    # Gọi AI
    try:
        ai_response = call_claude_api(data.message, history, user_context)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi gọi AI: {str(e)}"
        )

    # ✅ FIX: Enforce history limit TRƯỚC KHI lưu AI response
    enforce_history_limit(current_user.id, db)

    # ✅ Validate AI response trước khi lưu
    if ai_response["type"] in ("roadmap", "folder_tree") and not ai_response["data"]:
        print(f"[CHATBOT] ⚠️ AI returned type={ai_response['type']} but no data! Fallback to None")
        ai_response["type"] = None
        ai_response["data"] = None

    # ✅ AUTO-APPLY FILTER: Backend tự lưu cấu hình lọc vào DB, Frontend chỉ cần reload
    if ai_response["type"] == "filter" and ai_response["data"] and data.project_id:
        try:
            filter_data = ai_response["data"]
            # Kiểm tra project thuộc về user
            project = db.query(models.Item).filter(
                models.Item.id == data.project_id,
                models.Item.type == "PROJECT",
                models.Item.owner_id == current_user.id
            ).first()

            if project:
                # Tìm hoặc tạo FilterSettings
                settings = db.query(models.FilterSettings).filter(
                    models.FilterSettings.project_id == data.project_id,
                    models.FilterSettings.user_id == current_user.id
                ).first()

                if not settings:
                    settings = models.FilterSettings(
                        user_id=current_user.id,
                        project_id=data.project_id,
                        enabled=True,
                        filter_config=json.dumps(filter_data)
                    )
                    db.add(settings)
                else:
                    settings.enabled = True
                    settings.filter_config = json.dumps(filter_data)

                db.flush()
                print(f"[CHATBOT] ✅ Auto-applied filter to project {data.project_id}: {len(filter_data.get('filters', []))} rules")

                # Đổi type thành filter_applied để Frontend biết chỉ cần reload
                ai_response["type"] = "filter_applied"
                ai_response["data"] = {
                    "project_id": data.project_id,
                    "filters_count": len(filter_data.get("filters", [])),
                    "logic": filter_data.get("logic", "and")
                }
            else:
                print(f"[CHATBOT] ⚠️ Project {data.project_id} not found or not owned by user, skip auto-apply")
        except Exception as e:
            print(f"[CHATBOT] ⚠️ Auto-apply filter failed: {str(e)}, keeping original filter response")

    # Lưu response của AI
    ai_msg = models.ChatMessage(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        role="assistant",
        message=ai_response["message"],
        type=ai_response["type"],
        data=json.dumps(ai_response["data"]) if ai_response["data"] else None,
        created_at=datetime.now(timezone.utc)
    )
    db.add(ai_msg)

    try:
        db.commit()
        print(f"[CHATBOT] ✅ AI response saved: {ai_msg.id}, type={ai_msg.type}, has_data={ai_msg.data is not None}")
        return {"status": "received"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu phản hồi AI: {str(e)}")


@router.get("/chatbot", summary="Lấy phản hồi AI mới nhất")
def get_latest_response(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    GET /chatbot
    Trả về phản hồi mới nhất của AI.
    
    ✅ FIX: Response format match với frontend expectation
    Frontend expect: {role: "assistant", content: "...", type: "...", data: {...}}
    """
    print(f"[CHATBOT] GET latest - User {current_user.id}")

    latest = db.query(models.ChatMessage).filter(
        models.ChatMessage.user_id == current_user.id,
        models.ChatMessage.role == "assistant"
    ).order_by(models.ChatMessage.created_at.desc()).first()

    if not latest:
        raise HTTPException(status_code=404, detail="Chưa có phản hồi nào")

    data = None
    if latest.data:
        try:
            data = json.loads(latest.data)
            print(f"[CHATBOT]   - Data parsed successfully, keys: {list(data.keys()) if data else None}")
        except Exception as e:
            print(f"[CHATBOT]   - Failed to parse data: {e}")
            data = None

    # ✅ FIX: Match frontend extractAIMessage() expectation
    # Frontend checks: data.role === 'assistant' && data.content
    response = {
        "role": "assistant",        # ← Frontend cần field này
        "content": latest.message,  # ← Frontend expect "content", không phải "message"
        "type": latest.type,
        "data": data
    }
    
    print(f"[CHATBOT]   - Response: type={response['type']}, has_data={response['data'] is not None}")
    return response


@router.get("/chatbot/history", summary="Lấy lịch sử hội thoại")
def get_history(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    GET /chatbot/history
    Trả về tối đa 50 tin nhắn, sắp xếp từ cũ đến mới.
    
    ✅ FIX: Frontend expect ARRAY trực tiếp, không phải object wrapper
    Frontend code: _messages = Array.isArray(data) ? data : [];
    """
    print(f"[CHATBOT] GET history - User {current_user.id}")

    messages = db.query(models.ChatMessage).filter(
        models.ChatMessage.user_id == current_user.id
    ).order_by(models.ChatMessage.created_at.asc()).limit(HISTORY_LIMIT).all()

    history = []
    for msg in messages:
        # Format message với field "content" (frontend expect)
        data = None
        if msg.data:
            try:
                data = json.loads(msg.data)
            except:
                data = None
        
        history.append({
            "id": msg.id,
            "role": msg.role,
            "content": msg.message,  # ✅ Frontend expect "content"
            "type": msg.type,
            "data": data,
            "created_at": msg.created_at.isoformat().replace("+00:00", "Z")
        })

    # ✅ FIX: Return ARRAY trực tiếp, không wrap trong object
    # Frontend code: _messages = Array.isArray(data) ? data.slice(-50) : [];
    return history


@router.delete("/chatbot", summary="Xóa toàn bộ lịch sử hội thoại")
def clear_history(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    DELETE /chatbot
    Xóa toàn bộ lịch sử hội thoại của user. Không thể hoàn tác.
    """
    print(f"[CHATBOT] DELETE history - User {current_user.id}")

    db.query(models.ChatMessage).filter(
        models.ChatMessage.user_id == current_user.id
    ).delete()

    try:
        db.commit()
        print(f"[CHATBOT] DELETE ✅ History cleared")
        return {"status": "cleared"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chatbot/save/folder-tree", status_code=status.HTTP_201_CREATED, summary="Lưu folder tree vào DB")
def save_folder_tree(
    data: schemas.SaveFolderTreeRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    POST /chatbot/save/folder-tree
    Lưu folder tree AI tạo vào DB thực.
    Xử lý theo thứ tự: FOLDER → PROJECT → TASK
    Tự sinh id thật, bỏ qua AI-generated id.
    """
    print(f"[CHATBOT] SAVE folder-tree - User {current_user.id}, {len(data.tree)} items")

    # Map AI id → DB id thật (dùng để resolve parent_id và project_id)
    id_map = {}
    saved = {"folders": 0, "projects": 0, "tasks": 0}

    # Lấy position hiện tại để không bị trùng
    max_position = db.query(models.Item).filter(
        models.Item.owner_id == current_user.id,
        models.Item.parent_id == None
    ).count()

    # Bước 1: Xử lý FOLDER
    for item in data.tree:
        if item.type != "FOLDER":
            continue
        real_id = str(uuid.uuid4())
        id_map[item.id] = real_id

        parent_real_id = id_map.get(item.parent_id) if item.parent_id else None

        db_item = models.Item(
            id=real_id,
            owner_id=current_user.id,
            name=item.name,
            type="FOLDER",
            parent_id=parent_real_id,
            position=item.position + max_position,
            color=validate_color(item.color),
            expanded=False
        )
        db.add(db_item)
        saved["folders"] += 1

    db.flush()  # Flush để FOLDER có trong DB trước khi PROJECT reference

    # Bước 2: Xử lý PROJECT
    for item in data.tree:
        if item.type != "PROJECT":
            continue
        real_id = str(uuid.uuid4())
        id_map[item.id] = real_id

        parent_real_id = id_map.get(item.parent_id) if item.parent_id else None

        db_item = models.Item(
            id=real_id,
            owner_id=current_user.id,
            name=item.name,
            type="PROJECT",
            parent_id=parent_real_id,
            position=item.position,
            color=validate_color(item.color),
            expanded=False
        )
        db.add(db_item)
        saved["projects"] += 1

    db.flush()  # Flush để PROJECT có trong DB trước khi TASK reference

    # Bước 3: Xử lý TASK
    now = datetime.now(timezone.utc)
    for item in data.tree:
        if item.type != "TASK":
            continue

        # Resolve project_id thật
        real_project_id = id_map.get(item.project_id)
        if not real_project_id:
            print(f"[CHATBOT] ⚠️ Task {item.name} có project_id không hợp lệ, bỏ qua")
            continue

        # Parse dates
        start_date = now
        due_date = now
        if item.start_date:
            try:
                start_date = datetime.fromisoformat(item.start_date.replace("Z", "+00:00"))
            except:
                start_date = now
        if item.due_date:
            try:
                due_date = datetime.fromisoformat(item.due_date.replace("Z", "+00:00"))
            except:
                due_date = now

        db_task = models.Task(
            project_id=real_project_id,
            position=item.position + 1,
            name=item.name,
            priority=item.priority if item.priority in ('high', 'medium', 'low') else 'low',
            start_date=start_date,
            due_date=due_date,
            time_spent_seconds=item.time_spent or 0,
            notes=item.notes or "",
            progress=item.process or 0
        )
        db.add(db_task)
        saved["tasks"] += 1

    try:
        db.commit()
        print(f"[CHATBOT] SAVE folder-tree ✅ {saved}")
        return {"saved": saved}
    except Exception as e:
        db.rollback()
        print(f"[CHATBOT] SAVE folder-tree ❌ {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu: {str(e)}")


@router.post("/chatbot/save/roadmap", status_code=status.HTTP_201_CREATED, summary="Lưu roadmap vào DB", response_model=schemas.SaveRoadmapResponse)
def save_roadmap(
    data: schemas.SaveRoadmapRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    POST /chatbot/save/roadmap
    Lưu roadmap AI tạo vào DB thực.
    Bỏ qua AI-generated id, tự sinh id thật.
    Dùng name làm tên bản ghi.
    """
    print(f"[CHATBOT] SAVE roadmap - User {current_user.id}, name={data.name}")

    nodes = data.nodes
    
    # --- AUTO CREATE FOLDER/PROJECT FROM ROADMAP ---
    max_position = db.query(models.Item).filter(
        models.Item.owner_id == current_user.id,
        models.Item.parent_id == None
    ).count()

    saved_items = 0
    created_items = []  # ← Theo dõi các item đã tạo để trả về cho Frontend
    id_map = {}

    # Pass 0: Pre-allocate real UUID cho tất cả FOLDER + PROJECT ngay từ đầu
    # → id_map đầy đủ trước khi bất kỳ INSERT nào xảy ra
    # → Index theo CẢ item.id LẪN node_key (phòng AI dùng node key làm parent_id)
    for node_key, node in nodes.items():
        item_data = node.get("item")
        if not item_data:
            continue
        if item_data.get("type") not in ("FOLDER", "PROJECT"):
            continue
        real_uuid = str(uuid.uuid4())
        ai_id = item_data.get("id")
        if ai_id and ai_id not in id_map:
            id_map[ai_id] = real_uuid
        # Cũng map node_key → cùng UUID (phòng AI dùng "n1" thay vì "f1" làm parent_id)
        if node_key not in id_map:
            id_map[node_key] = id_map.get(ai_id) or real_uuid

    # Bước 1: FOLDER trước
    for node_key, node in nodes.items():
        if "item" in node:
            item_data = node["item"]
            if item_data.get("type") != "FOLDER":
                continue

            ai_id = item_data.get("id")
            # Lấy UUID đã pre-allocate; fallback sinh mới nếu ai_id thiếu/None
            real_id = id_map.get(ai_id) or id_map.get(node_key) or str(uuid.uuid4())
            if ai_id:
                id_map[ai_id] = real_id
            id_map[node_key] = real_id  # luôn map node_key → real_id
            item_data["color"] = validate_color(item_data.get("color"))

            db_item = models.Item(
                id=real_id,
                owner_id=current_user.id,
                name=item_data.get("name", "Untitled"),
                type="FOLDER",
                parent_id=None,  # FOLDER không có cha trong roadmap
                position=max_position + saved_items,
                color=item_data["color"],
                expanded=False
            )
            db.add(db_item)
            item_data["id"] = real_id  # Thay thế cho frontend node graph
            saved_items += 1
            created_items.append({
                "id": real_id,
                "name": db_item.name,
                "type": db_item.type,
                "parent_id": db_item.parent_id,
                "position": db_item.position,
                "color": db_item.color,
                "expanded": db_item.expanded,
                "owner_id": db_item.owner_id,
                "ai_id": ai_id
            })

    db.flush()  # FOLDER phải có trong DB trước khi PROJECT reference

    # Bước 2: PROJECT sau
    for node_key, node in nodes.items():
        if "item" in node:
            item_data = node["item"]
            if item_data.get("type") != "PROJECT":
                continue

            ai_id = item_data.get("id")
            ai_parent_id = item_data.get("parent_id")
            real_parent_id = id_map.get(ai_parent_id)

            if ai_parent_id and not real_parent_id:
                print(f"[CHATBOT] ⚠️ SAVE roadmap: PROJECT '{item_data.get('name')}' "
                      f"có parent_id='{ai_parent_id}' nhưng không tìm thấy FOLDER/PROJECT tương ứng "
                      f"trong roadmap — lưu với parent_id=NULL")

            # Lấy UUID đã pre-allocate; fallback sinh mới nếu ai_id thiếu/None
            real_id = id_map.get(ai_id) or id_map.get(node_key) or str(uuid.uuid4())
            if ai_id:
                id_map[ai_id] = real_id
            id_map[node_key] = real_id  # luôn map node_key → real_id
            item_data["color"] = validate_color(item_data.get("color"))

            db_item = models.Item(
                id=real_id,
                owner_id=current_user.id,
                name=item_data.get("name", "Untitled"),
                type="PROJECT",
                parent_id=real_parent_id,  # đúng UUID thật, fallback None nếu map ko ra
                position=max_position + saved_items,
                color=item_data["color"],
                expanded=False
            )
            db.add(db_item)
            item_data["id"] = real_id  # Thay thế cho frontend node graph
            saved_items += 1
            created_items.append({
                "id": real_id,
                "name": db_item.name,
                "type": db_item.type,
                "parent_id": db_item.parent_id,
                "position": db_item.position,
                "color": db_item.color,
                "expanded": db_item.expanded,
                "owner_id": db_item.owner_id,
                "ai_id": ai_id
            })

    # if saved_items > 0:
    db.flush()
    print(f"[CHATBOT] SAVE roadmap - Auto created {saved_items} real folders/projects.")
    # -----------------------------------------------

    # Đảm bảo edge label không bao giờ là null
    edges = data.edges
    for edge in edges:
        if isinstance(edge, dict) and edge.get("label") is None:
            edge["label"] = ""

    roadmap = models.Roadmap(
        user_id=current_user.id,
        name=data.name,
        nodes=json.dumps(nodes),
        edges=json.dumps(edges),
        n_cnt=data.nCnt,
        pan_x=data.panX,
        pan_y=data.panY,
        zoom=data.zoom,
    )

    try:
        db.add(roadmap)
        db.commit()
        # Không cần refresh(roadmap) vì ta trả về danh sách Item
        print(f"[CHATBOT] SAVE roadmap ✅ Created {len(created_items)} items for roadmap '{roadmap.name}'")
        
        # TRẢ VỀ ĐÚNG TEMPLATE: Mảng các Item mới tạo (chuẩn ItemResponse) + roadmap details
        # Frontend có thể dùng dữ liệu này để push vào Workspace list
        return {
            "id": roadmap.id,
            "name": roadmap.name,
            "nodes": nodes,
            "edges": edges,
            "nCnt": roadmap.n_cnt,
            "panX": roadmap.pan_x,
            "panY": roadmap.pan_y,
            "zoom": roadmap.zoom,
            "created_items": created_items
        }
    except Exception as e:
        db.rollback()
        print(f"[CHATBOT] SAVE roadmap ❌ {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu roadmap: {str(e)}")
