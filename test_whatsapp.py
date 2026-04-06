import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from whatsapp_bot import identify_user, handle_incoming_message, get_whatsapp_config

def run_tests():
    db = SessionLocal()
    try:
        config = get_whatsapp_config(db)
        print("Config Loaded:", config.is_enabled)
        
        # Test number formatter
        print("--- Testing role mismatch ---")
        handle_incoming_message("254700000000", "Hi", db)
        session = db.query(models.WhatsAppSession).filter(models.WhatsAppSession.phone_number == "254700000000").first()
        print("Session created:", session is not None)
    except Exception as e:
        print("Exception:", e)
    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
