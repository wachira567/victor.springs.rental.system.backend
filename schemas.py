from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any
from datetime import datetime, date
from decimal import Decimal

# --- Users ---
class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: Optional[str] = "tenant"

class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    role: str
    is_approved: bool
    is_active: bool

    class Config:
        from_attributes = True

# --- Properties ---
class PropertyCreate(BaseModel):
    name: str = Field(..., max_length=150)
    location: Optional[str] = Field(None, max_length=200)
    landlord_id: int
    management_commission_rate: Optional[Decimal] = Decimal('0.00')
    code: Optional[str] = None
    num_units: Optional[int] = 0
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    property_type: Optional[str] = None

class PropertyOut(BaseModel):
    id: int
    name: str
    location: Optional[str] = None
    landlord_id: int
    management_commission_rate: Optional[Decimal] = Decimal('0.00')
    code: Optional[str] = None
    num_units: Optional[int] = 0
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    property_type: Optional[str] = None

    class Config:
        from_attributes = True

# --- Units ---
class UnitCreate(BaseModel):
    property_id: int
    unit_number: str
    unit_type: Optional[str] = None
    market_rent: Decimal
    is_vacant: Optional[bool] = True

class UnitOut(BaseModel):
    id: int
    property_id: int
    unit_number: str
    unit_type: Optional[str] = None
    market_rent: Decimal
    is_vacant: bool

    class Config:
        from_attributes = True

# --- Tenants ---
class TenantCreate(BaseModel):
    full_name: str = Field(..., max_length=150)
    national_id: str = Field(..., max_length=50)
    phone_number: str = Field(..., max_length=50)
    email: Optional[EmailStr] = None
    emergency_contact: Optional[str] = Field(None, max_length=150)
    gender: Optional[str] = None

class TenantOut(BaseModel):
    id: int
    full_name: str
    national_id: Optional[str] = None
    phone_number: str
    email: Optional[str] = None
    emergency_contact: Optional[str] = None
    gender: Optional[str] = None
    user_id: Optional[int] = None

    class Config:
        from_attributes = True

# --- Leases ---
class LeaseCreate(BaseModel):
    unit_id: int
    tenant_id: int
    start_date: date
    end_date: Optional[date] = None
    rent_amount: Decimal
    deposit_amount: Optional[Decimal] = Decimal('0.00')

class LeaseOut(BaseModel):
    id: int
    unit_id: int
    tenant_id: int
    start_date: date
    end_date: Optional[date] = None
    rent_amount: Decimal
    deposit_amount: Optional[Decimal] = Decimal('0.00')
    status: str
    # Joined data for display
    unit_number: Optional[str] = None
    property_name: Optional[str] = None
    tenant_name: Optional[str] = None

    class Config:
        from_attributes = True

# --- Invoices ---
class InvoiceCreate(BaseModel):
    lease_id: int
    billing_period: date
    type: Optional[str] = None
    amount: Decimal
    amount_paid: Optional[Decimal] = Decimal('0.00')
    is_paid: Optional[bool] = False

class InvoiceOut(BaseModel):
    id: int
    lease_id: int
    billing_period: date
    type: Optional[str] = None
    amount: Decimal
    amount_paid: Optional[Decimal] = Decimal('0.00')
    is_paid: bool
    # Joined data
    tenant_name: Optional[str] = None
    unit_number: Optional[str] = None
    property_name: Optional[str] = None

    class Config:
        from_attributes = True

# --- Bill Types ---
class BillTypeCreate(BaseModel):
    name: str = Field(..., max_length=100)

class BillTypeOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True

# --- Payments ---
class PaymentCreate(BaseModel):
    lease_id: int
    invoice_id: Optional[int] = None
    amount: Decimal
    payment_method: str = Field(..., max_length=50)
    reference_number: Optional[str] = Field(None, max_length=100)

class PaymentOut(BaseModel):
    id: int
    lease_id: int
    invoice_id: Optional[int] = None
    amount: Decimal
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    payment_date: datetime
    
    # Joined data
    tenant_name: Optional[str] = None
    unit_number: Optional[str] = None
    property_name: Optional[str] = None

    class Config:
        from_attributes = True

# --- Expenditures ---
class ExpenditureCreate(BaseModel):
    property_id: int
    notes: Optional[str] = None
    category: str = Field(..., max_length=100)
    amount: Decimal
    date: Optional[date] = None

class ExpenditureOut(BaseModel):
    id: int
    property_id: int
    notes: Optional[str] = None
    category: str
    amount: Decimal
    date: date
    # Joined data
    property_name: Optional[str] = None

    class Config:
        from_attributes = True

# --- Auth ---
class Token(BaseModel):
    access_token: str
    token_type: str

class GoogleLogin(BaseModel):
    token: str
    role: Optional[str] = "tenant"

# --- Meter Readings ---
class MeterReadingCreate(BaseModel):
    unit_id: int
    previous_reading: Decimal
    current_reading: Decimal
    consumption: Decimal
    rate: Decimal
    total_charge: Decimal
    reading_date: date

class MeterReadingOut(BaseModel):
    id: int
    unit_id: int
    previous_reading: Decimal
    current_reading: Decimal
    consumption: Decimal
    rate: Decimal
    total_charge: Decimal
    reading_date: date
    # Joined data
    unit_number: Optional[str] = None
    property_name: Optional[str] = None
    tenant_name: Optional[str] = None

    class Config:
        from_attributes = True
