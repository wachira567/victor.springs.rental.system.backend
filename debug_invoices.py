import sys
from database import SessionLocal
import models
import schemas
from sqlalchemy.orm import joinedload

db = SessionLocal()
try:
    invoices = db.query(models.Invoice).options(
        joinedload(models.Invoice.lease).joinedload(models.Lease.tenant),
        joinedload(models.Invoice.lease).joinedload(models.Lease.unit).joinedload(models.Unit.property)
    ).all()
    
    print(f"Loaded {len(invoices)} invoices")
    for i, inv in enumerate(invoices):
        try:
            data = schemas.InvoiceOut.model_validate(inv)
        except Exception as e:
            print(f"FAILED ON INVOICE ID {inv.id}")
            print(e)
            break
            
    print("Done")
except Exception as e:
    print(e)
finally:
    db.close()
