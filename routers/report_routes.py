from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, extract, and_
from typing import Optional
from datetime import datetime, date
import models, auth
from database import get_db
import csv
from io import StringIO, BytesIO
import json

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/export/payments")
def export_payments(
    format: str = Query("csv", regex="^(csv|json)$"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    payments = db.query(models.Payment).all()

    if format == "json":
        result = []
        for p in payments:
            result.append({
                "id": p.id,
                "lease_id": p.lease_id,
                "amount": str(p.amount),
                "method": p.payment_method,
                "reference": p.reference_number,
                "date": p.payment_date.isoformat() if p.payment_date else None,
            })
        return result
    else:
        si = StringIO()
        cw = csv.writer(si)
        cw.writerow(["ID", "Lease ID", "Amount", "Method", "Reference", "Date"])

        for p in payments:
            cw.writerow(
                [
                    p.id,
                    p.lease_id,
                    str(p.amount),
                    p.payment_method,
                    p.reference_number,
                    p.payment_date,
                ]
            )

        return Response(
            content=si.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=payments_export.csv"},
        )


@router.get("/export/tenants")
def export_tenants(
    format: str = Query("csv", regex="^(csv|json)$"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    tenants = db.query(models.Tenant).all()

    if format == "json":
        result = []
        for t in tenants:
            result.append({
                "id": t.id,
                "name": t.full_name,
                "phone": t.phone_number,
                "national_id": t.national_id,
            })
        return result
    else:
        si = StringIO()
        cw = csv.writer(si)
        cw.writerow(["ID", "Name", "Phone", "National ID"])

        for t in tenants:
            cw.writerow([t.id, t.full_name, t.phone_number, t.national_id])

        return Response(
            content=si.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=tenants_export.csv"},
        )


@router.get("/export/arrears")
def export_arrears(
    format: str = Query("csv", regex="^(csv|json)$"),
    property_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_role(["super_admin", "admin", "landlord"])
    ),
):
    query = (
        db.query(models.Invoice)
        .options(
            joinedload(models.Invoice.lease).joinedload(models.Lease.tenant),
            joinedload(models.Invoice.lease)
            .joinedload(models.Lease.unit)
            .joinedload(models.Unit.property),
        )
        .filter(models.Invoice.is_paid == False)
    )

    if property_id:
        query = (
            query.join(models.Invoice.lease)
            .join(models.Lease.unit)
            .filter(models.Unit.property_id == property_id)
        )

    if from_date:
        query = query.filter(models.Invoice.billing_period >= from_date)

    if to_date:
        query = query.filter(models.Invoice.billing_period <= to_date)

    invoices = query.all()

    if format == "json":
        result = []
        for inv in invoices:
            t_name = (
                inv.lease.tenant.full_name if inv.lease and inv.lease.tenant else "N/A"
            )
            u_num = (
                inv.lease.unit.unit_number if inv.lease and inv.lease.unit else "N/A"
            )
            p_name = (
                inv.lease.unit.property.name
                if inv.lease and inv.lease.unit and inv.lease.unit.property
                else "N/A"
            )
            bal = inv.amount - (inv.amount_paid or 0)
            result.append(
                {
                    "id": inv.id,
                    "tenant_name": t_name,
                    "unit_number": u_num,
                    "property_name": p_name,
                    "type": inv.type,
                    "billing_period": inv.billing_period.isoformat(),
                    "amount": float(inv.amount),
                    "amount_paid": float(inv.amount_paid or 0),
                    "balance": float(bal),
                }
            )
        return result
    else:
        si = StringIO()
        cw = csv.writer(si)
        cw.writerow(
            [
                "Invoice ID",
                "Tenant Name",
                "Unit",
                "Property",
                "Type",
                "Period",
                "Amount",
                "Paid",
                "Balance",
            ]
        )

        for inv in invoices:
            t_name = (
                inv.lease.tenant.full_name if inv.lease and inv.lease.tenant else "N/A"
            )
            u_num = (
                inv.lease.unit.unit_number if inv.lease and inv.lease.unit else "N/A"
            )
            p_name = (
                inv.lease.unit.property.name
                if inv.lease and inv.lease.unit and inv.lease.unit.property
                else "N/A"
            )
            bal = inv.amount - (inv.amount_paid or 0)
            cw.writerow(
                [
                    inv.id,
                    t_name,
                    u_num,
                    p_name,
                    inv.type,
                    inv.billing_period,
                    inv.amount,
                    inv.amount_paid or 0,
                    bal,
                ]
            )

        return Response(
            content=si.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=arrears_export.csv"},
        )


@router.get("/export/landlord-summary")
def export_landlord_summary(
    format: str = Query("csv", regex="^(csv|json)$"),
    landlord_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_role(["super_admin", "admin", "landlord"])
    ),
):
    query = db.query(models.Landlord)

    if landlord_id:
        query = query.filter(models.Landlord.id == landlord_id)

    landlords = query.all()

    result = []
    for landlord in landlords:
        properties = (
            db.query(models.Property)
            .filter(models.Property.landlord_id == landlord.id)
            .all()
        )
        property_ids = [p.id for p in properties]

        if not property_ids:
            result.append({
                "id": landlord.id,
                "landlord_name": landlord.name,
                "total_properties": 0,
                "total_collected": 0.0,
                "total_expenses": 0.0,
                "management_fee": 0.0,
                "total_remitted": 0.0,
                "net_amount": 0.0,
            })
            continue

        invoice_query = (
            db.query(func.sum(models.Invoice.amount_paid))
            .join(models.Invoice.lease)
            .join(models.Lease.unit)
            .filter(
                models.Unit.property_id.in_(property_ids),
                models.Invoice.is_paid == True,
            )
        )

        expense_query = db.query(func.sum(models.Expenditure.amount)).filter(
            models.Expenditure.property_id.in_(property_ids)
        )

        remittance_query = db.query(func.sum(models.LandlordRemittance.amount)).filter(
            models.LandlordRemittance.landlord_id == landlord.id
        )

        if from_date:
            invoice_query = invoice_query.filter(models.Invoice.billing_period >= from_date)
            expense_query = expense_query.filter(models.Expenditure.date >= from_date)
            remittance_query = remittance_query.filter(models.LandlordRemittance.date >= from_date)

        if to_date:
            invoice_query = invoice_query.filter(models.Invoice.billing_period <= to_date)
            expense_query = expense_query.filter(models.Expenditure.date <= to_date)
            remittance_query = remittance_query.filter(models.LandlordRemittance.date <= to_date)

        total_collected = float(invoice_query.scalar() or 0)
        total_expenses = float(expense_query.scalar() or 0)
        total_remitted = float(remittance_query.scalar() or 0)
        management_fee = total_collected * 0.10
        net_amount = total_collected - management_fee - total_expenses

        result.append({
            "id": landlord.id,
            "landlord_name": landlord.name,
            "total_properties": len(properties),
            "total_collected": total_collected,
            "total_expenses": total_expenses,
            "management_fee": management_fee,
            "total_remitted": total_remitted,
            "net_amount": net_amount,
        })

    if format == "json":
        return result
    else:
        si = StringIO()
        cw = csv.writer(si)
        cw.writerow([
            "Landlord",
            "Properties",
            "Total Collected",
            "Total Expenses",
            "Management Fee",
            "Total Remitted",
            "Net Amount",
        ])

        for item in result:
            cw.writerow([
                item["landlord_name"],
                item["total_properties"],
                item["total_collected"],
                item["total_expenses"],
                item["management_fee"],
                item["total_remitted"],
                item["net_amount"],
            ])

        return Response(
            content=si.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=landlord_summary_export.csv"},
        )


@router.get("/export/property-performance")
def export_property_performance(
    format: str = Query("csv", regex="^(csv|json)$"),
    property_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    query = db.query(models.Property)

    if property_id:
        query = query.filter(models.Property.id == property_id)

    properties = query.all()

    result = []
    for prop in properties:
        units = db.query(models.Unit).filter(models.Unit.property_id == prop.id).all()
        total_units = len(units)
        vacant_units = len([u for u in units if u.is_vacant])
        occupied_units = total_units - vacant_units

        invoice_query = (
            db.query(func.sum(models.Invoice.amount_paid))
            .join(models.Invoice.lease)
            .join(models.Lease.unit)
            .filter(models.Unit.property_id == prop.id, models.Invoice.is_paid == True)
        )

        expense_query = db.query(func.sum(models.Expenditure.amount)).filter(
            models.Expenditure.property_id == prop.id
        )

        if from_date:
            invoice_query = invoice_query.filter(models.Invoice.billing_period >= from_date)
            expense_query = expense_query.filter(models.Expenditure.date >= from_date)

        if to_date:
            invoice_query = invoice_query.filter(models.Invoice.billing_period <= to_date)
            expense_query = expense_query.filter(models.Expenditure.date <= to_date)

        total_revenue = float(invoice_query.scalar() or 0)
        total_expenses = float(expense_query.scalar() or 0)
        net_income = total_revenue - total_expenses
        occupancy_rate = (occupied_units / total_units * 100) if total_units > 0 else 0

        result.append({
            "id": prop.id,
            "property_name": prop.name,
            "total_units": total_units,
            "occupied_units": occupied_units,
            "vacant_units": vacant_units,
            "occupancy_rate": round(occupancy_rate, 2),
            "total_revenue": total_revenue,
            "total_expenses": total_expenses,
            "net_income": net_income,
        })

    if format == "json":
        return result
    else:
        si = StringIO()
        cw = csv.writer(si)
        cw.writerow([
            "Property",
            "Total Units",
            "Occupied",
            "Vacant",
            "Occupancy Rate",
            "Total Revenue",
            "Total Expenses",
            "Net Income",
        ])

        for item in result:
            cw.writerow([
                item["property_name"],
                item["total_units"],
                item["occupied_units"],
                item["vacant_units"],
                f"{item['occupancy_rate']}%",
                item["total_revenue"],
                item["total_expenses"],
                item["net_income"],
            ])

        return Response(
            content=si.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=property_performance_export.csv"},
        )


@router.get("/export/revenue")
def export_revenue(
    format: str = Query("csv", regex="^(csv|json)$"),
    property_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    query = db.query(models.Property)

    if property_id:
        query = query.filter(models.Property.id == property_id)

    properties = query.all()

    result = []
    for prop in properties:
        invoice_query = (
            db.query(
                models.Invoice.type,
                func.sum(models.Invoice.amount).label("total_amount"),
                func.sum(models.Invoice.amount_paid).label("total_paid"),
            )
            .join(models.Invoice.lease)
            .join(models.Lease.unit)
            .filter(models.Unit.property_id == prop.id)
            .group_by(models.Invoice.type)
        )

        if from_date:
            invoice_query = invoice_query.filter(models.Invoice.billing_period >= from_date)

        if to_date:
            invoice_query = invoice_query.filter(models.Invoice.billing_period <= to_date)

        invoice_data = invoice_query.all()

        revenue_by_type = []
        total_amount = 0
        total_paid = 0

        for inv_type, amount, paid in invoice_data:
            revenue_by_type.append({
                "type": inv_type,
                "amount": float(amount or 0),
                "paid": float(paid or 0),
                "pending": float(amount or 0) - float(paid or 0),
            })
            total_amount += float(amount or 0)
            total_paid += float(paid or 0)

        result.append({
            "id": prop.id,
            "property_name": prop.name,
            "revenue_by_type": revenue_by_type,
            "total_amount": total_amount,
            "total_paid": total_paid,
            "total_pending": total_amount - total_paid,
        })

    if format == "json":
        return result
    else:
        si = StringIO()
        cw = csv.writer(si)
        cw.writerow([
            "Property",
            "Invoice Type",
            "Total Amount",
            "Total Paid",
            "Pending",
        ])

        for item in result:
            if item["revenue_by_type"]:
                for revenue in item["revenue_by_type"]:
                    cw.writerow([
                        item["property_name"],
                        revenue["type"],
                        revenue["amount"],
                        revenue["paid"],
                        revenue["pending"],
                    ])
            else:
                cw.writerow([
                    item["property_name"],
                    "No invoices",
                    0,
                    0,
                    0,
                ])

        return Response(
            content=si.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=revenue_export.csv"},
        )


# Arrears Report
@router.get("/arrears")
def get_arrears_report(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    property_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_role(["super_admin", "admin", "landlord"])
    ),
):
    query = (
        db.query(models.Invoice)
        .options(
            joinedload(models.Invoice.lease).joinedload(models.Lease.tenant),
            joinedload(models.Invoice.lease)
            .joinedload(models.Lease.unit)
            .joinedload(models.Unit.property),
        )
        .filter(models.Invoice.is_paid == False)
    )

    if property_id:
        query = (
            query.join(models.Invoice.lease)
            .join(models.Lease.unit)
            .filter(models.Unit.property_id == property_id)
        )

    if from_date:
        query = query.filter(models.Invoice.billing_period >= from_date)

    if to_date:
        query = query.filter(models.Invoice.billing_period <= to_date)

    total = query.count()
    invoices = (
        query.order_by(models.Invoice.billing_period.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    result = []
    for inv in invoices:
        t_name = inv.lease.tenant.full_name if inv.lease and inv.lease.tenant else "N/A"
        u_num = inv.lease.unit.unit_number if inv.lease and inv.lease.unit else "N/A"
        p_name = (
            inv.lease.unit.property.name
            if inv.lease and inv.lease.unit and inv.lease.unit.property
            else "N/A"
        )
        bal = inv.amount - (inv.amount_paid or 0)
        result.append(
            {
                "id": inv.id,
                "tenant_name": t_name,
                "unit_number": u_num,
                "property_name": p_name,
                "type": inv.type,
                "billing_period": inv.billing_period.isoformat()
                if inv.billing_period
                else None,
                "amount": float(inv.amount),
                "amount_paid": float(inv.amount_paid or 0),
                "balance": float(bal),
            }
        )

    return {"data": result, "total": total, "page": page, "limit": limit}


# Landlord Summary Report - OPTIMIZED
@router.get("/landlord-summary")
def get_landlord_summary_report(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    landlord_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_role(["super_admin", "admin", "landlord"])
    ),
):
    # Build base query for landlords
    query = db.query(models.Landlord)
    
    if landlord_id:
        query = query.filter(models.Landlord.id == landlord_id)

    total = query.count()
    landlords = query.offset((page - 1) * limit).limit(limit).all()

    if not landlords:
        return {"data": [], "total": total, "page": page, "limit": limit}

    landlord_ids = [l.id for l in landlords]

    # Get all properties for these landlords in one query
    properties_query = db.query(models.Property).filter(
        models.Property.landlord_id.in_(landlord_ids)
    ).all()
    
    # Group properties by landlord
    properties_by_landlord = {}
    property_ids_by_landlord = {}
    for prop in properties_query:
        if prop.landlord_id not in properties_by_landlord:
            properties_by_landlord[prop.landlord_id] = []
            property_ids_by_landlord[prop.landlord_id] = []
        properties_by_landlord[prop.landlord_id].append(prop)
        property_ids_by_landlord[prop.landlord_id].append(prop.id)

    # Get all property IDs
    all_property_ids = [p.id for p in properties_query]
    
    if not all_property_ids:
        result = []
        for landlord in landlords:
            result.append({
                "id": landlord.id,
                "landlord_name": landlord.name,
                "total_properties": 0,
                "total_collected": 0.0,
                "total_expenses": 0.0,
                "management_fee": 0.0,
                "total_remitted": 0.0,
                "net_amount": 0.0,
            })
        return {"data": result, "total": total, "page": page, "limit": limit}

    # Build date filter conditions
    date_filters_invoice = []
    date_filters_expense = []
    date_filters_remittance = []
    
    if from_date:
        date_filters_invoice.append(models.Invoice.billing_period >= from_date)
        date_filters_expense.append(models.Expenditure.date >= from_date)
        date_filters_remittance.append(models.LandlordRemittance.date >= from_date)
    
    if to_date:
        date_filters_invoice.append(models.Invoice.billing_period <= to_date)
        date_filters_expense.append(models.Expenditure.date <= to_date)
        date_filters_remittance.append(models.LandlordRemittance.date <= to_date)

    # Get all invoice totals by property in one query
    invoice_query = (
        db.query(
            models.Unit.property_id,
            func.sum(models.Invoice.amount_paid).label('total_paid')
        )
        .join(models.Invoice.lease)
        .join(models.Lease.unit)
        .filter(
            models.Unit.property_id.in_(all_property_ids),
            models.Invoice.is_paid == True,
        )
    )
    for f in date_filters_invoice:
        invoice_query = invoice_query.filter(f)
    
    invoice_totals = {
        row.property_id: float(row.total_paid or 0)
        for row in invoice_query.group_by(models.Unit.property_id).all()
    }

    # Get all expense totals by property in one query
    expense_query = (
        db.query(
            models.Expenditure.property_id,
            func.sum(models.Expenditure.amount).label('total_expenses')
        )
        .filter(models.Expenditure.property_id.in_(all_property_ids))
    )
    for f in date_filters_expense:
        expense_query = expense_query.filter(f)
    
    expense_totals = {
        row.property_id: float(row.total_expenses or 0)
        for row in expense_query.group_by(models.Expenditure.property_id).all()
    }

    # Get all remittance totals by landlord in one query
    remittance_query = (
        db.query(
            models.LandlordRemittance.landlord_id,
            func.sum(models.LandlordRemittance.amount).label('total_remitted')
        )
        .filter(models.LandlordRemittance.landlord_id.in_(landlord_ids))
    )
    for f in date_filters_remittance:
        remittance_query = remittance_query.filter(f)
    
    remittance_totals = {
        row.landlord_id: float(row.total_remitted or 0)
        for row in remittance_query.group_by(models.LandlordRemittance.landlord_id).all()
    }

    # Build result
    result = []
    for landlord in landlords:
        prop_ids = property_ids_by_landlord.get(landlord.id, [])
        
        if not prop_ids:
            result.append({
                "id": landlord.id,
                "landlord_name": landlord.name,
                "total_properties": 0,
                "total_collected": 0.0,
                "total_expenses": 0.0,
                "management_fee": 0.0,
                "total_remitted": 0.0,
                "net_amount": 0.0,
            })
            continue

        total_collected = sum(invoice_totals.get(pid, 0) for pid in prop_ids)
        total_expenses = sum(expense_totals.get(pid, 0) for pid in prop_ids)
        total_remitted = remittance_totals.get(landlord.id, 0)
        management_fee = total_collected * 0.10
        net_amount = total_collected - management_fee - total_expenses

        result.append({
            "id": landlord.id,
            "landlord_name": landlord.name,
            "total_properties": len(prop_ids),
            "total_collected": total_collected,
            "total_expenses": total_expenses,
            "management_fee": management_fee,
            "total_remitted": total_remitted,
            "net_amount": net_amount,
        })

    return {"data": result, "total": total, "page": page, "limit": limit}


# Property Performance Report
@router.get("/property-performance")
def get_property_performance_report(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    property_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    query = db.query(models.Property)

    if property_id:
        query = query.filter(models.Property.id == property_id)

    total = query.count()
    properties = query.offset((page - 1) * limit).limit(limit).all()

    result = []
    for prop in properties:
        units = db.query(models.Unit).filter(models.Unit.property_id == prop.id).all()
        total_units = len(units)
        vacant_units = len([u for u in units if u.is_vacant])
        occupied_units = total_units - vacant_units

        invoice_query = (
            db.query(func.sum(models.Invoice.amount_paid))
            .join(models.Invoice.lease)
            .join(models.Lease.unit)
            .filter(models.Unit.property_id == prop.id, models.Invoice.is_paid == True)
        )

        expense_query = db.query(func.sum(models.Expenditure.amount)).filter(
            models.Expenditure.property_id == prop.id
        )

        if from_date:
            invoice_query = invoice_query.filter(models.Invoice.billing_period >= from_date)
            expense_query = expense_query.filter(models.Expenditure.date >= from_date)

        if to_date:
            invoice_query = invoice_query.filter(models.Invoice.billing_period <= to_date)
            expense_query = expense_query.filter(models.Expenditure.date <= to_date)

        total_revenue = float(invoice_query.scalar() or 0)
        total_expenses = float(expense_query.scalar() or 0)
        net_income = total_revenue - total_expenses
        occupancy_rate = (occupied_units / total_units * 100) if total_units > 0 else 0

        result.append(
            {
                "id": prop.id,
                "property_name": prop.name,
                "total_units": total_units,
                "occupied_units": occupied_units,
                "vacant_units": vacant_units,
                "occupancy_rate": round(occupancy_rate, 2),
                "total_revenue": total_revenue,
                "total_expenses": total_expenses,
                "net_income": net_income,
            }
        )

    return {"data": result, "total": total, "page": page, "limit": limit}


# Revenue Report
@router.get("/revenue")
def get_revenue_report(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    property_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"])),
):
    query = db.query(models.Property)

    if property_id:
        query = query.filter(models.Property.id == property_id)

    total = query.count()
    properties = query.offset((page - 1) * limit).limit(limit).all()

    result = []
    for prop in properties:
        invoice_query = (
            db.query(
                models.Invoice.type,
                func.sum(models.Invoice.amount).label("total_amount"),
                func.sum(models.Invoice.amount_paid).label("total_paid"),
            )
            .join(models.Invoice.lease)
            .join(models.Lease.unit)
            .filter(models.Unit.property_id == prop.id)
            .group_by(models.Invoice.type)
        )

        if from_date:
            invoice_query = invoice_query.filter(models.Invoice.billing_period >= from_date)

        if to_date:
            invoice_query = invoice_query.filter(models.Invoice.billing_period <= to_date)

        invoice_data = invoice_query.all()

        revenue_by_type = []
        total_amount = 0
        total_paid = 0

        for inv_type, amount, paid in invoice_data:
            revenue_by_type.append(
                {
                    "type": inv_type,
                    "amount": float(amount or 0),
                    "paid": float(paid or 0),
                    "pending": float(amount or 0) - float(paid or 0),
                }
            )
            total_amount += float(amount or 0)
            total_paid += float(paid or 0)

        result.append(
            {
                "id": prop.id,
                "property_name": prop.name,
                "revenue_by_type": revenue_by_type,
                "total_amount": total_amount,
                "total_paid": total_paid,
                "total_pending": total_amount - total_paid,
            }
        )

    return {"data": result, "total": total, "page": page, "limit": limit}


# -------------------------------------------------------------------
# 1. TENANT REPORTS
# -------------------------------------------------------------------
@router.get("/tenant-statement/{tenant_id}")
def get_tenant_statement(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_permission("reports"))
):
    """Detailed ledger for a single tenant."""
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    leases = db.query(models.Lease).filter(models.Lease.tenant_id == tenant_id).all()
    lease_ids = [l.id for l in leases]

    # Get all invoices (Debits)
    invoices = db.query(models.Invoice).filter(models.Invoice.lease_id.in_(lease_ids)).all()
    # Get all payments (Credits)
    payments = db.query(models.Payment).filter(models.Payment.lease_id.in_(lease_ids)).all()

    ledger = []
    for inv in invoices:
        ledger.append({
            "date": inv.billing_period,
            "description": f"Invoice: {inv.type}",
            "debit": float(inv.amount),
            "credit": 0.0,
            "type": "INVOICE",
            "ref": str(inv.id)
        })
    for pay in payments:
        ledger.append({
            "date": pay.payment_date.date() if isinstance(pay.payment_date, datetime) else pay.payment_date,
            "description": f"Payment: {pay.payment_method}",
            "debit": 0.0,
            "credit": float(pay.amount),
            "type": "PAYMENT",
            "ref": pay.reference_number
        })

    # Sort chronologically to calculate running balance
    ledger.sort(key=lambda x: x["date"])
    
    balance = 0.0
    for entry in ledger:
        balance += (entry["debit"] - entry["credit"])
        entry["balance"] = balance

    return {
        "tenant_name": tenant.full_name,
        "phone": tenant.phone_number,
        "statement": ledger,
        "current_balance": balance
    }


@router.get("/advance-payments")
def get_advance_payments(db: Session = Depends(get_db)):
    """Tenants who have paid more than their invoiced amounts."""
    # Find leases where total payments > total invoice amounts
    active_leases = db.query(models.Lease).options(joinedload(models.Lease.tenant), joinedload(models.Lease.unit)).filter(models.Lease.status == "ACTIVE").all()
    
    advances = []
    for lease in active_leases:
        total_invoiced = db.query(func.sum(models.Invoice.amount)).filter(models.Invoice.lease_id == lease.id).scalar() or 0
        total_paid = db.query(func.sum(models.Payment.amount)).filter(models.Payment.lease_id == lease.id).scalar() or 0
        
        if total_paid > total_invoiced:
            advances.append({
                "tenant_name": lease.tenant.full_name if lease.tenant else "N/A",
                "unit": lease.unit.unit_number if lease.unit else "N/A",
                "advance_amount": float(total_paid - total_invoiced)
            })
    return advances


# -------------------------------------------------------------------
# 2. FINANCIAL & COLLECTION REPORTS
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
# 3. PROPERTY & UTILITY REPORTS
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
