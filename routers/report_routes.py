from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, extract, and_
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import date
import models, schemas, auth
from database import get_db

router = APIRouter(prefix="/reports", tags=["reports"])

# -------------------------------------------------------------------
# 1. TENANT REPORTS
# -------------------------------------------------------------------
@router.get("/tenant-statement/{tenant_id}")
def get_tenant_statement(
    tenant_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_permission("reports"))
):
    """Detailed ledger for a tenant, filtered by date, showing cumulative bills."""
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    leases = db.query(models.Lease).filter(models.Lease.tenant_id == tenant_id).all()
    lease_ids = [l.id for l in leases]

    # Base Queries
    inv_query = db.query(models.Invoice).filter(models.Invoice.lease_id.in_(lease_ids))
    pay_query = db.query(models.Payment).filter(models.Payment.lease_id.in_(lease_ids))

    # Apply Date Filters for Cumulative Time Period
    if start_date:
        inv_query = inv_query.filter(models.Invoice.billing_period >= start_date)
        pay_query = pay_query.filter(func.date(models.Payment.payment_date) >= start_date)
    if end_date:
        inv_query = inv_query.filter(models.Invoice.billing_period <= end_date)
        pay_query = pay_query.filter(func.date(models.Payment.payment_date) <= end_date)

    invoices = inv_query.all()
    payments = pay_query.all()

    ledger = []
    cumulative_billed = 0.0
    cumulative_paid = 0.0

    for inv in invoices:
        amount = float(inv.amount)
        cumulative_billed += amount
        ledger.append({
            "date": inv.billing_period,
            "description": f"Bill: {inv.type}",
            "debit": amount,
            "credit": 0.0,
            "type": "INVOICE"
        })
        
    for pay in payments:
        amount = float(pay.amount)
        cumulative_paid += amount
        pay_date = pay.payment_date.date() if hasattr(pay.payment_date, 'date') else pay.payment_date
        ledger.append({
            "date": pay_date,
            "description": f"Payment: {pay.payment_method} ({pay.reference_number})",
            "debit": 0.0,
            "credit": amount,
            "type": "PAYMENT"
        })

    # Sort chronologically for the running balance
    ledger.sort(key=lambda x: x["date"])
    
    balance = 0.0
    for entry in ledger:
        balance += (entry["debit"] - entry["credit"])
        entry["balance"] = balance

    return {
        "tenant_name": tenant.full_name,
        "period_billed": cumulative_billed,
        "period_paid": cumulative_paid,
        "period_balance": cumulative_billed - cumulative_paid,
        "statement": ledger
    }

@router.get("/arrears")
def get_tenant_arrears(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_permission("reports"))
):
    """Global Arrears Report: All unpaid cumulative bills to date."""
    unpaid_invoices = (
        db.query(models.Invoice)
        .options(
            joinedload(models.Invoice.lease).joinedload(models.Lease.tenant),
            joinedload(models.Invoice.lease).joinedload(models.Lease.unit).joinedload(models.Unit.property)
        )
        .filter(models.Invoice.is_paid == False)
        .all()
    )

    arrears = []
    for inv in unpaid_invoices:
        balance = float(inv.amount) - float(inv.amount_paid)
        if balance > 0:
            arrears.append({
                "invoice_id": inv.id,
                "tenant_name": inv.lease.tenant.full_name if inv.lease.tenant else "N/A",
                "property_name": inv.lease.unit.property.name if inv.lease.unit.property else "N/A",
                "unit_number": inv.lease.unit.unit_number if inv.lease.unit else "N/A",
                "type": inv.type,
                "billing_period": str(inv.billing_period),
                "balance": balance
            })
    return arrears

