from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import event
from database import SessionLocal
from models import AuditLog
from auth import get_current_user_from_token
from typing import Optional
import json
from contextvars import ContextVar

# ContextVar to store the user ID during the request lifecycle
current_user_id: ContextVar[Optional[int]] = ContextVar("current_user_id", default=None)

def get_user_id_from_request(request: Request) -> Optional[int]:
    """Extract user ID from authorization header if present."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        db = SessionLocal()
        try:
            # Reusing the existing auth logic to decode the token manually
            user = get_current_user_from_token(token, db=db)
            return user.id if user else None
        except:
            return None
        finally:
            db.close()
    return None

class AuditTrailMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Extract user ID and set it in the ContextVar
        user_id = get_user_id_from_request(request)
        token = current_user_id.set(user_id)
        
        try:
            # We only care about state-changing methods for deeper logging,
            # but we set the user_id for everything to be safe.
            request.state.user_id = user_id
            response = await call_next(request)
            return response
        finally:
            # Always reset the token to avoid context leakage between requests
            current_user_id.reset(token)

def setup_audit_logging(engine):
    """Setup SQLAlchemy events to log changes to the audit_logs table."""
    
    @event.listens_for(SessionLocal, 'after_flush')
    def receive_after_flush(session, flush_context):
        try:
            # Determine the user_id if we have access to request context
            user_id = current_user_id.get()
            
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
                        record_id=getattr(obj, 'id', None), 
                        user_id=user_id,
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
                        user_id=user_id,
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
                        user_id=user_id,
                        old_data=state
                    ))
                    
            if logs:
                session.add_all(logs)
        except Exception as e:
            print(f"Audit log error: {e}")


