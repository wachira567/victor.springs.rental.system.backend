from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
import models
import logging

from whatsapp_bot import send_whatsapp_message
# Import your SMS dispatch logic here if it exists globally. For now we will mock it if it doesn't.
# Assume sms_routes has a method or we make a simple mock.

logger = logging.getLogger(__name__)

def process_scheduled_messages():
    db: Session = SessionLocal()
    print("Processing scheduled messages...")
    try:
        now = datetime.utcnow()
        # Find messages that are PENDING and dispatch_time is <= now
        messages = db.query(models.ScheduledMessage).filter(
            models.ScheduledMessage.status == "PENDING",
            models.ScheduledMessage.dispatch_time <= now
        ).all()

        for msg in messages:
            try:
                if msg.platform_type == "whatsapp":
                    success = send_whatsapp_message(msg.recipient_phone, msg.message_payload)
                    msg.status = "SENT" if success else "FAILED"
                elif msg.platform_type == "sms":
                    # MOCK SMS SEND
                    logger.info(f"[SMS DISPATCH] To: {msg.recipient_phone} - {msg.message_payload}")
                    msg.status = "SENT"
                else:
                    msg.status = "FAILED"
            except Exception as e:
                logger.error(f"Error sending scheduled message {msg.id}: {e}")
                msg.status = "FAILED"
            
            db.commit()

        # Handle Reminders (Optional: If we want reminders to send SMS directly)
        active_reminders = db.query(models.Reminder).filter(
            models.Reminder.is_active == True,
            models.Reminder.target_date <= now,
            models.Reminder.target_phone.isnot(None) # Only blast if they requested a phone ping
        ).all()

        for rem in active_reminders:
            try:
                note_content = rem.note.title if rem.note else "You have a scheduled reminder."
                payload = f"Reminder: {note_content}"
                if rem.platform == "whatsapp":
                    send_whatsapp_message(rem.target_phone, payload)
                else:
                    logger.info(f"[SMS REMINDER DISPATCH] To: {rem.target_phone} - {payload}")
                
                rem.is_active = False # Turn it off so it doesn't blast every minute
                db.commit()
            except Exception as e:
                logger.error(f"Error sending reminder {rem.id}: {e}")

    except Exception as e:
        logger.error(f"Scheduler job failed: {e}")
    finally:
        db.close()


scheduler = BackgroundScheduler()
# Run every 60 seconds
scheduler.add_job(process_scheduled_messages, 'interval', minutes=1)

def start_scheduler():
    scheduler.start()
    logger.info("Background Scheduler Started.")
    print("Scheduler started - checking if running:", scheduler.running)

def shutdown_scheduler():
    scheduler.shutdown()
    logger.info("Background Scheduler Shutdown.")
