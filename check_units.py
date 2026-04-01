from sqlalchemy.orm import Session
from database import SessionLocal
import models

def check_counts():
    db = SessionLocal()
    try:
        properties = db.query(models.Property).all()
        print(f"{'ID':<5} | {'Property Name':<30} | {'num_units':<10} | {'actual_unit_records':<20}")
        print("-" * 75)
        for p in properties:
            actual_count = db.query(models.Unit).filter(models.Unit.property_id == p.id).count()
            print(f"{p.id:<5} | {p.name:<30} | {p.num_units:<10} | {actual_count:<20}")
    finally:
        db.close()

if __name__ == "__main__":
    check_counts()
