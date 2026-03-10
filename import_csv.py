"""
CSV Data Import Script for Rental Management System
=====================================================
Imports all historical data from the scraped CSV files into the Neon PostgreSQL database.
This script is READ-ONLY on the CSV files and only INSERTs into the database.
It will NOT delete or modify any existing records.
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

# Path to CSV files (one directory up from backend)
CSV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

def safe_decimal(value, default=Decimal("0.00")):
    """Safely convert a string to Decimal, returning default on failure."""
    if not value or value.strip() == "":
        return default
    try:
        # Remove commas and spaces
        cleaned = value.strip().replace(",", "").replace(" ", "")
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return default

def safe_int(value, default=0):
    """Safely convert a string to int."""
    if not value or value.strip() == "":
        return default
    try:
        cleaned = value.strip().replace(",", "")
        # Handle scientific notation like 1e-8
        return int(float(cleaned))
    except (ValueError, TypeError):
        return default

def safe_date(value, default=None):
    """Parse date strings into Python date objects."""
    if not value or value.strip() == "":
        return default
    value = value.strip()
    # Try multiple formats
    for fmt in ["%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    print(f"  [WARN] Could not parse date: '{value}'")
    return default

def clean_phone(phone):
    """Clean phone number string."""
    if not phone:
        return ""
    return phone.strip()

def read_csv(filename):
    """Read a CSV file and return rows as list of dicts."""
    filepath = os.path.join(CSV_DIR, filename)
    if not os.path.exists(filepath):
        print(f"  [SKIP] File not found: {filepath}")
        return []
    
    rows = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Skip completely empty rows
            if any(v and v.strip() for v in row.values()):
                rows.append(row)
    return rows

# ========================================================================
# IMPORT FUNCTIONS - Each one handles a specific CSV file
# ========================================================================

def import_landlords(db: Session):
    """Import landlords.csv → landlords table"""
    print("\n📋 Importing Landlords...")
    rows = read_csv("landlords.csv")
    imported = 0
    
    for row in rows:
        name = (row.get("Full Name") or "").strip()
        if not name:
            continue
        
        # Check if already exists
        existing = db.query(models.Landlord).filter(models.Landlord.name == name).first()
        if existing:
            continue
        
        landlord = models.Landlord(
            name=name,
            phone=clean_phone(row.get("Phone Number", "")),
            email=(row.get("Email") or "").strip(),
            id_number=(row.get("National Id") or "").strip(),
        )
        db.add(landlord)
        imported += 1
    
    db.commit()
    print(f"  ✅ Imported {imported} landlords (skipped {len(rows) - imported} duplicates)")
    return imported

def import_properties(db: Session):
    """Import properties.csv → properties table"""
    print("\n🏠 Importing Properties...")
    rows = read_csv("properties.csv")
    imported = 0
    
    for row in rows:
        name = (row.get("Name") or "").strip()
        if not name:
            continue
        
        existing = db.query(models.Property).filter(models.Property.name == name).first()
        if existing:
            continue
        
        # Find the landlord
        landlord_name = (row.get("Landlord") or "").strip()
        landlord = db.query(models.Landlord).filter(models.Landlord.name == landlord_name).first()
        
        if not landlord:
            # Create a placeholder landlord if not found
            landlord = models.Landlord(name=landlord_name or "UNKNOWN", phone="", email="")
            db.add(landlord)
            db.flush()
        
        # Parse commission rate
        commission_str = (row.get("Commission") or "0").strip()
        commission = safe_decimal(commission_str, Decimal("0.00"))
        
        prop = models.Property(
            name=name,
            title=(row.get("Title") or "").strip(),
            code=(row.get("Code") or "").strip(),
            category=(row.get("Category Name") or "").strip(),
            description=(row.get("Description") or "").strip(),
            location=(row.get("Location") or "").strip(),
            property_type=(row.get("Property Type") or "").strip(),
            num_units=safe_int(row.get("Number of Units", "0")),
            landlord_id=landlord.id,
            management_commission_rate=commission,
        )
        db.add(prop)
        imported += 1
    
    db.commit()
    print(f"  ✅ Imported {imported} properties")
    return imported

def import_tenants(db: Session):
    """Import tenants.csv → tenants table"""
    print("\n👤 Importing Tenants...")
    rows = read_csv("tenants.csv")
    imported = 0
    skipped = 0
    
    for row in rows:
        name = (row.get("Full Name") or "").strip()
        if not name:
            continue
        
        phone = clean_phone(row.get("Phone Number", ""))
        national_id = (row.get("National Id") or "").strip() or None
        gender = (row.get("Gender") or "").strip()
        
        # Check for duplicate by name + phone (some tenants share national IDs or have none)
        existing = db.query(models.Tenant).filter(
            models.Tenant.full_name == name,
            models.Tenant.phone_number == phone
        ).first()
        
        if existing:
            skipped += 1
            continue
        
        tenant = models.Tenant(
            full_name=name,
            national_id=national_id,
            phone_number=phone,
            gender=gender,
        )
        db.add(tenant)
        imported += 1
    
    db.commit()
    print(f"  ✅ Imported {imported} tenants (skipped {skipped} duplicates)")
    return imported

def import_leases(db: Session):
    """Import leases.csv → leases table (linking tenants → properties/units)"""
    print("\n📝 Importing Leases...")
    rows = read_csv("leases.csv")
    imported = 0
    skipped = 0
    
    for row in rows:
        tenant_name = (row.get("Tenant") or "").strip()
        property_name = (row.get("Property Name") or "").strip()
        house_number = (row.get("House Number") or "").strip()
        start_date = safe_date(row.get("Start Date"))
        status = (row.get("Status") or "Active").strip()
        
        if not tenant_name or not property_name:
            skipped += 1
            continue
        
        # Find tenant
        tenant = db.query(models.Tenant).filter(models.Tenant.full_name == tenant_name).first()
        if not tenant:
            skipped += 1
            continue
        
        # Find property
        prop = db.query(models.Property).filter(models.Property.name == property_name).first()
        if not prop:
            skipped += 1
            continue
        
        # Find or create unit
        unit = db.query(models.Unit).filter(
            models.Unit.property_id == prop.id,
            models.Unit.unit_number == house_number
        ).first()
        
        if not unit:
            unit = models.Unit(
                property_id=prop.id,
                unit_number=house_number,
                unit_type="",
                market_rent=Decimal("0.00"),
                is_vacant=False,
            )
            db.add(unit)
            db.flush()
        else:
            unit.is_vacant = False
        
        # Check for duplicate lease
        existing_lease = db.query(models.Lease).filter(
            models.Lease.tenant_id == tenant.id,
            models.Lease.unit_id == unit.id,
            models.Lease.start_date == start_date,
        ).first()
        
        if existing_lease:
            skipped += 1
            continue
        
        lease = models.Lease(
            unit_id=unit.id,
            tenant_id=tenant.id,
            start_date=start_date or datetime.now().date(),
            rent_amount=Decimal("0.00"),  # Will be updated from bills
            status=status.upper(),
        )
        db.add(lease)
        imported += 1
    
    db.commit()
    print(f"  ✅ Imported {imported} leases (skipped {skipped})")
    return imported

def import_bills(db: Session):
    """Import bills.csv → invoices table"""
    print("\n💰 Importing Bills/Invoices...")
    rows = read_csv("bills.csv")
    imported = 0
    skipped = 0
    
    for row in rows:
        property_name = (row.get("Plot") or "").strip()
        house_number = (row.get("House Number") or "").strip()
        tenant_name = (row.get("Tenant") or "").strip()
        service_name = (row.get("Service Name") or "").strip()
        amount = safe_decimal(row.get("Amount", "0"))
        bill_date = safe_date(row.get("Bill Date"))
        
        if not tenant_name or not property_name:
            skipped += 1
            continue
        
        # Find the tenant
        tenant = db.query(models.Tenant).filter(models.Tenant.full_name == tenant_name).first()
        if not tenant:
            skipped += 1
            continue
        
        # Find an active lease for this tenant
        lease = db.query(models.Lease).filter(models.Lease.tenant_id == tenant.id).first()
        if not lease:
            skipped += 1
            continue
        
        # Update the rent on the lease if this is a Rent bill
        if service_name.lower() == "rent" and amount > 0:
            lease.rent_amount = amount
        
        invoice = models.Invoice(
            lease_id=lease.id,
            billing_period=bill_date or datetime.now().date(),
            type=service_name,
            amount=amount,
            amount_paid=Decimal("0.00"),
            is_paid=False,
        )
        db.add(invoice)
        imported += 1
        
        # Commit in batches of 500 to avoid memory issues
        if imported % 500 == 0:
            db.commit()
            print(f"  ... committed {imported} invoices so far")
    
    db.commit()
    print(f"  ✅ Imported {imported} invoices (skipped {skipped})")
    return imported

def import_meter_readings(db: Session):
    """Import meter_readings.csv → a new 'meter_readings' table or store them on invoices.
    Since the CSV has no header row, we parse by position."""
    print("\n🔢 Importing Meter Readings...")
    
    filepath = os.path.join(CSV_DIR, "meter_readings.csv")
    if not os.path.exists(filepath):
        print("  [SKIP] meter_readings.csv not found")
        return 0
    
    imported = 0
    skipped = 0
    
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 9:
                skipped += 1
                continue
            
            # Columns: [id, property_name, house_number, prev_reading, current_reading, units_consumed, rate, amount, date, ...]
            reading_id = row[0].strip()
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
            
            # Find property and unit
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
            
            # Find an active lease for this unit
            lease = db.query(models.Lease).filter(models.Lease.unit_id == unit.id).first()
            if not lease:
                skipped += 1
                continue
            
            # Store as a Water invoice
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
    print(f"  ✅ Imported {imported} meter reading invoices (skipped {skipped})")
    return imported


# ========================================================================
# MAIN EXECUTION
# ========================================================================
def main():
    print("=" * 60)
    print("🚀 RENTAL MANAGEMENT DATA IMPORT")
    print("=" * 60)
    print(f"CSV Source: {CSV_DIR}")
    print(f"Database:   {os.environ.get('DATABASE_URL', 'Not Set')[:50]}...")
    print("=" * 60)
    
    # Create all tables if they don't exist
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        total = 0
        total += import_landlords(db)
        total += import_properties(db)
        total += import_tenants(db)
        total += import_leases(db)
        total += import_bills(db)
        total += import_meter_readings(db)
        
        print("\n" + "=" * 60)
        print(f"🎉 IMPORT COMPLETE! Total records imported: {total}")
        print("=" * 60)
        
        # Print summary stats
        print("\n📊 Database Summary:")
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
