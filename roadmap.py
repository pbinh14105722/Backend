import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from typing import List

import models, database, schemas
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


# ========== HELPERS ==========

def build_roadmap_response(roadmap: models.Roadmap) -> dict:
    """Chuyển DB object sang response dict đúng format frontend"""
    return {
        "id": roadmap.id,
        "name": roadmap.name,
        "nodes": json.loads(roadmap.nodes or "{}"),
        "edges": json.loads(roadmap.edges or "[]"),
        "nCnt": roadmap.n_cnt,
        "panX": roadmap.pan_x,
        "panY": roadmap.pan_y,
        "zoom": roadmap.zoom,
    }


# ========== ROUTES ==========

# 1. GET /roadmap — Lấy danh sách tất cả roadmaps
@router.get(
    "/roadmap",
    summary="Lấy danh sách tất cả roadmaps"
)
def get_roadmaps(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    GET /roadmap

    Trả về tất cả roadmaps của user hiện tại.
    Frontend dùng nodes và edges để đếm số node/cạnh hiển thị.
    """
    print(f"[ROADMAP] GET LIST - User {current_user.id}")

    roadmaps = db.query(models.Roadmap).filter(
        models.Roadmap.user_id == current_user.id
    ).order_by(models.Roadmap.created_at.asc()).all()

    result = [build_roadmap_response(r) for r in roadmaps]
    print(f"[ROADMAP] GET LIST ✅ {len(result)} roadmaps")
    return result


# 2. POST /roadmap — Tạo roadmap mới
@router.post(
    "/roadmap",
    status_code=status.HTTP_201_CREATED,
    summary="Tạo roadmap mới"
)
def create_roadmap(
    data: schemas.RoadmapCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    POST /roadmap

    Tạo roadmap mới với canvas rỗng hoặc state được truyền vào.
    Trả về Roadmap object đầy đủ bao gồm id do server sinh ra.
    """
    print(f"[ROADMAP] POST - User {current_user.id}, name={data.name}")

    roadmap = models.Roadmap(
        user_id=current_user.id,
        name=data.name,
        nodes=json.dumps(data.nodes),
        edges=json.dumps(data.edges),
        n_cnt=data.nCnt,
        pan_x=data.panX,
        pan_y=data.panY,
        zoom=data.zoom,
    )

    try:
        db.add(roadmap)
        db.commit()
        db.refresh(roadmap)
        print(f"[ROADMAP] POST ✅ ID={roadmap.id}")
        return build_roadmap_response(roadmap)
    except Exception as e:
        db.rollback()
        print(f"[ROADMAP] POST ❌ {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi tạo roadmap: {str(e)}"
        )


# 3. GET /roadmap/{id} — Lấy chi tiết 1 roadmap
@router.get(
    "/roadmap/{roadmap_id}",
    summary="Lấy chi tiết một roadmap"
)
def get_roadmap(
    roadmap_id: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    GET /roadmap/{id}

    Trả về đầy đủ nodes, edges, nCnt, panX, panY, zoom.
    Frontend dùng để restore lại canvas khi chuyển roadmap.
    """
    print(f"[ROADMAP] GET {roadmap_id} - User {current_user.id}")

    roadmap = db.query(models.Roadmap).filter(
        models.Roadmap.id == roadmap_id,
        models.Roadmap.user_id == current_user.id
    ).first()

    if not roadmap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roadmap không tồn tại hoặc không thuộc về bạn"
        )

    print(f"[ROADMAP] GET ✅ {roadmap_id}")
    return build_roadmap_response(roadmap)


# 4. PATCH /roadmap/{id} — Partial update (đổi tên HOẶC lưu canvas)
@router.patch(
    "/roadmap/{roadmap_id}",
    summary="Cập nhật tên hoặc lưu canvas state"
)
def update_roadmap(
    roadmap_id: str,
    data: schemas.RoadmapUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    PATCH /roadmap/{id}

    Partial update — chỉ update field nào được gửi lên:
    - Trường hợp A (đổi tên): { "name": "tên mới" }
    - Trường hợp B (lưu canvas): { "nodes": {...}, "edges": [...], "nCnt": N, "panX": x, "panY": y, "zoom": z }

    KHÔNG bao giờ ghi đè field không có trong body.
    """
    print(f"[ROADMAP] PATCH {roadmap_id} - User {current_user.id}")

    roadmap = db.query(models.Roadmap).filter(
        models.Roadmap.id == roadmap_id,
        models.Roadmap.user_id == current_user.id
    ).first()

    if not roadmap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roadmap không tồn tại hoặc không thuộc về bạn"
        )

    # Chỉ update các field được gửi lên (partial update)
    update_data = data.model_dump(exclude_unset=True)

    if "name" in update_data:
        roadmap.name = update_data["name"]
        print(f"[ROADMAP] PATCH rename → '{update_data['name']}'")

    if "nodes" in update_data:
        # Đảm bảo edge label không bao giờ là null
        edges = update_data.get("edges", json.loads(roadmap.edges or "[]"))
        for edge in edges:
            if edge.get("label") is None:
                edge["label"] = ""
        roadmap.nodes = json.dumps(update_data["nodes"])
        roadmap.edges = json.dumps(edges)
        roadmap.n_cnt = update_data.get("nCnt", roadmap.n_cnt)
        roadmap.pan_x = update_data.get("panX", roadmap.pan_x)
        roadmap.pan_y = update_data.get("panY", roadmap.pan_y)
        roadmap.zoom  = update_data.get("zoom", roadmap.zoom)
        print(f"[ROADMAP] PATCH canvas saved, nodes={len(update_data['nodes'])}")

    try:
        db.commit()
        print(f"[ROADMAP] PATCH ✅ {roadmap_id}")
        return {"ok": True}
    except Exception as e:
        db.rollback()
        print(f"[ROADMAP] PATCH ❌ {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi cập nhật roadmap: {str(e)}"
        )


# 5. DELETE /roadmap/{id} — Xóa roadmap
@router.delete(
    "/roadmap/{roadmap_id}",
    summary="Xóa một roadmap"
)
def delete_roadmap(
    roadmap_id: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    DELETE /roadmap/{id}

    Xóa roadmap. Frontend đã kiểm tra không cho xóa nếu chỉ còn 1,
    nhưng backend vẫn validate lại.
    """
    print(f"[ROADMAP] DELETE {roadmap_id} - User {current_user.id}")

    roadmap = db.query(models.Roadmap).filter(
        models.Roadmap.id == roadmap_id,
        models.Roadmap.user_id == current_user.id
    ).first()

    if not roadmap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roadmap không tồn tại hoặc không thuộc về bạn"
        )

    # Validate: không cho xóa nếu chỉ còn 1 roadmap
    roadmap_count = db.query(models.Roadmap).filter(
        models.Roadmap.user_id == current_user.id
    ).count()

    if roadmap_count <= 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không thể xóa roadmap duy nhất"
        )

    try:
        db.delete(roadmap)
        db.commit()
        print(f"[ROADMAP] DELETE ✅ {roadmap_id}")
        return {"ok": True}
    except Exception as e:
        db.rollback()
        print(f"[ROADMAP] DELETE ❌ {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi xóa roadmap: {str(e)}"
        )