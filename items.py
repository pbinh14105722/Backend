"""
Items/Folders CRUD endpoints
Handles project folders and items with ownership verification
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import models
import schemas
import database
from dependencies import get_current_user

router = APIRouter(prefix="/items", tags=["Items & Folders"])


@router.get("", response_model=list[schemas.ItemResponse])
def get_all_items(
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(get_current_user)
):
    """
    Get all items/folders belonging to the current user
    Sorted by position in ascending order
    
    Args:
        db: Database session
        current_user: Authenticated user from JWT token
        
    Returns:
        List of items owned by the user
    """
    return db.query(models.Item)\
        .filter(models.Item.owner_id == current_user.id)\
        .order_by(models.Item.position.asc())\
        .all()


@router.post("", response_model=schemas.ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(
    item: schemas.ItemCreate, 
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(get_current_user)
):
    """
    Create a new item/folder
    
    Args:
        item: Item data to create
        db: Database session
        current_user: Authenticated user (will be set as owner)
        
    Returns:
        Created item with generated ID
        
    Raises:
        HTTPException: If database operation fails
    """
    db_item = models.Item(
        **item.model_dump(),
        owner_id=current_user.id
    )
    
    try:
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return db_item
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"Lỗi khi lưu vào database: {str(e)}"
        )


@router.put("/{item_id}", response_model=schemas.ItemResponse)
def update_item(
    item_id: str, 
    item_data: schemas.ItemUpdate, 
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(get_current_user)
):
    """
    Update an existing item/folder
    User can only update items they own
    
    Args:
        item_id: ID of item to update
        item_data: Fields to update
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Updated item
        
    Raises:
        HTTPException: If item not found or user doesn't have permission
    """
    # Find item with ownership check
    db_item = db.query(models.Item).filter(
        models.Item.id == item_id, 
        models.Item.owner_id == current_user.id
    ).first()
    
    if not db_item:
        raise HTTPException(
            status_code=404, 
            detail="Không tìm thấy mục này (hoặc bạn không có quyền)"
        )
    
    # Update only provided fields
    update_data = item_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_item, key, value)
    
    try:
        db.commit()
        db.refresh(db_item)
        return db_item
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"Lỗi khi cập nhật: {str(e)}"
        )


@router.post("/save-all")
def save_all_structure(
    items: list[schemas.ItemBatchUpdate], 
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Batch update multiple items at once (optimized for drag-and-drop reordering)
    Only updates safe fields: name, type, parent_id, position, color, expanded
    
    Args:
        items: List of items with updated data
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Success message with count of updated items
        
    Raises:
        HTTPException: If batch update fails
    """
    if not items:
        return {"message": "Không có dữ liệu để cập nhật"}
    
    item_ids = [item.id for item in items]
    
    # Find existing items belonging to current user
    db_items = db.query(models.Item).filter(
        models.Item.id.in_(item_ids),
        models.Item.owner_id == current_user.id
    ).all()

    db_items_dict = {item.id: item for item in db_items}

    updated_count = 0
    for item_data in items:
        db_item = db_items_dict.get(item_data.id)
        if db_item:
            # ✅ Only update safe fields (prevent owner_id tampering)
            safe_fields = ['name', 'type', 'parent_id', 'position', 'color', 'expanded']
            update_data = item_data.model_dump(include=safe_fields)
            for key, value in update_data.items():
                setattr(db_item, key, value)
            
            updated_count += 1

    try:
        db.commit()
        return {"message": f"Đã cập nhật {updated_count}/{len(items)} mục thành công"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"Lỗi khi lưu: {str(e)}"
        )


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: str, 
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(get_current_user)
):
    """
    Delete an item/folder
    User can only delete items they own
    
    Args:
        item_id: ID of item to delete
        db: Database session
        current_user: Authenticated user
        
    Raises:
        HTTPException: If item not found or user doesn't have permission
    """
    db_item = db.query(models.Item).filter(
        models.Item.id == item_id, 
        models.Item.owner_id == current_user.id
    ).first()
    
    if not db_item:
        raise HTTPException(
            status_code=404, 
            detail="Không tìm thấy mục này (hoặc bạn không có quyền)"
        )
    
    try:
        db.delete(db_item)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"Lỗi khi xóa: {str(e)}"
        )