import os
import sys
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend to path to import models
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import Base, Lease, Invoice, Payment, Unit, Tenant
from database import engine, SessionLocal

def reconcile():
    db = SessionLocal()
    try:
        print("Starting global payment reconciliation...")
        
        # 1. Get all leases
        leases = db.query(Lease).all()
        print(f"Found {len(leases)} leases to process.")
        
        for lease in leases:
            # 2. Get all invoices for this lease, ordered by date
            invoices = db.query(Invoice).filter(Invoice.lease_id == lease.id).order_by(Invoice.billing_period.asc()).all()
            
            # Reset all invoices for this lease first
            for inv in invoices:
                inv.amount_paid = 0
                inv.is_paid = False
            
            # 3. Get all payments for this lease
            payments = db.query(Payment).filter(Payment.lease_id == lease.id).all()
            total_payment_pool = sum(float(p.amount) for p in payments)
            
            print(f"Lease {lease.id}: Total Payments = KES {total_payment_pool:.2f}, Invoices = {len(invoices)}")
            
            # 4. Distribute the payment pool across invoices chronologically (FIFO)
            remaining_pool = total_payment_pool
            for inv in invoices:
                if remaining_pool <= 0:
                    break
                
                bill_amount = float(inv.amount)
                
                if remaining_pool >= bill_amount:
                    # Fully pay
                    inv.amount_paid = bill_amount
                    inv.is_paid = True
                    remaining_pool -= bill_amount
                else:
                    # Partially pay
                    inv.amount_paid = remaining_pool
                    inv.is_paid = False
                    remaining_pool = 0
            
        db.commit()
        print("Reconciliation complete!")
        
    except Exception as e:
        db.rollback()
        print(f"Error during reconciliation: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    reconcile()
