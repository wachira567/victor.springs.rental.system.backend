# Victor Springs Rental System - Backend

The core API and business logic layer for the Victor Springs Property Management System. This backend is designed for high security, structural integrity, and seamless data migration from legacy platforms.

## 🏗 Architecture Overview

The system follows a clean, modular architecture built on **FastAPI**:
- **`app.py`**: Entry point and middleware configuration (CORS, Audit Trail).
- **`models.py`**: SQLAlchemy database models with a global `AuditMixin` for change tracking.
- **`schemas.py`**: Pydantic models for request validation and response serialization.
- **`database.py`**: Database connection management and session utility.
- **`routers/`**: Grouped API endpoints (Auth, Core, Admin, etc.).
- **`migrations/`**: Alembic migration scripts for version-controlled schema updates.

## 🛡 Security & Accountability

### 1. Unified Audit Trail
A global middleware intercepts every data-modification request (POST, PUT, DELETE). 
- **Automatic Logging**: Every change is recorded in the `audit_logs` table.
- **Metadata**: Logs capture the `user_id`, `action_type`, `timestamp`, and the specific database table affected.
- **Transparency**: Admins can track exactly who reversed a bill or updated a lease.

### 2. RBAC (Role-Based Access Control)
Access is strictly enforced through JWT Bearer tokens with the following roles:
- **SUPER_ADMIN**: Full system control, user approvals, and configuration management.
- **ADMIN**: Property and financial management.
- **LANDLORD**: Read-only access to their specific properties and statements.
- **TENANT**: Access to personal bills and payment history.

### 3. Registration & Approval
New accounts default to an `inactive` state. Access is granted only after a `SUPER_ADMIN` approves the user via the specialized admin endpoint.

## 📊 Database Schema & Relationships

### Core Entities:
- **Landlords**: Own properties; referenced by Properties.
- **Properties (Apartments)**: Container for multiple Units.
- **Units**: Individual houses with specific unit numbers and market rents.
- **Tenants**: Residents with contact info and identity verification.
- **Leases**: The binding link between a `Tenant` and a `Unit`, tracking `start_date`, `rent_amount`, and `status`.

### Financial Layer:
- **Invoices (Bills)**: Generated for Rent, Water, Power, etc. Linked to a Lease.
- **BillTypes**: A dynamic lookup table for categories like "Garbage", "Security", "Water Deposit".
- **Payments**: Records of transactions, linked to specific Invoices.
- **MeterReadings**: Tracks water consumption for accurate billing.

## 🚀 Data Migration & Scraping

The system includes a dedicated suite for migrating data from `tolet.co.ke`:
- **`Web scrapping data/extract_missed_data.py`**: A Playwright-powered bot that logs into the legacy platform to pull:
    - `cashPayments`
    - `terminatedLeases`
    - Miscellaneous Reporting tables.
- **`import_missed_data.py`**: A high-performance insertion script that:
    - Parses legacy CSV files.
    - Maps records to the new normalized schema.
    - Performs pre-insertion validation to prevent duplicate UUIDs or orphan records.

## 🛠 Setup & Installation

### 1. Prerequisites
- Python 3.8+
- PostgreSQL
- `pipenv` or `venv`

### 2. Environment Variables (`.env`)
```env
DATABASE_URL=postgresql://postgres:password@localhost/victor_springs
SECRET_KEY=generate_a_secure_random_string_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=43200
GOOGLE_CLIENT_ID=optional_for_google_sso
```

### 3. Installation
```bash
# Set up virtual environment
python -m venv venv
source venv/bin/activate

# Install core dependencies
pip install fastapi uvicorn sqlalchemy psycopg2-binary passlib[bcrypt] python-multipart python-jose[cryptography] python-dotenv alembic playwright

# Install playwright browser for scrapers
playwright install chromium
```

### 4. Running the API
```bash
# Apply migrations
alembic upgrade head

# Start server
uvicorn app.py --reload --port 8000

pipenv run uvicorn app:app --reload

```

## 🔌 API Documentation
Once running, interactive documentation is available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
