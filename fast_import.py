import sys, os, csv, time
from datetime import datetime
from decimal import Decimal
sys.path.append('.')
from database import SessionLocal
import models
db = SessionLocal()

print("Caching...")
tenants = {t.full_name.lower(): t.id for t in db.query(models.Tenant.id, models.Tenant.full_name).all()}
units = {u.unit_number: u.id for u in db.query(models.Unit.id, models.Unit.unit_number).all()}
leases = db.query(models.Lease.id, models.Lease.tenant_id, models.Lease.unit_id).all()
lease_map = {}
for l in leases:
    lease_map[(l.tenant_id, l.unit_id)] = l.id
existing_refs = {p.reference_number for p in db.query(models.Payment.reference_number).filter(models.Payment.reference_number != None).all()}

print("Reading CSV...")
rows = []
with open('../Web scrapping data/cash_payments.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        rows.append(row)

new_payments = []
for i, row in enumerate(rows):
    tenant_name = (row.get('Tenant Name') or '').strip().lower()
    unit_number = (row.get('Unit Number') or '').strip()
    ref_number = (row.get('Ref Number') or '').strip()
    amount_str = row.get('Amount', '0').strip().replace(',', '').replace(' ', '')
    try:
        amount = Decimal(amount_str)
    except:
        amount = Decimal('0')
    if amount <= 0: continue
    
    tenant_id = None
    for k, v in tenants.items():
        if tenant_name in k:
            tenant_id = v
            break
            
    unit_id = units.get(unit_number)
    
    if not tenant_id or not unit_id: continue
    
    lease_id = lease_map.get((tenant_id, unit_id))
    if not lease_id: continue
    
    if ref_number and ref_number in existing_refs: continue
    
    date_val = datetime.now().date()
    received = row.get('Received On', '').strip()
    if received:
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%b %d, %Y', '%B %d, %Y', '%d/%m/%Y']:
            try:
                date_val = datetime.strptime(received, fmt).date()
                break
            except: pass
            
    payment = models.Payment(
        lease_id=lease_id,
        amount=amount,
        payment_method=(row.get('Payment Mode') or 'CASH').strip(),
        reference_number=ref_number if ref_number else f"AUTOGEN-{int(time.time())}-{i}",
        payment_date=date_val
    )
    new_payments.append(payment)
    if ref_number:
        existing_refs.add(ref_number)

print(f"Adding {len(new_payments)} payments...")
if new_payments:
    db.bulk_save_objects(new_payments)
    db.commit()
print("Done!")
