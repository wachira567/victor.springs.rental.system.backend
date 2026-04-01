from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
import models, schemas, auth
from database import get_db
from permissions import ALL_PERMISSIONS

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

@router.get("/permissions")
def get_permissions(current_user: models.User = Depends(auth.require_role(["super_admin"]))):
    return ALL_PERMISSIONS

@router.get("", response_model=schemas.UserPaginationOut)
def get_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
    search: Optional[str] = None,
    role: Optional[str] = None,
    page: int = 1,
    limit: int = 20
):
    query = db.query(models.User)
    if role:
        if "," in role:
            role_list = [r.strip() for r in role.split(",")]
            query = query.filter(models.User.role.in_(role_list))
        else:
            query = query.filter(models.User.role == role)
    if search:
        query = query.filter(
            (models.User.name.ilike(f"%{search}%")) |
            (models.User.email.ilike(f"%{search}%"))
        )
    
    total = query.count()
    users = query.order_by(models.User.id.desc()).offset((page-1)*limit).limit(limit).all()
    
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "users": users
    }

@router.post("", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def create_user(user: schemas.UserCreate, 
                db: Session = Depends(get_db), 
                current_user: models.User = Depends(auth.require_role(["super_admin"]))):
    
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = auth.get_password_hash(user.password)
    
    new_user = models.User(
        email=user.email,
        name=user.name,
        role=user.role,
        password_hash=hashed_password,
        is_approved=True,  # Admins creating users skips approval
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.put("/{user_id}", response_model=schemas.UserOut)
def update_user(user_id: int, 
                user_data: dict,
                db: Session = Depends(get_db),
                current_user: models.User = Depends(auth.require_role(["super_admin"]))):
    
    user_to_update = db.query(models.User).filter(models.User.id == user_id).first()
    if not user_to_update:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Prevent super_admin self-demotion or malicious edits
    if user_to_update.role == "super_admin" and user_to_update.id == current_user.id:
        if "role" in user_data and user_data["role"] != "super_admin":
            raise HTTPException(status_code=400, detail="Super Admin cannot demote themselves")

    if "name" in user_data:
        user_to_update.name = user_data["name"]
    if "email" in user_data:
        # Check if email is taken by another user
        existing = db.query(models.User).filter(models.User.email == user_data["email"], models.User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered to another user")
        user_to_update.email = user_data["email"]
    if "role" in user_data:
        user_to_update.role = user_data["role"]
    if "is_approved" in user_data:
        user_to_update.is_approved = user_data["is_approved"]
    if "is_active" in user_data:
        user_to_update.is_active = user_data["is_active"]
    if "permissions" in user_data:
        user_to_update.permissions = user_data["permissions"]
    if "password" in user_data and user_data["password"]:
        user_to_update.password_hash = auth.get_password_hash(user_data["password"])
        
    db.commit()
    db.refresh(user_to_update)
    return user_to_update

@router.delete("/{user_id}")
def delete_user(user_id: int, 
                db: Session = Depends(get_db),
                current_user: models.User = Depends(auth.require_role(["super_admin"]))):
    
    user_to_delete = db.query(models.User).filter(models.User.id == user_id).first()
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user_to_delete.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete yourself")
    if user_to_delete.role == "super_admin":
        # Don't delete other super admins for safety, unless overridden.
        # But for this system let's allow it as long as it's not self
        pass

    db.delete(user_to_delete)
    db.commit()
    return {"message": "User deleted successfully"}
