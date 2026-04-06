from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

import models, auth
from database import get_db

router = APIRouter(prefix="/logistics", tags=["logistics"])

# --- Schemas ---

class NoteCreate(BaseModel):
    title: str
    content: str
    date: str
    is_public: bool = False

class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    is_public: Optional[bool] = None

class ReminderCreate(BaseModel):
    note_id: Optional[int] = None
    target_date: datetime
    importance_color: str
    target_phone: Optional[str] = None
    platform: str

class MaintenanceCreate(BaseModel):
    tenant_id: Optional[int] = None
    contractor_id: Optional[int] = None
    task_details: str
    scheduled_date: Optional[datetime] = None

class MaintenanceUpdate(BaseModel):
    status: Optional[str] = None
    contractor_id: Optional[int] = None
    cost: Optional[float] = None
    landlord_deduction: Optional[float] = None
    task_details: Optional[str] = None

class ScheduledMessageCreate(BaseModel):
    dispatch_time: datetime
    message_payload: str
    platform_type: str
    recipient_phone: str

class BroadcastRequest(BaseModel):
    message: str
    platform: str = "sms"
    tenant_ids: List[int] = []

# ==============================================================================
# NOTES (Private by default, owner-scoped)
# ==============================================================================

@router.get("/notes")
def get_notes(
    show_all: bool = Query(False, description="Super admin: show notes from all users"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin", "landlord"]))
):
    """
    Returns notes visible to the current user:
    - Own notes (created_by_id == current user)
    - Public notes (is_public == True)
    - Super admin with show_all=True: all notes including deleted
    """
    query = db.query(models.Note).options(joinedload(models.Note.created_by))

    if current_user.role == "super_admin" and show_all:
        # Super admin sees everything
        pass
    else:
        # Regular users see their own notes + public notes, excluding deleted
        query = query.filter(models.Note.is_deleted == False)
        query = query.filter(
            or_(
                models.Note.created_by_id == current_user.id,
                models.Note.is_public == True,
                models.Note.created_by_id == None  # Legacy notes without owner
            )
        )

    notes = query.order_by(models.Note.date.desc()).all()

    return [
        {
            "id": n.id,
            "title": n.title,
            "content": n.content,
            "date": str(n.date),
            "is_deleted": n.is_deleted,
            "is_public": n.is_public if n.is_public is not None else False,
            "created_by_id": n.created_by_id,
            "created_by_name": n.created_by.name if n.created_by else "Unknown",
            "is_own": n.created_by_id == current_user.id,
        }
        for n in notes
    ]


@router.post("/notes")
def create_note(
    data: NoteCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))
):
    dt = datetime.strptime(data.date, "%Y-%m-%d").date()
    note = models.Note(
        title=data.title,
        content=data.content,
        date=dt,
        is_public=data.is_public,
        created_by_id=current_user.id
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return {
        "id": note.id,
        "title": note.title,
        "content": note.content,
        "date": str(note.date),
        "is_public": note.is_public,
        "is_deleted": note.is_deleted,
    }


@router.put("/notes/{note_id}")
def update_note(
    note_id: int,
    data: NoteUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))
):
    note = db.query(models.Note).filter(models.Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    # Only owner or super_admin can edit
    if note.created_by_id != current_user.id and current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="You can only edit your own notes")

    if data.title is not None:
        note.title = data.title
    if data.content is not None:
        note.content = data.content
    if data.is_public is not None:
        # Only admin/super_admin can toggle public
        note.is_public = data.is_public

    db.commit()
    return {"status": "success"}


@router.delete("/notes/{note_id}")
def delete_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))
):
    note = db.query(models.Note).filter(models.Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.created_by_id != current_user.id and current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="You can only delete your own notes")
    note.is_deleted = True
    db.commit()
    return {"message": "Note logically deleted"}


@router.post("/reminders")
def create_reminder(
    data: ReminderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))
):
    rem = models.Reminder(**data.model_dump())
    db.add(rem)
    db.commit()
    return {"status": "success"}


# ==============================================================================
# MAINTENANCE
# ==============================================================================

@router.post("/maintenance")
def create_maintenance(
    data: MaintenanceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))
):
    m = models.MaintenanceRequest(**data.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"status": "success", "id": m.id}


