"""
Meter Readings Import Script (retry)
=====================================
Re-imports only meter readings since the main import already completed
landlords, properties, tenants, leases, and bills/invoices.
"""

import csv
import os
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from database import engine, SessionLocal, Base
import models

CSV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

def safe_decimal(value, default=Decimal("0.00")):
    if not value or value.strip() == "":
        return default
    try:
        cleaned = value.strip().replace(",", "").replace(" ", "")
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return default

def safe_int(value, default=0):
    if not value or value.strip() == "":
        return default
    try:
        return int(float(value.strip().replace(",", "")))
    except (ValueError, TypeError):
        return default

def safe_date(value, default=None):
    if not value or value.strip() == "":
        return default
    value = value.strip()
    for fmt in ["%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return default

def main():
    print("=" * 60)
    print("🔢 METER READINGS IMPORT (RETRY)")
    print("=" * 60)

    filepath = os.path.join(CSV_DIR, "meter_readings.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] meter_readings.csv not found")
        return

    db = SessionLocal()
    imported = 0
    skipped = 0

    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 9:
                    skipped += 1
                    continue

                property_name = row[1].strip()
                house_number = row[2].strip()
                prev_reading = row[3].strip()
                current_reading = row[4].strip()
                units_consumed = safe_int(row[5])
                rate = safe_decimal(row[6])
                amount = safe_decimal(row[7])
                reading_date = safe_date(row[8])

                if not property_name or not house_number:
                    skipped += 1
                    continue

                prop = db.query(models.Property).filter(models.Property.name == property_name).first()
                if not prop:
                    skipped += 1
                    continue

                unit = db.query(models.Unit).filter(
                    models.Unit.property_id == prop.id,
                    models.Unit.unit_number == house_number
                ).first()
                if not unit:
                    skipped += 1
                    continue

                lease = db.query(models.Lease).filter(models.Lease.unit_id == unit.id).first()
                if not lease:
                    skipped += 1
                    continue

                invoice = models.Invoice(
                    lease_id=lease.id,
                    billing_period=reading_date or datetime.now().date(),
                    type=f"Water (Meter: {prev_reading}->{current_reading}, {units_consumed} units @{rate})",
                    amount=amount,
                    amount_paid=Decimal("0.00"),
                    is_paid=False,
                )
                db.add(invoice)
                imported += 1

                if imported % 500 == 0:
                    db.commit()
                    print(f"  ... committed {imported} meter reading invoices so far")

        db.commit()
        print(f"\n✅ Imported {imported} meter reading invoices (skipped {skipped})")
        
        # Print final summary
        print("\n📊 Final Database Summary:")
        print(f"   Landlords:  {db.query(models.Landlord).count()}")
        print(f"   Properties: {db.query(models.Property).count()}")
        print(f"   Units:      {db.query(models.Unit).count()}")
        print(f"   Tenants:    {db.query(models.Tenant).count()}")
        print(f"   Leases:     {db.query(models.Lease).count()}")
        print(f"   Invoices:   {db.query(models.Invoice).count()}")

    except Exception as e:
        db.rollback()
        print(f"\n❌ ERROR: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
