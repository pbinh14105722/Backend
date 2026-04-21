import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from typing import List

import models, database, schemas
from schemas import SortRule, validate_sort_rules
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

def verify_project_owner(project_id: str, user_id: int, db: Session):
    project = db.query(models.Item).filter(
        models.Item.id == project_id,
        models.Item.type == "PROJECT",
        models.Item.owner_id == user_id
    ).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project không tồn tại hoặc bạn không có quyền truy cập"
        )
    return project


def get_or_create_sort_settings(project_id: str, user_id: int, db: Session) -> models.SortSettings:
    settings = db.query(models.SortSettings).filter(
        models.SortSettings.project_id == project_id,
        models.SortSettings.user_id == user_id
    ).first()
    if not settings:
        settings = models.SortSettings(
            user_id=user_id,
            project_id=project_id,
            enabled=False,
            sort_config="[]"
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


# ========== ROUTES ==========

@router.get(
    "/project/{projectId}/sort",
    response_model=List[SortRule],
    summary="Lấy cài đặt sort hiện tại"
)
def get_sort_settings(
    projectId: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    GET /project/{projectId}/sort

    Trả về mảng các tiêu chí sort hiện tại.
    Trả về [] nếu chưa có hoặc đã tắt.
    """
    print(f"[SORT] GET - User {current_user.id}, Project {projectId}")

    verify_project_owner(projectId, current_user.id, db)
    settings = get_or_create_sort_settings(projectId, current_user.id, db)

    rules = json.loads(settings.sort_config or "[]")
    # Sắp xếp theo order trước khi trả về
    rules.sort(key=lambda r: r.get("order", 0))

    print(f"[SORT] GET ✅ {len(rules)} rules")
    return rules


@router.put(
    "/project/{projectId}/sort",
    summary="Cập nhật hoặc tắt sort"
)
def update_sort_settings(
    projectId: str,
    rules: List[SortRule],  # Body là mảng trực tiếp
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    PUT /project/{projectId}/sort

    - Body là mảng các tiêu chí sort
    - Truyền [] để tắt sort
    - Tối đa 5 rules, không trùng field, không trùng order
    """
    print(f"[SORT] PUT - User {current_user.id}, Project {projectId}, {len(rules)} rules")

    verify_project_owner(projectId, current_user.id, db)
    settings = get_or_create_sort_settings(projectId, current_user.id, db)

    if len(rules) == 0:
        # Tắt sort
        settings.enabled = False
        settings.sort_config = "[]"
        message = "Sort settings cleared"
        print(f"[SORT] PUT ✅ Tắt sort")
    else:
        # Validate rules
        try:
            validate_sort_rules(rules)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        settings.enabled = True
        settings.sort_config = json.dumps([r.model_dump() for r in rules])
        message = "Sort settings updated successfully"
        print(f"[SORT] PUT ✅ Bật sort với {len(rules)} rules")

    try:
        db.commit()
        return {"message": message}
    except Exception as e:
        db.rollback()
        print(f"[SORT] PUT ❌ Lỗi: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi lưu cài đặt sort: {str(e)}"
        )
