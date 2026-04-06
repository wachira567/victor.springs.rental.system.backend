import os
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime

import models, schemas, auth
from database import get_db
from whatsapp_bot import handle_incoming_message, send_whatsapp_message, get_whatsapp_config

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.environ.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "victorsprings_secret")

@router.get("/webhook")
def verify_webhook(request: Request):
    """Meta Webhook Verification Endpoint"""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == WHATSAPP_WEBHOOK_VERIFY_TOKEN:
            return Response(content=challenge, media_type="text/plain")
        else:
            raise HTTPException(status_code=403, detail="Verification token mismatch")
    return {"message": "Hello from WhatsApp Webhook"}

@router.post("/webhook")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    """Receives Messages from Meta"""
    data = await request.json()
    
    if data.get("object") == "whatsapp_business_account":
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                
                for msg in messages:
                    phone_number = msg.get("from")
                    if msg.get("type") == "text":
                        text_body = msg.get("text", {}).get("body", "")
                        handle_incoming_message(phone_number, text_body, db)
                        
    return {"status": "success"}

# --- Admin Endpoints ---

@router.get("/config", response_model=schemas.WhatsAppConfigOut)
def get_config(db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["super_admin"]))):
    return get_whatsapp_config(db)

@router.put("/config", response_model=schemas.WhatsAppConfigOut)
def update_config(config_data: schemas.WhatsAppConfigUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["super_admin"]))):
    config = get_whatsapp_config(db)
    
    update_data = config_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)
        
    db.commit()
    db.refresh(config)
    return config

@router.get("/sessions", response_model=List[schemas.WhatsAppSessionOut])
def get_sessions(
    state: str = None, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))
):
    query = db.query(models.WhatsAppSession)
    if state:
        query = query.filter(models.WhatsAppSession.current_state == state)
    # Order by active requests
    return query.order_by(models.WhatsAppSession.last_interaction_at.desc()).all()

@router.get("/sessions/{session_id}/messages", response_model=List[schemas.WhatsAppMessageOut])
def get_session_messages(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    session = db.query(models.WhatsAppSession).filter(models.WhatsAppSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    messages = db.query(models.WhatsAppMessage).filter(models.WhatsAppMessage.session_id == session_id).order_by(models.WhatsAppMessage.timestamp.asc()).all()
    return messages

@router.post("/sessions/{session_id}/reply")
def agent_reply(session_id: int, payload: Dict[str, str], db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    """Manual Agent Reply endpoint"""
    message_content = payload.get("message")
    if not message_content:
        raise HTTPException(status_code=400, detail="Message content required")
        
    session = db.query(models.WhatsAppSession).filter(models.WhatsAppSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # Send through Meta
    success = send_whatsapp_message(session.phone_number, message_content)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to dispatch message via WhatsApp API")
        
    # Log the message
    msg = models.WhatsAppMessage(
        session_id=session.id,
        sender="agent",
        content=message_content,
        timestamp=datetime.utcnow()
    )
    db.add(msg)
    db.commit()
    return {"message": "Reply sent successfully"}

@router.get("/analytics")
def get_analytics(db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["super_admin", "admin"]))):
    total_sessions = db.query(models.WhatsAppSession).count()
    active_agent_chats = db.query(models.WhatsAppSession).filter(models.WhatsAppSession.current_state == "AGENT_CHAT").count()
    total_messages = db.query(models.WhatsAppMessage).count()
    
    tenant_sessions = db.query(models.WhatsAppSession).filter(models.WhatsAppSession.user_role == "tenant").count()
    landlord_sessions = db.query(models.WhatsAppSession).filter(models.WhatsAppSession.user_role == "landlord").count()
    
    return {
        "total_sessions": total_sessions,
        "active_agent_chats": active_agent_chats,
        "total_messages": total_messages,
        "by_role": {
            "tenant": tenant_sessions,
            "landlord": landlord_sessions
        }
    }