@router.get("/maintenance")
def get_maintenance(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))
):
    """Returns maintenance requests with tenant property/unit info for contractor messages."""
    query = db.query(models.MaintenanceRequest).options(
        joinedload(models.MaintenanceRequest.tenant).joinedload(models.Tenant.leases).joinedload(models.Lease.unit).joinedload(models.Unit.property),
        joinedload(models.MaintenanceRequest.contractor)
    )
    if status:
        query = query.filter(models.MaintenanceRequest.status == status.upper())
    results = query.order_by(models.MaintenanceRequest.created_at.desc()).all()

    out = []
    for r in results:
        # Get tenant's active lease info for property/unit details
        tenant_unit = None
        tenant_property = None
        if r.tenant and r.tenant.leases:
            active_lease = next((l for l in r.tenant.leases if l.status == "ACTIVE"), None)
            if active_lease and active_lease.unit:
                tenant_unit = active_lease.unit.unit_number
                if active_lease.unit.property:
                    tenant_property = active_lease.unit.property.name

        out.append({
            "id": r.id,
            "task_details": r.task_details,
            "status": r.status,
            "scheduled_date": r.scheduled_date.isoformat() if r.scheduled_date else None,
            "cost": float(r.cost) if r.cost else 0,
            "landlord_deduction": float(r.landlord_deduction) if r.landlord_deduction else 0,
            "tenant_id": r.tenant_id,
            "tenant_name": r.tenant.full_name if r.tenant else None,
            "tenant_phone": r.tenant.phone_number if r.tenant else None,
            "tenant_unit": tenant_unit,
            "tenant_property": tenant_property,
            "contractor_id": r.contractor_id,
            "contractor_name": r.contractor.name if r.contractor else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return out


@router.put("/maintenance/{request_id}")
def update_maintenance(
    request_id: int,
    data: MaintenanceUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))
):
    m = db.query(models.MaintenanceRequest).filter(models.MaintenanceRequest.id == request_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Maintenance request not found")

    if data.status is not None:
        m.status = data.status.upper()
    if data.contractor_id is not None:
        m.contractor_id = data.contractor_id
    if data.task_details is not None:
        m.task_details = data.task_details

    if current_user.role == "super_admin":
        if data.cost is not None:
            m.cost = data.cost
        if data.landlord_deduction is not None:
            m.landlord_deduction = data.landlord_deduction

    m.updated_by_id = current_user.id
    db.commit()
    db.refresh(m)
    return {"status": "success", "message": "Maintenance request updated"}


# ==============================================================================
# SCHEDULED MESSAGES
# ==============================================================================

@router.post("/scheduled_messages")
def schedule_message(
    data: ScheduledMessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))
):
    m = models.ScheduledMessage(**data.model_dump())
    db.add(m)
    db.commit()
    return {"status": "success"}


@router.get("/scheduled_messages")
def get_scheduled_messages(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))
):
    return db.query(models.ScheduledMessage).order_by(models.ScheduledMessage.dispatch_time.desc()).all()


# ==============================================================================
# BROADCAST MESSAGING (Super Admin Only)
# ==============================================================================

@router.get("/broadcast/active-tenants")
def get_active_tenants_for_broadcast(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query("", description="Search by name or phone"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin"]))
):
    query = db.query(models.Tenant).filter(models.Tenant.is_active == True)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                models.Tenant.full_name.ilike(search_term),
                models.Tenant.phone_number.ilike(search_term),
                models.Tenant.email.ilike(search_term)
            )
        )
    total = query.count()
    tenants = query.order_by(models.Tenant.full_name).offset((page - 1) * limit).limit(limit).all()
    return {
        "tenants": [
            {"id": t.id, "full_name": t.full_name, "phone_number": t.phone_number, "email": t.email, "is_active": t.is_active}
            for t in tenants
        ],
        "total": total, "page": page, "limit": limit,
        "total_pages": (total + limit - 1) // limit
    }


@router.get("/broadcast/arrears-summary")
def get_arrears_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin"]))
):
    leases = (
        db.query(models.Lease)
        .options(
            joinedload(models.Lease.tenant),
            joinedload(models.Lease.unit).joinedload(models.Unit.property),
            joinedload(models.Lease.invoices),
            joinedload(models.Lease.payments)
        )
        .filter(models.Lease.status == "ACTIVE")
        .all()
    )
    arrears_list = []
    for lease in leases:
        if not lease.tenant or not getattr(lease.tenant, 'is_active', True):
            continue
        total_invoiced = sum(float(inv.amount) for inv in (lease.invoices or []))
        total_paid = sum(float(p.amount) for p in (lease.payments or []))
        balance = total_invoiced - total_paid
        if balance > 0:
            arrears_list.append({
                "tenant_id": lease.tenant_id,
                "tenant_name": lease.tenant.full_name,
                "phone_number": lease.tenant.phone_number,
                "unit": lease.unit.unit_number if lease.unit else "N/A",
                "property": lease.unit.property.name if lease.unit and lease.unit.property else "N/A",
                "rent_amount": float(lease.rent_amount),
                "total_invoiced": total_invoiced, "total_paid": total_paid,
                "arrears": round(balance, 2)
            })
    return arrears_list


@router.post("/broadcast/send")
def send_broadcast(
    data: BroadcastRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin"]))
):
    if data.tenant_ids:
        tenants = db.query(models.Tenant).filter(models.Tenant.id.in_(data.tenant_ids), models.Tenant.is_active == True).all()
    else:
        tenants = db.query(models.Tenant).filter(models.Tenant.is_active == True).all()

    results = []
    for tenant in tenants:
        if not tenant.phone_number:
            results.append({"tenant_id": tenant.id, "name": tenant.full_name, "status": "UNDELIVERED", "reason": "No phone number"})
            continue
        msg = models.ScheduledMessage(
            dispatch_time=datetime.utcnow(),
            message_payload=data.message,
            platform_type=data.platform,
            recipient_phone=tenant.phone_number,
            status="DELIVERED"
        )
        db.add(msg)
        results.append({"tenant_id": tenant.id, "name": tenant.full_name, "phone": tenant.phone_number, "status": "DELIVERED"})

    db.commit()
    return {
        "total_sent": len([r for r in results if r["status"] == "DELIVERED"]),
        "total_failed": len([r for r in results if r["status"] == "UNDELIVERED"]),
        "details": results
    }