# -------------------------------------------------------------------
# 2. LANDLORD & PROPERTY REPORTS
# -------------------------------------------------------------------
@router.get("/landlord-statement")
def get_landlord_statement(
    landlord_id: Optional[int] = None,
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_permission("reports"))
):
    """Property Statement / Landlord Summary: Calculates cumulative collections and bills for a time period."""
    prop_query = db.query(models.Property).options(joinedload(models.Property.landlord))
    if landlord_id:
        prop_query = prop_query.filter(models.Property.landlord_id == landlord_id)
    properties = prop_query.all()

    statements = []
    for prop in properties:
        # 1. Cumulative Bills (Total Invoiced in period)
        total_billed = (
            db.query(func.sum(models.Invoice.amount))
            .join(models.Lease, models.Lease.id == models.Invoice.lease_id)
            .join(models.Unit, models.Unit.id == models.Lease.unit_id)
            .filter(
                models.Unit.property_id == prop.id,
                models.Invoice.billing_period >= start_date,
                models.Invoice.billing_period <= end_date
            ).scalar() or 0
        )

        # 2. Cumulative Collections (Total Paid in period)
        total_collected = (
            db.query(func.sum(models.Payment.amount))
            .join(models.Lease, models.Lease.id == models.Payment.lease_id)
            .join(models.Unit, models.Unit.id == models.Lease.unit_id)
            .filter(
                models.Unit.property_id == prop.id,
                func.date(models.Payment.payment_date) >= start_date,
                func.date(models.Payment.payment_date) <= end_date
            ).scalar() or 0
        )

        # 3. Cumulative Expenditures in period
        total_expenses = (
            db.query(func.sum(models.Expenditure.amount))
            .filter(
                models.Expenditure.property_id == prop.id,
                models.Expenditure.date >= start_date,
                models.Expenditure.date <= end_date
            ).scalar() or 0
        )

        rate = float(prop.management_commission_rate or 0) / 100
        management_fee = float(total_collected) * rate
        net_remittance = float(total_collected) - management_fee - float(total_expenses)

        statements.append({
            "property_id": prop.id,
            "property_name": prop.name,
            "landlord_name": prop.landlord.name if prop.landlord else "N/A",
            "cumulative_billed": float(total_billed),
            "cumulative_collected": float(total_collected),
            "expenses": float(total_expenses),
            "management_fee": management_fee,
            "net_payout": net_remittance
        })

    return {
        "period": f"{start_date} to {end_date}",
        "data": statements
    }

# -------------------------------------------------------------------
# 3. FINANCIAL & COLLECTION REPORTS
# -------------------------------------------------------------------
@router.get("/daily-collection")
def get_daily_collections(
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_permission("reports"))
):
    """Daily summary of payments received."""
    payments = (
        db.query(
            func.date(models.Payment.payment_date).label("pay_date"),
            models.Payment.payment_method,
            func.sum(models.Payment.amount).label("total_collected")
        )
        .filter(func.date(models.Payment.payment_date) >= start_date)
        .filter(func.date(models.Payment.payment_date) <= end_date)
        .group_by(func.date(models.Payment.payment_date), models.Payment.payment_method)
        .order_by(func.date(models.Payment.payment_date).desc())
        .all()
    )
    return [{"date": str(p.pay_date), "method": p.payment_method, "amount": float(p.total_collected)} for p in payments]


@router.get("/commissions")
def get_commission_report(
    month: int,
    year: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_permission("reports"))
):
    """Calculates management commissions earned by Victor Springs per property."""
    properties = db.query(models.Property).all()
    report = []
    
    total_commission_all = 0.0
    for prop in properties:
        # Sum payments made to units in this property during the specific month
        collected = (
            db.query(func.sum(models.Payment.amount))
            .join(models.Lease)
            .join(models.Unit)
            .filter(
                models.Unit.property_id == prop.id,
                extract('month', models.Payment.payment_date) == month,
                extract('year', models.Payment.payment_date) == year
            )
            .scalar() or 0
        )
        
        rate = float(prop.management_commission_rate or 0) / 100
        commission = float(collected) * rate
        total_commission_all += commission
        
        if collected > 0:
            report.append({
                "property_name": prop.name,
                "collection_amount": float(collected),
                "commission_rate_percent": float(prop.management_commission_rate or 0),
                "commission_earned": commission
            })
            
    return {"month": month, "year": year, "total_earned": total_commission_all, "breakdown": report}


# -------------------------------------------------------------------
# 4. PROPERTY & UTILITY REPORTS
# -------------------------------------------------------------------
@router.get("/vacant-units")
def get_vacant_units_report(db: Session = Depends(get_db)):
    """Detailed view of all vacant units and potential lost revenue."""
    vacant = db.query(models.Unit).options(joinedload(models.Unit.property)).filter(models.Unit.is_vacant == True).all()
    
    result = []
    potential_revenue = 0.0
    for v in vacant:
        potential_revenue += float(v.market_rent)
        result.append({
            "property_name": v.property.name if v.property else "N/A",
            "unit_number": v.unit_number,
            "unit_type": v.unit_type,
            "market_rent": float(v.market_rent)
        })
        
    return {"total_vacant": len(vacant), "potential_lost_revenue": potential_revenue, "units": result}
