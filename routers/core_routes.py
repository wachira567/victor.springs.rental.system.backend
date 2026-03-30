from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from typing import List
import models, schemas, auth
from database import get_db

router = APIRouter(prefix="/core", tags=["core"])

# ==============================================================================
# PROPERTIES
# ==============================================================================
@router.get("/properties", response_model=List[schemas.PropertyOut])
def get_properties(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    properties = db.query(models.Property).all()
    return properties

@router.post("/properties", response_model=schemas.PropertyOut, status_code=status.HTTP_201_CREATED)
def create_property(property: schemas.PropertyCreate, 
                    db: Session = Depends(get_db), 
                    current_user: models.User = Depends(auth.require_role(["super_admin", "admin", "landlord"]))):
    
    new_property = models.Property(**property.model_dump())
    new_property.created_by_id = current_user.id 
    
    db.add(new_property)
    db.commit()
    db.refresh(new_property)
    return new_property

# ==============================================================================
# UNITS
# ==============================================================================
@router.get("/units", response_model=List[schemas.UnitOut])
def get_units(vacant: bool = None, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    query = db.query(models.Unit)
    if vacant is not None:
        query = query.filter(models.Unit.is_vacant == vacant)
    return query.all()

# ==============================================================================
# TENANTS
# ==============================================================================
@router.get("/tenants", response_model=List[schemas.TenantOut])
def get_tenants(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    tenants = db.query(models.Tenant).all()
    return tenants

@router.post("/tenants", response_model=schemas.TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(tenant: schemas.TenantCreate, 
                  db: Session = Depends(get_db), 
                  current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    
    db_tenant = db.query(models.Tenant).filter(models.Tenant.national_id == tenant.national_id).first()
    if db_tenant:
        raise HTTPException(status_code=400, detail="Tenant with this National ID already exists")

    new_tenant = models.Tenant(**tenant.model_dump())
    new_tenant.created_by_id = current_user.id
    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)
    return new_tenant

# ==============================================================================
# LEASES (with joined unit/property/tenant data)
# ==============================================================================
@router.get("/leases")
def get_leases(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    leases = db.query(models.Lease).options(
        joinedload(models.Lease.tenant),
        joinedload(models.Lease.unit).joinedload(models.Unit.property)
    ).all()
    result = []
    for lease in leases:
        data = {
            "id": lease.id,
            "unit_id": lease.unit_id,
            "tenant_id": lease.tenant_id,
            "start_date": str(lease.start_date),
            "end_date": str(lease.end_date) if lease.end_date else None,
            "rent_amount": float(lease.rent_amount),
            "deposit_amount": float(lease.deposit_amount) if lease.deposit_amount else 0,
            "status": lease.status,
            "unit_number": None,
            "property_name": None,
            "tenant_name": None,
        }
        # Join unit and property
        if lease.unit:
            data["unit_number"] = lease.unit.unit_number
            if lease.unit.property:
                data["property_name"] = lease.unit.property.name
        # Join tenant
        if lease.tenant:
            data["tenant_name"] = lease.tenant.full_name
        result.append(data)
    return result

@router.post("/leases", status_code=status.HTTP_201_CREATED)
def create_lease(lease: schemas.LeaseCreate, 
                 db: Session = Depends(get_db), 
                 current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
                 
    new_lease = models.Lease(**lease.model_dump())
    new_lease.created_by_id = current_user.id
    db.add(new_lease)
    db.commit()
    db.refresh(new_lease)
    return {"id": new_lease.id, "status": new_lease.status}

# ==============================================================================
# INVOICES
# ==============================================================================
from datetime import date
from sqlalchemy.orm import joinedload

@router.post("/invoices/generate", status_code=status.HTTP_201_CREATED)
def generate_monthly_invoices(db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    active_leases = db.query(models.Lease).filter(models.Lease.status == "ACTIVE").all()
    current_month = date.today().replace(day=1)
    
    generated = 0
    for lease in active_leases:
        # Check if rent invoice for this exact month exists
        existing = db.query(models.Invoice).filter(
            models.Invoice.lease_id == lease.id,
            models.Invoice.type == "Rent",
            models.Invoice.billing_period == current_month
        ).first()
        
        if not existing:
            new_inv = models.Invoice(
                lease_id=lease.id,
                billing_period=current_month,
                type="Rent",
                amount=lease.rent_amount,
                amount_paid=0,
                is_paid=False,
                created_by_id=current_user.id
            )
            db.add(new_inv)
            generated += 1
            
    db.commit()
    return {"message": f"Successfully generated {generated} new rent invoices for {current_month.strftime('%B %Y')}."}
@router.get("/invoices")
def get_invoices(
    response: Response,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    offset = (page - 1) * limit
    
    # Get total count for pagination via Response header
    total_count = db.query(models.Invoice).count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    # Use eager loading to prevent N+1 query timeouts on large datasets (12k+ invoices)
    invoices = db.query(models.Invoice).options(
        joinedload(models.Invoice.lease).joinedload(models.Lease.tenant),
        joinedload(models.Invoice.lease).joinedload(models.Lease.unit).joinedload(models.Unit.property)
    ).order_by(models.Invoice.billing_period.desc()).offset(offset).limit(limit).all()
    
    result = []
    for inv in invoices:
        data = schemas.InvoiceOut.model_validate(inv).model_dump()
        if inv.lease:
            if inv.lease.tenant:
                data["tenant_name"] = inv.lease.tenant.full_name
            if inv.lease.unit:
                data["unit_number"] = inv.lease.unit.unit_number
                if inv.lease.unit.property:
                    data["property_name"] = inv.lease.unit.property.name
        result.append(data)
    return result

@router.post("/invoices", response_model=schemas.InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(invoice: schemas.InvoiceCreate,
                   db: Session = Depends(get_db),
                   current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    new_invoice = models.Invoice(**invoice.model_dump())
    new_invoice.created_by_id = current_user.id
    db.add(new_invoice)
    db.commit()
    db.refresh(new_invoice)
    
    # Reload with joined data so frontend parsing matches InvoiceOut
    inv = db.query(models.Invoice).options(
        joinedload(models.Invoice.lease).joinedload(models.Lease.tenant),
        joinedload(models.Invoice.lease).joinedload(models.Lease.unit).joinedload(models.Unit.property)
    ).filter(models.Invoice.id == new_invoice.id).first()
    
    data = schemas.InvoiceOut.model_validate(inv).model_dump()
    if inv.lease:
        if inv.lease.tenant:
            data["tenant_name"] = inv.lease.tenant.full_name
        if inv.lease.unit:
            data["unit_number"] = inv.lease.unit.unit_number
            if inv.lease.unit.property:
                data["property_name"] = inv.lease.unit.property.name
    return data

@router.delete("/invoices/{invoice_id}", status_code=status.HTTP_200_OK)
def reverse_invoice(invoice_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    inv = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    if inv.amount_paid and inv.amount_paid > 0:
        raise HTTPException(status_code=400, detail="Cannot reverse an invoice that currently has payments allocated to it.")
        
    # Serialize old state before deletion
    old_state = {
        "id": inv.id,
        "lease_id": inv.lease_id,
        "type": inv.type,
        "amount": str(inv.amount),
        "billing_period": str(inv.billing_period)
    }
    db.delete(inv)
    
    # Manually Inject REVERSE AuditLog to bypass standard alchemy hook because we want explicit metadata
    import json
    new_log = models.AuditLog(
        action="REVERSE_INVOICE",
        table_name="invoices",
        record_id=invoice_id,
        user_id=current_user.id,
        old_data=old_state,
        new_data=None # Explicitly set new_data to None for a reverse action
    )
    db.add(new_log)
    db.commit()
    
    return {"message": "Invoice reversed successfully"}

# ==============================================================================
# BILL TYPES
# ==============================================================================

@router.get("/bill-types", response_model=List[schemas.BillTypeOut])
def get_bill_types(db: Session = Depends(get_db)):
    # Auto-seed defaults if table is completely empty
    count = db.query(models.BillType).count()
    if count == 0:
        defaults = ["Rent", "Water Bill", "Garbage Collection", "Security Fee", "Service Charge", "Power", "Rent Deposit", "Water Deposit"]
        for d in defaults:
            db.add(models.BillType(name=d))
        db.commit()
        
    return db.query(models.BillType).order_by(models.BillType.name).all()

@router.post("/bill-types", response_model=schemas.BillTypeOut, status_code=status.HTTP_201_CREATED)
def create_bill_type(bill_type: schemas.BillTypeCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    existing = db.query(models.BillType).filter(models.BillType.name.ilike(bill_type.name)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bill type with this name already exists")
    new_bt = models.BillType(name=bill_type.name)
    db.add(new_bt)
    db.commit()
    db.refresh(new_bt)
    return new_bt

@router.delete("/bill-types/{bt_id}")
def delete_bill_type(bt_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    bt = db.query(models.BillType).filter(models.BillType.id == bt_id).first()
    if not bt:
        raise HTTPException(status_code=404, detail="Bill type not found")
    
    # Check if invoices use this type string (they store the strict string natively)
    in_use = db.query(models.Invoice).filter(models.Invoice.type == bt.name).first()
    if in_use:
        raise HTTPException(status_code=400, detail="Cannot delete this bill type because it is actively used in existing invoices.")
        
    db.delete(bt)
    db.commit()
    return {"message": "Bill type deleted"}

# ==============================================================================
# PAYMENTS
# ==============================================================================
@router.get("/payments", response_model=List[schemas.PaymentOut])
def get_payments(
    response: Response,
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    offset = (page - 1) * limit
    total_count = db.query(models.Payment).count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    payments = db.query(models.Payment).options(
        joinedload(models.Payment.lease).joinedload(models.Lease.tenant),
        joinedload(models.Payment.lease).joinedload(models.Lease.unit).joinedload(models.Unit.property)
    ).order_by(models.Payment.payment_date.desc()).offset(offset).limit(limit).all()
    
    # Enhance payments with lease details
    enhanced_payments = []
    for p in payments:
        pd = schemas.PaymentOut.model_validate(p).model_dump()
        
        if p.lease:
            if p.lease.tenant:
                pd["tenant_name"] = p.lease.tenant.full_name
            if p.lease.unit:
                pd["unit_number"] = p.lease.unit.unit_number
                if p.lease.unit.property:
                    pd["property_name"] = p.lease.unit.property.name
                    
        enhanced_payments.append(pd)
        
    return enhanced_payments

@router.post("/payments", response_model=schemas.PaymentOut, status_code=status.HTTP_201_CREATED)
def create_payment(payment: schemas.PaymentCreate, 
                   db: Session = Depends(get_db), 
                   current_user: models.User = Depends(auth.require_role(["super_admin", "admin", "tenant"]))):
                   
    new_payment = models.Payment(**payment.model_dump())
    new_payment.created_by_id = current_user.id
    db.add(new_payment)
    db.commit()
    db.refresh(new_payment)
    return new_payment

# --- Meter Readings ---

@router.get("/meter-readings", response_model=List[schemas.MeterReadingOut])
def get_meter_readings(
    response: Response,
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    offset = (page - 1) * limit
    total_count = db.query(models.MeterReading).count()
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    readings = db.query(models.MeterReading).options(
        joinedload(models.MeterReading.unit).joinedload(models.Unit.property),
        joinedload(models.MeterReading.unit).joinedload(models.Unit.leases).joinedload(models.Lease.tenant)
    ).order_by(models.MeterReading.reading_date.desc()).offset(offset).limit(limit).all()
    
    enhanced_readings = []
    for r in readings:
        rd = schemas.MeterReadingOut.model_validate(r).model_dump()
        if r.unit:
            rd["unit_number"] = r.unit.unit_number
            if r.unit.property:
                rd["property_name"] = r.unit.property.name
                
            # Find the active lease from the joined leases
            active_lease = next((l for l in r.unit.leases if l.status == "ACTIVE"), None)
            if active_lease and active_lease.tenant:
                rd["tenant_name"] = active_lease.tenant.full_name
                
        enhanced_readings.append(rd)
        
    return enhanced_readings

@router.post("/meter-readings", response_model=schemas.MeterReadingOut, status_code=status.HTTP_201_CREATED)
def create_meter_reading(reading: schemas.MeterReadingCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    new_reading = models.MeterReading(**reading.model_dump())
    new_reading.created_by_id = current_user.id
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)
    return new_reading

# ==============================================================================
# EXPENDITURES
# ==============================================================================
@router.get("/expenditures", response_model=List[schemas.ExpenditureOut])
def get_expenditures(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    expenditures = db.query(models.Expenditure).all()
    result = []
    for exp in expenditures:
        data = {
            "id": exp.id,
            "property_id": exp.property_id,
            "notes": exp.notes,
            "category": exp.category,
            "amount": exp.amount,
            "date": exp.date,
            "property_name": exp.property.name if exp.property else None
        }
        result.append(data)
    return result

@router.post("/expenditures", response_model=schemas.ExpenditureOut, status_code=status.HTTP_201_CREATED)
def create_expenditure(expenditure: schemas.ExpenditureCreate,
                       db: Session = Depends(get_db),
                       current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    
    new_expenditure = models.Expenditure(**expenditure.model_dump())
    new_expenditure.created_by_id = current_user.id
    db.add(new_expenditure)
    db.commit()
    db.refresh(new_expenditure)
    
    data = schemas.ExpenditureOut.model_validate(new_expenditure)
    data.property_name = new_expenditure.property.name if new_expenditure.property else None
    return data
