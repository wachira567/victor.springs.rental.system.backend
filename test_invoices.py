import sys
from database import SessionLocal
import models
import schemas

db = SessionLocal()
try:
    invoices = db.query(models.Invoice).all()
    for inv in invoices:
        data = schemas.InvoiceOut.model_validate(inv)
        if inv.lease:
            if inv.lease.tenant:
                data.tenant_name = inv.lease.tenant.full_name
            if inv.lease.unit:
                data.unit_number = inv.lease.unit.unit_number
                if inv.lease.unit.property:
                    data.property_name = inv.lease.unit.property.name
    print("Success")
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    db.close()
