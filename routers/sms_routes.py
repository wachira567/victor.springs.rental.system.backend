from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session, joinedload
from typing import List
import models, schemas, auth
from database import get_db

router = APIRouter(prefix="/sms", tags=["sms"])

# Using schemas directly from schemas.py now

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

@router.get("/templates", response_model=List[schemas.SmsTemplateOut])
def get_templates(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    return db.query(models.SmsTemplate).all()

@router.post("/templates", response_model=schemas.SmsTemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(template: schemas.SmsTemplateCreate, 
                    db: Session = Depends(get_db), 
                    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    new_template = models.SmsTemplate(**template.model_dump())
    new_template.created_by_id = current_user.id
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    return new_template

@router.put("/templates/{template_id}", response_model=schemas.SmsTemplateOut)
def update_template(template_id: int,
                    template: schemas.SmsTemplateCreate,
                    db: Session = Depends(get_db),
                    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    db_template = db.query(models.SmsTemplate).filter(models.SmsTemplate.id == template_id).first()
    if not db_template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    for key, value in template.model_dump().items():
        setattr(db_template, key, value)
    db_template.updated_by_id = current_user.id
    
    db.commit()
    db.refresh(db_template)
    return db_template

@router.delete("/templates/{template_id}")
def delete_template(template_id: int,
                   db: Session = Depends(get_db),
                   current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    db_template = db.query(models.SmsTemplate).filter(models.SmsTemplate.id == template_id).first()
    if not db_template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Check if template is used in any schedules
    schedules = db.query(models.SmsSchedule).filter(models.SmsSchedule.template_id == template_id).first()
    if schedules:
        raise HTTPException(status_code=400, detail="Cannot delete template that is used in schedules")
    
    db.delete(db_template)
    db.commit()
    return {"message": "Template deleted successfully"}

@router.get("/schedules", response_model=List[schemas.SmsScheduleOut])
def get_schedules(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    return db.query(models.SmsSchedule).all()

@router.post("/schedules", response_model=schemas.SmsScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(schedule: schemas.SmsScheduleCreate, 
                    db: Session = Depends(get_db), 
                    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    new_schedule = models.SmsSchedule(**schedule.model_dump())
    new_schedule.created_by_id = current_user.id
    db.add(new_schedule)
    db.commit()
    db.refresh(new_schedule)
    return new_schedule

@router.post("/dispatch/manual")
def dispatch_manual(dispatch: schemas.ManualDispatch,
                    db: Session = Depends(get_db),
                    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    
    tenants = db.query(models.Tenant).filter(models.Tenant.id.in_(dispatch.tenant_ids)).all()
    sent_count = 0
    for tenant in tenants:
        msg = dispatch.message_content.replace('{tenant_name}', tenant.full_name)
        mock_send_sms(tenant.phone_number, msg, tenant.id, db)
        sent_count += 1
        
    return {"message": f"Successfully dispatched {sent_count} messages."}

@router.get("/logs")
def get_sms_logs(
    response: Response,
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    offset = (page - 1) * limit
    
    query = db.query(models.SmsLog)
    total_count = query.count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    
    logs = (
        query.options(joinedload(models.SmsLog.tenant))
        .order_by(models.SmsLog.sent_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    
    result = []
    for log in logs:
        result.append({
            "id": log.id,
            "tenant_id": log.tenant_id,
            "tenant_name": log.tenant.full_name if log.tenant else None,
            "phone_number": log.phone_number,
            "message_content": log.message_content,
            "sent_at": str(log.sent_at),
            "status": log.status
        })
    return result
