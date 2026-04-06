import os
import requests
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict, Any, Optional, Tuple

import models

import logging
logger = logging.getLogger(__name__)

# Constants
GRAPH_VERSION = os.environ.get("WHATSAPP_GRAPH_VERSION", "v18.0")
WHATSAPP_API_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_NUMBER_1_TOKEN", "")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_NUMBER_1_ID", "")

def get_whatsapp_config(db: Session) -> models.WhatsAppConfig:
    config = db.query(models.WhatsAppConfig).first()
    if not config:
        config = models.WhatsAppConfig(
            is_enabled=True,
            allow_tenant_access=True,
            allow_landlord_access=True,
            tenant_allowed_features=["bills", "rent", "arrears", "payments", "agent_chat"],
            landlord_allowed_features=["stats", "agent_chat"],
            inactivity_timeout_minutes=5
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    return config

def send_whatsapp_message(to_phone: str, text: str) -> bool:
    if not WHATSAPP_PHONE_ID or not WHATSAPP_TOKEN:
        logger.warning(f"WhatsApp credentials not set. Mock sending to {to_phone}: {text}")
        return True # Mock send
        
    url = f"{WHATSAPP_API_URL}/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text}
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message: {e} - Response: {getattr(response, 'text', '')}")
        return False

def format_phone(phone: str) -> str:
    # Basic standardization. Converts local to +254 or strips + depending on your needs.
    # We will strip '+' and space to just match numeric strings.
    import re
    cleaned = re.sub(r'\D', '', phone)
    if cleaned.startswith('254') or cleaned.startswith('1'):
        pass
    elif cleaned.startswith('0'):
        cleaned = '254' + cleaned[1:]
    return cleaned

def identify_user(phone: str, db: Session) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """Returns (role, user_id, full_name)"""
    config = get_whatsapp_config(db)
    
    # 1. Check Super Admin / Admin (Users table)
    user = db.query(models.User).filter(func.replace(models.User.email, ' ', '') == phone).first() # we don't have phone in User?
    # Actually, Users don't have phone_number. Or do they? Let's check Tenant/Landlord first, and if we match user_id, check role
    
    # 2. Check Tenants
    tenant = db.query(models.Tenant).filter(models.Tenant.phone_number == phone).first()
    # Or format matching
    if tenant and config.allow_tenant_access:
        return ("tenant", tenant.id, tenant.full_name)
        
    # 3. Check Landlords
    landlord = db.query(models.Landlord).filter(models.Landlord.phone == phone).first()
    if landlord and config.allow_landlord_access:
        return ("landlord", landlord.id, landlord.name)
        
    return (None, None, None)

def handle_incoming_message(phone: str, message: str, db: Session):
    config = get_whatsapp_config(db)
    if not config.is_enabled:
        return
        
    cleaned_phone = format_phone(phone)
    
    session = db.query(models.WhatsAppSession).filter(models.WhatsAppSession.phone_number == cleaned_phone).first()
    
    now = datetime.utcnow()
    
    # Session Timeout Logic
    if session:
        if now - session.last_interaction_at > timedelta(minutes=config.inactivity_timeout_minutes):
            session.current_state = "MAIN_MENU" # Reset
        session.last_interaction_at = now
    else:
        role, u_id, name = identify_user(cleaned_phone, db)
        # Attempt fallback matching if standard doesn't work (e.g. 07xx instead of 2547xx)
        if not role and cleaned_phone.startswith("254"):
            role, u_id, name = identify_user("0" + cleaned_phone[3:], db)
        
        if not role:
            send_whatsapp_message(cleaned_phone, "Sorry, your phone number is not registered in our system.")
            return

        session = models.WhatsAppSession(
            phone_number=cleaned_phone,
            user_id=u_id,
            user_role=role,
            user_name=name,
            current_state="MAIN_MENU",
            last_interaction_at=now
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        
    # Log incoming message
    msg = models.WhatsAppMessage(
        session_id=session.id,
        sender="user",
        content=message,
        timestamp=now
    )
    db.add(msg)
    
    # Handle Live Agent Chat State
    if session.current_state == "AGENT_CHAT":
        # Do not auto respond, let the agent handle it.
        # But allow user to type "EXIT" to leave Agent mode
        if message.lower().strip() == "exit":
            session.current_state = "MAIN_MENU"
            db.commit()
            bot_reply = "You left the chat with the agent. Let me know what else I can help with:\n\n" + get_main_menu(session.user_role, config)
            send_whatsapp_message(cleaned_phone, bot_reply)
            msg_reply = models.WhatsAppMessage(session_id=session.id, sender="bot", content=bot_reply)
            db.add(msg_reply)
        db.commit()
        return

    # Normal State Machine
    reply_text = ""
    user_input = message.strip()
    
    if session.current_state == "MAIN_MENU":
        if user_input == "1" and "bills" in config.tenant_allowed_features and session.user_role == "tenant":
            reply_text = retrieve_tenant_bills(session.user_id, db)
        elif user_input == "2" and "arrears" in config.tenant_allowed_features and session.user_role == "tenant":
            reply_text = retrieve_tenant_arrears(session.user_id, db)
        elif user_input == "1" and "stats" in config.landlord_allowed_features and session.user_role == "landlord":
            reply_text = retrieve_landlord_stats(session.user_id, db)
        elif user_input == "9" and "agent_chat" in (config.tenant_allowed_features if session.user_role=="tenant" else config.landlord_allowed_features):
            session.current_state = "AGENT_CHAT"
            reply_text = "An agent has been notified and will be with you shortly. Type EXIT to leave this chat."
        else:
            reply_text = "Welcome to VictorSprings!\n\n" + get_main_menu(session.user_role, config)
    
    else:
        # Default fallback
        session.current_state = "MAIN_MENU"
        reply_text = "I didn't understand that.\n\n" + get_main_menu(session.user_role, config)

    if reply_text:
        send_whatsapp_message(cleaned_phone, reply_text)
        b_msg = models.WhatsAppMessage(
            session_id=session.id,
            sender="bot",
            content=reply_text,
            timestamp=datetime.utcnow()
        )
        db.add(b_msg)
        
    db.commit()

def get_main_menu(role: str, config: models.WhatsAppConfig) -> str:
    if role == "tenant":
        menu = "Please choose an option:\n"
        if "bills" in config.tenant_allowed_features: menu += "1. View My Rent & Bills\n"
        if "arrears" in config.tenant_allowed_features: menu += "2. View Arrears\n"
        if "agent_chat" in config.tenant_allowed_features: menu += "9. Speak to an Agent\n"
        return menu
    elif role == "landlord":
        menu = "Landlord Portal:\n"
        if "stats" in config.landlord_allowed_features: menu += "1. Property & Tenant Stats\n"
        if "agent_chat" in config.landlord_allowed_features: menu += "9. Speak to an Agent\n"
        return menu
    return "Menu not available."


# Custom Data Resolvers
def retrieve_tenant_bills(tenant_id: int, db: Session) -> str:
    # Simplified: Get unpaid invoices for the tenant
    leases = db.query(models.Lease).filter(models.Lease.tenant_id == tenant_id, models.Lease.status == "ACTIVE").all()
    if not leases:
        return "You have no active leases."
        
    reply = "Your Bills:\n\n"
    total_due = 0
    for lease in leases:
        invoices = db.query(models.Invoice).filter(models.Invoice.lease_id == lease.id, models.Invoice.is_paid == False).all()
        for inv in invoices:
            due = inv.amount - inv.amount_paid
            reply += f"- {inv.type} for {inv.billing_period.strftime('%B %Y')}: KES {due}\n"
            total_due += due
            
    if total_due == 0:
        reply += "You have no outstanding bills. Thank you!"
    else:
        reply += f"\nTotal Due: KES {total_due}"
    return reply

def retrieve_tenant_arrears(tenant_id: int, db: Session) -> str:
    # Just reusing bills logic, but can be tailored specifically for past-due.
    return retrieve_tenant_bills(tenant_id, db)

def retrieve_landlord_stats(landlord_id: int, db: Session) -> str:
    properties = db.query(models.Property).filter(models.Property.landlord_id == landlord_id).all()
    if not properties:
        return "No properties found under your account."
        
    total_units = 0
    total_tenants = 0
    for prop in properties:
        units = db.query(models.Unit).filter(models.Unit.property_id == prop.id).all()
        total_units += len(units)
        occupied = [u for u in units if not u.is_vacant]
        total_tenants += len(occupied)
        
    reply = f"Property Statistics:\n\n"
    reply += f"Total Properties: {len(properties)}\n"
    reply += f"Total Units: {total_units}\n"
    reply += f"Occupied Units (Tenants): {total_tenants}\n"
    reply += f"Vacant Units: {total_units - total_tenants}"
    return reply

