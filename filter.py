import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import models, database, schemas
from schemas import FilterSettingsUpdate, FilterSettingsResponse
from dependencies import get_current_user, verify_project_owner

router = APIRouter()


# ========== HELPERS ==========

def get_or_create_filter_settings(project_id: str, user_id: int, db: Session) -> models.FilterSettings:
    settings = db.query(models.FilterSettings).filter(
        models.FilterSettings.project_id == project_id,
        models.FilterSettings.user_id == user_id
    ).first()
    if not settings:
        settings = models.FilterSettings(
            user_id=user_id,
            project_id=project_id,
            enabled=False,
            filter_config=json.dumps({"logic": "and", "filters": []})
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def build_filter_response(settings: models.FilterSettings) -> dict:
    """Chuyển DB object sang response dict đúng format"""
    data = json.loads(settings.filter_config or '{"logic": "and", "filters": []}')

    # Tương thích ngược: record cũ lưu dạng list [] thay vì object
    if isinstance(data, list):
        return {"logic": "and", "filters": data}

    return {
        "logic": data.get("logic", "and"),
        "filters": data.get("filters", [])
    }


# ========== ROUTES ==========

@router.get(
    "/project/{projectId}/filter",
    response_model=FilterSettingsResponse,
    summary="Lấy cài đặt filter hiện tại"
)
def get_filter_settings(
    projectId: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    GET /project/{projectId}/filter

    Trả về object filter hiện tại.
    Trả về {"logic": "and", "filters": []} nếu chưa có hoặc đã tắt.
    """
    print(f"[FILTER] GET - User {current_user.id}, Project {projectId}")

    verify_project_owner(projectId, current_user.id, db)
    settings = get_or_create_filter_settings(projectId, current_user.id, db)

    response = build_filter_response(settings)
    print(f"[FILTER] GET ✅ {len(response['filters'])} filters, logic={response['logic']}")
    return response


@router.put(
    "/project/{projectId}/filter",
    summary="Cập nhật hoặc tắt filter"
)
def update_filter_settings(
    projectId: str,
    data: FilterSettingsUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    PUT /project/{projectId}/filter

    - filters=[]  → tắt filter
    - logic mặc định "and" nếu không truyền
    - Tối đa 10 rules
    """
    print(f"[FILTER] PUT - User {current_user.id}, Project {projectId}, {len(data.filters)} filters")

    verify_project_owner(projectId, current_user.id, db)
    settings = get_or_create_filter_settings(projectId, current_user.id, db)

    if len(data.filters) == 0:
        # Tắt filter
        settings.enabled = False
        settings.filter_config = json.dumps({"logic": data.logic, "filters": []})
        message = "Filter settings cleared"
        print(f"[FILTER] PUT ✅ Tắt filter")
    else:
        # Bật filter
        settings.enabled = True
        settings.filter_config = json.dumps({
            "logic": data.logic,
            "filters": [f.model_dump() for f in data.filters]
        })
        message = "Filter settings updated successfully"
        print(f"[FILTER] PUT ✅ Bật filter với {len(data.filters)} rules, logic={data.logic}")

    try:
        db.commit()
        return {"message": message}
    except Exception as e:
        db.rollback()
        print(f"[FILTER] PUT ❌ Lỗi: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi lưu cài đặt filter: {str(e)}"
        )
