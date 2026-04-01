from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
import auth
import schemas
import models
from database import get_db
from google.oauth2 import id_token
from google.auth.transport import requests
import os

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "YOUR_GOOGLE_CLIENT_ID")

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    hashed_password = auth.get_password_hash(user.password)
    
    new_user = models.User(
        email=user.email,
        name=user.name,
        password_hash=hashed_password,
        role=user.role,
        is_approved=False # Requires admin approval
    )
    db.add(new_user)
    db.commit()
    return {"message": "Registration successful. Pending Super Admin approval."}

@router.post("/login", response_model=schemas.Token)
def login(user_credentials: schemas.UserCreate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == user_credentials.email).first()
    if not user or not auth.verify_password(user_credentials.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Credentials")
        
    if not user.is_approved:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account pending approval")
        
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": str(user.id), "role": user.role, "permissions": user.permissions or []}, 
        expires_delta=access_token_expires
    )
    
    # Audit Log for Login
    db.add(models.AuditLog(
        action="LOGIN",
        table_name="users",
        record_id=user.id,
        user_id=user.id,
        new_data={"email": user.email, "method": "password"}
    ))
    db.commit()

    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/google", response_model=schemas.Token)
def google_login(google_login_data: schemas.GoogleLogin, db: Session = Depends(get_db)):
    try:
        idinfo = id_token.verify_oauth2_token(
            google_login_data.token, requests.Request(), GOOGLE_CLIENT_ID
        )
        
        email = idinfo.get("email")
        name = idinfo.get("name")
        google_id = idinfo.get("sub")
        
        if not email:
            raise HTTPException(status_code=400, detail="Email not provided by Google")
            
        user = db.query(models.User).filter(models.User.email == email).first()
        
        if not user:
            # Register new user from Google
            user = models.User(
                email=email,
                name=name,
                google_id=google_id,
                role=google_login_data.role, # default tenant or what frontend sends
                is_approved=True if google_login_data.role == "tenant" else False # tenants auto-approved, others need admin
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        elif not user.google_id:
            # Link google account if email matches existing
            user.google_id = google_id
            db.commit()
            
        if not user.is_approved:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account pending admin approval")
            
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account inactive")
            
        access_token = auth.create_access_token(
            data={"sub": str(user.id), "role": user.role, "permissions": user.permissions or []}, 
            expires_delta=access_token_expires
        )

        # Audit Log for Google Login
        db.add(models.AuditLog(
            action="LOGIN",
            table_name="users",
            record_id=user.id,
            user_id=user.id,
            new_data={"email": user.email, "method": "google"}
        ))
        db.commit()

        return {"access_token": access_token, "token_type": "bearer"}
        
    except ValueError as e:
        # Invalid token
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {str(e)}")

@router.post("/admin/approve/{user_id}")
def approve_user(user_id: int, current_user: models.User = Depends(auth.require_role(["super_admin"])), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.is_approved = True
    db.commit()
    return {"message": f"User {user.email} approved."}
