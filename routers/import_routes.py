from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import pandas as pd
import io
import math
import models, schemas, auth
from database import get_db

router = APIRouter(prefix="/imports", tags=["imports"])

def safe_float(val):
    if pd.isna(val):
        return 0.0
    return float(val)

def safe_str(val):
    if pd.isna(val):
        return ""
    return str(val).strip()

@router.post("/preview")
async def preview_import(
    target_entity: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin"]))
):
    valid_targets = ["tenants", "payments"]
    if target_entity not in valid_targets:
        raise HTTPException(status_code=400, detail=f"Invalid target entity. Must be one of: {valid_targets}")

    contents = await file.read()
    
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        elif file.filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail="Only CSV and Excel files are supported")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

    # Standardize column names (lowercase, replace spaces with underscores)
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    
    preview_data = []
    
    # Process Tenants
    if target_entity == "tenants":
        required_cols = ["full_name", "phone_number", "national_id", "email"]
        for _, row in df.iterrows():
            record = {k: safe_str(v) for k, v in row.items()}
            errors = []
            
            for col in required_cols:
                if not record.get(col):
                    errors.append(f"Missing '{col}'")
                    
            status_flag = "valid"
            
            # Check duplicates in DB
            if not errors:
                existing_nid = db.query(models.Tenant).filter(models.Tenant.national_id == record['national_id']).first()
                if existing_nid:
                    errors.append("National ID already exists in system")
                    status_flag = "duplicate"
                
                existing_phone = db.query(models.Tenant).filter(models.Tenant.phone_number == record['phone_number']).first()
                if existing_phone:
                    errors.append("Phone Number already exists in system")
                    status_flag = "duplicate"
            
            if errors and status_flag != "duplicate":
                status_flag = "invalid"
                
            preview_data.append({
                "data": record,
                "status": status_flag,
                "errors": errors
            })

    # Process Payments
    elif target_entity == "payments":
        required_cols = ["lease_id", "amount", "payment_method", "reference_number"]
        for _, row in df.iterrows():
            record = {k: safe_str(v) for k, v in row.items()}
            errors = []
            
            # Type casting wrapper
            try:
                record["amount"] = safe_float(row.get("amount", 0))
                record["lease_id"] = int(float(row.get("lease_id", 0))) if not pd.isna(row.get("lease_id")) else None
            except:
                pass
            
            for col in required_cols:
                if not record.get(col):
                    errors.append(f"Missing '{col}'")
                    
            status_flag = "valid"
            
            if not errors:
                # Validation checks against DB
                lease = db.query(models.Lease).filter(models.Lease.id == record['lease_id']).first()
                if not lease:
                    errors.append(f"Lease ID {record['lease_id']} not found")
                
                if record.get('reference_number'):
                    existing_pay = db.query(models.Payment).filter(models.Payment.reference_number == record['reference_number']).first()
                    if existing_pay:
                        errors.append("Reference Number already exists")
                        status_flag = "duplicate"

            if errors and status_flag != "duplicate":
                status_flag = "invalid"
                
            preview_data.append({
                "data": record,
                "status": status_flag,
                "errors": errors
            })

    return {
        "target_entity": target_entity,
        "total_rows": len(df),
        "columns": df.columns.tolist(),
        "preview": preview_data
    }


@router.post("/commit")
def commit_import(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin"]))
):
    target_entity = payload.get("target_entity")
    records = payload.get("records", [])
    
    if not records:
        raise HTTPException(status_code=400, detail="No records provided to commit")
        
    inserted_count = 0
    
    try:
        if target_entity == "tenants":
            for r in records:
                # Only insert if no conflict exists
                conflict = db.query(models.Tenant).filter(
                    (models.Tenant.national_id == r['national_id']) | 
                    (models.Tenant.phone_number == r['phone_number'])
                ).first()
                
                if not conflict:
                    new_tenant = models.Tenant(
                        full_name=r.get('full_name'),
                        email=r.get('email'),
                        phone_number=r.get('phone_number'),
                        national_id=r.get('national_id'),
                        gender=r.get('gender', 'Other'),
                        emergency_contact=r.get('emergency_contact'),
                        created_by_id=current_user.id
                    )
                    db.add(new_tenant)
                    inserted_count += 1
                    
        elif target_entity == "payments":
            for r in records:
                conflict = False
                if r.get('reference_number'):
                    conflict = db.query(models.Payment).filter(models.Payment.reference_number == r['reference_number']).first()
                
                if not conflict:
                    new_payment = models.Payment(
                        lease_id=r['lease_id'],
                        amount=r['amount'],
                        payment_method=r.get('payment_method', 'Bank Transfer'),
                        reference_number=r.get('reference_number'),
                        created_by_id=current_user.id
                    )
                    db.add(new_payment)
                    inserted_count += 1
                    
                    # FIFO allocation inline logic for imports
                    amount_to_allocate = float(new_payment.amount)
                    unpaid_invoices = (
                        db.query(models.Invoice)
                        .filter(models.Invoice.lease_id == new_payment.lease_id, models.Invoice.is_paid == False)
                        .order_by(models.Invoice.billing_period.asc())
                        .all()
                    )

                    for inv in unpaid_invoices:
                        if amount_to_allocate <= 0: break
                        current_balance = float(inv.amount) - float(inv.amount_paid)
                        if amount_to_allocate >= current_balance:
                            inv.amount_paid = float(inv.amount)
                            inv.is_paid = True
                            amount_to_allocate -= current_balance
                        else:
                            inv.amount_paid = float(inv.amount_paid) + amount_to_allocate
                            amount_to_allocate = 0

        db.commit()
        return {"message": "Import completed", "inserted": inserted_count}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database commit failed: {str(e)}")
