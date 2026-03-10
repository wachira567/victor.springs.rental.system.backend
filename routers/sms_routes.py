from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import models, schemas, auth
from database import get_db

router = APIRouter(prefix="/sms", tags=["sms"])

class SmsTemplateCreate(schemas.BaseModel):
    name: str
    content: str

class SmsTemplateOut(SmsTemplateCreate):
    id: int
    class Config:
        from_attributes = True

class SmsScheduleCreate(schemas.BaseModel):
    template_id: int
    target_group: str = "ALL_TENANTS"
    send_day: int
    send_time: str
    is_active: bool = True

class SmsScheduleOut(SmsScheduleCreate):
    id: int
    class Config:
        from_attributes = True

class ManualDispatch(schemas.BaseModel):
    tenant_ids: List[int]
    message_content: str

# --- MOCK SMS SERVICE ---
def mock_send_sms(phone_number: str, message: str, tenant_id: int, db: Session):
    print(f"\n[SMS DISPATCHED] To: {phone_number} | Msg: {message}\n")
    log = models.SmsLog(
        tenant_id=tenant_id,
        phone_number=phone_number,
        message_content=message,
        status="SENT"
    )
    db.add(log)
    db.commit()
    return True

@router.get("/templates", response_model=List[SmsTemplateOut])
def get_templates(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    return db.query(models.SmsTemplate).all()

@router.post("/templates", response_model=SmsTemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(template: SmsTemplateCreate, 
                    db: Session = Depends(get_db), 
                    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    new_template = models.SmsTemplate(**template.model_dump())
    new_template.created_by_id = current_user.id
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    return new_template

@router.get("/schedules", response_model=List[SmsScheduleOut])
def get_schedules(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    return db.query(models.SmsSchedule).all()

@router.post("/schedules", response_model=SmsScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(schedule: SmsScheduleCreate, 
                    db: Session = Depends(get_db), 
                    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    new_schedule = models.SmsSchedule(**schedule.model_dump())
    new_schedule.created_by_id = current_user.id
    db.add(new_schedule)
    db.commit()
    db.refresh(new_schedule)
    return new_schedule

@router.post("/dispatch/manual")
def dispatch_manual(dispatch: ManualDispatch,
                    db: Session = Depends(get_db),
                    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    
    tenants = db.query(models.Tenant).filter(models.Tenant.id.in_(dispatch.tenant_ids)).all()
    sent_count = 0
    for tenant in tenants:
        msg = dispatch.message_content.replace('{tenant_name}', tenant.full_name)
        mock_send_sms(tenant.phone_number, msg, tenant.id, db)
        sent_count += 1
        
    return {"message": f"Successfully dispatched {sent_count} messages."}
