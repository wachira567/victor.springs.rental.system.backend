"""
Missed Data Import Script
=====================================================
Imports specifically the newly scraped data (cash_payments, terminated_leases) 
into the PostgreSQL database.
"""

import csv
import os
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from database import engine, SessionLocal, Base
import models

# Path to CSV files (one directory up from backend, inside 'Web scrapping data')
CSV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Web scrapping data")

def safe_decimal(value, default=Decimal("0.00")):
    if not value or value.strip() == "":
        return default
    try:
        cleaned = value.strip().replace(",", "").replace(" ", "")
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return default

def safe_date(value, default=None):
    if not value or value.strip() == "":
        return default
    value = value.strip()
    # Try multiple formats including with time
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    print(f"  [WARN] Could not parse date: '{value}'")
    return default

def read_csv(filename):
    filepath = os.path.join(CSV_DIR, filename)
    if not os.path.exists(filepath):
        print(f"  [SKIP] File not found: {filepath}")
        return []
    
    rows = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if any(v and v.strip() for v in row.values()):
                rows.append(row)
    return rows

def import_cash_payments(db: Session):
    print("\n💵 Importing Cash Payments...")
    rows = read_csv("cash_payments.csv")
    imported = 0
    skipped = 0
    
    for row in rows:
        tenant_name = (row.get("Tenant Name") or "").strip()
        unit_number = (row.get("Unit Number") or "").strip()
        ref_number = (row.get("Ref Number") or "").strip()
        payment_mode = (row.get("Payment Mode") or "CASH").strip()
        amount = safe_decimal(row.get("Amount", "0"))
        received_on = safe_date(row.get("Received On"))
        
        if not tenant_name or not unit_number or amount <= 0:
            skipped += 1
            continue
            
        # Check if payment already exists
        existing = db.query(models.Payment).filter(models.Payment.reference_number == ref_number).first()
        if existing and ref_number:
            skipped += 1
            continue
            
        # Find Tenant
        tenant = db.query(models.Tenant).filter(models.Tenant.full_name.ilike(f"%{tenant_name}%")).first()
        if not tenant:
            skipped += 1
            continue
            
        # Find Unit
        unit = db.query(models.Unit).filter(models.Unit.unit_number == unit_number).first()
        if not unit:
            skipped += 1
            continue
            
        # Find Lease
        lease = db.query(models.Lease).filter(
            models.Lease.tenant_id == tenant.id,
            models.Lease.unit_id == unit.id
        ).first()
        
        if not lease:
            skipped += 1
            continue
            
        payment = models.Payment(
            lease_id=lease.id,
            amount=amount,
            payment_method=payment_mode,
            reference_number=ref_number if ref_number else f"MANUAL-{imported}-{int(datetime.now().timestamp())}",
            payment_date=received_on or datetime.now().date()
        )
        
        db.add(payment)
        imported += 1
        
        if imported % 500 == 0:
            db.commit()
            print(f"  ... committed {imported} payments so far")
            
    db.commit()
    print(f"  ✅ Imported {imported} cash payments (skipped {skipped})")
    return imported

def import_terminated_leases(db: Session):
    print("\n📝 Importing Terminated Leases...")
    rows = read_csv("terminated_leases.csv")
    imported = 0
    skipped = 0
    
    for row in rows:
        property_name = (row.get("Property Name") or "").strip()
        house_number = (row.get("House Number") or "").strip()
        tenant_name = (row.get("Tenant") or "").strip()
        start_date = safe_date(row.get("Start Date"))
        terminated_at = safe_date(row.get("Terminated At"))
        
        if not property_name or not house_number or not tenant_name:
            skipped += 1
            continue
            
        # Find Property
        prop = db.query(models.Property).filter(models.Property.name == property_name).first()
        if not prop:
            skipped += 1
            continue
            
        # Find Unit
        unit = db.query(models.Unit).filter(
            models.Unit.property_id == prop.id,
            models.Unit.unit_number == house_number
        ).first()
        
        if not unit:
            skipped += 1
            continue
            
        # Find Tenant
        tenant = db.query(models.Tenant).filter(models.Tenant.full_name.ilike(f"%{tenant_name}%")).first()
        if not tenant:
            skipped += 1
            continue
            
        # Check if lease already exists
        existing = db.query(models.Lease).filter(
            models.Lease.tenant_id == tenant.id,
            models.Lease.unit_id == unit.id
        ).first()
        
        if existing:
            # Update existing to terminated
            if existing.status != "TERMINATED":
                existing.status = "TERMINATED"
                existing.end_date = terminated_at
                imported += 1
            else:
                skipped += 1
            continue
            
        # Create new terminated lease
        lease = models.Lease(
            unit_id=unit.id,
            tenant_id=tenant.id,
            start_date=start_date or datetime.now().date(),
            end_date=terminated_at,
            rent_amount=Decimal("0.00"),
            status="TERMINATED"
        )
        
        db.add(lease)
        imported += 1
        
    db.commit()
    print(f"  ✅ Imported/Updated {imported} terminated leases (skipped {skipped})")
    return imported

def main():
    print("=" * 60)
    print("🚀 IMPORTING MISSED SECONDARY DATA")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        total = 0
        total += import_cash_payments(db)
        total += import_terminated_leases(db)
        print("\n" + "=" * 60)
        print(f"🎉 IMPORT COMPLETE! Total records processed: {total}")
        print("=" * 60)
    except Exception as e:
        db.rollback()
        print(f"\n❌ ERROR: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
