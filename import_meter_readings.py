import csv
import sys
import os
from datetime import datetime

# Set up environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
import models

def import_meter_readings(csv_path):
    print(f"Importing meter readings from {csv_path}...")
    db = SessionLocal()
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            # Format: ID, PropertyName, UnitName, Prev, Current, Cons, Rate, Total, Date
            reader = csv.reader(f)
            
            imported_count = 0
            skipped_count = 0
            
            for row in reader:
                if not row or len(row) < 9:
                    continue
                    
                # Parse columns
                try:    
                    property_name = row[1].strip()
                    unit_number = row[2].strip()
                    prev_reading = float(row[3])
                    curr_reading = float(row[4])
                    consumption = float(row[5])
                    rate = float(row[6])
                    total = float(row[7])
                    date_str = row[8].strip()
                    
                    if not date_str or not unit_number:
                        continue
                        
                    reading_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    # Skip header or malformed rows
                    continue
                
                # Find matching unit
                unit = db.query(models.Unit).filter(models.Unit.unit_number == unit_number).first()
                if not unit:
                    print(f"Skipping reading for unknown unit: {unit_number}")
                    skipped_count += 1
                    continue
                    
                # Check if this reading already exists to prevent duplicates
                existing = db.query(models.MeterReading).filter(
                    models.MeterReading.unit_id == unit.id,
                    models.MeterReading.reading_date == reading_date
                ).first()
                
                if not existing:
                    # Some IDs might be missing or out of order, try parsing column 0
                    try:
                        record_id = int(row[0])
                    except ValueError:
                        record_id = None
                        
                    new_reading = models.MeterReading(
                        id=record_id, # Can be None if malformed, DB will auto-increment
                        unit_id=unit.id,
                        previous_reading=prev_reading,
                        current_reading=curr_reading,
                        consumption=consumption,
                        rate=rate,
                        total_charge=total,
                        reading_date=reading_date
                    )
                    db.add(new_reading)
                    imported_count += 1
                    
                    # Commit in batches of 100
                    if imported_count % 100 == 0:
                        db.commit()
                        print(f"Imported {imported_count} readings...")
                        
            # Final commit
            db.commit()
            print(f"Import complete! Imported: {imported_count}. Skipped: {skipped_count}.")
            
    except Exception as e:
        db.rollback()
        print(f"Error during import: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    csv_file = "../Web scrapping data/meter_readings.csv"
    if os.path.exists(csv_file):
        import_meter_readings(csv_file)
    else:
        print(f"File not found: {csv_file}")
