import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import auth_routes, core_routes, sms_routes, report_routes, user_routes, config_routes

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

app.include_router(auth_routes.router)
app.include_router(core_routes.router)
app.include_router(sms_routes.router)
app.include_router(report_routes.router)
app.include_router(user_routes.router)
app.include_router(config_routes.router)

@app.get("/")
def root():
    return {"message": "Rental Management API is running", "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
