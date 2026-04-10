import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import auth_routes, core_routes, sms_routes, report_routes, user_routes, config_routes, whatsapp_routes, reminders_routes, import_routes
from scheduler import start_scheduler, shutdown_scheduler

from audit import AuditTrailMiddleware, setup_audit_logging
from database import engine

app = FastAPI(title="Rental Management API")

setup_audit_logging(engine)

frontend_urls = os.getenv("FRONTEND_URL", "http://localhost:5173,http://127.0.0.1:5173").split(",")

app.add_middleware(AuditTrailMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[url.strip() for url in frontend_urls if url.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# @app.on_event("startup")
# async def startup_event():
#     try:
#         print("Starting scheduler...")
#         start_scheduler()
#         print("Scheduler started successfully")
#     except Exception as e:
#         print(f"Error starting scheduler: {e}")
#         import traceback
#         traceback.print_exc()
#         # Don't let scheduler failure crash the app
#         pass

@app.on_event("shutdown")
async def shutdown_event():
    try:
        shutdown_scheduler()
    except Exception as e:
        print(f"Error shutting down scheduler: {e}")

# Restored all routers
app.include_router(auth_routes.router)
app.include_router(core_routes.router)
app.include_router(sms_routes.router)
app.include_router(report_routes.router)
app.include_router(user_routes.router)
app.include_router(config_routes.router)
app.include_router(whatsapp_routes.router)
app.include_router(reminders_routes.router)
app.include_router(import_routes.router)

@app.get("/")
def root():
    return {"message": "Rental Management API is running", "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
