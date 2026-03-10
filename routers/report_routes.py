from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy.orm import Session, joinedload
import models, auth
from database import get_db
import csv
from io import StringIO

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/export/payments")
def export_payments(db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    payments = db.query(models.Payment).all()
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Lease ID', 'Amount', 'Method', 'Reference', 'Date'])
    
    for p in payments:
         cw.writerow([p.id, p.lease_id, str(p.amount), p.payment_method, p.reference_number, p.payment_date])
         
    return Response(
        content=si.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=payments_export.csv"}
    )

@router.get("/export/tenants")
def export_tenants(db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    tenants = db.query(models.Tenant).all()
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Name', 'Phone', 'National ID'])
    
    for t in tenants:
         cw.writerow([t.id, t.full_name, t.phone_number, t.national_id])
         
    return Response(
        content=si.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tenants_export.csv"}
    )

@router.get("/export/arrears")
def export_arrears(format: str = "csv", db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["super_admin", "admin", "landlord"]))):
    invoices = db.query(models.Invoice).options(
        joinedload(models.Invoice.lease).joinedload(models.Lease.tenant),
        joinedload(models.Invoice.lease).joinedload(models.Lease.unit).joinedload(models.Unit.property)
    ).filter(models.Invoice.is_paid == False).all()
    
    if format == "json":
        result = []
        for inv in invoices:
            t_name = inv.lease.tenant.full_name if inv.lease and inv.lease.tenant else "N/A"
            u_num = inv.lease.unit.unit_number if inv.lease and inv.lease.unit else "N/A"
            p_name = inv.lease.unit.property.name if inv.lease and inv.lease.unit and inv.lease.unit.property else "N/A"
            bal = inv.amount - (inv.amount_paid or 0)
            result.append({
                "id": inv.id,
                "tenant_name": t_name,
                "unit_number": u_num,
                "property_name": p_name,
                "type": inv.type,
                "billing_period": inv.billing_period.isoformat(),
                "amount": float(inv.amount),
                "amount_paid": float(inv.amount_paid or 0),
                "balance": float(bal)
            })
        return result
    else:
        si = StringIO()
        cw = csv.writer(si)
        cw.writerow(['Invoice ID', 'Tenant Name', 'Unit', 'Property', 'Type', 'Period', 'Amount', 'Paid', 'Balance'])
        
        for inv in invoices:
            t_name = inv.lease.tenant.full_name if inv.lease and inv.lease.tenant else "N/A"
            u_num = inv.lease.unit.unit_number if inv.lease and inv.lease.unit else "N/A"
            p_name = inv.lease.unit.property.name if inv.lease and inv.lease.unit and inv.lease.unit.property else "N/A"
            bal = inv.amount - (inv.amount_paid or 0)
            cw.writerow([inv.id, t_name, u_num, p_name, inv.type, inv.billing_period, inv.amount, inv.amount_paid or 0, bal])
             
        return Response(
            content=si.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=arrears_export.csv"}
        )
