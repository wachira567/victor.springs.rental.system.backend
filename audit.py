from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import event
from database import SessionLocal
from models import AuditLog
from auth import get_current_user_from_token
from typing import Optional
import json

def get_user_id_from_request(request: Request) -> Optional[int]:
    """Extract user ID from authorization header if present."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            # Reusing the existing auth logic to decode the token manually
            user = get_current_user_from_token(token, db=SessionLocal())
            return user.id if user else None
        except:
            return None
    return None

class AuditTrailMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # We only care about state-changing methods
        if request.method not in ["POST", "PUT", "PATCH", "DELETE"]:
            return await call_next(request)

        user_id = get_user_id_from_request(request)

        # We will attach an event listener to the session to track changes
        # This is somewhat complex because session lifecycle in FastAPI dependencies
        # But we can define a factory for the listener and attach it globally or per request context.
        
        # A simpler approach in middleware without deep SQLAlchemy event integration
        # is just to log the request itself, but let's try to capture the response status.
        
        # Actually, global SQLAlchemy event listener is better placed in database.py or main.py.
        # This middleware will mainly act as a request logger or stash the user_id in the request state.
        request.state.user_id = user_id
        
        response = await call_next(request)
        return response

def setup_audit_logging(engine):
    """Setup SQLAlchemy events to log changes to the audit_logs table."""
    
    @event.listens_for(SessionLocal, 'after_flush')
    def receive_after_flush(session, flush_context):
        # Determine the user_id if we have access to request context (e.g., via ContextVar)
        # For simplicity, if we don't have a ContextVar, we might have to pass it around,
        # but SQLAlchemy events don't easily know about the HTTP request.
        
        # We log changes here
        logs = []
        
        for obj in session.new:
            if hasattr(obj, '__tablename__') and obj.__tablename__ != 'audit_logs':
                state = obj.__dict__.copy()
                state.pop('_sa_instance_state', None)
                # Convert non-serializable objects
                state = {k: str(v) for k, v in state.items()}
                
                logs.append(AuditLog(
                    action='INSERT',
                    table_name=obj.__tablename__,
                    # record_id might not be available until commit for auto-increment
                    record_id=getattr(obj, 'id', None), 
                    new_data=state
                ))
                
        for obj in session.dirty:
            if hasattr(obj, '__tablename__') and obj.__tablename__ != 'audit_logs':
                state = obj.__dict__.copy()
                state.pop('_sa_instance_state', None)
                state = {k: str(v) for k, v in state.items()}
                
                # Try to get old state from history
                from sqlalchemy.orm.attributes import get_history
                old_state = {}
                for attr in state.keys():
                    hist = get_history(obj, attr)
                    if hist.deleted:
                        old_state[attr] = str(hist.deleted[0])
                        
                logs.append(AuditLog(
                    action='UPDATE',
                    table_name=obj.__tablename__,
                    record_id=getattr(obj, 'id', None),
                    old_data=old_state,
                    new_data=state
                ))
                
        for obj in session.deleted:
            if hasattr(obj, '__tablename__') and obj.__tablename__ != 'audit_logs':
                state = obj.__dict__.copy()
                state.pop('_sa_instance_state', None)
                state = {k: str(v) for k, v in state.items()}
                
                logs.append(AuditLog(
                    action='DELETE',
                    table_name=obj.__tablename__,
                    record_id=getattr(obj, 'id', None),
                    old_data=state
                ))
                
        if logs:
            session.add_all(logs)

